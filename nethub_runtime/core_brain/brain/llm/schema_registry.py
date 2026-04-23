from __future__ import annotations

from typing import Any


class SchemaRegistry:
    def __init__(self, schemas: dict[str, dict[str, Any]]) -> None:
        self.schemas = dict(schemas)

    def get_intent_schema(self) -> dict[str, Any]:
        return dict(self.schemas.get("intent") or {})

    def get_schema(self, name: str) -> dict[str, Any]:
        return dict(self.schemas.get(name) or {})
