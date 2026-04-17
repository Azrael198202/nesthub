import asyncio

from fastapi import FastAPI
from api.public_api.storage.memory_store import MemoryStore
from api.public_api.storage.temp_file_store import TempFileStore
from api.public_api.services.bridge_service import BridgeService
from api.public_api.routes import bridge_im, bridge_hub, bridge_messages, health, temp_files

app = FastAPI()

# In-memory store and service
store = MemoryStore()
temp_file_store = TempFileStore()
bridge_service = BridgeService(store, temp_file_store)
app.state.bridge_service = bridge_service
app.state.temp_file_store = temp_file_store
app.state.temp_file_cleanup_task = None

# Mount routes
app.include_router(bridge_im.router, prefix="/api/bridge")
app.include_router(bridge_hub.router, prefix="/api/bridge")
app.include_router(bridge_messages.router, prefix="/api/bridge")
app.include_router(health.router, prefix="/api")
app.include_router(temp_files.router, prefix="/api")


async def _temp_file_cleanup_loop() -> None:
	while True:
		temp_file_store.cleanup_expired()
		await asyncio.sleep(300)


@app.on_event("startup")
async def startup_temp_file_cleanup() -> None:
	if app.state.temp_file_cleanup_task is None:
		app.state.temp_file_cleanup_task = asyncio.create_task(_temp_file_cleanup_loop())


@app.on_event("shutdown")
async def shutdown_temp_file_cleanup() -> None:
	task = app.state.temp_file_cleanup_task
	if task is not None:
		task.cancel()
		try:
			await task
		except asyncio.CancelledError:
			pass
		app.state.temp_file_cleanup_task = None
