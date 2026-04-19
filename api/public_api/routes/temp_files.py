from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse


router = APIRouter()


@router.get("/temp-files/{file_id}/{file_name}")
async def download_temp_file(request: Request, file_id: str, file_name: str):
    record = request.app.state.temp_file_store.get(file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Temporary file not found or expired")
    if record.file_name != file_name:
        raise HTTPException(status_code=404, detail="Temporary file name does not match")
    return FileResponse(path=record.stored_path, filename=record.file_name, media_type=record.content_type)


def _received_base() -> Path:
    configured = os.getenv("NESTHUB_PUBLIC_API_RECEIVED_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "received"


@router.get("/received/{date_prefix}/{file_name}")
async def download_received_file(date_prefix: str, file_name: str):
    """Serve files saved from LINE uploads (persistent, not TTL-limited)."""
    # Sanitise path components — reject anything that looks like traversal
    if ".." in date_prefix or "/" in date_prefix or ".." in file_name or "/" in file_name:
        raise HTTPException(status_code=400, detail="Invalid path")
    file_path = _received_base() / date_prefix / file_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Received file not found")
    return FileResponse(path=file_path, filename=file_name)