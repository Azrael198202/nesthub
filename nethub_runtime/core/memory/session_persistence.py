"""
Session persistence backends for SessionStore.

Business-domain principle:
  Core code (SessionStore) is unaware of how data is stored — it delegates
  to a ``SessionPersistence`` implementation injected at startup.  The core
  continues to work without any persistence (in-memory only) as before.

Backends provided:
  - ``NullSessionPersistence``   — no-op; default when nothing is configured
  - ``SQLiteSessionPersistence`` — durable SQLite file; survives restarts

Injected by ``AICore.__init__`` into ``SessionStore`` so that business-domain
data persists without touching core logic.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("nethub_runtime.core.session_persistence")


# ---------------------------------------------------------------------------
# Abstract protocol
# ---------------------------------------------------------------------------

class SessionPersistence(ABC):
    """Interface that SessionStore uses to load/save session payloads."""

    @abstractmethod
    def load(self, session_id: str) -> dict[str, Any] | None:
        """Load a stored session payload; return None if not found."""

    @abstractmethod
    def save(self, session_id: str, payload: dict[str, Any]) -> None:
        """Persist a session payload (upsert)."""

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Remove a stored session."""

    @abstractmethod
    def list_ids(self) -> list[str]:
        """Return all stored session IDs."""


# ---------------------------------------------------------------------------
# Null backend (default)
# ---------------------------------------------------------------------------

class NullSessionPersistence(SessionPersistence):
    """No-op persistence — matches the pre-existing in-memory-only behaviour."""

    def load(self, session_id: str) -> dict[str, Any] | None:
        return None

    def save(self, session_id: str, payload: dict[str, Any]) -> None:
        pass

    def delete(self, session_id: str) -> None:
        pass

    def list_ids(self) -> list[str]:
        return []

    def clear_all(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class SQLiteSessionPersistence(SessionPersistence):
    """Durable session store backed by a local SQLite file.

    Thread-safe: every public method acquires ``self._lock`` so that
    concurrent requests sharing the same process don't corrupt the DB.

    Args:
        db_path: Path to the SQLite file.  The parent directory will be
                 created if it does not exist.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()
        LOGGER.info("SQLiteSessionPersistence ready at %s", self._db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")   # safe concurrent reads
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)

    def load(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT payload FROM sessions WHERE session_id = ?", (session_id,)
                )
                row = cur.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except Exception as exc:
            LOGGER.warning("session_persistence: corrupt payload for %s: %s", session_id, exc)
            return None

    def save(self, session_id: str, payload: dict[str, Any]) -> None:
        now = datetime.now(UTC).isoformat()
        serialised = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (session_id, payload, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        payload    = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (session_id, serialised, now),
                )

    def delete(self, session_id: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def list_ids(self) -> list[str]:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("SELECT session_id FROM sessions ORDER BY updated_at DESC")
                return [row[0] for row in cur.fetchall()]

    def clear_all(self) -> None:
        """Delete all stored sessions (used for test isolation)."""
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM sessions")
