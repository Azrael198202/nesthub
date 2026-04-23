from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest


@dataclass(slots=True)
class OrchestrationContext:
    request_id: str
    task_id: str
    req: ChatRequest
    context_bundle: dict[str, Any]
    intent: dict[str, Any]
    route: dict[str, Any]
    workflow: dict[str, Any]
    answer_text: str
    execution: dict[str, Any]
