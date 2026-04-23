from __future__ import annotations

from typing import Any


def build_runtime_result(
    *,
    request_id: str,
    session_id: str,
    task_id: str,
    intent: dict[str, Any],
    route: dict[str, Any],
    workflow_plan: dict[str, Any],
    answer_text: str,
    long_term_memory_written: bool,
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    plan_steps = list(workflow_plan.get("steps") or [])
    steps = [
        {
            "id": step.get("task_id"),
            "step_index": step.get("step_index"),
            "name": step.get("name"),
            "status": "completed",
            "objective": step.get("objective"),
            "inputs": step.get("input_schema"),
            "outputs": step.get("output_schema"),
            "validation": step.get("validation_rule"),
        }
        for step in plan_steps
    ]

    return {
        "request_id": request_id,
        "session_id": session_id,
        "task_id": task_id,
        "intent": intent,
        "route": route,
        "result": {"type": "answer", "content": answer_text},
        "state_updates": {
            "main_session_updated": True,
            "task_session_updated": True,
            "long_term_memory_written": long_term_memory_written,
        },
        # Compatibility fields used by TVBox runtime parser.
        "task": {"task_id": task_id, "intent": intent.get("name", "general_chat"), "domain": "general"},
        "workflow_plan": workflow_plan,
        "execution_result": {
            "execution_type": "chat",
            "steps": steps,
            "structured_trace": traces,
            "final_output": {"answer": {"content": answer_text, "message": answer_text}},
            "execution_plan": [
                {
                    "name": "execute_response",
                    "executor_type": "model_route",
                    "capability": {"model_choice": route},
                    "selector": {
                        "reason": "local_first_with_fallback",
                        "intent_confidence": float(intent.get("confidence") or 0.0),
                    },
                    "inputs": ["message", "context_bundle", "intent"],
                    "outputs": ["answer"],
                },
            ],
            "core_brain": {"version": "phase0"},
        },
        "artifacts": [],
        "agent": None,
        "blueprints": [],
    }
