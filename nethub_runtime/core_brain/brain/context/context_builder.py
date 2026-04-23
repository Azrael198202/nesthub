from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.memory.services.long_term_memory_service import LongTermMemoryService
from nethub_runtime.core_brain.brain.memory.services.session_memory_service import SessionMemoryService
from nethub_runtime.core_brain.brain.memory.services.task_memory_service import TaskMemoryService


class ContextBuilder:
    def __init__(
        self,
        *,
        system_context: dict[str, Any],
        session_memory: SessionMemoryService,
        task_memory: TaskMemoryService,
        long_term_memory: LongTermMemoryService,
    ) -> None:
        self.system_context = system_context
        self.session_memory = session_memory
        self.task_memory = task_memory
        self.long_term_memory = long_term_memory

    def build(self, req: ChatRequest) -> dict[str, Any]:
        task_id = req.task_id or f"task_{req.session_id}"
        return {
            "system_context": self.system_context,
            "session_context": self.session_memory.load(req.session_id),
            "task_context": self.task_memory.load(task_id),
            "long_term_context": self.long_term_memory.retrieve(req.message, top_k=3),
            "execution_context": {
                "client": req.client.model_dump(),
                "mode": req.mode,
                "context_policy": req.context_policy,
            },
        }
