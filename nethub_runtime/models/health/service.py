from __future__ import annotations

from typing import Any


class ProviderHealthService:
    def check(self, provider: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": str(provider.get("provider") or "unknown"),
            "model": str(provider.get("model") or ""),
            "status": "unknown",
        }
