from __future__ import annotations

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