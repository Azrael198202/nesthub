from __future__ import annotations

from nethub_runtime.core.schemas.agent_framework_schema import WorkflowCompositionSchema, WorkflowComponentSchema
from nethub_runtime.core.enums import WorkflowComponentType
from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema


class WorkflowCompositionService:
    def build_composition(self, task: TaskSchema, subtasks: list[SubTask]) -> WorkflowCompositionSchema:
        components: list[WorkflowComponentSchema] = []
        knowledge_agents: list[str] = []
        execution_agents: list[str] = []
        analysis_agents: list[str] = []
        tools: list[str] = []
        analyzers: list[str] = []
        io_operations: list[str] = []

        if task.domain in {"agent_management", "knowledge_ops"}:
            knowledge_agents.append("information_agent")
            components.append(
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.AGENT,
                    name="knowledge_agent",
                    responsibility="Provide structured knowledge and state for downstream workflow steps.",
                )
            )

        if task.constraints.get("need_agent") or task.domain in {"general", "multimodal_ops"}:
            execution_agents.append("execution_agent")
            components.append(
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.AGENT,
                    name="execution_agent",
                    responsibility="Execute user-directed actions and coordinate operational steps.",
                    dependencies=["knowledge_agent"] if knowledge_agents else [],
                )
            )

        if any(req in {"insight", "summary", "analysis"} for req in task.output_requirements):
            analysis_agents.append("analysis_agent")
            analyzers.append("content_analyzer")
            components.append(
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.ANALYZER,
                    name="analysis_module",
                    responsibility="Analyze and summarize intermediate workflow content.",
                    dependencies=["knowledge_agent"] if knowledge_agents else [],
                )
            )

        if any(req in {"artifact", "document", "file"} for req in task.output_requirements):
            tools.append("file_builder")
            components.append(
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.TOOL,
                    name="document_tool",
                    responsibility="Generate a document or structured artifact from workflow outputs.",
                    dependencies=[item.name for item in components if item.component_type in {WorkflowComponentType.AGENT, WorkflowComponentType.ANALYZER}],
                )
            )
            io_operations.append("file_write")
            components.append(
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.IO,
                    name="io_operation",
                    responsibility="Persist or deliver generated workflow outputs.",
                    dependencies=["document_tool"],
                )
            )

        components.append(
            WorkflowComponentSchema(
                component_type=WorkflowComponentType.WORKFLOW,
                name="workflow_orchestrator",
                responsibility="Coordinate knowledge, execution, analysis, tools, and IO operations.",
                dependencies=[item.name for item in components],
            )
        )

        return WorkflowCompositionSchema(
            workflow_name=f"{task.intent}_workflow",
            objective=task.input_text,
            knowledge_agents=knowledge_agents,
            execution_agents=execution_agents,
            analysis_agents=analysis_agents,
            tools=tools,
            analyzers=analyzers,
            io_operations=io_operations,
            components=components,
            metadata={
                "task_intent": task.intent,
                "task_domain": task.domain,
                "subtask_names": [item.name for item in subtasks],
                "system_owner": "nesthub_runtime",
                "agent_creation_managed_by": "nesthub_runtime",
                "workflow_execution_managed_by": "nesthub_runtime",
                "runtime_issue_resolution_managed_by": "nesthub_runtime",
            },
        )
