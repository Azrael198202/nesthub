from __future__ import annotations

from typing import Any


class IntentKBService:
    def retrieve(self, intent_name: str) -> list[str]:
        if not intent_name:
            return []
        return [f"intent:{intent_name}:baseline_policy"]
