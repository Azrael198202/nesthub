from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.services.agent_framework_service import AgentFrameworkService
from nethub_runtime.core.services.information_profile_signal_analyzer import InformationProfileSignalAnalyzer
from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


class InformationAgentService:
    def __init__(self, session_store: Any, vector_store: Any, model_router: Any | None = None, semantic_policy_store: SemanticPolicyStore | None = None) -> None:
        self.session_store = session_store
        self.vector_store = vector_store
        self.model_router = model_router
        self.agent_framework_service = AgentFrameworkService()
        self.semantic_policy_store = semantic_policy_store or SemanticPolicyStore(policy_path=SEMANTIC_POLICY_PATH)
        self.profile_signal_analyzer = InformationProfileSignalAnalyzer(model_router=model_router, semantic_policy_store=semantic_policy_store)

    def _runtime_semantic_policy(self) -> dict[str, Any]:
        try:
            return self.semantic_policy_store.load_runtime_policy()
        except Exception:
            return {}

    def _information_collection_policy(self) -> dict[str, Any]:
        payload = self._runtime_semantic_policy().get("information_collection", {})
        return payload if isinstance(payload, dict) else {}

    def _default_completion_phrase(self) -> str:
        configured = str(self._information_collection_policy().get("default_completion_phrase") or "").strip()
        if configured:
            return configured
        phrases = self._completion_phrases()
        return phrases[0] if phrases else ""

    def _completion_phrases(self) -> list[str]:
        phrases = self._information_collection_policy().get("completion_phrases", [])
        normalized = [str(item).strip() for item in phrases if str(item).strip()]
        return normalized or [self._default_completion_phrase()]

    def _creation_followup_prompt(self) -> str:
        configured = str(self._information_collection_policy().get("creation_followup_prompt") or "").strip()
        if configured:
            return configured
        return "Please continue refining the agent settings; reply with the configured completion phrase when done."

    def _message_text(self, key: str, default: str) -> str:
        messages = self._information_collection_policy().get("messages", {})
        if not isinstance(messages, dict):
            return default
        configured = str(messages.get(key) or "").strip()
        return configured or default

    def _default_text(self, key: str, default: str) -> str:
        defaults = self._information_collection_policy().get("defaults", {})
        if not isinstance(defaults, dict):
            return default
        configured = str(defaults.get(key) or "").strip()
        return configured or default

    def _activation_keyword_templates(self) -> list[str]:
        payload = self._information_collection_policy().get("activation_keyword_templates", [])
        if not isinstance(payload, list):
            return []
        templates: list[str] = []
        for item in payload:
            value = str(item).strip()
            if value and value not in templates:
                templates.append(value)
        return templates

    def _build_activation_keywords(
        self,
        *,
        entity_label: str,
        query_aliases: dict[str, str] | None = None,
        existing: list[str] | None = None,
    ) -> list[str]:
        keywords: list[str] = []
        for item in list(existing or []):
            value = str(item).strip()
            if value and value not in keywords:
                keywords.append(value)
        aliases = query_aliases or {}
        for key in aliases.keys():
            value = str(key).strip()
            if value and value not in keywords:
                keywords.append(value)
        for template in self._activation_keyword_templates():
            try:
                value = template.format(entity_label=entity_label).strip()
            except Exception:
                value = template.strip()
            if value and value not in keywords:
                keywords.append(value)
        return keywords

    def _explicit_creation_completion_requested(self, user_text: str, *, finalize_requested: bool = False) -> bool:
        if finalize_requested:
            return True
        text = str(user_text or "").strip()
        if not text:
            return False
        markers = set(self._completion_phrases())
        return any(marker and marker in text for marker in markers)

    def default_information_field_definitions(self) -> list[dict[str, str]]:
        configured_fields = self._information_collection_policy().get("default_fields", [])
        if isinstance(configured_fields, list):
            normalized_configured = self._normalize_schema_fields(configured_fields)
            if normalized_configured:
                return normalized_configured
        return [
            {"key": "item_name", "prompt": self._default_text("field_prompt_item_name", "Please provide the item name.")},
            {"key": "item_type", "prompt": self._default_text("field_prompt_item_type", "Please provide the item type or role.")},
            {"key": "summary", "prompt": self._default_text("field_prompt_summary", "Please provide a short summary.")},
            {"key": "details", "prompt": self._default_text("field_prompt_details", "Please add any extra details, or reply with the completion phrase.")},
        ]

    def _default_agent_workflow_state(self, user_text: str = "") -> dict[str, Any]:
        return {
            "status": "collecting_requirements",
            "purpose": "",
            "entity_label": "",
            "profile": "generic_information",
            "capture_mode": "guided_collection",
            "schema_fields": self.default_information_field_definitions(),
            "known_fields": {},
            "missing_fields": ["purpose", "schema_fields"],
            "activation_keywords": [],
            "query_aliases": {},
            "completion_phrase": self._default_completion_phrase(),
            "next_action": "ask_user",
            "next_question": self._message_text(
                "creation_initial_question",
                "What information should this agent collect? If complete, you can also provide the completion condition.",
            ),
            "summary": user_text.strip(),
            "completion_ready": False,
            "conversation": [{"role": "user", "content": user_text}] if user_text.strip() else [],
        }

    def _normalize_schema_fields(self, schema_fields: Any) -> list[dict[str, str]]:
        if not isinstance(schema_fields, list):
            return self.default_information_field_definitions()
        normalized: list[dict[str, str]] = []
        for item in schema_fields:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            prompt = str(item.get("prompt") or "").strip()
            if not key:
                continue
            normalized.append({"key": key, "prompt": prompt or self._default_text("schema_prompt_template", "Please provide {key}.").format(key=key)})
        return normalized or self.default_information_field_definitions()

    def _normalize_agent_workflow_state(self, payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
        previous = previous or {}
        known_fields = payload.get("known_fields") if isinstance(payload.get("known_fields"), dict) else previous.get("known_fields", {})
        query_aliases = payload.get("query_aliases") if isinstance(payload.get("query_aliases"), dict) else previous.get("query_aliases", {})
        activation_keywords = payload.get("activation_keywords") if isinstance(payload.get("activation_keywords"), list) else previous.get("activation_keywords", [])
        missing_fields = payload.get("missing_fields") if isinstance(payload.get("missing_fields"), list) else previous.get("missing_fields", [])
        conversation = payload.get("conversation") if isinstance(payload.get("conversation"), list) else previous.get("conversation", [])
        purpose = str(payload.get("purpose") or previous.get("purpose") or "").strip()
        entity_label = str(
            payload.get("entity_label")
            or previous.get("entity_label")
            or purpose
            or self._default_text("entity_label_default", "Information Item")
        ).strip()
        profile = str(payload.get("profile") or previous.get("profile") or "generic_information").strip() or "generic_information"
        capture_mode = str(payload.get("capture_mode") or previous.get("capture_mode") or "guided_collection").strip() or "guided_collection"
        default_completion_phrase = self._default_completion_phrase()
        completion_phrase = str(payload.get("completion_phrase") or previous.get("completion_phrase") or default_completion_phrase).strip() or default_completion_phrase
        next_action = str(payload.get("next_action") or previous.get("next_action") or "ask_user").strip() or "ask_user"
        next_question = str(
            payload.get("next_question")
            or previous.get("next_question")
            or self._default_text("next_question_default", "Please continue.")
        ).strip() or self._default_text("next_question_default", "Please continue.")
        summary = str(payload.get("summary") or previous.get("summary") or purpose or entity_label).strip()
        return {
            "status": str(payload.get("status") or previous.get("status") or "collecting_requirements"),
            "purpose": purpose,
            "entity_label": entity_label,
            "profile": profile,
            "capture_mode": capture_mode,
            "schema_fields": self._normalize_schema_fields(payload.get("schema_fields") or previous.get("schema_fields")),
            "known_fields": {str(key): value for key, value in dict(known_fields).items()},
            "missing_fields": [str(item) for item in missing_fields if str(item).strip()],
            "activation_keywords": [str(item).strip() for item in activation_keywords if str(item).strip()],
            "query_aliases": {str(key): str(value) for key, value in dict(query_aliases).items()},
            "completion_phrase": completion_phrase,
            "next_action": next_action,
            "next_question": next_question,
            "summary": summary,
            "completion_ready": bool(payload.get("completion_ready", previous.get("completion_ready", False))),
            "conversation": [item for item in conversation if isinstance(item, dict)],
        }

    def _fallback_agent_workflow_update(self, previous: dict[str, Any], user_text: str, *, finalize_requested: bool = False) -> dict[str, Any]:
        state = self._normalize_agent_workflow_state(previous, previous)
        conversation = list(state.get("conversation", []))
        if user_text.strip():
            conversation.append({"role": "user", "content": user_text.strip()})
        purpose = state.get("purpose") or user_text.strip()
        profile = self.infer_requirement_profile(purpose or user_text.strip(), user_text.strip())
        inferred_entity_label = str(profile.get("entity_label") or "").strip()
        inferred_schema = self._normalize_schema_fields(profile.get("knowledge_schema") or [])
        inferred_aliases = {str(key): str(value) for key, value in dict(profile.get("query_aliases") or {}).items()}
        entity_label = (
            inferred_entity_label
            or state.get("entity_label")
            or self.normalize_slug(purpose).replace("_", " ")
            or self._default_text("entity_label_default", "Information Item")
        )
        completion_requested = finalize_requested or any(marker in user_text for marker in self._completion_phrases())
        schema_fields = inferred_schema or state.get("schema_fields") or self.default_information_field_definitions()
        if not state.get("purpose") and user_text.strip() and not completion_requested:
            return self._normalize_agent_workflow_state(
                {
                    **state,
                    "purpose": user_text.strip(),
                    "entity_label": entity_label,
                    "profile": str(profile.get("profile") or state.get("profile") or "generic_information"),
                    "capture_mode": str(profile.get("capture_mode") or state.get("capture_mode") or "guided_collection"),
                    "query_aliases": inferred_aliases,
                    "schema_fields": schema_fields,
                    "summary": user_text.strip(),
                    "conversation": conversation,
                    "missing_fields": ["schema_fields", "activation_keywords"],
                    "next_question": self._message_text(
                        "creation_schema_question",
                        "Please list the fields this agent should collect and define the completion condition.",
                    ),
                    "next_action": "ask_user",
                },
                state,
            )
        if completion_requested:
            activation_keywords = self._build_activation_keywords(
                entity_label=entity_label,
                query_aliases=inferred_aliases,
                existing=state.get("activation_keywords") or [],
            )
            return self._normalize_agent_workflow_state(
                {
                    **state,
                    "purpose": purpose,
                    "entity_label": entity_label,
                    "profile": str(profile.get("profile") or state.get("profile") or "generic_information"),
                    "capture_mode": str(profile.get("capture_mode") or state.get("capture_mode") or "guided_collection"),
                    "query_aliases": inferred_aliases,
                    "schema_fields": schema_fields,
                    "conversation": conversation,
                    "completion_ready": True,
                    "missing_fields": [],
                    "activation_keywords": activation_keywords,
                    "next_action": "finalize_agent",
                    "next_question": "",
                    "summary": state.get("summary") or purpose,
                    "schema_fields": schema_fields,
                },
                state,
            )
        return self._normalize_agent_workflow_state(
            {
                **state,
                "purpose": purpose,
                "entity_label": entity_label,
                "profile": str(profile.get("profile") or state.get("profile") or "generic_information"),
                "capture_mode": str(profile.get("capture_mode") or state.get("capture_mode") or "guided_collection"),
                "query_aliases": inferred_aliases,
                "schema_fields": schema_fields,
                "conversation": conversation,
                "next_question": self._message_text(
                    "creation_continue_question",
                    "If fields and completion condition are ready, reply with the completion phrase; otherwise continue refining.",
                ),
                "next_action": "ask_user",
            },
            state,
        )

    def _invoke_agent_workflow_model(self, previous: dict[str, Any], user_text: str, *, finalize_requested: bool = False) -> dict[str, Any] | None:
        if self.model_router is None:
            return None
        prompt = (
            "You are planning a conversational information-agent creation workflow for NestHub. Return JSON only.\n"
            "Decide the next workflow node and update the evolving agent definition.\n"
            "Required output keys: purpose, entity_label, profile, capture_mode, schema_fields, known_fields, missing_fields, activation_keywords, query_aliases, completion_phrase, next_action, next_question, summary, completion_ready.\n"
            "Allowed profile values: generic_information, entity_directory, structured_timeline.\n"
            "Allowed capture_mode values: guided_collection, direct_record_extraction.\n"
            "When information is still missing, next_action should be ask_user and next_question should contain the exact follow-up question for the user.\n"
            "When enough information is collected or the user indicates completion, set completion_ready=true and next_action=finalize_agent.\n"
            f"finalize_requested: {json.dumps(finalize_requested)}\n"
            f"previous_state: {json.dumps(previous, ensure_ascii=False)}\n"
            f"latest_user_input: {json.dumps(user_text, ensure_ascii=False)}"
        )
        holder: dict[str, Any] = {}

        def _runner() -> None:
            try:
                holder["response"] = asyncio.run(
                    self.model_router.invoke(
                        task_type="intent_analysis",
                        prompt=prompt,
                        system_prompt="Return valid JSON only. Do not use markdown fences.",
                        temperature=0,
                    )
                )
            except Exception as exc:
                holder["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=20)
        raw = holder.get("response")
        if not isinstance(raw, str) or not raw.strip():
            return None
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json\n", "", 1).strip()
        try:
            payload = json.loads(cleaned)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _advance_agent_creation_workflow(self, previous: dict[str, Any], user_text: str, *, finalize_requested: bool = False) -> dict[str, Any]:
        payload = self._invoke_agent_workflow_model(previous, user_text, finalize_requested=finalize_requested)
        if payload is None:
            return self._fallback_agent_workflow_update(previous, user_text, finalize_requested=finalize_requested)
        merged = self._normalize_agent_workflow_state(payload, previous)
        if user_text.strip():
            merged.setdefault("conversation", list(previous.get("conversation", [])))
            merged["conversation"] = [*list(previous.get("conversation", [])), {"role": "user", "content": user_text.strip()}]
        explicit_completion = self._explicit_creation_completion_requested(user_text, finalize_requested=finalize_requested)
        # Guardrail: never auto-complete agent creation unless user explicitly confirms completion.
        if not explicit_completion:
            merged["completion_ready"] = False
            if str(merged.get("next_action") or "") == "finalize_agent":
                merged["next_action"] = "ask_user"
                merged["next_question"] = (
                    str(merged.get("next_question") or "").strip()
                    or self._creation_followup_prompt()
                )
        return merged

    def _build_blueprint_from_workflow_state(self, workflow_state: dict[str, Any]) -> dict[str, Any]:
        purpose = str(workflow_state.get("purpose") or workflow_state.get("summary") or self._default_text("purpose_default", "Information Collection")).strip()
        entity_label = str(
            workflow_state.get("entity_label")
            or purpose
            or self._default_text("entity_label_default", "Information Item")
        ).strip()
        schema_fields = self._normalize_schema_fields(workflow_state.get("schema_fields"))
        profile = str(workflow_state.get("profile") or "generic_information")
        if profile == "generic_information":
            if entity_label and entity_label != self._default_text("entity_label_default", "Information Item"):
                profile = "entity_directory"
        capture_mode = str(workflow_state.get("capture_mode") or "guided_collection")
        activation_keywords = self._build_activation_keywords(
            entity_label=entity_label,
            query_aliases=workflow_state.get("query_aliases") or {},
            existing=[str(item).strip() for item in workflow_state.get("activation_keywords", []) if str(item).strip()],
        )
        base_profile = {
            "profile": profile,
            "entity_label": entity_label,
            "role": self._default_text("role_template", "{entity_label} Information Agent").format(entity_label=entity_label),
            "knowledge_schema": schema_fields,
            "query_aliases": {str(key): str(value) for key, value in dict(workflow_state.get("query_aliases") or {}).items()},
            "completion_phrase": str(workflow_state.get("completion_phrase") or self._default_completion_phrase()),
            "capture_mode": capture_mode,
            "knowledge_added_message": self._default_text(
                "knowledge_added_message_template",
                "Added successfully and recorded {entity_label} information.",
            ).format(entity_label=entity_label),
            "signals": {
                "combined_text": purpose,
                "profile_seed": profile,
                "entity_label": entity_label,
                "role_name": self._default_text("role_template", "{entity_label} Information Agent").format(entity_label=entity_label),
                "knowledge_added_message": self._default_text(
                    "knowledge_added_message_template",
                    "Added successfully and recorded {entity_label} information.",
                ).format(entity_label=entity_label),
                "query_aliases": workflow_state.get("query_aliases") or {},
                "knowledge_schema": schema_fields,
            },
            "agent_class": "information",
            "agent_layer": "knowledge",
            "workflow_roles": ["knowledge_base"],
            "framework_metadata": {"generated_by": "ai_workflow", "workflow_summary": workflow_state.get("summary", purpose)},
        }
        identity = self.build_agent_identity(purpose, base_profile)
        return {
            **identity,
            "profile": profile,
            "role": self._default_text("role_template", "{entity_label} Information Agent").format(entity_label=entity_label),
            "description": purpose,
            "knowledge_entity_label": entity_label,
            "knowledge_schema": schema_fields,
            "query_aliases": base_profile["query_aliases"],
            "completion_phrase": base_profile["completion_phrase"],
            "capture_mode": capture_mode,
            "knowledge_added_message": base_profile["knowledge_added_message"],
            "agent_class": "information",
            "agent_layer": "knowledge",
            "workflow_roles": ["knowledge_base"],
            "framework_metadata": base_profile["framework_metadata"],
            "activation_keywords": activation_keywords,
        }

    def infer_requirement_signals(self, purpose: str, specification: str = "") -> dict[str, Any]:
        return self.profile_signal_analyzer.analyze(purpose, specification)

    def _resolve_profile_definition(self, signals: dict[str, Any]) -> dict[str, Any] | None:
        return self.agent_framework_service.resolve_information_profile_definition(
            purpose=str(signals.get("combined_text") or ""),
            signals=signals,
        )

    def build_field_definitions(self, signals: dict[str, Any]) -> list[dict[str, str]]:
        profile_definition = self._resolve_profile_definition(signals)
        if profile_definition is not None:
            schema = profile_definition.get("knowledge_schema", [])
            if isinstance(schema, list) and schema:
                return [item for item in schema if isinstance(item, dict)]
        return self.default_information_field_definitions()

    def build_query_aliases(self, signals: dict[str, Any]) -> dict[str, str]:
        profile_definition = self._resolve_profile_definition(signals)
        aliases = profile_definition.get("query_aliases", {}) if profile_definition is not None else {}
        return {str(key): str(value) for key, value in aliases.items()} if isinstance(aliases, dict) else {}

    def infer_profile_name(self, signals: dict[str, Any]) -> str:
        profile_definition = self._resolve_profile_definition(signals)
        return str(profile_definition.get("profile_name") or "generic_information") if profile_definition is not None else "generic_information"

    def infer_entity_label(self, signals: dict[str, Any]) -> str:
        profile = self.agent_framework_service.infer_information_profile(
            purpose=str(signals.get("combined_text") or ""),
            signals=signals,
        )
        return profile.entity_label

    def infer_role_name(self, signals: dict[str, Any]) -> str:
        profile_definition = self._resolve_profile_definition(signals)
        if profile_definition is not None and profile_definition.get("role_name"):
            return str(profile_definition.get("role_name"))
        return self._default_text("role_default", "Information Management Agent")

    def infer_capture_mode(self, signals: dict[str, Any]) -> str:
        profile = self.agent_framework_service.infer_information_profile(
            purpose=str(signals.get("combined_text") or ""),
            signals=signals,
        )
        return profile.preferred_capture_mode

    def infer_knowledge_added_message(self, signals: dict[str, Any]) -> str:
        profile_definition = self._resolve_profile_definition(signals)
        if profile_definition is not None and profile_definition.get("knowledge_added_message"):
            return str(profile_definition.get("knowledge_added_message"))
        return self._default_text("knowledge_added_message_default", "Added successfully and recorded the information.")

    def normalize_slug(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", text.lower()).strip("_")
        return normalized or "information_agent"

    def infer_requirement_profile(self, purpose: str, specification: str = "") -> dict[str, Any]:
        signals = self.infer_requirement_signals(purpose, specification)
        framework_profile = self.agent_framework_service.infer_information_profile(purpose=purpose, signals=signals)
        return {
            "profile": framework_profile.profile_name,
            "entity_label": framework_profile.entity_label,
            "role": self.infer_role_name(signals),
            "knowledge_schema": self.build_field_definitions(signals),
            "query_aliases": self.build_query_aliases(signals),
            "completion_phrase": self._default_completion_phrase(),
            "capture_mode": framework_profile.preferred_capture_mode,
            "knowledge_added_message": self.infer_knowledge_added_message(signals),
            "signals": signals,
            "agent_class": framework_profile.agent_class.value,
            "agent_layer": framework_profile.agent_layer.value,
            "workflow_roles": framework_profile.workflow_roles,
            "framework_metadata": framework_profile.metadata,
        }

    def build_agent_identity(self, purpose: str, profile: dict[str, Any]) -> dict[str, str]:
        base_slug = self.normalize_slug(purpose or str(profile.get("entity_label") or "information_agent"))
        profile_slug = str(profile.get("profile") or "information")
        agent_id = f"{profile_slug}_{base_slug}"
        return {
            "agent_id": agent_id,
            "name": agent_id,
            "knowledge_namespace": f"agent_knowledge/{agent_id}",
        }

    def infer_agent_blueprint(self, purpose: str, specification: str = "") -> dict[str, Any]:
        profile = self.infer_requirement_profile(purpose, specification)
        identity = self.build_agent_identity(purpose or specification, profile)
        return {
            **identity,
            "profile": profile.get("profile", "generic_information"),
            "role": profile.get("role", self._default_text("role_default", "Information Management Agent")),
            "description": purpose or self._default_text("description_default", "Used to record and query structured information."),
            "knowledge_entity_label": profile.get("entity_label", self._default_text("entity_label_default", "Information Item")),
            "knowledge_schema": profile.get("knowledge_schema", self.default_information_field_definitions()),
            "query_aliases": profile.get("query_aliases", {}),
            "completion_phrase": profile.get("completion_phrase", self._default_completion_phrase()),
            "capture_mode": profile.get("capture_mode", "guided_collection"),
            "knowledge_added_message": profile.get(
                "knowledge_added_message",
                self._default_text("knowledge_added_message_default", "Added successfully and recorded the information."),
            ),
            "agent_class": profile.get("agent_class", "information"),
            "agent_layer": profile.get("agent_layer", "knowledge"),
            "workflow_roles": profile.get("workflow_roles", ["knowledge_base"]),
            "framework_metadata": profile.get("framework_metadata", {}),
        }

    def _persist_knowledge_records(self, configured_agent: dict[str, Any], records_to_add: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        existing_records = dict(configured_agent.get("knowledge_records") or {})
        field_defs = configured_agent.get("knowledge_schema") or self.default_information_field_definitions()
        vector_records: list[dict[str, Any]] = []

        for record in records_to_add:
            record_id = f"knowledge_{len(existing_records) + 1}"
            complete_record = {"record_id": record_id, **record}
            existing_records[record_id] = complete_record
            content = "\n".join(f"{item['key']}: {complete_record.get(item['key'], '')}" for item in field_defs)
            vector_records.append(
                self.vector_store.add_knowledge(
                    namespace=str(configured_agent.get("knowledge_namespace") or "agent_knowledge/information_agent"),
                    content=content,
                    metadata={
                        "agent_id": configured_agent.get("agent_id"),
                        "record_id": record_id,
                        "record": complete_record,
                        "entity_label": configured_agent.get(
                            "knowledge_entity_label",
                            self._default_text("entity_label_default", "Information Item"),
                        ),
                    },
                    item_id=record_id,
                )
            )

        return existing_records, vector_records

    def _extract_direct_knowledge_records(
        self,
        text: str,
        extract_records: Any,
        configured_agent: dict[str, Any],
    ) -> list[dict[str, Any]]:
        extracted = extract_records(text) or []
        field_defs = configured_agent.get("knowledge_schema") or self.default_information_field_definitions()
        field_keys = {str(item.get("key")) for item in field_defs if isinstance(item, dict) and item.get("key")}
        direct_records: list[dict[str, Any]] = []
        for item in extracted:
            record = {
                "item_name": item.get("actor") or item.get("label") or item.get("content") or self._default_text("unnamed_record_default", "Unnamed Item"),
                "item_type": item.get("record_type") or "generic",
                "summary": item.get("content") or item.get("raw_text") or text,
                "contact": item.get("location") or "",
                "details": item.get("raw_text") or text,
            }
            direct_records.append({key: value for key, value in record.items() if key in field_keys})
        return direct_records

    def _extract_capture_value_text(self, text: str) -> str:
        raw = str(text).strip()
        for separator in ("：", ":"):
            if separator in raw:
                left, right = raw.split(separator, 1)
                if left.strip() and right.strip():
                    return right.strip()
        return raw

    def _extract_capture_label_text(self, text: str) -> str:
        raw = str(text).strip()
        for separator in ("：", ":"):
            if separator in raw:
                left, right = raw.split(separator, 1)
                if left.strip() and right.strip():
                    return left.strip().lower()
        return ""

    def _resolve_capture_field_key(
        self,
        *,
        text: str,
        configured_agent: dict[str, Any],
        field_defs: list[dict[str, str]],
        fallback_field_key: str,
    ) -> str:
        label = self._extract_capture_label_text(text)
        if not label:
            return fallback_field_key

        alias_map = {str(key).lower(): str(value) for key, value in dict(configured_agent.get("query_aliases") or {}).items()}
        if label in alias_map:
            return alias_map[label]

        builtin_alias_map = {
            str(key).lower(): str(value)
            for key, value in dict(self._information_collection_policy().get("field_aliases") or {}).items()
        }
        if label in builtin_alias_map:
            return builtin_alias_map[label]

        for item in field_defs:
            key = str(item.get("key") or "")
            prompt = str(item.get("prompt") or "").lower()
            if label == key.lower() or (prompt and label in prompt):
                return key

        return fallback_field_key

    def find_record_by_text(self, text: str, records: dict[str, Any], schema_fields: list[dict[str, str]]) -> dict[str, Any] | None:
        candidate_keys = [item.get("key", "") for item in schema_fields]
        normalized_text = str(text).strip().lower()
        for record in records.values():
            for key in candidate_keys:
                token = str(record.get(key, "")).strip()
                normalized_token = token.lower()
                if not token:
                    continue
                if normalized_token in normalized_text or normalized_text in normalized_token:
                    return record
                for alias in self._record_match_aliases(token):
                    if alias and alias in normalized_text:
                        return record
        return None

    def _record_match_aliases(self, token: str) -> list[str]:
        normalized = str(token).strip().lower()
        if not normalized:
            return []

        aliases = {normalized}
        for suffix in self._information_collection_policy().get("record_name_suffixes", []):
            if normalized.endswith(suffix):
                trimmed = normalized[: -len(suffix)].strip()
                if trimmed:
                    aliases.add(trimmed)

        for separator in self._information_collection_policy().get("record_name_split_separators", []):
            if separator in normalized:
                for part in normalized.split(separator):
                    part = part.strip()
                    if len(part) >= 2:
                        aliases.add(part)

        return sorted(alias for alias in aliases if len(alias) >= 2)

    def infer_query_field(self, text: str, field_aliases: dict[str, str], schema_fields: list[dict[str, str]]) -> str | None:
        normalized_text = str(text).lower()
        mapping = {str(key).lower(): str(value) for key, value in field_aliases.items()}
        for keyword, field in mapping.items():
            if keyword and keyword in normalized_text:
                return field

        schema_keyword_map = self._information_collection_policy().get("field_query_keywords", {})
        for item in schema_fields:
            key = str(item.get("key") or "")
            prompt = str(item.get("prompt") or "")
            candidates = [key.lower(), prompt.lower()]
            candidates.extend(schema_keyword_map.get(key, []))
            if any(candidate and candidate in normalized_text for candidate in candidates):
                return key
        return None

    def answer_record_field(self, text: str, record: dict[str, Any], field_aliases: dict[str, str], entity_label: str, schema_fields: list[dict[str, str]]) -> str:
        mapping = {str(key): str(value) for key, value in field_aliases.items()}
        normalized_text = text.lower()
        semantic_field = self.infer_query_field(text, field_aliases, schema_fields)
        for field_name, value in record.items():
            if field_name in {"record_id", "details"}:
                continue
            normalized_field = str(field_name).replace("_", " ").lower()
            if semantic_field is None and normalized_field in normalized_text and value not in (None, ""):
                semantic_field = field_name
                break
        if semantic_field:
            subject = record.get("item_name") or record.get("item_type") or entity_label
            return self._message_text("answer_field_template", "{subject} {field} is {value}.").format(
                subject=subject,
                field=semantic_field,
                value=record.get(semantic_field),
            )
        for keyword, field in mapping.items():
            if keyword in text:
                value = record.get(field)
                if value:
                    subject = record.get("item_name") or record.get("item_type") or entity_label
                    return self._message_text("answer_keyword_template", "{subject} {keyword} is {value}.").format(
                        subject=subject,
                        keyword=keyword,
                        value=value,
                    )
                subject = record.get("item_name") or record.get("item_type") or entity_label
                return self._message_text("answer_keyword_missing_template", "No {keyword} is recorded for {subject}.").format(
                    subject=subject,
                    keyword=keyword,
                )
        subject = record.get("item_name") or record.get("item_type") or entity_label
        return self._message_text("answer_record_found_template", "Found {entity_label} data for {subject}.").format(
            subject=subject,
            entity_label=entity_label,
        )

    def build_configured_agent_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        configured_agent = state.get("configured_agent") or {}
        return {
            "agent_id": configured_agent.get("agent_id", "information_agent"),
            "name": configured_agent.get("name", "information_agent"),
            "role": configured_agent.get("role", self._default_text("role_default", "Information Management Agent")),
            "description": configured_agent.get(
                "description",
                configured_agent.get("purpose", self._default_text("description_default", "Used to record and query structured information.")),
            ),
            "knowledge_namespace": configured_agent.get("knowledge_namespace", "agent_knowledge/information_agent"),
            "knowledge_entity_label": configured_agent.get(
                "knowledge_entity_label",
                self._default_text("entity_label_default", "Information Item"),
            ),
            "schema_fields": [item.get("key") for item in configured_agent.get("knowledge_schema", self.default_information_field_definitions())],
            "knowledge_records": list((configured_agent.get("knowledge_records") or {}).values()),
            "status": configured_agent.get("status", "draft"),
            "profile": configured_agent.get("profile", "generic_information"),
            "agent_class": configured_agent.get("agent_class", "information"),
            "agent_layer": configured_agent.get("agent_layer", "knowledge"),
            "workflow_roles": configured_agent.get("workflow_roles", ["knowledge_base"]),
            "activation_keywords": configured_agent.get("activation_keywords", []),
        }

    def _setup_completion_hint(self, draft: dict[str, Any]) -> str:
        purpose = str(draft.get("purpose") or "").strip()
        if purpose:
            return self._message_text(
                "setup_completion_hint_with_purpose",
                "If there is nothing else, reply with the completion phrase. The system will auto-complete fields for \"{purpose}\".",
            ).format(purpose=purpose)
        return self._message_text(
            "setup_completion_hint_generic",
            "If there is nothing else, reply with the completion phrase. The system will auto-complete field collection.",
        )

    def manage_information_agent(
        self,
        *,
        text: str,
        task: TaskSchema,
        context: CoreContextSchema,
        normalize_yes_no: Any,
        sanitize_member_value: Any,
        extract_records: Any,
    ) -> dict[str, Any]:
        state = self.session_store.get(context.session_id)
        configured_agent = state.get("configured_agent") or {}
        setup = state.get("agent_setup") or {}
        collection = state.get("knowledge_collection") or {}

        if task.intent == "create_information_agent" and not setup.get("active"):
            # First turn always enters guided creation mode; do not auto-finalize.
            workflow_state = self._default_agent_workflow_state(text)
            updated = self.session_store.patch(
                context.session_id,
                {
                    "agent_setup": {
                        "active": True,
                        "stage": "ai_workflow",
                        "draft": {"name": "information_agent"},
                        "workflow_state": workflow_state,
                    },
                },
            )
            return {
                "message": str(
                    workflow_state.get("next_question")
                    or self._message_text(
                        "creation_initial_question",
                        "What information should this agent collect? If complete, you can also provide the completion condition.",
                    )
                ),
                "dialog_state": {"stage": "ai_workflow", "next_action": workflow_state.get("next_action", "ask_user")},
                "agent": self.build_configured_agent_payload(updated),
                "workflow_state": workflow_state,
            }

        if task.intent in {"create_information_agent", "refine_information_agent", "finalize_information_agent"} and setup.get("active"):
            previous_workflow_state = setup.get("workflow_state") or self._default_agent_workflow_state()
            workflow_state = self._advance_agent_creation_workflow(
                previous_workflow_state,
                text,
                finalize_requested=task.intent == "finalize_information_agent",
            )

            if workflow_state.get("completion_ready"):
                blueprint = self._build_blueprint_from_workflow_state(workflow_state)
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "configured_agent": {
                            **blueprint,
                            "purpose": workflow_state.get("purpose", blueprint.get("description", "")),
                            "specification": workflow_state.get("summary", ""),
                            "status": "active",
                            "knowledge_records": configured_agent.get("knowledge_records", {}),
                        },
                        "agent_setup": {
                            "active": False,
                            "stage": "completed",
                            "draft": {
                                **(setup.get("draft") or {}),
                                "purpose": workflow_state.get("purpose", ""),
                                "specification": workflow_state.get("summary", ""),
                            },
                            "workflow_state": workflow_state,
                        },
                    },
                )
                return {
                    "message": self._message_text(
                        "creation_completed_template",
                        "Creation completed for {role}. Activation keywords: {activation_keywords}",
                    ).format(
                        role=blueprint["role"],
                        activation_keywords=", ".join(blueprint.get("activation_keywords", [])),
                    ),
                    "dialog_state": {"stage": "completed", "next_action": "activate_agent"},
                    "agent": self.build_configured_agent_payload(updated),
                    "workflow_state": workflow_state,
                }

            updated = self.session_store.patch(
                context.session_id,
                {
                    "agent_setup": {
                        "active": True,
                        "stage": "ai_workflow",
                        "draft": {
                            **(setup.get("draft") or {}),
                            "purpose": workflow_state.get("purpose", ""),
                            "specification": workflow_state.get("summary", ""),
                        },
                        "workflow_state": workflow_state,
                    }
                },
            )
            return {
                "message": str(workflow_state.get("next_question") or self._setup_completion_hint(updated.get('agent_setup', {}).get('draft', {}))),
                "dialog_state": {"stage": "ai_workflow", "next_action": workflow_state.get("next_action", "ask_user")},
                "agent": self.build_configured_agent_payload(updated),
                "workflow_state": workflow_state,
            }

        if task.intent == "capture_agent_knowledge":
            if configured_agent.get("status") != "active" and not collection.get("active"):
                return {
                    "message": self._message_text(
                        "configured_agent_missing_message",
                        "No active information agent is available yet. Please complete creation first.",
                    ),
                    "dialog_state": {"stage": "configured_agent_missing"},
                }

            field_defs = configured_agent.get("knowledge_schema") or self.default_information_field_definitions()
            completion_phrase = str(configured_agent.get("completion_phrase") or self._default_completion_phrase())
            if not collection.get("active") and configured_agent.get("capture_mode") == "direct_record_extraction":
                direct_records = self._extract_direct_knowledge_records(text, extract_records, configured_agent)
                if direct_records:
                    records, vector_records = self._persist_knowledge_records(configured_agent, direct_records)
                    updated = self.session_store.patch(
                        context.session_id,
                        {
                            "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                            "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                        },
                    )
                    base_message = str(
                        configured_agent.get("knowledge_added_message")
                        or self._default_text("knowledge_added_message_default", "Added successfully and recorded the information.")
                    )
                    message = (
                        base_message
                        if len(direct_records) == 1
                        else self._message_text(
                            "knowledge_added_batch_template",
                            "Added successfully and recorded {count} {entity_label} entries.",
                        ).format(
                            count=len(direct_records),
                            entity_label=configured_agent.get(
                                "knowledge_entity_label",
                                self._default_text("entity_label_default", "Information Item"),
                            ),
                        )
                    )
                    return {
                        "message": message,
                        "dialog_state": {"stage": "knowledge_added"},
                        "knowledge": direct_records[0] if len(direct_records) == 1 else direct_records,
                        "knowledge_vector_record": vector_records[0] if len(vector_records) == 1 else vector_records,
                        "agent": self.build_configured_agent_payload(updated),
                    }

            if not collection.get("active"):
                first_field = field_defs[0]
                target_field_key = self._resolve_capture_field_key(
                    text=text,
                    configured_agent=configured_agent,
                    field_defs=field_defs,
                    fallback_field_key=first_field["key"],
                )
                normalized_value_text = self._extract_capture_value_text(text)
                if normalized_value_text and normalized_value_text != str(text).strip():
                    initial_data = {
                        target_field_key: sanitize_member_value(target_field_key, normalized_value_text)
                    }
                    next_index = next(
                        (index for index, item in enumerate(field_defs) if item["key"] not in initial_data),
                        len(field_defs),
                    )
                    if next_index >= len(field_defs):
                        records, vector_records = self._persist_knowledge_records(configured_agent, [initial_data])
                        record = list(records.values())[-1]
                        updated = self.session_store.patch(
                            context.session_id,
                            {
                                "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                                "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                            },
                        )
                        return {
                            "message": str(
                                configured_agent.get("knowledge_added_message")
                                or self._default_text("knowledge_added_message_default", "Added successfully and recorded the information.")
                            ),
                            "dialog_state": {"stage": "knowledge_added"},
                            "knowledge": record,
                            "knowledge_vector_record": vector_records[0],
                            "agent": self.build_configured_agent_payload(updated),
                        }

                    updated = self.session_store.patch(
                        context.session_id,
                        {
                            "knowledge_collection": {
                                "active": True,
                                "field_index": next_index,
                                "fields": field_defs,
                                "data": initial_data,
                            }
                        },
                    )
                    next_field = field_defs[next_index]
                    return {
                        "message": next_field["prompt"],
                        "dialog_state": {"stage": "collecting_knowledge", "current_field": next_field["key"]},
                        "partial_knowledge": initial_data,
                        "agent": self.build_configured_agent_payload(updated),
                    }

                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "knowledge_collection": {
                            "active": True,
                            "field_index": 0,
                            "fields": field_defs,
                            "data": {},
                        }
                    },
                )
                return {
                    "message": field_defs[0]["prompt"],
                    "dialog_state": {"stage": "collecting_knowledge", "current_field": field_defs[0]["key"]},
                    "agent": self.build_configured_agent_payload(updated),
                }

            current_index = int(collection.get("field_index", 0))
            current_field = field_defs[current_index]
            data = dict(collection.get("data") or {})
            target_field_key = self._resolve_capture_field_key(
                text=text,
                configured_agent=configured_agent,
                field_defs=field_defs,
                fallback_field_key=current_field["key"],
            )
            value = sanitize_member_value(target_field_key, self._extract_capture_value_text(text))
            if target_field_key == field_defs[-1]["key"] and completion_phrase in text:
                if value:
                    data[target_field_key] = value
                records, vector_records = self._persist_knowledge_records(configured_agent, [data])
                record = list(records.values())[-1]
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                        "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                    },
                )
                return {
                    "message": str(
                        configured_agent.get("knowledge_added_message")
                        or self._default_text("knowledge_added_message_default", "Added successfully and recorded the information.")
                    ),
                    "dialog_state": {"stage": "knowledge_added"},
                    "knowledge": record,
                    "knowledge_vector_record": vector_records[0],
                    "agent": self.build_configured_agent_payload(updated),
                }

            data[target_field_key] = value
            next_index = next(
                (index for index, item in enumerate(field_defs) if item["key"] not in data),
                len(field_defs),
            )
            if next_index >= len(field_defs):
                records, vector_records = self._persist_knowledge_records(configured_agent, [data])
                record = list(records.values())[-1]
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                        "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                    },
                )
                return {
                    "message": str(
                        configured_agent.get("knowledge_added_message")
                        or self._default_text("knowledge_added_message_default", "Added successfully and recorded the information.")
                    ),
                    "dialog_state": {"stage": "knowledge_added"},
                    "knowledge": record,
                    "knowledge_vector_record": vector_records[0],
                    "agent": self.build_configured_agent_payload(updated),
                }

            updated = self.session_store.patch(
                context.session_id,
                {
                    "knowledge_collection": {
                        "active": True,
                        "field_index": next_index,
                        "fields": field_defs,
                        "data": data,
                    }
                },
            )
            next_field = field_defs[next_index]
            return {
                "message": next_field["prompt"],
                "dialog_state": {"stage": "collecting_knowledge", "current_field": next_field["key"]},
                "partial_knowledge": data,
                "agent": self.build_configured_agent_payload(updated),
            }

        return {"message": self._message_text("no_executable_operation_message", "No executable information-agent operation is available.")}

    def query_information_knowledge(self, *, text: str, context: CoreContextSchema) -> dict[str, Any]:
        state = self.session_store.get(context.session_id)
        configured_agent = state.get("configured_agent") or {}
        if configured_agent.get("status") != "active":
            recovered_agent = self._recover_configured_agent_from_promoted_facts(context.session_id)
            if recovered_agent:
                configured_agent = recovered_agent
                state = self.session_store.patch(
                    context.session_id,
                    {"configured_agent": {**configured_agent, "knowledge_records": configured_agent.get("knowledge_records") or {}}},
                )
        records = configured_agent.get("knowledge_records") or {}
        if configured_agent.get("status") != "active":
            return {
                "message": self._message_text("query_before_creation_message", "No information agent has been fully created yet."),
                "answer": None,
                "knowledge_hits": [],
            }
        schema_fields = configured_agent.get("knowledge_schema") or self.default_information_field_definitions()
        entity_label = str(
            configured_agent.get("knowledge_entity_label")
            or self._default_text("entity_label_default", "Information Item")
        )
        normalized_text = str(text).strip().lower()
        record = self.find_record_by_text(text, records, schema_fields)
        knowledge_hits = self.vector_store.search(
            text,
            namespace=str(configured_agent.get("knowledge_namespace") or "agent_knowledge/information_agent"),
            top_k=5,
        )
        if record and not knowledge_hits:
            fallback_query = " ".join(
                str(record.get(key, ""))
                for key in [item.get("key", "") for item in schema_fields]
                if record.get(key)
            )
            knowledge_hits = self.vector_store.search(
                fallback_query,
                namespace=str(configured_agent.get("knowledge_namespace") or "agent_knowledge/information_agent"),
                top_k=5,
            )
        if not record and knowledge_hits:
            first_hit = knowledge_hits[0]
            record = (first_hit.get("metadata") or {}).get("record")
        if not record:
            promoted_fact_hits = self.vector_store.search(
                text,
                namespace="information_agent_fact",
                top_k=5,
            )
            filtered_fact_hits = self._filter_promoted_fact_hits(promoted_fact_hits, configured_agent, session_id=context.session_id)
            if not filtered_fact_hits:
                all_fact_hits = [
                    item
                    for item in list(getattr(self.vector_store, "_items", []))
                    if str(item.get("namespace") or "") == "information_agent_fact"
                ]
                filtered_fact_hits = self._filter_promoted_fact_hits(all_fact_hits, configured_agent, session_id=context.session_id)
            if filtered_fact_hits:
                knowledge_hits = [*knowledge_hits, *filtered_fact_hits]
                first_fact = filtered_fact_hits[0]
                record = (first_fact.get("metadata") or {}).get("record")
        list_query_markers = [str(item) for item in self._information_collection_policy().get("list_query_markers", []) if str(item).strip()]
        if not record and not knowledge_hits and records and any(marker in normalized_text for marker in list_query_markers):
            knowledge_hits = [
                {
                    "metadata": {
                        "record": item,
                        "record_id": item.get("record_id"),
                        "agent_id": configured_agent.get("agent_id"),
                    }
                }
                for item in records.values()
            ]
        if not record:
            return {
                "message": self._message_text(
                    "query_not_found_template",
                    "No matching {entity_label} information was found.",
                ).format(entity_label=entity_label),
                "answer": None,
                "knowledge_hits": knowledge_hits,
            }
        answer = self.answer_record_field(text, record, configured_agent.get("query_aliases") or {}, entity_label, schema_fields)
        return {"message": answer, "answer": answer, "knowledge": record, "knowledge_hits": knowledge_hits}

    def _filter_promoted_fact_hits(self, hits: list[dict[str, Any]], configured_agent: dict[str, Any], session_id: str | None = None) -> list[dict[str, Any]]:
        agent_id = str(configured_agent.get("agent_id") or "").strip()
        entity_label = str(configured_agent.get("knowledge_entity_label") or "").strip()
        normalized_session_id = str(session_id or "").strip()
        filtered: list[dict[str, Any]] = []
        for hit in hits:
            metadata = hit.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            record = metadata.get("record") if isinstance(metadata.get("record"), dict) else None
            if record is None:
                continue
            metadata_session_id = str(metadata.get("session_id") or "").strip()
            metadata_agent_id = str(metadata.get("agent_id") or "").strip()
            metadata_entity_label = str(metadata.get("entity_label") or "").strip()
            if normalized_session_id and metadata_session_id and metadata_session_id != normalized_session_id:
                continue
            if agent_id and metadata_agent_id and metadata_agent_id != agent_id:
                continue
            if entity_label and metadata_entity_label and metadata_entity_label != entity_label:
                continue
            filtered.append(hit)
        return filtered

    def _recover_configured_agent_from_promoted_facts(self, session_id: str) -> dict[str, Any]:
        items = list(getattr(self.vector_store, "_items", []))
        fallback_record: dict[str, Any] | None = None
        for item in reversed(items):
            if str(item.get("namespace") or "") != "information_agent_fact":
                continue
            metadata = item.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            if session_id and str(metadata.get("session_id") or "") != session_id:
                continue
            metadata_type = str(metadata.get("type") or "")
            if metadata_type == "information_agent_record" and fallback_record is None:
                fallback_record = metadata
                continue
            if metadata_type != "information_agent_definition":
                continue
            entity_label = str(
                metadata.get("entity_label")
                or self._default_text("entity_label_default", "Information Item")
            )
            schema_fields = [
                {
                    "key": str(item),
                    "prompt": self._default_text("schema_prompt_template", "Please provide {key}.").format(key=str(item)),
                }
                for item in list(metadata.get("schema_fields") or [])
                if str(item).strip()
            ] or self.default_information_field_definitions()
            return {
                "agent_id": str(metadata.get("agent_id") or f"recovered_{session_id}"),
                "name": str(metadata.get("agent_id") or f"{entity_label}_agent"),
                "role": self._default_text("role_template", "{entity_label} Information Agent").format(entity_label=entity_label),
                "description": self._default_text(
                    "recovered_description_template",
                    "Recovered {entity_label} information agent from long-term memory.",
                ).format(entity_label=entity_label),
                "knowledge_namespace": "agent_knowledge/information_agent",
                "knowledge_entity_label": entity_label,
                "knowledge_schema": schema_fields,
                "query_aliases": dict(metadata.get("query_aliases") or {}),
                "activation_keywords": list(metadata.get("activation_keywords") or []),
                "profile": str(metadata.get("profile") or "generic_information"),
                "agent_class": "information",
                "agent_layer": "knowledge",
                "workflow_roles": ["knowledge_base"],
                "status": "active",
                "knowledge_records": {},
            }
        if fallback_record is not None:
            entity_label = str(
                fallback_record.get("entity_label")
                or self._default_text("entity_label_default", "Information Item")
            )
            return {
                "agent_id": str(fallback_record.get("agent_id") or f"recovered_{session_id}"),
                "name": str(fallback_record.get("agent_id") or f"{entity_label}_agent"),
                "role": self._default_text("role_template", "{entity_label} Information Agent").format(entity_label=entity_label),
                "description": self._default_text(
                    "recovered_description_template",
                    "Recovered {entity_label} information agent from long-term memory.",
                ).format(entity_label=entity_label),
                "knowledge_namespace": "agent_knowledge/information_agent",
                "knowledge_entity_label": entity_label,
                "knowledge_schema": self.default_information_field_definitions(),
                "query_aliases": {},
                "activation_keywords": [],
                "profile": "generic_information",
                "agent_class": "information",
                "agent_layer": "knowledge",
                "workflow_roles": ["knowledge_base"],
                "status": "active",
                "knowledge_records": {},
            }
        return {}
