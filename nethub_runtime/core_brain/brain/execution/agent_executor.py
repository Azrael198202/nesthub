from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.agents.scheduler.service import AgentSchedulerService


class AgentExecutor:
    def __init__(self, scheduler: AgentSchedulerService) -> None:
        self.scheduler = scheduler

    def bind(self, workflow_step: dict[str, Any]) -> dict[str, Any]:
        return self.scheduler.assign(step=workflow_step)
