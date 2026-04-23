from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.llm.model_registry import ModelRegistry
from nethub_runtime.core_brain.brain.routing.policy_loader import PolicyLoader


class RouteSelector:
    def __init__(self, model_registry: ModelRegistry, policy_loader: PolicyLoader) -> None:
        self.model_registry = model_registry
        self.policy_loader = policy_loader

    def choose(self, *, confidence: float, allow_external: bool) -> dict[str, Any]:
        local_model = self.model_registry.chat_model() or self.model_registry.intent_model()
        selected = dict(local_model)
        escalated = False

        if allow_external and confidence < self.policy_loader.local_threshold():
            fallback = str(local_model.get("fallback") or "")
            if fallback:
                # Use the configured fallback model id if it exists.
                fallback_config = self.model_registry.get(fallback) or {"id": fallback, "model": fallback, "provider": "external"}
                selected = dict(fallback_config)
                escalated = True

        return {
            "provider": str(selected.get("provider") or "unknown"),
            "model": str(selected.get("id") or selected.get("model") or "unknown"),
            "escalated": escalated,
        }
