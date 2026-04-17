from __future__ import annotations

from nethub_runtime.core.schemas.blueprint_schema import BlueprintSchema
from nethub_runtime.core.services.runtime_design_synthesizer import RuntimeDesignSynthesizer
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema
from nethub_runtime.core.services.registry import Registry
from nethub_runtime.core.utils.id_generator import generate_id


class BlueprintGenerator:
    """Generates blueprints dynamically and registers them for reuse."""

    def __init__(self, registry: Registry | None = None, synthesizer: RuntimeDesignSynthesizer | None = None) -> None:
        self.registry = registry or Registry()
        self.synthesizer = synthesizer or RuntimeDesignSynthesizer()

    def generate(self, task: TaskSchema, workflow: WorkflowSchema) -> BlueprintSchema:
        synthesis = self.synthesizer.synthesize_blueprint(task=task.model_dump(), workflow=workflow.model_dump())
        blueprint = BlueprintSchema(
            blueprint_id=generate_id("blueprint"),
            name=f"{task.domain}:{task.intent}:generated",
            domain=task.domain,
            intent=task.intent,
            inputs=["input_text", "context"],
            outputs=task.output_requirements,
            steps=[step.name for step in workflow.steps],
            metadata={"generated": True, "synthesis": synthesis, "synthesis_source": "nethub_runtime"},
        )
        self.registry.register(blueprint.name, blueprint)
        return blueprint
