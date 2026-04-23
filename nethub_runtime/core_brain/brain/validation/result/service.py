from __future__ import annotations

from typing import Any


class ResultValidationService:
    def summarize(
        self,
        *,
        step_validations: list[dict[str, Any]],
        intent_validation: dict[str, Any],
        trace_summary: dict[str, Any],
    ) -> dict[str, Any]:
        all_steps_ok = all(bool(item.get("step_goal_met")) for item in step_validations)
        intent_ok = bool(intent_validation.get("intent_alignment"))
        trace_ok = bool(trace_summary.get("all_success"))
        return {
            "ok": all_steps_ok and intent_ok and trace_ok,
            "step_validation_count": len(step_validations),
            "intent_validation": intent_validation,
            "trace_summary": trace_summary,
        }
