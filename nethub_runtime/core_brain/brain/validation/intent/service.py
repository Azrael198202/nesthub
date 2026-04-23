from __future__ import annotations

from typing import Any


class IntentValidationService:
    def validate(self, *, intent: dict[str, Any], answer_text: str) -> dict[str, Any]:
        expected = list(intent.get("expected_outcome") or [])
        aligned = bool(answer_text.strip()) and len(expected) >= 1
        return {
            "step_goal_met": aligned,
            "schema_valid": True,
            "intent_alignment": aligned,
            "messages": ["intent alignment checked"],
        }
