from __future__ import annotations

from typing import Any


class StepValidationService:
    def validate(self, step_execution: dict[str, Any]) -> dict[str, Any]:
        status = str(step_execution.get("status") or "failed")
        return {
            "step_goal_met": status == "success",
            "schema_valid": True,
            "intent_alignment": None,
            "messages": ["step validation complete"],
        }
