from __future__ import annotations

from typing import Any
from uuid import uuid4

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.chat.chat_service import ChatService
from nethub_runtime.core_brain.brain.chat.response_builder import build_runtime_result
from nethub_runtime.core_brain.brain.context.context_builder import ContextBuilder
from nethub_runtime.core_brain.brain.memory.repositories.execution_repo import ExecutionRepo
from nethub_runtime.core_brain.brain.memory.services.long_term_memory_service import LongTermMemoryService
from nethub_runtime.core_brain.brain.memory.services.session_memory_service import SessionMemoryService
from nethub_runtime.core_brain.brain.memory.services.task_memory_service import TaskMemoryService
from nethub_runtime.core_brain.brain.routing.router_service import RouterService
from nethub_runtime.core_brain.brain.workflows.graph.chat_graph import ChatGraphRunner


class BrainFacade:
    def __init__(
        self,
        *,
        context_builder: ContextBuilder,
        chat_service: ChatService,
        router_service: RouterService,
        session_memory: SessionMemoryService,
        task_memory: TaskMemoryService,
        long_term_memory: LongTermMemoryService,
        execution_repo: ExecutionRepo,
        workflow_runner: ChatGraphRunner,
    ) -> None:
        self.context_builder = context_builder
        self.chat_service = chat_service
        self.router_service = router_service
        self.session_memory = session_memory
        self.task_memory = task_memory
        self.long_term_memory = long_term_memory
        self.execution_repo = execution_repo
        self.workflow_runner = workflow_runner

    async def handle_chat(self, req: ChatRequest) -> dict[str, Any]:
        request_id = f"req_{uuid4().hex[:12]}"
        task_id = req.task_id or f"task_{req.session_id}"

        state: dict[str, Any] = {
            "req": req,
            "request_id": request_id,
            "task_id": task_id,
            "context_bundle": {},
            "intent": {},
            "route": {},
            "answer": "",
        }

        def _pipeline(work_state: dict[str, Any]) -> dict[str, Any]:
            return work_state

        # Keep deterministic step order and let ChatGraphRunner own execution boundary.
        state = await self.workflow_runner.run(state=state, pipeline=_pipeline)

        context_bundle = self.context_builder.build(req)
        intent = await self.chat_service.analyze_intent(req, context_bundle)
        route = self.router_service.select_route(intent=intent, allow_external=req.allow_external)
        answer = await self.chat_service.generate_answer(req=req, context_bundle=context_bundle, route=route)

        self.session_memory.write_turn(req.session_id, req.message, answer)
        self.task_memory.write(task_id, {"intent": intent, "last_message": req.message, "last_answer": answer})
        if intent.get("confidence", 0.0) >= 0.85:
            self.long_term_memory.write_fact(req.message)

        result = build_runtime_result(
            request_id=request_id,
            session_id=req.session_id,
            task_id=task_id,
            intent=intent,
            route=route,
            answer_text=answer,
        )
        self.execution_repo.append({"request_id": request_id, "session_id": req.session_id, "task_id": task_id, "intent": intent, "route": route})
        return result
