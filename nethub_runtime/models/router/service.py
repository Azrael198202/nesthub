from __future__ import annotations

from typing import Any


class ProviderRouter:
    """Minimal provider routing abstraction for runtime fallback decisions."""

    def choose(self, *, primary: dict[str, Any], fallback: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        options = [primary]
        if fallback:
            options.append(fallback)
        return options
