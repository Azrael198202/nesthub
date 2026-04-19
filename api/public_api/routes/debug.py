"""Debug endpoints for diagnosing LINE file receive / pipeline events.

Exposed under /api/debug/ — intended for test/diagnostic use only.

Endpoints:
  GET /api/debug/file-events          → JSON list of recent events
  GET /api/debug/file-events/text     → plain text log (downloadable)
  DELETE /api/debug/file-events       → clear the log
"""

from __future__ import annotations

import os
from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()

# Guard: disable in production unless explicitly opted in
_DEBUG_ENABLED = os.getenv("NESTHUB_DEBUG_ENDPOINTS", "false").lower() in ("1", "true", "yes")


def _log(request: Request) -> list[dict[str, Any]]:
    """Return the shared file-event log from app.state (created lazily)."""
    if not hasattr(request.app.state, "file_event_log"):
        request.app.state.file_event_log = []
    return request.app.state.file_event_log


def append_event(request: Request, event: dict[str, Any]) -> None:
    """Called by other routes/services to record a file pipeline event."""
    log = _log(request)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        **event,
    }
    log.append(entry)
    # Keep at most 500 entries to avoid unbounded memory growth
    if len(log) > 500:
        del log[:-500]


@router.get("/file-events")
async def get_file_events(request: Request, limit: int = 100):
    """Return the most recent file pipeline events as JSON."""
    if not _DEBUG_ENABLED:
        return {"enabled": False, "hint": "Set NESTHUB_DEBUG_ENDPOINTS=true to enable"}
    events = _log(request)
    return {
        "total": len(events),
        "events": events[-limit:],
    }


@router.get("/file-events/text", response_class=PlainTextResponse)
async def get_file_events_text(request: Request, limit: int = 200):
    """Return the most recent file pipeline events as a plain text log.

    Useful for NestHub to download and inspect pipeline state.
    """
    if not _DEBUG_ENABLED:
        return "debug endpoints disabled — set NESTHUB_DEBUG_ENDPOINTS=true"
    events = _log(request)
    lines: list[str] = [
        f"=== public_api file-event log ({len(events)} entries) ===",
        f"generated: {datetime.now(UTC).isoformat()}",
        "",
    ]
    for ev in events[-limit:]:
        ts = ev.get("ts", "")
        action = ev.get("action", "")
        status = ev.get("status", "")
        detail = "  ".join(
            f"{k}={v}"
            for k, v in ev.items()
            if k not in ("ts", "action", "status")
        )
        lines.append(f"[{ts}] {action:<30} status={status:<20} {detail}")
    return "\n".join(lines)


@router.delete("/file-events")
async def clear_file_events(request: Request):
    """Clear the in-memory event log."""
    if not _DEBUG_ENABLED:
        return {"enabled": False}
    _log(request).clear()
    return {"cleared": True}
