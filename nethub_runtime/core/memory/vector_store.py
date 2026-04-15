from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import VECTOR_STORE_POLICY_PATH, ensure_core_config_dir


class VectorStore:
    """Vector store facade with pluggable backend policy."""

    def __init__(self, policy_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path or VECTOR_STORE_POLICY_PATH
        self.policy = self._load_policy()
        self._items: list[dict[str, Any]] = []

    def _load_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            default = {
                "active": "memory",
                "stores": [{"name": "memory", "provider": "in_memory", "enabled": True}],
            }
            self.policy_path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
            return default
        return json.loads(self.policy_path.read_text(encoding="utf-8"))

    def active_store(self) -> dict[str, Any]:
        active_name = self.policy.get("active", "memory")
        stores = self.policy.get("stores", [])
        for item in stores:
            if item.get("name") == active_name:
                return item
        return {"name": "memory", "provider": "in_memory", "enabled": True}

    def add(self, item: dict[str, Any]) -> None:
        self._items.append(item)

    def search(self, _query: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self._items[:top_k]
