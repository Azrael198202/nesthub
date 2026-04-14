from fastapi import FastAPI
from api.public_api.storage.memory_store import MemoryStore
from api.public_api.services.bridge_service import BridgeService
from api.public_api.routes import bridge_im, bridge_hub, bridge_messages, health

app = FastAPI()

# In-memory store and service
store = MemoryStore()
bridge_service = BridgeService(store)
app.state.bridge_service = bridge_service

# Mount routes
app.include_router(bridge_im.router, prefix="/api/bridge")
app.include_router(bridge_hub.router, prefix="/api/bridge")
app.include_router(bridge_messages.router, prefix="/api/bridge")
app.include_router(health.router, prefix="/api")
