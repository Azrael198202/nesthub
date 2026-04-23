from __future__ import annotations

from typing import Any


class TraceEvaluatorService:
    def evaluate(self, traces: list[dict[str, Any]]) -> dict[str, Any]:
        failed = [item for item in traces if item.get("status") != "success"]
        return {
            "total": len(traces),
            "failed": len(failed),
            "all_success": len(failed) == 0,
        }
