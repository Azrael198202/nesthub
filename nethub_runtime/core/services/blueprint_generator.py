from __future__ import annotations

from nethub_runtime.core.schemas.blueprint_schema import BlueprintSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema
from nethub_runtime.core.services.registry import Registry
from nethub_runtime.core.utils.id_generator import generate_id


class BlueprintGenerator:
    """Generates blueprints dynamically and registers them for reuse."""

    def __init__(self, registry: Registry | None = None) -> None:
        self.registry = registry or Registry()

    def generate(self, task: TaskSchema, workflow: WorkflowSchema) -> BlueprintSchema:
        blueprint = BlueprintSchema(
            blueprint_id=generate_id("blueprint"),
            name=f"{task.domain}:{task.intent}:generated",
            domain=task.domain,
            intent=task.intent,
            inputs=["input_text", "context"],
            outputs=task.output_requirements,
            steps=[step.name for step in workflow.steps],
            metadata={"generated": True},
        )
        self.registry.register(f"{task.domain}:{task.intent}", blueprint)
        return blueprint
