"""External log monitor — fetches public_api debug events after each bridge interaction.

After nethub_runtime processes a LINE/bridge message it calls
``fetch_and_save()``.  The function:

1. Reads ``NETHUB_LLM_ROUTER_ENDPOINT`` from the environment (same value used
   for bridge polling — no extra config required).
2. GETs ``{endpoint}/api/debug/file-events`` (JSON) **and**
   ``{endpoint}/api/debug/file-events/text`` (plain text).
3. Writes both files under ``nethub_runtime/external_logs/``:
   - ``file_events_<YYYYMMDD_HHMMSS>.json``   ← full JSON snapshot
   - ``file_events_latest.json``               ← always overwritten (easy to read)
   - ``file_events_latest.txt``                ← plain-text version

The directory is ``<workspace_root>/external_logs/`` where workspace_root is
resolved from ``NESTHUB_WORKSPACE_PATH`` env or the package root.

Failures are silently logged (never raise) so the bridge loop is not blocked.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

logger = logging.getLogger("nethub_runtime.integrations.external_log_monitor")


def _external_logs_dir() -> Path:
    workspace = os.getenv("NESTHUB_WORKSPACE_PATH", "").strip()
    base = Path(workspace) if workspace else Path(__file__).resolve().parents[2]
    logs_dir = base / "external_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def _router_endpoint() -> str:
    return os.getenv("NETHUB_LLM_ROUTER_ENDPOINT", "").strip().rstrip("/")


async def fetch_and_save(label: str = "") -> None:
    """Fetch public_api debug file-events and write to external_logs/.

    ``label`` is an optional tag added to the JSON snapshot (e.g. bridge_message_id).
    No-op when NETHUB_LLM_ROUTER_ENDPOINT is not set.
    """
    endpoint = _router_endpoint()
    if not endpoint:
        logger.debug("NETHUB_LLM_ROUTER_ENDPOINT not set — skipping external log fetch")
        return

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            json_resp = await client.get(f"{endpoint}/api/debug/file-events")
            text_resp = await client.get(f"{endpoint}/api/debug/file-events/text")
    except Exception as exc:
        logger.warning("external_log_monitor: fetch failed (%s): %s", endpoint, exc)
        return

    logs_dir = _external_logs_dir()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # ── JSON snapshot (timestamped + latest) ──────────────────────────────
    try:
        data: dict[str, Any] = json_resp.json() if json_resp.status_code == 200 else {
            "error": f"HTTP {json_resp.status_code}",
            "body": json_resp.text[:500],
        }
        data["_fetched_at"] = datetime.now(UTC).isoformat()
        data["_label"] = label
        data["_source"] = endpoint

        snapshot_path = logs_dir / f"file_events_{ts}.json"
        snapshot_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        latest_json = logs_dir / "file_events_latest.json"
        latest_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(
            "external_log_monitor: saved %d events → %s",
            len(data.get("events") or []),
            snapshot_path,
        )
    except Exception as exc:
        logger.warning("external_log_monitor: JSON write failed: %s", exc)

    # ── Plain-text (latest only) ───────────────────────────────────────────
    try:
        text_body = text_resp.text if text_resp.status_code == 200 else (
            f"HTTP {text_resp.status_code}\n{text_resp.text[:500]}"
        )
        latest_txt = logs_dir / "file_events_latest.txt"
        latest_txt.write_text(text_body, encoding="utf-8")
    except Exception as exc:
        logger.warning("external_log_monitor: text write failed: %s", exc)
