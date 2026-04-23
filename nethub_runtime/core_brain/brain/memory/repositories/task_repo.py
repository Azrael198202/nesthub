from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskRepo:
    _data: dict[str, dict[str, Any]] = field(default_factory=dict)

    def write(self, task_id: str, payload: dict[str, Any]) -> None:
        self._data[task_id] = dict(payload)

    def read(self, task_id: str) -> dict[str, Any]:
        return dict(self._data.get(task_id, {}))
