from __future__ import annotations

from typing import Any


class Registry:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def register(self, name: str, obj: Any) -> None:
        self.items[name] = obj

    def get(self, name: str) -> Any:
        return self.items.get(name)

    def unregister(self, name: str) -> None:
        self.items.pop(name, None)

    def list(self) -> list[str]:
        return list(self.items.keys())
