from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import Lock
from typing import Any

from nethub_runtime.config.settings import generated_root


class SessionStore:
    """Thread-safe session state store with simple file persistence."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._lock = Lock()
        self._storage_path = storage_path or (generated_root() / "memory" / "session_store.json")
        self._state: dict[str, dict[str, Any]] = self._load_state()

    def _load_state(self) -> dict[str, dict[str, Any]]:
        try:
            if not self._storage_path.exists():
                return {}
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                normalized: dict[str, dict[str, Any]] = {}
                for key, value in payload.items():
                    if isinstance(value, dict):
                        normalized[str(key)] = value
                return normalized
        except Exception:
            return {}
        return {}

    def _persist_state(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = json.dumps(self._state, ensure_ascii=False, indent=2)
        self._storage_path.write_text(snapshot, encoding="utf-8")

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            return deepcopy(payload)

    def patch(self, session_id: str, patch_data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            payload.update(patch_data)
            self._persist_state()
            return deepcopy(payload)

    def append_records(self, session_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            payload.setdefault("records", [])
            payload["records"].extend(records)
            self._persist_state()
            return deepcopy(payload)
