from __future__ import annotations

import logging
from copy import deepcopy
from threading import Lock
from typing import Any, Callable


LOGGER = logging.getLogger("nethub_runtime.core.session")


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
    """Thread-safe in-memory session state store with optional compaction."""

    def __init__(self, compactor: SessionCompactor | None = None) -> None:
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._compactor = compactor

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
            if self._compactor is not None:
                payload["records"] = self._compactor.maybe_compact(payload["records"])
            return deepcopy(payload)
