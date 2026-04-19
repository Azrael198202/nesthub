"""
AI Core main entrypoint. Instantiates the core engine and exposes FastAPI app.
"""
import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from nethub_runtime.core.routers.core_api import router as core_router
from nethub_runtime.core.services.core_engine import AICore

app = FastAPI(title="NestHub AI Core")
app.include_router(core_router, prefix="/core")

SEMANTIC_MEMORY_DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "examples" / "semantic-memory-dashboard"
if SEMANTIC_MEMORY_DASHBOARD_DIR.exists():
	app.mount(
		"/examples/semantic-memory-dashboard",
		StaticFiles(directory=str(SEMANTIC_MEMORY_DASHBOARD_DIR), html=True),
		name="semantic-memory-dashboard",
	)


class CoreEngine:
	"""Synchronous wrapper around AICore for simple scripting and legacy tests.

	Maps the current async result structure into a flat dict with keys:
	  ``task``, ``workflow`` (steps list), and ``result`` (extracted records).
	"""

	def __init__(self) -> None:
		self._core = AICore()

	def handle(self, input_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
		raw = asyncio.run(self._core.handle(input_text, context, fmt="dict", use_langraph=False))
		if not isinstance(raw, dict):
			return {"task": {}, "workflow": {"steps": []}, "result": []}

		task = raw.get("task", {})
		execution_result = raw.get("execution_result", {})
		final_output = execution_result.get("final_output", {})

		# Collect workflow steps from the plan (if present) or final_output keys
		workflow_plan = raw.get("workflow_plan", {})
		steps = list(workflow_plan.get("steps", final_output.keys()))
		records = final_output.get("extract_records", {}).get("records", [])

		return {
			"task": task,
			"workflow": {"steps": steps},
			"result": records,
			"execution_result": execution_result,
		}
