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
        self.registry.register(
            "agent_management:create_information_agent",
            BlueprintSchema(
                blueprint_id="bp_information_agent_create",
                name="Information Agent Creation Blueprint",
                domain="agent_management",
                intent="create_information_agent",
                inputs=["input_text", "session_state"],
                outputs=["agent", "dialog"],
                steps=["manage_information_agent"],
            ),
        )
        self.registry.register(
            "agent_management:refine_information_agent",
            BlueprintSchema(
                blueprint_id="bp_information_agent_refine",
                name="Information Agent Setup Blueprint",
                domain="agent_management",
                intent="refine_information_agent",
                inputs=["input_text", "session_state"],
                outputs=["agent", "dialog"],
                steps=["manage_information_agent"],
            ),
        )
        self.registry.register(
            "agent_management:finalize_information_agent",
            BlueprintSchema(
                blueprint_id="bp_information_agent_finalize",
                name="Information Agent Finalization Blueprint",
                domain="agent_management",
                intent="finalize_information_agent",
                inputs=["input_text", "session_state"],
                outputs=["agent", "dialog"],
                steps=["manage_information_agent"],
            ),
        )
        self.registry.register(
            "agent_management:capture_agent_knowledge",
            BlueprintSchema(
                blueprint_id="bp_information_agent_capture_knowledge",
                name="Information Agent Knowledge Capture Blueprint",
                domain="agent_management",
                intent="capture_agent_knowledge",
                inputs=["input_text", "session_state"],
                outputs=["knowledge", "dialog"],
                steps=["manage_information_agent"],
            ),
        )
        self.registry.register(
            "knowledge_ops:query_agent_knowledge",
            BlueprintSchema(
                blueprint_id="bp_information_agent_query_knowledge",
                name="Information Agent Knowledge Query Blueprint",
                domain="knowledge_ops",
                intent="query_agent_knowledge",
                inputs=["input_text", "session_state"],
                outputs=["answer", "knowledge_hits"],
                steps=["query_information_knowledge"],
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
