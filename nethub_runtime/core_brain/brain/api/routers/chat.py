from __future__ import annotations

from fastapi import APIRouter

from nethub_runtime.core_brain.api.chat import chat as chat_endpoint
from nethub_runtime.core_brain.api.chat import compat_core_chat as compat_core_chat_endpoint
from nethub_runtime.core_brain.api.chat import core_brain_chat as core_brain_chat_endpoint

router = APIRouter()
router.add_api_route("/core-brain/chat", core_brain_chat_endpoint, methods=["POST"])
router.add_api_route("/core/chat", compat_core_chat_endpoint, methods=["POST"])
router.add_api_route("/chat", chat_endpoint, methods=["POST"])
