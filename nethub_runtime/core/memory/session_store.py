from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any


class SessionStore:
    """Thread-safe in-memory session state store."""

    def __init__(self) -> None:
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            return deepcopy(payload)

    def patch(self, session_id: str, patch_data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            payload.update(patch_data)
            return deepcopy(payload)

    def append_records(self, session_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            payload.setdefault("records", [])
            payload["records"].extend(records)
            return deepcopy(payload)
