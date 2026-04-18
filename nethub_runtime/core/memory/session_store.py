from __future__ import annotations

import logging
from copy import deepcopy
from threading import Lock
from typing import Any, Callable

from nethub_runtime.core.memory.session_persistence import (
    NullSessionPersistence,
    SessionPersistence,
)

LOGGER = logging.getLogger("nethub_runtime.core.session")

# Prefix used to distinguish task sessions from main sessions
_TASK_SESSION_PREFIX = "task:"


# ---------------------------------------------------------------------------
# Session Compactor
# Inspired by OpenClaw's compaction pipeline:
#   When session records exceed max_records, old entries are summarised into
#   a single compact record so the active window stays bounded.
#
# The caller supplies an optional ``summarize_fn`` — any callable that takes
# a list[dict] and returns a string summary.  When no function is provided,
# compaction is a no-op (safe default for tests / cold-start).
# ---------------------------------------------------------------------------


class SessionCompactor:
    """Compacts session records when they exceed a configurable threshold.

    Args:
        max_records:     Compact when ``len(records) > max_records``.
        compact_to:      Target record count *after* compaction (default 5).
                         The oldest ``len(records) - compact_to`` records are
                         replaced by a single summary record.
        summarize_fn:    Callable(records: list[dict]) -> str.
                         Should produce a short natural-language summary.
                         When None, falls back to a plain JSON-dump summary.
    """

    def __init__(
        self,
        max_records: int = 50,
        compact_to: int = 5,
        summarize_fn: Callable[[list[dict[str, Any]]], str] | None = None,
    ) -> None:
        self.max_records = max_records
        self.compact_to = compact_to
        self._summarize_fn = summarize_fn

    def maybe_compact(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return a (possibly compacted) copy of *records*.

        When ``len(records) <= max_records`` the original list is returned
        unchanged.  Otherwise the oldest entries are replaced by one compact
        summary record.
        """
        if len(records) <= self.max_records:
            return records

        keep_tail = max(1, self.compact_to - 1)      # reserve 1 slot for summary
        old_records = records[:-keep_tail] if keep_tail > 0 else records
        new_tail = records[-keep_tail:] if keep_tail > 0 else []

        summary_text = self._summarize(old_records)
        summary_record: dict[str, Any] = {
            "role": "system",
            "type": "compaction_summary",
            "content": summary_text,
            "compacted_count": len(old_records),
        }
        compacted = [summary_record, *new_tail]
        LOGGER.info(
            "Session compacted: %d → %d records (%d summarised)",
            len(records),
            len(compacted),
            len(old_records),
        )
        return compacted

    def _summarize(self, records: list[dict[str, Any]]) -> str:
        if self._summarize_fn is not None:
            try:
                return self._summarize_fn(records)
            except Exception as exc:
                LOGGER.warning("summarize_fn failed (%s); using fallback", exc)
        # Fallback: plain-text dump of role + content
        lines: list[str] = []
        for r in records:
            role = r.get("role", "?")
            content = str(r.get("content") or r.get("output") or "")[:200]
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)


class SessionStore:
    """Thread-safe session state store with optional compaction, context-window
    limiting, topic-scoped task sessions, and pluggable persistence.

    Architecture
    ------------
    * **Main session** (``session_id``) — long-lived, per-user.  Stores
      accumulated preferences, summaries, and compacted history.
    * **Task session** (``task:{main_session_id}:{topic}``) — short-lived,
      per-task.  Isolated context so individual tasks don't pollute each other.
      ``create_task_session()`` creates one; ``close_task_session()`` merges a
      summary back into the main session and removes the task session.

    Context window
    --------------
    When ``max_window_messages`` is set, ``append_records`` keeps only the
    most recent N messages (after compaction).  Suitable default is 10–20 per
    the homework spec.

    Persistence
    -----------
    Inject a ``SessionPersistence`` implementation (e.g.
    ``SQLiteSessionPersistence``) at construction time.  On first ``get()``
    miss the store loads from the backend; on every mutation it saves back.
    When no persistence is configured the store remains in-memory only.
    """

    def __init__(
        self,
        compactor: SessionCompactor | None = None,
        *,
        persistence: SessionPersistence | None = None,
        max_window_messages: int | None = None,
    ) -> None:
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._compactor = compactor
        self._persistence: SessionPersistence = persistence or NullSessionPersistence()
        self._max_window = max_window_messages  # None = no trimming

    # ------------------------------------------------------------------
    # Core read/write
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            if session_id not in self._state:
                # Try to restore from persistence backend
                loaded = self._persistence.load(session_id)
                if loaded is not None:
                    self._state[session_id] = loaded
                    LOGGER.debug("session_store: restored %s from persistence", session_id)
                else:
                    self._state[session_id] = {"records": []}
            return deepcopy(self._state[session_id])

    def patch(self, session_id: str, patch_data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            payload.update(patch_data)
            self._persistence.save(session_id, payload)
            return deepcopy(payload)

    def append_records(self, session_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            payload = self._state.setdefault(session_id, {"records": []})
            payload.setdefault("records", [])
            payload["records"].extend(records)
            if self._compactor is not None:
                payload["records"] = self._compactor.maybe_compact(payload["records"])
            # Context-window trim: keep only the most recent N messages
            if self._max_window and len(payload["records"]) > self._max_window:
                payload["records"] = payload["records"][-self._max_window:]
            self._persistence.save(session_id, payload)
            return deepcopy(payload)

    def delete(self, session_id: str) -> None:
        """Remove a session from memory and persistence."""
        with self._lock:
            self._state.pop(session_id, None)
            self._persistence.delete(session_id)

    def list_sessions(self) -> list[str]:
        """Return all known session IDs (in-memory + persisted)."""
        with self._lock:
            memory_ids = set(self._state.keys())
        persisted_ids = set(self._persistence.list_ids())
        return sorted(memory_ids | persisted_ids)

    # ------------------------------------------------------------------
    # Task session helpers (main + task architecture)
    # ------------------------------------------------------------------

    def create_task_session(self, main_session_id: str, topic: str) -> str:
        """Create an isolated task session scoped to *main_session_id* / *topic*.

        The task session ID has the form ``task:{main_session_id}:{topic}``.
        It is pre-populated with ``_meta`` pointing back to the main session
        so handlers know the lineage without inspecting IDs.

        Returns the new task session ID.
        """
        task_session_id = f"{_TASK_SESSION_PREFIX}{main_session_id}:{topic}"
        with self._lock:
            if task_session_id not in self._state:
                self._state[task_session_id] = {
                    "records": [],
                    "_meta": {
                        "type": "task_session",
                        "main_session_id": main_session_id,
                        "topic": topic,
                    },
                }
                self._persistence.save(task_session_id, self._state[task_session_id])
                LOGGER.debug(
                    "session_store: created task session %s (main=%s topic=%s)",
                    task_session_id, main_session_id, topic,
                )
        return task_session_id

    def close_task_session(
        self,
        task_session_id: str,
        *,
        summary: str | None = None,
        merge_to_main: bool = True,
    ) -> None:
        """Close a task session, optionally merging a summary into the main session.

        Args:
            task_session_id: The task session to close.
            summary:         Short text summary of the task result to merge back.
            merge_to_main:   When True and *summary* is provided, appends a
                             ``task_summary`` record to the main session.
        """
        if not task_session_id.startswith(_TASK_SESSION_PREFIX):
            LOGGER.warning("close_task_session called on non-task session: %s", task_session_id)
            return

        with self._lock:
            payload = self._state.get(task_session_id, {})
            meta = payload.get("_meta", {})
            main_session_id = meta.get("main_session_id")
            topic = meta.get("topic", "")

        if merge_to_main and summary and main_session_id:
            self.append_records(
                main_session_id,
                [{"role": "system", "type": "task_summary", "topic": topic, "content": summary}],
            )

        self.delete(task_session_id)
        LOGGER.debug("session_store: closed task session %s", task_session_id)

    def list_task_sessions(self, main_session_id: str) -> list[str]:
        """Return all open task session IDs for *main_session_id*."""
        prefix = f"{_TASK_SESSION_PREFIX}{main_session_id}:"
        return [sid for sid in self.list_sessions() if sid.startswith(prefix)]

    def is_task_session(self, session_id: str) -> bool:
        return session_id.startswith(_TASK_SESSION_PREFIX)

    def main_session_id(self, task_session_id: str) -> str | None:
        """Extract the main session ID from a task session ID, or return None."""
        payload = self.get(task_session_id)
        return payload.get("_meta", {}).get("main_session_id")
