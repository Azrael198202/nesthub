from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.workflows.planner.service import WorkflowPlannerService


class WorkflowPlanningService:
    def __init__(self, planner: WorkflowPlannerService) -> None:
        self.planner = planner

    def plan(
        self,
        *,
        req: ChatRequest,
        task_id: str,
        intent: dict[str, Any],
        route: dict[str, Any],
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        return self.planner.plan(req=req, task_id=task_id, intent=intent, route=route, context_bundle=context_bundle)
