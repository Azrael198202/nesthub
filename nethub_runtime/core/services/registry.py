from __future__ import annotations

import json
from pathlib import Path
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


class JsonRegistry(Registry):
    """File-backed registry with hot-reload support."""

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path
        self._last_mtime: float | None = None
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text("{}", encoding="utf-8")
            self.items = {}
            self._last_mtime = self.file_path.stat().st_mtime
            return
        self.items = json.loads(self.file_path.read_text(encoding="utf-8"))
        self._last_mtime = self.file_path.stat().st_mtime

    def _save(self) -> None:
        serializable: dict[str, Any] = {}
        for key, value in self.items.items():
            if hasattr(value, "model_dump"):
                serializable[key] = value.model_dump()
            else:
                serializable[key] = value
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        self._last_mtime = self.file_path.stat().st_mtime

    def hot_reload(self) -> None:
        if not self.file_path.exists():
            return
        current_mtime = self.file_path.stat().st_mtime
        if self._last_mtime is None or current_mtime > self._last_mtime:
            self._load()

    def register(self, name: str, obj: Any) -> None:
        self.items[name] = obj
        self._save()

    def unregister(self, name: str) -> None:
        self.items.pop(name, None)
        self._save()
