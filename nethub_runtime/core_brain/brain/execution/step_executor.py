from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nethub_runtime.core_brain.brain.execution.agent_executor import AgentExecutor
from nethub_runtime.core_brain.brain.execution.tool_executor import ToolExecutor


class StepExecutor:
    def __init__(self, *, tool_executor: ToolExecutor, agent_executor: AgentExecutor) -> None:
        self.tool_executor = tool_executor
        self.agent_executor = agent_executor

    def run_step(
        self,
        *,
        step: dict[str, Any],
        req: dict[str, Any],
        workflow_id: str,
        route: dict[str, Any],
        answer_text: str,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC).isoformat()
        agent = self.agent_executor.bind({**step, "workflow_id": workflow_id})
        tool_calls = self.tool_executor.run_tools(list(step.get("required_tools") or []), req)

        output: dict[str, Any] = {"status": "completed"}
        if step.get("name") == "execute_response":
            output = {"answer_text": answer_text, "selected_model": route.get("model")}
        elif step.get("name") == "analyze_intent":
            output = {"intent_name": intent.get("name"), "intent_id": intent.get("intent_id")}

        return {
            "task_id": step.get("task_id"),
            "step_index": step.get("step_index"),
            "name": step.get("name"),
            "agent": agent,
            "tool_calls": tool_calls,
            "task_input": {
                "session_id": req.get("session_id"),
                "message": req.get("message"),
                "input_schema": step.get("input_schema"),
            },
            "task_output": output,
            "status": "success",
            "error_reason": None,
            "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(),
        }
