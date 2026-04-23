from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.chat.brain_facade import BrainFacade
from nethub_runtime.core_brain.brain.chat.chat_service import ChatService
from nethub_runtime.core_brain.brain.context.context_builder import ContextBuilder
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
from nethub_runtime.core_brain.brain.routing.policy_loader import PolicyLoader
from nethub_runtime.core_brain.brain.routing.route_selector import RouteSelector
from nethub_runtime.core_brain.brain.routing.router_service import RouterService
from nethub_runtime.core_brain.brain.workflows.graph.chat_graph import ChatGraphRunner
from nethub_runtime.core_brain.config import ConfigLoader


@dataclass(slots=True)
class _CoreBrainStores:
    session_repo: SessionRepo
    task_repo: TaskRepo
    long_term_repo: LongTermRepo
    execution_repo: ExecutionRepo


class CoreBrainEngine:
    def __init__(self) -> None:
        cfg = ConfigLoader().load()
        stores = _CoreBrainStores(
            session_repo=SessionRepo(),
            task_repo=TaskRepo(),
            long_term_repo=LongTermRepo(),
            execution_repo=ExecutionRepo(),
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

        self._stores = stores
        self.facade = BrainFacade(
            context_builder=context_builder,
            chat_service=chat_service,
            router_service=router_service,
            session_memory=session_memory,
            task_memory=task_memory,
            long_term_memory=long_term_memory,
            execution_repo=stores.execution_repo,
            workflow_runner=ChatGraphRunner(),
        )

        # Compatibility attributes expected by bootstrap callers.
        self.model_router = None
        self.workflow_executor = None
        self.agent_builder = None
        self.tool_registry = None

    async def handle(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
        fmt: str = "dict",
        use_langraph: bool = True,
    ) -> dict[str, Any] | str:
        payload = dict(context or {})
        req = ChatRequest(
            session_id=str(payload.get("session_id") or "default"),
            task_id=str(payload.get("task_id") or "") or None,
            user_id=str((payload.get("metadata") or {}).get("user_id") or "tvbox"),
            message=input_text,
            allow_external=bool((payload.get("metadata") or {}).get("allow_external", True)),
            mode="chat",
        )
        result = await self.facade.handle_chat(req)
        if fmt == "text":
            return str((result.get("result") or {}).get("content") or "")
        return result

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
        return {"ok": True, "message": "core-brain phase0 has no plugin runtime"}

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
            "artifacts": {},
        }

    def build_training_manifest(self, profile: str = "lora_sft") -> dict[str, Any]:
        return {
            "profile": profile,
            "dataset_ready": False,
            "runs": [],
        }

    def inspect_training_runner(self, profile: str = "lora_sft", backend: str = "mock") -> dict[str, Any]:
        return {
            "profile": profile,
            "backend": backend,
            "ready": True,
            "last_run": None,
        }

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
