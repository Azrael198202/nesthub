from __future__ import annotations

from typing import Any

from nethub_runtime.core.services.agent_designer import AgentDesigner
from nethub_runtime.core.services.blueprint_generator import BlueprintGenerator
from nethub_runtime.core.services.blueprint_resolver import BlueprintResolver
from nethub_runtime.core.services.capability_router import CapabilityRouter
from nethub_runtime.core.services.context_manager import ContextManager
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator
from nethub_runtime.core.services.intent_analyzer import IntentAnalyzer
from nethub_runtime.core.services.registry import Registry
from nethub_runtime.core.services.result_integrator import ResultIntegrator
from nethub_runtime.core.services.task_decomposer import TaskDecomposer
from nethub_runtime.core.services.workflow_planner import WorkflowPlanner
from nethub_runtime.core.memory.vector_store import VectorStore


class AICore:
    def __init__(self) -> None:
        self.context_manager = ContextManager()
        self.intent_analyzer = IntentAnalyzer()
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.blueprint_registry = Registry()
        self.blueprint_resolver = BlueprintResolver(registry=self.blueprint_registry)
        self.blueprint_generator = BlueprintGenerator(registry=self.blueprint_registry)
        self.agent_designer = AgentDesigner()
        self.capability_router = CapabilityRouter()
        self.execution_coordinator = ExecutionCoordinator(session_store=self.context_manager.session_store)
        self.result_integrator = ResultIntegrator()
        self.vector_store = VectorStore()

    async def handle(self, input_text: str, context: dict[str, Any] | None = None, fmt: str = "dict") -> dict[str, Any] | str:
        ctx = self.context_manager.load(context)
        ctx = self.context_manager.enrich(ctx)
        task = await self.intent_analyzer.analyze(input_text, ctx)
        subtasks = await self.task_decomposer.decompose(task)
        workflow = await self.workflow_planner.plan(task, subtasks)
        blueprints = self.blueprint_resolver.resolve(task, workflow)
        if not blueprints:
            blueprints = [self.blueprint_generator.generate(task, workflow)]
        agent = None
        if self.agent_designer.should_generate(task):
            agent = self.agent_designer.generate(task, workflow)
        plan = self.capability_router.route_workflow(task, workflow)
        execution_result = self.execution_coordinator.execute(plan, task, ctx)
        vector_backend = self.vector_store.active_store()
        return self.result_integrator.build_response(
            task=task,
            workflow=workflow,
            blueprints=[item.model_dump() for item in blueprints],
            agent=agent.model_dump() if agent else None,
            execution_result={**execution_result, "vector_store": vector_backend},
            context=ctx,
            fmt=fmt,
        )
