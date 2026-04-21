from __future__ import annotations

from typing import Any

from nethub_runtime.execution.dispatcher import ExecutionGraphDispatcher
from nethub_runtime.execution.pipeline import ExecutionUpgradePipeline


class ExecutionTaskRunner:
	"""Coordinates prepare, dispatch, and resume flows for core+ runtime."""

	def __init__(self, pipeline: ExecutionUpgradePipeline) -> None:
		self.pipeline = pipeline
		self.dispatcher = ExecutionGraphDispatcher(pipeline.profile)

	async def prepare(self, input_text: str, context: dict[str, Any] | None, task: dict[str, Any] | None = None) -> dict[str, Any]:
		prepared = await self.pipeline.prepare(input_text, context, task)
		prepared["dispatch"] = self.dispatcher.dispatch(prepared["request_plan"], task)
		return prepared

	async def resume_human_review(self, input_text: str, context: dict[str, Any] | None, task: dict[str, Any] | None = None) -> dict[str, Any]:
		next_context = dict(context or {})
		metadata = dict(next_context.get("metadata") or {})
		metadata.setdefault("human_review_response", {})
		next_context["metadata"] = metadata
		prepared = await self.pipeline.resume_review(input_text, next_context, task)
		prepared["dispatch"] = self.dispatcher.dispatch(prepared["request_plan"], task)
		return prepared
