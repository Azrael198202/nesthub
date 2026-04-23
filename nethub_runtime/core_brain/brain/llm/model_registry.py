from __future__ import annotations

from typing import Any


class ModelRegistry:
    def __init__(self, registry_config: dict[str, Any]) -> None:
        self.registry_config = registry_config
        self.models = {
            str(item.get("id")): item
            for item in registry_config.get("models", [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }

    def get(self, model_id: str) -> dict[str, Any]:
        return dict(self.models.get(model_id, {}))

    def intent_model(self) -> dict[str, Any]:
        routing = self.registry_config.get("routing", {})
        return self.get(str(routing.get("intent") or ""))

    def chat_model(self) -> dict[str, Any]:
        routing = self.registry_config.get("routing", {})
        return self.get(str(routing.get("chat") or ""))
