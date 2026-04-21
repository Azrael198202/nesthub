from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from nethub_runtime.core.services.core_engine import AICore
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
        next_context["metadata"] = metadata
        yield {"event": "core_plus_planned", "core_version": self.version, "request_plan": request_plan, "dispatch": preparation.get("dispatch", {})}
        async for event in self._base_core.handle_stream(input_text, next_context, fmt=fmt):
            if event.get("event") == "final" and isinstance(event.get("result"), dict):
                event = {**event, "result": self.pipeline.enrich_result(dict(event["result"]), request_plan, preparation=preparation)}
            yield event