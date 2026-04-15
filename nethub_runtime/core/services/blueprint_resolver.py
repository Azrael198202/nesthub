from __future__ import annotations

from nethub_runtime.core.schemas.blueprint_schema import BlueprintSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema
from nethub_runtime.core.services.registry import Registry


class BlueprintResolver:
    """Resolves reusable blueprints from in-memory registry."""

    def __init__(self, registry: Registry | None = None) -> None:
        self.registry = registry or Registry()
        self._register_builtin_blueprints()

    def _register_builtin_blueprints(self) -> None:
        self.registry.register(
            "data_ops:data_record",
            BlueprintSchema(
                blueprint_id="bp_data_record",
                name="Generic Data Record Blueprint",
                domain="data_ops",
                intent="data_record",
                inputs=["input_text", "session_state"],
                outputs=["records", "summary"],
                steps=["extract_records", "persist_records"],
            ),
        )
        self.registry.register(
            "data_ops:data_query",
            BlueprintSchema(
                blueprint_id="bp_data_query",
                name="Generic Data Query Blueprint",
                domain="data_ops",
                intent="data_query",
                inputs=["input_text", "session_state"],
                outputs=["aggregation", "summary"],
                steps=["parse_query", "aggregate_query"],
            ),
        )

    def resolve(self, task: TaskSchema, workflow: WorkflowSchema) -> list[BlueprintSchema]:
        key = f"{task.domain}:{task.intent}"
        item = self.registry.get(key)
        if item:
            if isinstance(item, dict):
                return [BlueprintSchema(**item)]
            return [item]
        for name in self.registry.list():
            candidate = self.registry.get(name)
            if isinstance(candidate, dict):
                candidate = BlueprintSchema(**candidate)
            if isinstance(candidate, BlueprintSchema) and set(candidate.steps).issuperset({s.name for s in workflow.steps}):
                return [candidate]
        return []
