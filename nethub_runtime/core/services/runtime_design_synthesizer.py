from __future__ import annotations

import asyncio
import json
import threading
from typing import Any


class RuntimeDesignSynthesizer:
    """Synthesizes runtime blueprint and agent design metadata from task/workflow state."""

    def __init__(self, model_router: Any | None = None) -> None:
        self.model_router = model_router

    def synthesize_blueprint(self, *, task: dict[str, Any], workflow: dict[str, Any]) -> dict[str, Any]:
        synthesized = self._invoke_json(
            task_type="task_planning",
            system_prompt=(
                "You are the NestHub runtime blueprint synthesizer. "
                "Return JSON only with concise blueprint reasoning."
            ),
            prompt=(
                "Synthesize blueprint metadata for the current runtime request.\n"
                f"task={json.dumps(task, ensure_ascii=False)}\n"
                f"workflow={json.dumps(workflow, ensure_ascii=False)}\n"
                "Return JSON with keys: purpose_summary, reasoning, io_summary, execution_profile, recommended_models, recommended_tools."
            ),
        )
        if synthesized:
            return synthesized

        step_names = [str(step.get("name") or "") for step in workflow.get("steps", []) if isinstance(step, dict)]
        outputs = [str(item) for item in task.get("output_requirements", [])]
        domain = str(task.get("domain") or "general")
        intent = str(task.get("intent") or "general_task")
        return {
            "purpose_summary": f"Runtime blueprint for {domain}:{intent}.",
            "reasoning": f"Synthesized from {len(step_names)} workflow steps and {len(outputs)} output requirements.",
            "io_summary": {"inputs": ["input_text", "context"], "outputs": outputs},
            "execution_profile": {"step_count": len(step_names), "step_names": step_names, "mode": "runtime_generated"},
            "recommended_models": [self._guess_model_family(intent, step_names)],
            "recommended_tools": self._guess_tools(step_names),
        }

    def synthesize_agent_spec(self, *, task: dict[str, Any], workflow: dict[str, Any] | None) -> dict[str, Any]:
        synthesized = self._invoke_json(
            task_type="agent_reasoning",
            system_prompt="You are the NestHub runtime agent designer. Return JSON only.",
            prompt=(
                "Design a runtime agent specification.\n"
                f"task={json.dumps(task, ensure_ascii=False)}\n"
                f"workflow={json.dumps(workflow or {}, ensure_ascii=False)}\n"
                "Return JSON with keys: name, role, description, goals, model_policy, tool_policy, memory_type, memory_capacity, max_iterations, timeout_sec, retry_policy, reasoning_summary."
            ),
        )
        if synthesized:
            return synthesized

        intent = str(task.get("intent") or "general_task")
        input_text = str(task.get("input_text") or "")
        return {
            "name": f"Runtime Agent {intent}",
            "role": intent,
            "description": f"Runtime synthesized agent for: {input_text[:80]}",
            "goals": [f"Fulfill {intent}", "Return a user-visible result"],
            "model_policy": {"default": self._guess_model_family(intent, [])},
            "tool_policy": [],
            "memory_type": "short_term",
            "memory_capacity": 100,
            "max_iterations": 5,
            "timeout_sec": 300,
            "retry_policy": "exponential_backoff",
            "reasoning_summary": "Derived from runtime task intent and available workflow context.",
        }

    def _invoke_json(self, *, task_type: str, system_prompt: str, prompt: str) -> dict[str, Any] | None:
        if self.model_router is None:
            return None

        holder: dict[str, Any] = {}

        def _runner() -> None:
            try:
                holder["response"] = asyncio.run(
                    self.model_router.invoke(
                        task_type=task_type,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=0.2,
                    )
                )
            except Exception as exc:
                holder["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=20)
        raw = holder.get("response")
        if not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        if cleaned.startswith("Model response (mock):"):
            return None
        try:
            payload = json.loads(cleaned)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _guess_model_family(self, intent: str, step_names: list[str]) -> str:
        lowered = intent.lower()
        if "file" in lowered or any("generate" in step for step in step_names):
            return "code_generation"
        if "agent" in lowered:
            return "agent_reasoning"
        return "task_planning"

    def _guess_tools(self, step_names: list[str]) -> list[str]:
        tools: list[str] = []
        for step_name in step_names:
            if step_name.startswith("file_"):
                tools.append("file_builder")
            elif step_name.startswith("web_"):
                tools.append("web_automation")
            elif step_name.startswith("manage_"):
                tools.append("session_store")
        return list(dict.fromkeys(tools))