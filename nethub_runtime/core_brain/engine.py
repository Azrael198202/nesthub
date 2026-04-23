from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from nethub_runtime.core_brain.brain.agents.manager.service import AgentManagerService
from nethub_runtime.core_brain.brain.agents.registry.service import AgentRegistryService
from nethub_runtime.core_brain.brain.agents.scheduler.service import AgentSchedulerService
from nethub_runtime.core_brain.brain.agents.state.store import AgentStateStore
from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.artifacts.codegen_engine import CodeGenEngine
from nethub_runtime.core_brain.brain.artifacts.lifecycle_service import ArtifactLifecycleService
from nethub_runtime.core_brain.brain.chat.chat_service import ChatService
from nethub_runtime.core_brain.brain.context.context_builder import ContextBuilder
from nethub_runtime.core_brain.brain.execution.agent_executor import AgentExecutor
from nethub_runtime.core_brain.brain.execution.step_executor import StepExecutor
from nethub_runtime.core_brain.brain.execution.tool_executor import ToolExecutor
from nethub_runtime.core_brain.brain.kb.blueprint_kb.service import BlueprintKBService
from nethub_runtime.core_brain.brain.kb.intent_kb.service import IntentKBService
from nethub_runtime.core_brain.brain.kb.retrieval.service import RetrievalService
from nethub_runtime.core_brain.brain.kb.workflow_kb.service import WorkflowKBService
from nethub_runtime.core_brain.brain.llm.litellm_client import LiteLLMClient
from nethub_runtime.core_brain.brain.llm.model_registry import ModelRegistry
from nethub_runtime.core_brain.brain.llm.prompt_registry import PromptRegistry
from nethub_runtime.core_brain.brain.memory.repositories.execution_repo import ExecutionRepo
from nethub_runtime.core_brain.brain.memory.repositories.long_term_repo import LongTermRepo
from nethub_runtime.core_brain.brain.memory.repositories.session_repo import SessionRepo
from nethub_runtime.core_brain.brain.memory.repositories.task_repo import TaskRepo
from nethub_runtime.core_brain.brain.memory.services.long_term_memory_service import LongTermMemoryService
from nethub_runtime.core_brain.brain.memory.services.session_memory_service import SessionMemoryService
from nethub_runtime.core_brain.brain.memory.services.task_memory_service import TaskMemoryService
from nethub_runtime.core_brain.brain.orchestration.service import OrchestrationService
from nethub_runtime.core_brain.brain.planning.intent_service import IntentPlanningService
from nethub_runtime.core_brain.brain.planning.route_service import RoutePlanningService
from nethub_runtime.core_brain.brain.planning.workflow_service import WorkflowPlanningService
from nethub_runtime.core_brain.brain.routing.policy_loader import PolicyLoader
from nethub_runtime.core_brain.brain.routing.route_selector import RouteSelector
from nethub_runtime.core_brain.brain.routing.router_service import RouterService
from nethub_runtime.core_brain.brain.trace.evaluator.service import TraceEvaluatorService
from nethub_runtime.core_brain.brain.trace.recorder.service import TraceRecorderService
from nethub_runtime.core_brain.brain.trace.store.repository import TraceRepository
from nethub_runtime.core_brain.brain.validation.intent.service import IntentValidationService
from nethub_runtime.core_brain.brain.validation.result.service import ResultValidationService
from nethub_runtime.core_brain.brain.validation.schemas.service import SchemaValidationService
from nethub_runtime.core_brain.brain.validation.step.service import StepValidationService
from nethub_runtime.core_brain.brain.workflows.builder.service import WorkflowBuilderService
from nethub_runtime.core_brain.brain.workflows.executor.service import WorkflowExecutorService
from nethub_runtime.core_brain.brain.workflows.planner.service import WorkflowPlannerService
from nethub_runtime.core_brain.brain.workflows.registry.service import WorkflowRegistryService
from nethub_runtime.core_brain.brain.workflows.state.store import WorkflowStateStore
from nethub_runtime.core_brain.config import ConfigLoader
from nethub_runtime.core_brain.contracts.validator import ContractValidator


@dataclass(slots=True)
class _CoreBrainStores:
    session_repo: SessionRepo
    task_repo: TaskRepo
    long_term_repo: LongTermRepo
    execution_repo: ExecutionRepo
    trace_repo: TraceRepository


class CoreBrainEngine:
    def __init__(self) -> None:
        cfg = ConfigLoader().load()
        stores = _CoreBrainStores(
            session_repo=SessionRepo(),
            task_repo=TaskRepo(),
            long_term_repo=LongTermRepo(),
            execution_repo=ExecutionRepo(),
            trace_repo=TraceRepository(),
        )

        session_memory = SessionMemoryService(stores.session_repo)
        task_memory = TaskMemoryService(stores.task_repo)
        long_term_memory = LongTermMemoryService(stores.long_term_repo)

        model_registry = ModelRegistry(cfg.model_registry)
        prompt_registry = PromptRegistry(cfg.prompt_registry)
        llm_client = LiteLLMClient()
        policy_loader = PolicyLoader(cfg.routing_policy)
        route_selector = RouteSelector(model_registry=model_registry, policy_loader=policy_loader)
        router_service = RouterService(route_selector=route_selector)
        context_builder = ContextBuilder(
            system_context=cfg.app.get("system_context", {}),
            session_memory=session_memory,
            task_memory=task_memory,
            long_term_memory=long_term_memory,
        )
        chat_service = ChatService(llm_client=llm_client, model_registry=model_registry, prompt_registry=prompt_registry)

        contract_validator = ContractValidator()
        schema_validation = SchemaValidationService(contract_validator)
        intent_planning = IntentPlanningService(chat_service)
        route_planning = RoutePlanningService(router_service)

        workflow_state = WorkflowStateStore()
        workflow_registry = WorkflowRegistryService()
        workflow_builder = WorkflowBuilderService()
        workflow_planner = WorkflowPlannerService(
            builder=workflow_builder,
            registry=workflow_registry,
            state_store=workflow_state,
        )
        workflow_planning = WorkflowPlanningService(workflow_planner)

        agent_registry = AgentRegistryService()
        agent_state = AgentStateStore()
        agent_manager = AgentManagerService(agent_registry, agent_state)
        agent_scheduler = AgentSchedulerService(agent_manager)
        tool_executor = ToolExecutor()
        agent_executor = AgentExecutor(agent_scheduler)
        step_executor = StepExecutor(tool_executor=tool_executor, agent_executor=agent_executor)
        trace_recorder = TraceRecorderService(repository=stores.trace_repo, validator=contract_validator)
        trace_evaluator = TraceEvaluatorService()
        step_validator = StepValidationService()
        workflow_executor = WorkflowExecutorService(
            step_executor=step_executor,
            trace_recorder=trace_recorder,
            trace_evaluator=trace_evaluator,
            step_validator=step_validator,
        )

        retrieval_service = RetrievalService(
            intent_kb=IntentKBService(),
            workflow_kb=WorkflowKBService(),
            blueprint_kb=BlueprintKBService(),
        )
        artifact_lifecycle = ArtifactLifecycleService()
        intent_validation = IntentValidationService()
        result_validation = ResultValidationService()

        self._stores = stores
        self.orchestrator = OrchestrationService(
            context_builder=context_builder,
            chat_service=chat_service,
            intent_planning=intent_planning,
            route_planning=route_planning,
            workflow_planning=workflow_planning,
            workflow_executor=workflow_executor,
            schema_validation=schema_validation,
            intent_validation=intent_validation,
            result_validation=result_validation,
            retrieval_service=retrieval_service,
            artifact_lifecycle=artifact_lifecycle,
            session_memory=session_memory,
            task_memory=task_memory,
            long_term_memory=long_term_memory,
            execution_repo=stores.execution_repo,
        )

        # Compatibility attributes expected by bootstrap callers.
        self.model_router = None
        self.workflow_executor = workflow_executor
        self.agent_builder = CodeGenEngine()
        self.tool_registry = None
        self.facade = self

    async def handle(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
        fmt: str = "dict",
        use_langraph: bool = True,
    ) -> dict[str, Any] | str:
        _ = use_langraph
        payload = dict(context or {})
        req = ChatRequest(
            session_id=str(payload.get("session_id") or "default"),
            task_id=str(payload.get("task_id") or "") or None,
            user_id=str((payload.get("metadata") or {}).get("user_id") or "tvbox"),
            message=input_text,
            allow_external=bool((payload.get("metadata") or {}).get("allow_external", True)),
            mode="chat",
        )
        result = await self.handle_request(req)
        if fmt == "text":
            return str((result.get("result") or {}).get("content") or "")
        return result

    async def handle_chat(self, req: ChatRequest) -> dict[str, Any]:
        return await self.handle_request(req)

    async def handle_request(self, req: ChatRequest) -> dict[str, Any]:
        return await self.orchestrator.handle(req)

    async def handle_stream(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
        fmt: str = "dict",
    ) -> AsyncGenerator[dict[str, Any], None]:
        result = await self.handle(input_text, context=context, fmt="dict", use_langraph=True)
        yield {"event": "intent_analyzed", "intent": result.get("intent")}
        yield {"event": "workflow_planned", "workflow": result.get("workflow_plan")}
        for step in ((result.get("execution_result") or {}).get("steps") or []):
            yield {"event": "step_completed", "step": step}
        yield {"event": "final", "result": result if fmt == "dict" else str((result.get("result") or {}).get("content") or "")}
        yield {"event": "lifecycle_end"}

    def reload_plugins(self) -> dict[str, Any]:
        return {"ok": True, "message": "core-brain phase1 has no plugin runtime"}

    def inspect_semantic_memory(self, policy_key: str | None = None, status: str | None = None) -> dict[str, Any]:
        facts = self._stores.long_term_repo.search(policy_key or "", top_k=20)
        return {
            "total": len(facts),
            "items": [{"text": item, "status": status or "active"} for item in facts],
        }

    def inspect_runtime_memory(self, query: str | None = None, namespace: str | None = None, top_k: int = 5) -> dict[str, Any]:
        facts = self._stores.long_term_repo.search(query or "", top_k=top_k)
        return {
            "query": query or "",
            "namespace": namespace or "*",
            "vector_hits": [{"text": item, "score": 1.0} for item in facts],
            "promotion_artifacts": [],
            "semantic_memory_summary": {"total_facts": len(self._stores.long_term_repo._facts)},
            "semantic_memory_latest_rollback": None,
        }

    def inspect_private_brain_summary(self) -> dict[str, Any]:
        return {
            "sessions": len(self._stores.session_repo._data),
            "tasks": len(self._stores.task_repo._data),
            "events": len(self._stores.execution_repo._events),
            "traces": len(self._stores.trace_repo.all()),
        }

    def build_training_manifest(self, profile: str = "lora_sft") -> dict[str, Any]:
        return {"profile": profile, "dataset_ready": False, "runs": []}

    def inspect_training_runner(self, profile: str = "lora_sft", backend: str = "mock") -> dict[str, Any]:
        return {"profile": profile, "backend": backend, "ready": True, "last_run": None}

    def start_training_run(
        self,
        profile: str = "lora_sft",
        backend: str = "mock",
        dry_run: bool = True,
        note: str = "",
    ) -> dict[str, Any]:
        return {
            "profile": profile,
            "backend": backend,
            "dry_run": dry_run,
            "note": note,
            "status": "queued" if not dry_run else "dry_run_ok",
        }
