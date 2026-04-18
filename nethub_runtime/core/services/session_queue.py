"""
Session Queue — per-session concurrency control with three queue modes.

Inspired by OpenClaw's Command Queue system:
  collect  — hold all inbound messages until the current run finishes,
              then start a new turn with all queued payloads.
  steer    — inject queued messages into the *current* run at the next
              model boundary (best-effort; falls back to followup).
  followup — hold messages; after the run ends start a fresh follow-up
              turn for each queued item in order.

For nesthub each ``handle()`` / ``handle_stream()`` call acquires a
per-session slot via ``SessionQueueManager.run_slot()``.  Concurrent
callers for the same session_id wait their turn and are queued according
to the configured mode.

Usage::

    mgr = SessionQueueManager.from_policy(policy_dict)

    async with mgr.run_slot(session_id) as slot:
        # slot.queued_inputs contains any messages that arrived while
        # waiting (relevant for collect / followup modes).
        result = await core.handle(slot.input_text, context)

Configuration (from ``runtime_behavior.session.queue``)::

    {
      "mode": "collect",     # collect | steer | followup
      "debounce_ms": 300,    # ms to wait for more messages before dispatching
      "max_queued": 10       # hard cap on queued items (excess dropped)
    }
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

LOGGER = logging.getLogger("nethub_runtime.core.session_queue")

_VALID_MODES = {"collect", "steer", "followup"}


@dataclass
class RunSlot:
    """Context passed to callers inside ``run_slot()``."""

    session_id: str
    input_text: str
    mode: str
    # Messages that were queued while this slot was waiting to acquire the
    # session lane.  In collect/followup modes callers may choose to
    # process these after the primary run.
    queued_inputs: list[str] = field(default_factory=list)


class _SessionLane:
    """Serialises runs for one session.  Thread-safe via asyncio.Lock."""

    def __init__(self, session_id: str, mode: str, max_queued: int) -> None:
        self.session_id = session_id
        self.mode = mode
        self.max_queued = max_queued
        self._lock = asyncio.Lock()
        self._pending: list[str] = []

    @asynccontextmanager
    async def acquire(self, input_text: str) -> AsyncGenerator[RunSlot, None]:
        """Acquire the lane for *input_text*.

        Concurrent callers wait here.  While waiting their ``input_text``
        is added to ``_pending``.  The caller that eventually acquires
        the lock drains the queue into ``slot.queued_inputs``.
        """
        if self._lock.locked():
            if len(self._pending) < self.max_queued:
                self._pending.append(input_text)
                LOGGER.debug(
                    "Session %s queued input (mode=%s pending=%d)",
                    self.session_id, self.mode, len(self._pending),
                )
            else:
                LOGGER.warning(
                    "Session %s queue full (max=%d); dropping input",
                    self.session_id, self.max_queued,
                )

        async with self._lock:
            # Drain any inputs queued while we were waiting.
            queued = list(self._pending)
            self._pending.clear()
            slot = RunSlot(
                session_id=self.session_id,
                input_text=input_text,
                mode=self.mode,
                queued_inputs=queued,
            )
            try:
                yield slot
            finally:
                pass  # lock released automatically


class SessionQueueManager:
    """Manages per-session lanes across all active sessions.

    Args:
        mode:        Default queue mode for all sessions.
        debounce_ms: Not enforced at queue layer (handled by channel layer);
                     stored for observability.
        max_queued:  Hard cap on pending messages per session.
    """

    def __init__(
        self,
        mode: str = "collect",
        debounce_ms: int = 300,
        max_queued: int = 10,
    ) -> None:
        if mode not in _VALID_MODES:
            LOGGER.warning("Unknown queue mode %r — falling back to 'collect'", mode)
            mode = "collect"
        self.mode = mode
        self.debounce_ms = debounce_ms
        self.max_queued = max_queued
        self._lanes: dict[str, _SessionLane] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_policy(cls, policy: dict[str, Any] | None = None) -> "SessionQueueManager":
        """Build from a ``runtime_behavior.session.queue`` policy dict."""
        cfg = policy or {}
        return cls(
            mode=str(cfg.get("mode", "collect")),
            debounce_ms=int(cfg.get("debounce_ms", 300)),
            max_queued=int(cfg.get("max_queued", 10)),
        )

    @asynccontextmanager
    async def run_slot(
        self,
        session_id: str,
        input_text: str = "",
    ) -> AsyncGenerator[RunSlot, None]:
        """Acquire a run slot for *session_id*.

        Serialises concurrent calls within the same session.  Yields a
        :class:`RunSlot` with any messages that accumulated while waiting.
        """
        lane = await self._get_lane(session_id)
        async with lane.acquire(input_text) as slot:
            yield slot

    async def _get_lane(self, session_id: str) -> _SessionLane:
        async with self._lock:
            if session_id not in self._lanes:
                self._lanes[session_id] = _SessionLane(
                    session_id=session_id,
                    mode=self.mode,
                    max_queued=self.max_queued,
                )
            return self._lanes[session_id]

    def status(self) -> dict[str, Any]:
        """Return a snapshot of all active lanes."""
        return {
            sid: {
                "mode": lane.mode,
                "pending": len(lane._pending),
                "locked": lane._lock.locked(),
            }
            for sid, lane in self._lanes.items()
        }
