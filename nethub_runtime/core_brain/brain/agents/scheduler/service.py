from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.agents.manager.service import AgentManagerService


class AgentSchedulerService:
    def __init__(self, manager: AgentManagerService) -> None:
        self.manager = manager

    def assign(self, *, step: dict[str, Any], workflow_id: str | None = None) -> dict[str, Any]:
        agent_type = str(step.get("assigned_agent_type") or "runtime_agent")
        workflow_ref = str(workflow_id or step.get("workflow_id") or "wf_runtime")
        return self.manager.ensure_agent(agent_type=agent_type, workflow_id=workflow_ref)
