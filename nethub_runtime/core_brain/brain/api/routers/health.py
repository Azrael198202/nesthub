from __future__ import annotations

from fastapi import APIRouter

from nethub_runtime.core_brain.api.health import core_brain_health as core_brain_health_endpoint

router = APIRouter()
router.add_api_route("/core-brain/health", core_brain_health_endpoint, methods=["GET"])
