from __future__ import annotations

from nethub_runtime.core.enums import AgentClass, AgentLayer, WorkflowComponentType
from nethub_runtime.core.schemas.agent_framework_schema import AgentFrameworkProfile, WorkflowCompositionSchema, WorkflowComponentSchema


class AgentFrameworkService:
    def infer_information_profile(self, *, purpose: str, signals: dict[str, object]) -> AgentFrameworkProfile:
        combined = str(signals.get("combined_text") or purpose)
        if bool(signals.get("is_timeline")):
            return AgentFrameworkProfile(
                agent_class=AgentClass.INFORMATION,
                agent_layer=AgentLayer.KNOWLEDGE,
                profile_name="structured_timeline",
                entity_label="日程安排",
                supports_knowledge_base=True,
                preferred_capture_mode="direct_record_extraction",
                workflow_roles=["knowledge_base", "workflow_context"],
                metadata={"domain": "schedule", "combined_text": combined},
            )
        if bool(signals.get("is_directory")):
            entity_label = "外部联系人" if any(token in combined for token in ("联系人", "通讯录", "外部", "老师", "同事", "医生", "物业")) else "家庭成员"
            return AgentFrameworkProfile(
                agent_class=AgentClass.INFORMATION,
                agent_layer=AgentLayer.KNOWLEDGE,
                profile_name="entity_directory",
                entity_label=entity_label,
                supports_knowledge_base=True,
                preferred_capture_mode="guided_collection",
                workflow_roles=["knowledge_base", "workflow_context"],
                metadata={"domain": "directory", "combined_text": combined},
            )
        return AgentFrameworkProfile(
            agent_class=AgentClass.INFORMATION,
            agent_layer=AgentLayer.KNOWLEDGE,
            profile_name="generic_information",
            entity_label="信息条目",
            supports_knowledge_base=True,
            preferred_capture_mode="guided_collection",
            workflow_roles=["knowledge_base"],
            metadata={"domain": "generic", "combined_text": combined},
        )

    def build_workflow_composition_template(self) -> WorkflowCompositionSchema:
        return WorkflowCompositionSchema(
            workflow_name="hybrid_user_request_workflow",
            objective="Combine knowledge agents, execution agents, analyzers, tools, and IO operations to satisfy user requests.",
            knowledge_agents=["information_agent"],
            execution_agents=["execution_agent"],
            analysis_agents=["analysis_agent"],
            tools=["file_builder", "structured_output_tool"],
            analyzers=["content_summarizer", "document_analyzer"],
            io_operations=["file_write", "external_delivery"],
            components=[
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.AGENT,
                    name="knowledge_agent",
                    responsibility="Provide structured domain knowledge for downstream execution.",
                ),
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.AGENT,
                    name="execution_agent",
                    responsibility="Perform user-requested actions using tools and knowledge context.",
                    dependencies=["knowledge_agent"],
                ),
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.ANALYZER,
                    name="analysis_module",
                    responsibility="Analyze, summarize, or transform intermediate content.",
                    dependencies=["knowledge_agent"],
                ),
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.TOOL,
                    name="document_tool",
                    responsibility="Generate structured artifacts such as documents or reports.",
                    dependencies=["execution_agent", "analysis_module"],
                ),
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.IO,
                    name="io_operation",
                    responsibility="Persist or deliver workflow outputs through supported channels.",
                    dependencies=["document_tool"],
                ),
                WorkflowComponentSchema(
                    component_type=WorkflowComponentType.WORKFLOW,
                    name="workflow_orchestrator",
                    responsibility="Coordinate knowledge, execution, analysis, tools, and IO into a single user-facing workflow.",
                    dependencies=["knowledge_agent", "execution_agent", "analysis_module", "document_tool", "io_operation"],
                ),
            ],
            metadata={
                "system_owner": "nesthub_runtime",
                "agent_creation_managed_by": "nesthub_runtime",
                "workflow_execution_managed_by": "nesthub_runtime",
                "runtime_issue_resolution_managed_by": "nesthub_runtime",
            },
        )
