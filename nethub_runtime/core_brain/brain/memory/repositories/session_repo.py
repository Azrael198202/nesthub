from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionRepo:
    _data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def append(self, session_id: str, role: str, content: str) -> None:
        self._data.setdefault(session_id, []).append({"role": role, "content": content})
        self._data[session_id] = self._data[session_id][-20:]

    def read(self, session_id: str) -> list[dict[str, Any]]:
        return list(self._data.get(session_id, []))
