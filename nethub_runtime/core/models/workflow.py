from __future__ import annotations

from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema

WorkflowStep = WorkflowStepSchema
WorkflowSpec = WorkflowSchema

__all__ = ["WorkflowStep", "WorkflowSpec"]
