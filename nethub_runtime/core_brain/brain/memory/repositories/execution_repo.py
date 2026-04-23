from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionRepo:
    _events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, event: dict[str, Any]) -> None:
        self._events.append(dict(event))
        self._events = self._events[-500:]

    def all(self) -> list[dict[str, Any]]:
        return list(self._events)
