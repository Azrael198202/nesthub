from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from nethub_runtime.core.services.core_engine import AICore
from nethub_runtime.core.services.runtime_keyword_signal_analyzer import RuntimeKeywordSignalAnalyzer
from nethub_runtime.execution.pipeline import ExecutionUpgradePipeline
from nethub_runtime.execution.task_runner import ExecutionTaskRunner


class CorePlusEngine:
    """Non-invasive core upgrade wrapper with config-driven orchestration."""

    def __init__(self, model_config_path: str | None = None, base_core: Any | None = None) -> None:
        self._base_core = base_core or AICore(model_config_path=model_config_path)
        self.pipeline = ExecutionUpgradePipeline(base_core=self._base_core)
        self.task_runner = ExecutionTaskRunner(self.pipeline)
        self.version = self.pipeline.profile.get("version", "core_plus")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base_core, name)

    def _rule_prejudge(self, input_text: str) -> dict[str, Any]:
        return self.pipeline._match_rule(input_text)

    def _build_request_plan(self, input_text: str, context: dict[str, Any] | None) -> dict[str, Any]:
        return self.pipeline.build_request_plan(input_text, context)

    def _evaluate_result(self, result: dict[str, Any], request_plan: dict[str, Any]) -> dict[str, Any]:
        return self.pipeline.evaluate_result(result, request_plan)

    def _build_data_routing(self, result: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        return self.pipeline.build_data_routing(result, evaluation)

    def _build_training_signal(self, result: dict[str, Any], evaluation: dict[str, Any], routing: dict[str, Any]) -> dict[str, Any]:
        return self.pipeline.build_training_signal(result, evaluation, routing)

    def _build_stats(self, request_plan: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
        return self.pipeline.build_runtime_stats(request_plan, evaluation)

    def _enrich_result(self, result: dict[str, Any], request_plan: dict[str, Any]) -> dict[str, Any]:
        return self.pipeline.enrich_result(result, request_plan)

    def _forced_task_from_request_plan(self, request_plan: dict[str, Any], input_text: str) -> dict[str, Any]:
        selected_graph = str((request_plan.get("intent_router") or {}).get("selected_graph") or "intent_router_graph")
        rule_intent = str((request_plan.get("rule_prejudge") or {}).get("intent") or "general_task")
        mapping: dict[str, dict[str, Any]] = {
            "schedule_graph": {
                "intent": "schedule_create",
                "domain": "data_ops",
                "output_requirements": ["message", "records"],
            },
            "expense_record_graph": {
                "intent": "record_expense",
                "domain": "data_management",
                "output_requirements": ["message", "records"],
            },
            "document_summary_graph": {
                "intent": "document_summary",
                "domain": "content_generation",
                "output_requirements": ["summary"],
            },
            "external_search_graph": {
                "intent": "web_research_task",
                "domain": "knowledge_ops",
                "output_requirements": ["summary"],
            },
            "rag_qa_graph": {
                "intent": "query_agent_knowledge",
                "domain": "knowledge_ops",
                "output_requirements": ["answer"],
            },
        }
        intent_fallbacks: dict[str, dict[str, Any]] = {
            "create_information_agent": {
                "intent": "create_information_agent",
                "domain": "agent_management",
                "output_requirements": ["agent", "dialog"],
            },
            "refine_information_agent": {
                "intent": "refine_information_agent",
                "domain": "agent_management",
                "output_requirements": ["agent", "dialog"],
            },
            "finalize_information_agent": {
                "intent": "finalize_information_agent",
                "domain": "agent_management",
                "output_requirements": ["agent", "dialog"],
            },
            "capture_agent_knowledge": {
                "intent": "capture_agent_knowledge",
                "domain": "agent_management",
                "output_requirements": ["knowledge", "dialog"],
            },
            "query_agent_knowledge": {
                "intent": "query_agent_knowledge",
                "domain": "knowledge_ops",
                "output_requirements": ["answer", "knowledge_hits"],
            },
        }
        base = mapping.get(
            selected_graph,
            intent_fallbacks.get(
                rule_intent,
                {
                    "intent": rule_intent,
                    "domain": "general",
                    "output_requirements": ["message"],
                },
            ),
        )
        return {
            "task_id": f"core_plus_forced_{selected_graph}",
            "intent": base["intent"],
            "domain": base["domain"],
            "constraints": {"need_agent": False},
            "output_requirements": list(base["output_requirements"]),
            "metadata": {
                "forced_by_core_plus": True,
                "selected_graph": selected_graph,
                "request_plan_version": str(request_plan.get("version") or "core_plus"),
                "input_preview": input_text[:120],
                "capability_orchestration": dict(request_plan.get("capability_orchestration") or {}),
                "request_plan": request_plan,
            },
        }

    def _session_state_for_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        session_id = str((context or {}).get("session_id") or "").strip()
        if not session_id:
            return {}
        session_store = getattr(getattr(self._base_core, "context_manager", None), "session_store", None)
        if session_store is None or not hasattr(session_store, "get"):
            return {}
        try:
            payload = session_store.get(session_id)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _keyword_signals(self, text: str) -> dict[str, Any]:
        coordinator = getattr(self._base_core, "execution_coordinator", None)
        semantic_policy_store = getattr(coordinator, "semantic_policy_store", None)
        model_router = getattr(self._base_core, "model_router", None)
        analyzer = RuntimeKeywordSignalAnalyzer(model_router=model_router, semantic_policy_store=semantic_policy_store)
        try:
            payload = analyzer.analyze(text)
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _should_skip_forced_task(self, *, input_text: str, context: dict[str, Any] | None) -> bool:
        state = self._session_state_for_context(context)
        if not state:
            return False

        setup = state.get("agent_setup") or {}
        collection = state.get("knowledge_collection") or {}
        configured_agent = state.get("configured_agent") or {}
        if bool(setup.get("active")) or bool(collection.get("active")):
            return True
        if str(configured_agent.get("status") or "").strip() != "active":
            return False

        keyword_signals = self._keyword_signals(input_text)
        action_flags = keyword_signals.get("action_flags", {}) if isinstance(keyword_signals, dict) else {}
        intent_hints = set(keyword_signals.get("intent_hints", [])) if isinstance(keyword_signals, dict) else set()

        if bool(action_flags.get("query_like")) or bool(action_flags.get("knowledge_capture_like")):
            return True

        return bool(
            {"query_agent_knowledge", "capture_agent_knowledge", "refine_information_agent", "finalize_information_agent"}
            & intent_hints
        )

    async def handle(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
        fmt: str = "dict",
        use_langraph: bool = True,
    ) -> dict[str, Any] | str:
        next_context = dict(context or {})
        metadata = dict(next_context.get("metadata") or {})
        preparation = await self.task_runner.prepare(input_text, next_context)
        request_plan = preparation["request_plan"]
        metadata["core_plus_request_plan"] = request_plan
        metadata["core_plus_preparation"] = preparation
        if self._should_skip_forced_task(input_text=input_text, context=next_context):
            metadata.pop("core_plus_forced_task", None)
        else:
            metadata["core_plus_forced_task"] = self._forced_task_from_request_plan(request_plan, input_text)
        next_context["metadata"] = metadata
        result = await self._base_core.handle(input_text, next_context, fmt=fmt, use_langraph=use_langraph)
        if fmt != "dict" or not isinstance(result, dict):
            return result
        return self.pipeline.enrich_result(result, request_plan, preparation=preparation)

    async def handle_stream(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
        fmt: str = "dict",
    ) -> AsyncGenerator[dict[str, Any], None]:
        next_context = dict(context or {})
        metadata = dict(next_context.get("metadata") or {})
        preparation = await self.task_runner.prepare(input_text, next_context)
        request_plan = preparation["request_plan"]
        metadata["core_plus_request_plan"] = request_plan
        metadata["core_plus_preparation"] = preparation
        if self._should_skip_forced_task(input_text=input_text, context=next_context):
            metadata.pop("core_plus_forced_task", None)
        else:
            metadata["core_plus_forced_task"] = self._forced_task_from_request_plan(request_plan, input_text)
        next_context["metadata"] = metadata
        yield {"event": "core_plus_planned", "core_version": self.version, "request_plan": request_plan, "dispatch": preparation.get("dispatch", {})}
        async for event in self._base_core.handle_stream(input_text, next_context, fmt=fmt):
            if event.get("event") == "final" and isinstance(event.get("result"), dict):
                event = {**event, "result": self.pipeline.enrich_result(dict(event["result"]), request_plan, preparation=preparation)}
            yield event
