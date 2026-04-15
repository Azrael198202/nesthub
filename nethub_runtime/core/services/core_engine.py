from __future__ import annotations

from typing import Any

from nethub_runtime.core.config.settings import AGENT_REGISTRY_PATH, BLUEPRINT_REGISTRY_PATH, MODEL_REGISTRY_PATH
from nethub_runtime.core.memory.vector_store import VectorStore
from nethub_runtime.core.services.agent_designer import AgentDesigner
from nethub_runtime.core.services.blueprint_generator import BlueprintGenerator
from nethub_runtime.core.services.blueprint_resolver import BlueprintResolver
from nethub_runtime.core.services.capability_router import CapabilityRouter
from nethub_runtime.core.services.context_manager import ContextManager
from nethub_runtime.core.services.dependency_manager import DependencyManager
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator
from nethub_runtime.core.services.intent_analyzer import IntentAnalyzer
from nethub_runtime.core.services.registry import JsonRegistry
from nethub_runtime.core.services.result_integrator import ResultIntegrator
from nethub_runtime.core.services.security_guard import SecurityGuard
from nethub_runtime.core.services.task_decomposer import TaskDecomposer
from nethub_runtime.core.services.workflow_planner import WorkflowPlanner
from nethub_runtime.core.utils.logger import get_logger


class AICore:
    def __init__(self) -> None:
        self.logger = get_logger("nethub_runtime.core.engine")
        self.context_manager = ContextManager()
        self.intent_analyzer = IntentAnalyzer()
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.model_registry = JsonRegistry(MODEL_REGISTRY_PATH)
        self.blueprint_registry = JsonRegistry(BLUEPRINT_REGISTRY_PATH)
        self.agent_registry = JsonRegistry(AGENT_REGISTRY_PATH)
        self.blueprint_resolver = BlueprintResolver(registry=self.blueprint_registry)
        self.blueprint_generator = BlueprintGenerator(registry=self.blueprint_registry)
        self.agent_designer = AgentDesigner()
        self.capability_router = CapabilityRouter()
        self.execution_coordinator = ExecutionCoordinator(session_store=self.context_manager.session_store)
        self.result_integrator = ResultIntegrator()
        self.vector_store = VectorStore()
        self.dependency_manager = DependencyManager()
        self.security_guard = SecurityGuard()

    def reload_plugins(self) -> dict[str, Any]:
        """Reload plugin-enabled services from config without restarting process."""
        self.intent_analyzer = IntentAnalyzer()
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.capability_router = CapabilityRouter()
        return {
            "status": "reloaded",
            "intent_analyzer_plugins": len(self.intent_analyzer.plugins),
            "task_decomposer_plugins": len(self.task_decomposer.plugins),
            "workflow_planner_plugins": len(self.workflow_planner.plugins),
        }

    async def handle(self, input_text: str, context: dict[str, Any] | None = None, fmt: str = "dict") -> dict[str, Any] | str:
        self.security_guard.validate_output_format(fmt)
        self.model_registry.hot_reload()
        self.blueprint_registry.hot_reload()
        self.agent_registry.hot_reload()
        dependency_status = self.dependency_manager.check()

        ctx = self.context_manager.load(context)
        ctx = self.context_manager.enrich(ctx)
        self.logger.info("Handling request trace=%s session=%s", ctx.trace_id, ctx.session_id)
        try:
            task = await self.intent_analyzer.analyze(input_text, ctx)
            subtasks = await self.task_decomposer.decompose(task)
            workflow = await self.workflow_planner.plan(task, subtasks)
            blueprints = self.blueprint_resolver.resolve(task, workflow)
            if not blueprints:
                blueprints = [self.blueprint_generator.generate(task, workflow)]
            for blueprint in blueprints:
                self.blueprint_registry.register(blueprint.name, blueprint)

            agent = None
            if self.agent_designer.should_generate(task):
                agent = self.agent_designer.generate(task, workflow)
                self.agent_registry.register(agent.name, agent)

            plan = self.capability_router.route_workflow(task, workflow)
            self.security_guard.validate_plan(plan)
            for step in plan:
                model_choice = (step.get("capability") or {}).get("model_choice", {})
                provider = model_choice.get("provider", "unknown")
                model = model_choice.get("model", "unknown")
                self.model_registry.register(f"{provider}:{model}", model_choice)

            execution_result = self.execution_coordinator.execute(plan, task, ctx)
            vector_backend = self.vector_store.active_store()
            return self.result_integrator.build_response(
                task=task,
                workflow=workflow,
                blueprints=[item.model_dump() for item in blueprints],
                agent=agent.model_dump() if agent else None,
                execution_result={**execution_result, "vector_store": vector_backend, "dependency_status": dependency_status},
                context=ctx,
                fmt=fmt,
            )
        except Exception as exc:
            self.logger.error("Core handle failed trace=%s error=%s", ctx.trace_id, exc)
            raise
