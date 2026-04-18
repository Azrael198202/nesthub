from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any

from nethub_runtime.core.config.settings import VECTOR_STORE_POLICY_PATH, ensure_core_config_dir
from nethub_runtime.config.settings import generated_root


class VectorStore:
    """Vector store facade with pluggable backend policy."""

    def __init__(self, policy_path: Path | None = None, storage_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path or VECTOR_STORE_POLICY_PATH
        self.policy = self._load_policy()
        self._storage_path = storage_path or (generated_root() / "memory" / "vector_store.json")
        self._lock = Lock()
        self._items: list[dict[str, Any]] = self._load_items()

    def _load_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            default = {
                "active": "memory",
                "stores": [
                    {"name": "memory", "provider": "in_memory", "enabled": True},
                    {"name": "pgvector", "provider": "pgvector", "enabled": False},
                ],
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
        with self._lock:
            self._items.append(item)
            self._persist_items()

    def _load_items(self) -> list[dict[str, Any]]:
        try:
            if not self._storage_path.exists():
                return []
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
        except Exception:
            return []
        return []

    def _persist_items(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps(self._items, ensure_ascii=False, indent=2), encoding="utf-8")

    def _tokenize(self, text: str) -> set[str]:
        tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
        return {token for token in tokens if token}

    def add_knowledge(
        self,
        *,
        namespace: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "id": item_id or f"{namespace}_{len(self._items) + 1}",
            "namespace": namespace,
            "content": content,
            "metadata": metadata or {},
            "tokens": sorted(self._tokenize(content)),
            "backend": self.active_store(),
        }
        with self._lock:
            self._items.append(record)
            self._persist_items()
        return record

    def search(self, query: str, top_k: int = 5, namespace: str | None = None) -> list[dict[str, Any]]:
        query_tokens = self._tokenize(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        with self._lock:
            items = list(self._items)
        for item in items:
            if namespace and item.get("namespace") != namespace:
                continue
            item_tokens = set(item.get("tokens") or [])
            score = len(query_tokens & item_tokens)
            if not query_tokens:
                score = 1
            elif score == 0 and query.lower() not in str(item.get("content", "")).lower():
                continue
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:top_k]]
