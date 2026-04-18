from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable

from nethub_runtime.core.config.settings import VECTOR_STORE_POLICY_PATH, ensure_core_config_dir

LOGGER = logging.getLogger("nethub_runtime.core.vector_store")

# ---------------------------------------------------------------------------
# SQLite vector persistence backend
# ---------------------------------------------------------------------------

_VS_SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_items (
    item_id     TEXT PRIMARY KEY,
    namespace   TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    tokens      TEXT NOT NULL DEFAULT '[]',
    embedding   TEXT,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vs_namespace ON vector_items (namespace);
"""


class SQLiteVectorPersistence:
    """Durable persistence backend for VectorStore using a local SQLite file.

    Injected at startup by ``AICore.__init__`` so the business-domain layer
    keeps vector knowledge across restarts without touching core VectorStore
    logic.

    Thread-safe: all public methods acquire ``self._lock``.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
        LOGGER.info("SQLiteVectorPersistence ready at %s", self._db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_VS_SCHEMA)

    def load_all(self) -> list[dict[str, Any]]:
        """Load all persisted items into memory on startup."""
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT item_id, namespace, content, metadata, tokens, embedding FROM vector_items"
                )
                rows = cur.fetchall()
        items = []
        for row in rows:
            item_id, namespace, content, metadata_s, tokens_s, embedding_s = row
            item: dict[str, Any] = {
                "id": item_id,
                "namespace": namespace,
                "content": content,
                "metadata": json.loads(metadata_s or "{}"),
                "tokens": json.loads(tokens_s or "[]"),
            }
            if embedding_s:
                try:
                    item["embedding"] = json.loads(embedding_s)
                except Exception:
                    pass
            items.append(item)
        return items

    def save(self, item: dict[str, Any]) -> None:
        """Persist a single vector item (upsert)."""
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        embedding_s = json.dumps(item["embedding"]) if item.get("embedding") else None
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO vector_items (item_id, namespace, content, metadata, tokens, embedding, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        namespace  = excluded.namespace,
                        content    = excluded.content,
                        metadata   = excluded.metadata,
                        tokens     = excluded.tokens,
                        embedding  = excluded.embedding,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item["id"],
                        item["namespace"],
                        item["content"],
                        json.dumps(item.get("metadata") or {}, ensure_ascii=False),
                        json.dumps(item.get("tokens") or [], ensure_ascii=False),
                        embedding_s,
                        now,
                    ),
                )

    def delete(self, item_id: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM vector_items WHERE item_id = ?", (item_id,))


class VectorStore:
    """Vector store facade with pluggable backend policy and optional embedding.

    Embedding strategy (Task 3)
    ---------------------------
    When an ``embedding_fn`` is injected at construction time the store uses
    cosine similarity for search (real semantic matching).  Without one it
    falls back to keyword-overlap scoring so tests and cold-starts always work.

    The ``embedding_fn`` contract::

        embedding_fn(text: str) -> list[float]

    Injected by ``AICore.__init__`` when ``sentence-transformers`` is available
    so the core code (this file) is decoupled from that heavy dependency.
    """

    def __init__(
        self,
        policy_path: Path | None = None,
        *,
        embedding_fn: Callable[[str], list[float]] | None = None,
        persistence: SQLiteVectorPersistence | None = None,
    ) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path or VECTOR_STORE_POLICY_PATH
        self.policy = self._load_policy()
        self._embedding_fn = embedding_fn
        self._persistence = persistence
        # Load previously persisted items on startup
        if self._persistence is not None:
            self._items: list[dict[str, Any]] = self._persistence.load_all()
            LOGGER.info("VectorStore: loaded %d items from SQLite", len(self._items))
        else:
            self._items = []

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
        self._items.append(item)

    def _tokenize(self, text: str) -> set[str]:
        tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
        return {token for token in tokens if token}

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def add_knowledge(
        self,
        *,
        namespace: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        item_id: str | None = None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": item_id or f"{namespace}_{len(self._items) + 1}",
            "namespace": namespace,
            "content": content,
            "metadata": metadata or {},
            "tokens": sorted(self._tokenize(content)),
            "backend": self.active_store(),
        }
        if self._embedding_fn is not None:
            try:
                record["embedding"] = self._embedding_fn(content)
            except Exception as exc:
                LOGGER.debug("embedding_fn failed for item %s: %s", record["id"], exc)
        self._items.append(record)
        # Persist to SQLite backend (business domain layer)
        if self._persistence is not None:
            try:
                self._persistence.save(record)
            except Exception as exc:
                LOGGER.debug("VectorStore persistence save failed: %s", exc)
        return record

    def search(self, query: str, top_k: int = 5, namespace: str | None = None) -> list[dict[str, Any]]:
        if self._embedding_fn is not None:
            return self._search_embedding(query, top_k, namespace)
        return self._search_keyword(query, top_k, namespace)

    def _search_embedding(self, query: str, top_k: int, namespace: str | None) -> list[dict[str, Any]]:
        try:
            query_vec = self._embedding_fn(query)  # type: ignore[misc]
        except Exception as exc:
            LOGGER.debug("embedding_fn failed for query; falling back to keyword: %s", exc)
            return self._search_keyword(query, top_k, namespace)

        scored: list[tuple[float, dict[str, Any]]] = []
        for item in self._items:
            if namespace and item.get("namespace") != namespace:
                continue
            item_vec = item.get("embedding")
            if item_vec is None:
                continue
            score = self._cosine(query_vec, item_vec)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def _search_keyword(self, query: str, top_k: int, namespace: str | None) -> list[dict[str, Any]]:
        query_tokens = self._tokenize(query)
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in self._items:
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
