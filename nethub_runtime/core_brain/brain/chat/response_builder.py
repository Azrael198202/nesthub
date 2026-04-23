from __future__ import annotations

from typing import Any


def build_runtime_result(
    *,
    request_id: str,
    session_id: str,
    task_id: str,
    intent: dict[str, Any],
    route: dict[str, Any],
    answer_text: str,
) -> dict[str, Any]:
    steps = [
        {"name": "preprocess", "status": "completed", "output": {"message": "input normalized"}},
        {"name": "load_context", "status": "completed", "output": {"message": "context assembled"}},
        {"name": "intent_analysis", "status": "completed", "output": intent},
        {"name": "decide_route", "status": "completed", "output": route},
        {"name": "generate_result", "status": "completed", "output": {"message": answer_text}},
        {"name": "writeback_state", "status": "completed", "output": {"message": "memory updated"}},
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
            "long_term_memory_written": False,
        },
        # Compatibility fields used by TVBox runtime parser.
        "task": {"task_id": task_id, "intent": intent.get("intent_name", "general_chat"), "domain": "general"},
        "workflow_plan": {"steps": [item["name"] for item in steps]},
        "execution_result": {
            "execution_type": "chat",
            "steps": steps,
            "final_output": {"answer": {"content": answer_text, "message": answer_text}},
            "execution_plan": [
                {"name": "generate_result", "capability": {"model_choice": route}},
            ],
            "core_brain": {"version": "phase0"},
        },
        "artifacts": [],
        "agent": None,
        "blueprints": [],
    }
