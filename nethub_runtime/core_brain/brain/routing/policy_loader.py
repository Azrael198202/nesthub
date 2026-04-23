from __future__ import annotations

from typing import Any


class PolicyLoader:
    def __init__(self, routing_policy: dict[str, Any]) -> None:
        self.routing_policy = routing_policy

    def local_threshold(self) -> float:
        threshold = (self.routing_policy.get("escalation") or {}).get("external_on_confidence_below", 0.5)
        try:
            return float(threshold)
        except Exception:
            return 0.5

    def allow_external_by_default(self) -> bool:
        return bool((self.routing_policy.get("escalation") or {}).get("allow_external_default", True))
