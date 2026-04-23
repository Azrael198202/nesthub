from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from nethub_runtime.core_brain.brain.api.dto.chat_request import ChatRequest
from nethub_runtime.core_brain.brain.artifacts.lifecycle_service import ArtifactLifecycleService
from nethub_runtime.core_brain.brain.chat.chat_service import ChatService
from nethub_runtime.core_brain.brain.chat.response_builder import build_runtime_result
from nethub_runtime.core_brain.brain.context.context_builder import ContextBuilder
from nethub_runtime.core_brain.brain.kb.retrieval.service import RetrievalService
from nethub_runtime.core_brain.brain.memory.repositories.execution_repo import ExecutionRepo
from nethub_runtime.core_brain.brain.memory.services.long_term_memory_service import LongTermMemoryService
from nethub_runtime.core_brain.brain.memory.services.session_memory_service import SessionMemoryService
from nethub_runtime.core_brain.brain.memory.services.task_memory_service import TaskMemoryService
from nethub_runtime.core_brain.brain.orchestration.pipeline import OrchestrationContext
from nethub_runtime.core_brain.brain.planning.intent_service import IntentPlanningService
from nethub_runtime.core_brain.brain.planning.route_service import RoutePlanningService
from nethub_runtime.core_brain.brain.planning.workflow_service import WorkflowPlanningService
from nethub_runtime.core_brain.brain.validation.intent.service import IntentValidationService
from nethub_runtime.core_brain.brain.validation.result.service import ResultValidationService
from nethub_runtime.core_brain.brain.validation.schemas.service import SchemaValidationService
from nethub_runtime.core_brain.brain.workflows.executor.service import WorkflowExecutorService


class OrchestrationService:
    def __init__(
        self,
        *,
        context_builder: ContextBuilder,
        chat_service: ChatService,
        intent_planning: IntentPlanningService,
        route_planning: RoutePlanningService,
        workflow_planning: WorkflowPlanningService,
        workflow_executor: WorkflowExecutorService,
        schema_validation: SchemaValidationService,
        intent_validation: IntentValidationService,
        result_validation: ResultValidationService,
        retrieval_service: RetrievalService,
        artifact_lifecycle: ArtifactLifecycleService,
        session_memory: SessionMemoryService,
        task_memory: TaskMemoryService,
        long_term_memory: LongTermMemoryService,
        execution_repo: ExecutionRepo,
    ) -> None:
        self.context_builder = context_builder
        self.chat_service = chat_service
        self.intent_planning = intent_planning
        self.route_planning = route_planning
        self.workflow_planning = workflow_planning
        self.workflow_executor = workflow_executor
        self.schema_validation = schema_validation
        self.intent_validation = intent_validation
        self.result_validation = result_validation
        self.retrieval_service = retrieval_service
        self.artifact_lifecycle = artifact_lifecycle
        self.session_memory = session_memory
        self.task_memory = task_memory
        self.long_term_memory = long_term_memory
        self.execution_repo = execution_repo

    async def handle(self, req: ChatRequest) -> dict[str, Any]:
        request_id = f"req_{uuid4().hex[:12]}"
        task_id = req.task_id or f"task_{req.session_id}"

        context_bundle = self.context_builder.build(req)
        raw_intent = await self.intent_planning.analyze(req=req, context_bundle=context_bundle)
        intent = self.schema_validation.validate_intent(raw_intent)
        route = self.route_planning.select(intent=intent, allow_external=req.allow_external)
        raw_workflow = self.workflow_planning.plan(
            req=req,
            task_id=task_id,
            intent=intent,
            route=route,
            context_bundle=context_bundle,
        )
        workflow = self.schema_validation.validate_workflow(raw_workflow)

        kb_refs = self.retrieval_service.retrieve(intent_name=str(intent.get("name") or ""), workflow_name=str(workflow.get("name") or ""))
        context_bundle["kb_refs"] = kb_refs
        answer_text = await self.chat_service.generate_answer(req=req, context_bundle=context_bundle, route=route)
        execution = self.workflow_executor.execute(
            workflow=workflow,
            req_payload={"session_id": req.session_id, "message": req.message},
            route=route,
            answer_text=answer_text,
            intent=intent,
        )

        intent_validation = self.intent_validation.validate(intent=intent, answer_text=answer_text)
        final_validation = self.result_validation.summarize(
            step_validations=execution.get("step_validations") or [],
            intent_validation=intent_validation,
            trace_summary=execution.get("trace_summary") or {},
        )

        self.session_memory.write_turn(req.session_id, req.message, answer_text)
        self.task_memory.write(task_id, {"intent": intent, "last_message": req.message, "last_answer": answer_text})
        long_term_memory_written = bool(intent.get("confidence", 0.0) >= 0.85)
        if long_term_memory_written:
            self.long_term_memory.write_fact(req.message)

        manifest = self.artifact_lifecycle.create_draft(
            {
                "id": f"artifact_{request_id}",
                "type": "execution_trace",
                "source_intent": str(intent.get("intent_id") or ""),
                "source_task": task_id,
                "version": "1.0.0",
                "status": "draft",
                "runnable": False,
                "registered_at": datetime.now(UTC).isoformat(),
                "workflow_id": workflow.get("workflow_id"),
                "session_id": req.session_id,
                "trace_id": ((execution.get("traces") or [{}])[-1]).get("trace_id"),
            }
        )
        if final_validation.get("ok"):
            manifest = self.artifact_lifecycle.register(manifest)
            manifest = self.artifact_lifecycle.activate(manifest)
        else:
            manifest = self.artifact_lifecycle.fail(manifest, "final validation failed")

        result = build_runtime_result(
            request_id=request_id,
            session_id=req.session_id,
            task_id=task_id,
            intent=intent,
            route=route,
            workflow_plan=workflow,
            answer_text=answer_text,
            long_term_memory_written=long_term_memory_written,
            traces=list(execution.get("traces") or []),
        )
        result["execution_result"]["validation"] = final_validation
        result["artifacts"] = [{"manifest": manifest}]

        self.execution_repo.append(
            {
                "request_id": request_id,
                "session_id": req.session_id,
                "task_id": task_id,
                "intent": intent,
                "route": route,
                "workflow_plan": workflow,
                "traces": execution.get("traces") or [],
                "validation": final_validation,
            }
        )
        return result
