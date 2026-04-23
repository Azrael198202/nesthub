from __future__ import annotations

from typing import Any


class TraceRepository:
    def __init__(self) -> None:
        self._traces: list[dict[str, Any]] = []

    def append(self, trace: dict[str, Any]) -> None:
        self._traces.append(dict(trace))
        self._traces = self._traces[-2000:]

    def all(self) -> list[dict[str, Any]]:
        return list(self._traces)
