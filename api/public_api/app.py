import asyncio
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI
from api.public_api.storage.memory_store import MemoryStore
from api.public_api.storage.temp_file_store import TempFileStore
from api.public_api.services.bridge_service import BridgeService
from api.public_api.routes import bridge_im, bridge_hub, bridge_messages, health, temp_files, debug

logger = logging.getLogger("public_api.app")

app = FastAPI()

# In-memory store and service
store = MemoryStore()
temp_file_store = TempFileStore()
bridge_service = BridgeService(store, temp_file_store)
app.state.bridge_service = bridge_service
app.state.temp_file_store = temp_file_store
app.state.temp_file_cleanup_task = None
app.state.received_cleanup_task = None

# Mount routes
app.include_router(bridge_im.router, prefix="/api/bridge")
app.include_router(bridge_hub.router, prefix="/api/bridge")
app.include_router(bridge_messages.router, prefix="/api/bridge")
app.include_router(health.router, prefix="/api")
app.include_router(temp_files.router, prefix="/api")
app.include_router(debug.router, prefix="/api/debug")


def _received_base() -> Path:
    configured = os.getenv("NESTHUB_PUBLIC_API_RECEIVED_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / "received"


async def _temp_file_cleanup_loop() -> None:
    while True:
        temp_file_store.cleanup_expired()
        await asyncio.sleep(300)


_RECEIVED_TTL_SECONDS = 10 * 60  # keep received/ files for 10 minutes


async def _received_cleanup_loop() -> None:
    """Delete files in received/ that are older than _RECEIVED_TTL_SECONDS."""
    while True:
        await asyncio.sleep(60)  # check every minute
        base = _received_base()
        if not base.exists():
            continue
        cutoff = time.time() - _RECEIVED_TTL_SECONDS
        removed = 0
        try:
            for file_path in base.rglob("*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff:
                    try:
                        file_path.unlink()
                        removed += 1
                    except OSError:
                        pass
            # Remove empty date subdirectories
            for date_dir in base.iterdir():
                if date_dir.is_dir() and not any(date_dir.iterdir()):
                    try:
                        date_dir.rmdir()
                    except OSError:
                        pass
        except Exception as exc:
            logger.warning("received cleanup error: %s", exc)
        if removed:
            logger.info("received cleanup: removed %d expired file(s)", removed)


@app.on_event("startup")
async def startup_temp_file_cleanup() -> None:
    if app.state.temp_file_cleanup_task is None:
        app.state.temp_file_cleanup_task = asyncio.create_task(_temp_file_cleanup_loop())
    if app.state.received_cleanup_task is None:
        app.state.received_cleanup_task = asyncio.create_task(_received_cleanup_loop())


@app.on_event("shutdown")
async def shutdown_temp_file_cleanup() -> None:
    for attr in ("temp_file_cleanup_task", "received_cleanup_task"):
        task = getattr(app.state, attr, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            setattr(app.state, attr, None)
