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
            "household_budget:expense_record",
            BlueprintSchema(
                blueprint_id="bp_expense_record",
                name="Household Expense Record Blueprint",
                domain="household_budget",
                intent="expense_record",
                inputs=["input_text", "session_state"],
                outputs=["records", "summary"],
                steps=["extract_records", "persist_records"],
            ),
        )
        self.registry.register(
            "household_budget:expense_query",
            BlueprintSchema(
                blueprint_id="bp_expense_query",
                name="Household Expense Query Blueprint",
                domain="household_budget",
                intent="expense_query",
                inputs=["input_text", "session_state"],
                outputs=["aggregation", "summary"],
                steps=["parse_query", "aggregate_query"],
            ),
        )

    def resolve(self, task: TaskSchema, workflow: WorkflowSchema) -> list[BlueprintSchema]:
        key = f"{task.domain}:{task.intent}"
        item = self.registry.get(key)
        if item:
            return [item]
        for name in self.registry.list():
            candidate = self.registry.get(name)
            if isinstance(candidate, BlueprintSchema) and set(candidate.steps).issuperset({s.name for s in workflow.steps}):
                return [candidate]
        return []
