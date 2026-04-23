from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.routing.router_service import RouterService


class RoutePlanningService:
    def __init__(self, router_service: RouterService) -> None:
        self.router_service = router_service

    def select(self, *, intent: dict[str, Any], allow_external: bool) -> dict[str, Any]:
        route = self.router_service.select_route(intent=intent, allow_external=allow_external)
        return {
            "model": str(route.get("model") or ""),
            "provider": str(route.get("provider") or ""),
            "fallback_model": str(route.get("fallback_model") or ""),
            "reason": str(route.get("reason") or "route_selector"),
        }
