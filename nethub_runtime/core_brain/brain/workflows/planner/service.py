from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.workflows.builder.service import WorkflowBuilderService
from nethub_runtime.core_brain.brain.workflows.registry.service import WorkflowRegistryService
from nethub_runtime.core_brain.brain.workflows.state.store import WorkflowStateStore


class WorkflowPlannerService:
    def __init__(
        self,
        *,
        builder: WorkflowBuilderService,
        registry: WorkflowRegistryService,
        state_store: WorkflowStateStore,
    ) -> None:
        self.builder = builder
        self.registry = registry
        self.state_store = state_store

    def plan(
        self,
        *,
        req: ChatRequest,
        task_id: str,
        intent: dict[str, Any],
        route: dict[str, Any],
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        workflow = self.builder.build(req=req, task_id=task_id, intent=intent, route=route, context_bundle=context_bundle)
        self.registry.register(workflow)
        self.state_store.put(str(workflow.get("workflow_id") or ""), {"status": "draft", "steps": {}})
        return workflow
