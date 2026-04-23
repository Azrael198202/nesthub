from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.routing.route_selector import RouteSelector


class RouterService:
    def __init__(self, route_selector: RouteSelector) -> None:
        self.route_selector = route_selector

    def select_route(self, *, intent: dict[str, Any], allow_external: bool) -> dict[str, Any]:
        confidence = float(intent.get("confidence") or 0.0)
        return self.route_selector.choose(confidence=confidence, allow_external=allow_external)
