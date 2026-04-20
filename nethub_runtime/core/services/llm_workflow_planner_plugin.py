"""LLM-driven workflow planner plugin.

When NestHub receives a request that no domain-specific plugin handles
(e.g. "总结文档 → 翻译 → 整理成 txt 发给我", or a completely novel compound
task), this plugin asks the LLM to decompose the request into an ordered
list of named steps, then builds a real ``WorkflowSchema`` from that plan.

Design principles
-----------------
- **No business keywords in code** — the LLM interprets the request; the
  plugin only enforces structure.
- **Graceful fallback** — if the LLM call fails or returns un-parseable
  JSON, the plugin yields a single ``single_step`` step so execution
  always continues.
- **Registered handlers win** — steps whose names match a registered
  execution-handler are dispatched to that handler; everything else is
  dispatched to ``_run_llm_step`` (the generic LLM executor).
- **Context passed to each step** — each step receives the prior step
  outputs via ``step_outputs``, so steps can chain naturally.
- **Writes to knowledge base** — a successful plan is recorded to the
  RuntimeLearningStore so future identical intents reuse it without LLM
  overhead.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema
from nethub_runtime.core.utils.id_generator import generate_id

LOGGER = logging.getLogger(__name__)

# Tasks that are already handled by higher-priority domain plugins — this
# plugin only activates for intents that fall through to it.
_HANDLED_INTENTS = frozenset({
    "data_record", "data_query",
    "create_information_agent", "refine_information_agent",
    "finalize_information_agent", "capture_agent_knowledge", "query_agent_knowledge",
    "ocr_task", "stt_task", "tts_task", "image_generation_task", "video_generation_task",
    "file_generation_task", "file_delivery_task", "file_upload_task", "web_research_task",
})

# Minimum request complexity (word count) for LLM planning to be triggered.
# Short, simple requests are better served by the default single_step handler.
_MIN_WORD_COUNT = 6


def _llm_plan_workflow(input_text: str) -> list[dict[str, Any]] | None:
    """Ask the LLM to decompose *input_text* into a workflow step list.

    Returns a list of ``{"name": str, "goal": str, "label": str}`` dicts,
    or *None* if the call fails.
    """
    # Build a lean candidate list from available cloud APIs.
    candidates: list[tuple[str, str | None]] = []
    if os.getenv("GROQ_API_KEY"):
        candidates.append(("groq/llama-3.3-70b-versatile", os.getenv("GROQ_API_KEY")))
    if os.getenv("GEMINI_API_KEY"):
        candidates.append(("gemini/gemini-2.0-flash", os.getenv("GEMINI_API_KEY")))
    if os.getenv("OPENAI_API_KEY"):
        candidates.append(("openai/gpt-4o-mini", os.getenv("OPENAI_API_KEY")))

    if not candidates:
        return None

    system_prompt = (
        "You are a workflow planning assistant. "
        "Given a user request, decompose it into an ordered list of atomic steps that can be "
        "executed sequentially. Each step must have:\n"
        "  - name: a short snake_case identifier (e.g. summarize_document, translate_text, save_file)\n"
        "  - goal: one sentence describing what the step does\n"
        "  - label: a short human-readable emoji label (e.g. '📄 文档总结')\n\n"
        "Return ONLY a valid JSON array. No prose, no markdown fences. Example:\n"
        '[{"name":"summarize_document","goal":"Summarize the uploaded document.","label":"📄 Summary"}]'
    )
    user_prompt = (
        f"Decompose this request into workflow steps:\n\n{input_text}\n\n"
        "Return ONLY a JSON array of step objects."
    )

    for model, api_key in candidates:
        try:
            from litellm import completion  # type: ignore

            resp = completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                api_key=api_key,
                timeout=20,
                max_tokens=512,
            )
            raw = (resp.choices[0].message.content or "").strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            steps = json.loads(raw)
            if isinstance(steps, list) and steps:
                LOGGER.info("LLM (%s) planned %d steps for request", model, len(steps))
                return steps
        except Exception as exc:
            LOGGER.debug("LLM workflow planning failed with %s: %s", model, exc)
            continue

    return None


def _record_plan(input_text: str, steps: list[dict[str, Any]]) -> None:
    """Write the resolved plan to the RuntimeLearningStore as a reuse hint."""
    try:
        from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
        from nethub_runtime.core.memory.runtime_learning_store import RuntimeLearningStore

        store = RuntimeLearningStore(SEMANTIC_POLICY_PATH)
        store.record_attempt(
            task_type="general_task",
            gap="workflow_planning",
            strategy="llm_decomposition",
            outcome="success",
            detail=f"steps={[s['name'] for s in steps]} input={input_text[:80]}",
            model_id="llm_workflow_planner",
        )
    except Exception as exc:
        LOGGER.debug("Could not record plan to learning store: %s", exc)


def _infer_executor_type(step_name: str) -> str:
    """Return the executor type for *step_name*.

    Named steps that have dedicated handlers run as ``tool``; everything
    else falls through to the generic LLM executor.
    """
    known_tool_steps = {
        # document plugin
        "analyze_document", "summarize_document", "translate_summary", "save_document_file",
        # multimodal
        "ocr_extract", "stt_transcribe", "tts_synthesize", "image_generate",
        "video_generate", "file_generate", "file_read",
        # artifact
        "generate_workflow_artifact", "generate_runtime_patch",
        "persist_workflow_output", "validate_runtime_patch", "verify_runtime_patch",
    }
    if step_name in known_tool_steps:
        return "tool"
    return "llm"


class LLMWorkflowPlannerPlugin:
    """High-priority workflow planner that uses the LLM for open-ended tasks.

    Triggers on ``general_task`` (and any unrecognised intent) when the
    request is complex enough (>= ``_MIN_WORD_COUNT`` words).  Domain
    plugins that fire first (higher ``priority``) are unaffected.
    """

    priority = 50  # between DefaultWorkflowPlannerPlugin(10) and domain plugins(110)

    def match(self, task: TaskSchema, _subtasks: list[SubTask]) -> bool:
        if task.intent in _HANDLED_INTENTS:
            return False
        word_count = len(task.input_text.split())
        return word_count >= _MIN_WORD_COUNT

    def run(self, task: TaskSchema, subtasks: list[SubTask]) -> WorkflowSchema:
        steps_raw = _llm_plan_workflow(task.input_text)

        if not steps_raw:
            LOGGER.warning("LLM workflow planner got no plan, falling back to single_step")
            steps_raw = [{"name": "single_step", "goal": "Handle the user request.", "label": "⚙️ Execute"}]

        steps: list[WorkflowStepSchema] = []
        prev_step_id: str | None = None
        for raw in steps_raw:
            name = str(raw.get("name") or "single_step").strip()
            goal = str(raw.get("goal") or "").strip()
            label = str(raw.get("label") or name).strip()
            executor = _infer_executor_type(name)
            step_id = generate_id("step")
            steps.append(
                WorkflowStepSchema(
                    step_id=step_id,
                    name=name,
                    task_type=task.intent,
                    executor_type=executor,
                    inputs=["input_text", "session_state", "step_outputs"],
                    outputs=["message", "content"],
                    depends_on=[prev_step_id] if prev_step_id else [],
                    retry=1,
                    metadata={
                        "goal": goal,
                        "display_label": label,
                        "selection_basis": "llm_workflow_planner",
                    },
                )
            )
            prev_step_id = step_id

        if steps_raw and steps_raw[0].get("name") != "single_step":
            _record_plan(task.input_text, steps_raw)

        return WorkflowSchema(
            workflow_id=generate_id("workflow"),
            task_id=task.task_id,
            mode="normal",
            steps=steps,
            composition={
                "plugin": "llm_workflow_planner",
                "intent": task.intent,
                "step_count": len(steps),
            },
        )


def llm_workflow_planner_plugin() -> LLMWorkflowPlannerPlugin:
    return LLMWorkflowPlannerPlugin()
