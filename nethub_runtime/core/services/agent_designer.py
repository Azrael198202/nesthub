from __future__ import annotations

from nethub_runtime.core.schemas.agent_schema import AgentSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema
from nethub_runtime.core.utils.id_generator import generate_id


class AgentDesigner:
    """Generates agent definitions when long-term capability is requested."""

    def should_generate(self, task: TaskSchema) -> bool:
        keywords = ("智能体", "agent", "长期", "复用")
        text = task.input_text.lower()
        return any(keyword in text for keyword in keywords)

    def generate(self, task: TaskSchema, workflow: WorkflowSchema) -> AgentSchema:
        return AgentSchema(
            agent_id=generate_id("agent"),
            name=f"{task.domain}_{task.intent}_agent",
            role="execution_specialist",
            goals=[f"Handle {task.intent} requests reliably."],
            responsibilities=[step.name for step in workflow.steps],
            capabilities=["intent_analysis", "workflow_execution", "result_integration"],
            model_strategy={"primary": "rule-based", "fallback": "llm-router"},
            tool_strategy={"allowed": ["parser", "query_engine"]},
            metadata={"generated_from_task_id": task.task_id},
        )
