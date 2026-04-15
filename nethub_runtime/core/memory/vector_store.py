from __future__ import annotations

from typing import Any


class VectorStore:
    """Minimal placeholder for semantic memory extension."""

    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    def add(self, item: dict[str, Any]) -> None:
        self._items.append(item)

    def search(self, _query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self._items[:top_k]
