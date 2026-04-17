from __future__ import annotations

from nethub_runtime.core.enums import AgentClass, AgentLayer, WorkflowComponentType
from nethub_runtime.core.config.settings import ensure_core_config_dir
from nethub_runtime.core.schemas.agent_framework_schema import AgentFrameworkProfile, WorkflowCompositionSchema, WorkflowComponentSchema


class AgentFrameworkService:
    def __init__(self) -> None:
        ensure_core_config_dir()
        self._generated_profiles: dict[str, dict[str, object]] = {}

    def _normalize_text(self, value: str) -> str:
        return " ".join(str(value).strip().lower().split())

    def _build_generated_profile_definition(self, signals: dict[str, object]) -> dict[str, object] | None:
        seed = str(signals.get("profile_seed") or "generic_information")
        entity_label = str(signals.get("entity_label") or "信息条目")
        role_name = str(signals.get("role_name") or "信息管理智能体")
        knowledge_added_message = str(signals.get("knowledge_added_message") or "已完成添加，并已记录该信息。")
        knowledge_schema = [item for item in list(signals.get("knowledge_schema") or []) if isinstance(item, dict)]
        raw_query_aliases = signals.get("query_aliases")
        query_aliases = {str(key): str(value) for key, value in raw_query_aliases.items()} if isinstance(raw_query_aliases, dict) else {}
        if seed == "structured_timeline":
            return {
                "profile_name": "structured_timeline",
                "entity_label": entity_label,
                "agent_class": AgentClass.INFORMATION.value,
                "agent_layer": AgentLayer.KNOWLEDGE.value,
                "preferred_capture_mode": "direct_record_extraction",
                "workflow_roles": ["knowledge_base"],
                "role_name": role_name,
                "knowledge_added_message": knowledge_added_message,
                "query_aliases": query_aliases,
                "knowledge_schema": knowledge_schema,
                "metadata": {"generated_by": "runtime_inference", "profile_seed": seed},
            }
        if seed == "entity_directory":
            return {
                "profile_name": "entity_directory",
                "entity_label": entity_label,
                "agent_class": AgentClass.INFORMATION.value,
                "agent_layer": AgentLayer.KNOWLEDGE.value,
                "preferred_capture_mode": "guided_collection",
                "workflow_roles": ["knowledge_base"],
                "role_name": role_name,
                "knowledge_added_message": knowledge_added_message,
                "query_aliases": query_aliases,
                "knowledge_schema": knowledge_schema,
                "metadata": {"generated_by": "runtime_inference", "profile_seed": seed},
            }
        return None

    def resolve_information_profile_definition(self, *, purpose: str, signals: dict[str, object]) -> dict[str, object] | None:
        combined = str(signals.get("combined_text") or purpose).strip()
        cache_key = self._normalize_text(combined)
        if cache_key not in self._generated_profiles:
            generated = self._build_generated_profile_definition(signals)
            if generated is not None:
                self._generated_profiles[cache_key] = generated
        return self._generated_profiles.get(cache_key)

    def infer_information_profile(self, *, purpose: str, signals: dict[str, object]) -> AgentFrameworkProfile:
        combined = str(signals.get("combined_text") or purpose)
        profile_definition = self.resolve_information_profile_definition(purpose=purpose, signals=signals)
        if profile_definition is not None:
            return AgentFrameworkProfile(
                agent_class=AgentClass(str(profile_definition.get("agent_class") or AgentClass.INFORMATION.value)),
                agent_layer=AgentLayer(str(profile_definition.get("agent_layer") or AgentLayer.KNOWLEDGE.value)),
                profile_name=str(profile_definition.get("profile_name") or "generic_information"),
                entity_label=str(profile_definition.get("entity_label") or "信息条目"),
                supports_knowledge_base=True,
                preferred_capture_mode=str(profile_definition.get("preferred_capture_mode") or "guided_collection"),
                workflow_roles=[str(item) for item in profile_definition.get("workflow_roles", []) if str(item).strip()] or ["knowledge_base"],
                metadata={**(profile_definition.get("metadata") or {}), "combined_text": combined},
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
