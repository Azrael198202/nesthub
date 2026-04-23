from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.contracts.blueprint import BlueprintContract


class BlueprintRegistry:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    def register(self, blueprint_payload: dict[str, Any]) -> dict[str, Any]:
        blueprint = BlueprintContract.model_validate(blueprint_payload).model_dump(mode="python")
        self._items[str(blueprint["blueprint_id"])] = blueprint
        return blueprint

    def get(self, blueprint_id: str) -> dict[str, Any]:
        return dict(self._items.get(blueprint_id) or {})
