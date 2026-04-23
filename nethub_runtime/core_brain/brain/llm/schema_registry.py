from __future__ import annotations

from typing import Any


class SchemaRegistry:
    def __init__(self, intent_schema: dict[str, Any]) -> None:
        self.intent_schema = intent_schema

    def get_intent_schema(self) -> dict[str, Any]:
        return dict(self.intent_schema)
