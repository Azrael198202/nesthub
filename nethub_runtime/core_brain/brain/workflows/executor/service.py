from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.brain.execution.step_executor import StepExecutor
from nethub_runtime.core_brain.brain.trace.evaluator.service import TraceEvaluatorService
from nethub_runtime.core_brain.brain.trace.recorder.service import TraceRecorderService
from nethub_runtime.core_brain.brain.validation.step.service import StepValidationService


class WorkflowExecutorService:
    def __init__(
        self,
        *,
        step_executor: StepExecutor,
        trace_recorder: TraceRecorderService,
        trace_evaluator: TraceEvaluatorService,
        step_validator: StepValidationService,
    ) -> None:
        self.step_executor = step_executor
        self.trace_recorder = trace_recorder
        self.trace_evaluator = trace_evaluator
        self.step_validator = step_validator

    def execute(
        self,
        *,
        workflow: dict[str, Any],
        req_payload: dict[str, Any],
        route: dict[str, Any],
        answer_text: str,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        traces: list[dict[str, Any]] = []
        step_validations: list[dict[str, Any]] = []
        workflow_id = str(workflow.get("workflow_id") or "")
        for step in list(workflow.get("steps") or []):
            step_exec = self.step_executor.run_step(
                step=step,
                req=req_payload,
                workflow_id=workflow_id,
                route=route,
                answer_text=answer_text,
                intent=intent,
            )
            step_validation = self.step_validator.validate(step_exec)
            step_validations.append(step_validation)
            traces.append(
                self.trace_recorder.record(
                    workflow_id=workflow_id,
                    intent_id=str(intent.get("intent_id") or ""),
                    step_execution=step_exec,
                    intent_alignment=step_validation.get("intent_alignment"),
                )
            )
        trace_summary = self.trace_evaluator.evaluate(traces)
        return {
            "traces": traces,
            "step_validations": step_validations,
            "trace_summary": trace_summary,
        }
