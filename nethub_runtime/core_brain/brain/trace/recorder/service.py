from __future__ import annotations

from typing import Any
from uuid import uuid4

from nethub_runtime.core_brain.brain.trace.store.repository import TraceRepository
from nethub_runtime.core_brain.contracts.validator import ContractValidator


class TraceRecorderService:
    def __init__(self, *, repository: TraceRepository, validator: ContractValidator) -> None:
        self.repository = repository
        self.validator = validator

    def record(
        self,
        *,
        workflow_id: str,
        intent_id: str,
        step_execution: dict[str, Any],
        intent_alignment: bool | None,
    ) -> dict[str, Any]:
        trace_payload = {
            "trace_id": f"trace_{uuid4().hex[:12]}",
            "workflow_id": workflow_id,
            "task_id": step_execution.get("task_id"),
            "step_index": step_execution.get("step_index"),
            "intent_id": intent_id,
            "agent_id": ((step_execution.get("agent") or {}).get("agent_id") or "agent_runtime"),
            "agent_type": ((step_execution.get("agent") or {}).get("agent_type") or "runtime_agent"),
            "blueprint_id": ((step_execution.get("agent") or {}).get("blueprint_id")),
            "tool_calls": list(step_execution.get("tool_calls") or []),
            "task_input": dict(step_execution.get("task_input") or {}),
            "task_output": dict(step_execution.get("task_output") or {}),
            "validation_result": {
                "step_goal_met": step_execution.get("status") == "success",
                "schema_valid": True,
                "intent_alignment": intent_alignment,
                "messages": ["trace recorded"],
            },
            "retry_count": 0,
            "fallback_used": False,
            "status": step_execution.get("status") or "success",
            "error_reason": step_execution.get("error_reason"),
            "started_at": step_execution.get("started_at"),
            "finished_at": step_execution.get("finished_at"),
        }
        trace = self.validator.validate_trace(trace_payload).model_dump(mode="python")
        self.repository.append(trace)
        return trace
