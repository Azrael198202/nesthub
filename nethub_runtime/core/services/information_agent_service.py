from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import Any

from nethub_runtime.core.services.agent_framework_service import AgentFrameworkService
from nethub_runtime.core.services.information_profile_signal_analyzer import InformationProfileSignalAnalyzer
from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


class InformationAgentService:
    CONTEXT_WINDOW_MESSAGES = 20

    def __init__(self, session_store: Any, vector_store: Any, model_router: Any | None = None, semantic_policy_store: SemanticPolicyStore | None = None) -> None:
        self.session_store = session_store
        self.vector_store = vector_store
        self.model_router = model_router
        self.agent_framework_service = AgentFrameworkService()
        self.profile_signal_analyzer = InformationProfileSignalAnalyzer(model_router=model_router, semantic_policy_store=semantic_policy_store)

    def _trim_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(messages) <= self.CONTEXT_WINDOW_MESSAGES:
            return messages
        return messages[-self.CONTEXT_WINDOW_MESSAGES :]

    def _normalize_task_session_state(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = payload or {}
        return {
            "configured_agent": payload.get("configured_agent") if isinstance(payload.get("configured_agent"), dict) else {},
            "agent_setup": payload.get("agent_setup") if isinstance(payload.get("agent_setup"), dict) else {},
            "knowledge_collection": payload.get("knowledge_collection") if isinstance(payload.get("knowledge_collection"), dict) else {},
            "conversation": self._trim_messages([item for item in (payload.get("conversation") or []) if isinstance(item, dict)]),
        }

    def _detect_topic_from_text(self, text: str, task_sessions: dict[str, Any]) -> str | None:
        normalized = text.strip()
        if not normalized:
            return None
        for topic, payload in task_sessions.items():
            if not isinstance(payload, dict):
                continue
            configured_agent = payload.get("configured_agent") if isinstance(payload.get("configured_agent"), dict) else {}
            query_aliases = [str(item) for item in dict(configured_agent.get("query_aliases") or {}).keys()]
            activation_keywords = [str(item) for item in list(configured_agent.get("activation_keywords") or [])]
            identity_terms = [
                str(configured_agent.get("name") or ""),
                str(configured_agent.get("role") or ""),
                str(configured_agent.get("knowledge_entity_label") or ""),
            ]
            for term in [*query_aliases, *activation_keywords, *identity_terms]:
                if term and term in normalized:
                    return topic
        return None

    def _select_task_topic(self, state: dict[str, Any], task: TaskSchema, text: str) -> str:
        main_session = state.get("main_session") if isinstance(state.get("main_session"), dict) else {}
        task_sessions = state.get("task_sessions") if isinstance(state.get("task_sessions"), dict) else {}
        active_topic = str(main_session.get("active_topic") or "").strip()
        matched_topic = self._detect_topic_from_text(text, task_sessions)
        if matched_topic:
            return matched_topic
        if task.intent == "create_information_agent":
            return self.normalize_slug(text)[:64] or "information_agent_task"
        if active_topic:
            return active_topic
        return "information_agent_task"

    def _build_task_session_patch(self, state: dict[str, Any], topic: str, task_session: dict[str, Any]) -> dict[str, Any]:
        task_sessions = dict(state.get("task_sessions") or {})
        task_sessions[topic] = self._normalize_task_session_state(task_session)
        main_session = dict(state.get("main_session") or {})
        known_topics = [item for item in list(main_session.get("topics") or []) if isinstance(item, str) and item.strip()]
        if topic not in known_topics:
            known_topics.append(topic)
        main_session["topics"] = known_topics
        main_session["active_topic"] = topic
        active_session = task_sessions[topic]
        return {
            "main_session": main_session,
            "task_sessions": task_sessions,
            "configured_agent": active_session.get("configured_agent", {}),
            "agent_setup": active_session.get("agent_setup", {}),
            "knowledge_collection": active_session.get("knowledge_collection", {}),
        }

    def _resolve_task_session(self, state: dict[str, Any], task: TaskSchema, text: str) -> tuple[str, dict[str, Any]]:
        topic = self._select_task_topic(state, task, text)
        task_sessions = state.get("task_sessions") if isinstance(state.get("task_sessions"), dict) else {}
        selected = task_sessions.get(topic) if isinstance(task_sessions.get(topic), dict) else None
        if selected is None:
            selected = {
                "configured_agent": state.get("configured_agent") if isinstance(state.get("configured_agent"), dict) else {},
                "agent_setup": state.get("agent_setup") if isinstance(state.get("agent_setup"), dict) else {},
                "knowledge_collection": state.get("knowledge_collection") if isinstance(state.get("knowledge_collection"), dict) else {},
                "conversation": [],
            }
        task_session = self._normalize_task_session_state(selected)
        if text.strip():
            task_session["conversation"] = self._trim_messages(
                [*task_session.get("conversation", []), {"role": "user", "content": text.strip()}]
            )
        return topic, task_session

    def default_information_field_definitions(self) -> list[dict[str, str]]:
        return [
            {"key": "item_name", "prompt": "好的，请问要记录的对象名称是什么？"},
            {"key": "item_type", "prompt": "它属于什么类型或角色？"},
            {"key": "summary", "prompt": "请给出一句简要说明。"},
            {"key": "details", "prompt": "还有什么需要记录的？如果没有了，请回答 完成添加。"},
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
            "completion_phrase": "完成添加",
            "next_action": "ask_user",
            "next_question": "这个智能体需要收集什么信息？如果你已经描述完整，也可以直接说明完成条件。",
            "summary": user_text.strip(),
            "completion_ready": False,
            "conversation": self._trim_messages([{"role": "user", "content": user_text}] if user_text.strip() else []),
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
            normalized.append({"key": key, "prompt": prompt or f"请补充 {key}。"})
        return normalized or self.default_information_field_definitions()

    def _normalize_agent_workflow_state(self, payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
        previous = previous or {}
        known_fields = payload.get("known_fields") if isinstance(payload.get("known_fields"), dict) else previous.get("known_fields", {})
        query_aliases = payload.get("query_aliases") if isinstance(payload.get("query_aliases"), dict) else previous.get("query_aliases", {})
        activation_keywords = payload.get("activation_keywords") if isinstance(payload.get("activation_keywords"), list) else previous.get("activation_keywords", [])
        missing_fields = payload.get("missing_fields") if isinstance(payload.get("missing_fields"), list) else previous.get("missing_fields", [])
        conversation = payload.get("conversation") if isinstance(payload.get("conversation"), list) else previous.get("conversation", [])
        purpose = str(payload.get("purpose") or previous.get("purpose") or "").strip()
        entity_label = str(payload.get("entity_label") or previous.get("entity_label") or purpose or "信息条目").strip()
        profile = str(payload.get("profile") or previous.get("profile") or "generic_information").strip() or "generic_information"
        capture_mode = str(payload.get("capture_mode") or previous.get("capture_mode") or "guided_collection").strip() or "guided_collection"
        completion_phrase = str(payload.get("completion_phrase") or previous.get("completion_phrase") or "完成添加").strip() or "完成添加"
        next_action = str(payload.get("next_action") or previous.get("next_action") or "ask_user").strip() or "ask_user"
        next_question = str(payload.get("next_question") or previous.get("next_question") or "请继续补充。").strip() or "请继续补充。"
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
            "conversation": self._trim_messages([item for item in conversation if isinstance(item, dict)]),
        }

    def _fallback_agent_workflow_update(self, previous: dict[str, Any], user_text: str, *, finalize_requested: bool = False) -> dict[str, Any]:
        state = self._normalize_agent_workflow_state(previous, previous)
        conversation = list(state.get("conversation", []))
        if user_text.strip():
            conversation.append({"role": "user", "content": user_text.strip()})
        conversation = self._trim_messages(conversation)
        purpose = state.get("purpose") or user_text.strip()
        entity_label = state.get("entity_label") or self.normalize_slug(purpose).replace("_", " ") or "信息条目"
        completion_requested = finalize_requested or state.get("completion_phrase", "完成添加") in user_text or "完成创建" in user_text
        schema_fields = state.get("schema_fields") or self.default_information_field_definitions()
        if not state.get("purpose") and user_text.strip() and not completion_requested:
            return self._normalize_agent_workflow_state(
                {
                    **state,
                    "purpose": user_text.strip(),
                    "entity_label": entity_label,
                    "summary": user_text.strip(),
                    "conversation": conversation,
                    "missing_fields": ["schema_fields", "activation_keywords"],
                    "next_question": "请说明这个智能体需要收集哪些字段，以及什么情况下算创建完成。",
                    "next_action": "ask_user",
                },
                state,
            )
        if completion_requested:
            activation_keywords = state.get("activation_keywords") or [f"添加{entity_label}到{entity_label}智能体中", f"查询{entity_label}智能体"]
            return self._normalize_agent_workflow_state(
                {
                    **state,
                    "purpose": purpose,
                    "entity_label": entity_label,
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
                "conversation": conversation,
                "next_question": "如果字段和完成条件已经齐了，请直接回复完成创建；否则继续补充需要收集的信息。",
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
            merged["conversation"] = self._trim_messages(
                [*list(previous.get("conversation", [])), {"role": "user", "content": user_text.strip()}]
            )
        return merged

    def _build_blueprint_from_workflow_state(self, workflow_state: dict[str, Any]) -> dict[str, Any]:
        purpose = str(workflow_state.get("purpose") or workflow_state.get("summary") or "信息收集").strip()
        entity_label = str(workflow_state.get("entity_label") or purpose or "信息条目").strip()
        schema_fields = self._normalize_schema_fields(workflow_state.get("schema_fields"))
        profile = str(workflow_state.get("profile") or "generic_information")
        if profile == "generic_information":
            if entity_label and entity_label != "信息条目":
                profile = "entity_directory"
        capture_mode = str(workflow_state.get("capture_mode") or "guided_collection")
        activation_keywords = [str(item).strip() for item in workflow_state.get("activation_keywords", []) if str(item).strip()]
        if not activation_keywords:
            activation_keywords = [f"添加{entity_label}到{entity_label}智能体中", f"查询{entity_label}智能体"]
        base_profile = {
            "profile": profile,
            "entity_label": entity_label,
            "role": f"{entity_label}信息智能体",
            "knowledge_schema": schema_fields,
            "query_aliases": {str(key): str(value) for key, value in dict(workflow_state.get("query_aliases") or {}).items()},
            "completion_phrase": str(workflow_state.get("completion_phrase") or "完成添加"),
            "capture_mode": capture_mode,
            "knowledge_added_message": f"已完成添加，并已记录该{entity_label}信息。",
            "signals": {
                "combined_text": purpose,
                "profile_seed": profile,
                "entity_label": entity_label,
                "role_name": f"{entity_label}信息智能体",
                "knowledge_added_message": f"已完成添加，并已记录该{entity_label}信息。",
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
            "role": f"{entity_label}信息智能体",
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
        return "信息管理智能体"

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
        return "已完成添加，并已记录该信息。"

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
            "completion_phrase": "完成添加",
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
            "role": profile.get("role", "信息管理智能体"),
            "description": purpose or "用于记录和查询结构化信息。",
            "knowledge_entity_label": profile.get("entity_label", "信息条目"),
            "knowledge_schema": profile.get("knowledge_schema", self.default_information_field_definitions()),
            "query_aliases": profile.get("query_aliases", {}),
            "completion_phrase": profile.get("completion_phrase", "完成添加"),
            "capture_mode": profile.get("capture_mode", "guided_collection"),
            "knowledge_added_message": profile.get("knowledge_added_message", "已完成添加，并已记录该信息。"),
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
                        "entity_label": configured_agent.get("knowledge_entity_label", "信息条目"),
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
                "item_name": item.get("actor") or item.get("label") or item.get("content") or "未命名对象",
                "item_type": item.get("record_type") or "generic",
                "summary": item.get("content") or item.get("raw_text") or text,
                "contact": item.get("location") or "",
                "details": item.get("raw_text") or text,
            }
            direct_records.append({key: value for key, value in record.items() if key in field_keys})
        return direct_records

    def find_record_by_text(self, text: str, records: dict[str, Any], schema_fields: list[dict[str, str]]) -> dict[str, Any] | None:
        candidate_keys = [item.get("key", "") for item in schema_fields]
        for record in records.values():
            for key in candidate_keys:
                token = str(record.get(key, ""))
                if token and token in text:
                    return record
        return None

    def answer_record_field(self, text: str, record: dict[str, Any], field_aliases: dict[str, str], entity_label: str) -> str:
        mapping = {str(key): str(value) for key, value in field_aliases.items()}
        normalized_text = text.lower()
        semantic_field = None
        for field_name, value in record.items():
            if field_name in {"record_id", "details"}:
                continue
            normalized_field = str(field_name).replace("_", " ").lower()
            if normalized_field in normalized_text and value not in (None, ""):
                semantic_field = field_name
                break
        if semantic_field:
            subject = record.get("item_name") or record.get("item_type") or entity_label
            return f"{subject}的{semantic_field}是{record.get(semantic_field)}。"
        for keyword, field in mapping.items():
            if keyword in text:
                value = record.get(field)
                if value:
                    subject = record.get("item_name") or record.get("item_type") or entity_label
                    return f"{subject}的{keyword}是{value}。"
                subject = record.get("item_name") or record.get("item_type") or entity_label
                return f"当前没有记录{subject}的{keyword}。"
        subject = record.get("item_name") or record.get("item_type") or entity_label
        return f"已找到{subject}的{entity_label}资料。"

    def build_configured_agent_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        configured_agent = state.get("configured_agent") or {}
        return {
            "agent_id": configured_agent.get("agent_id", "information_agent"),
            "name": configured_agent.get("name", "information_agent"),
            "role": configured_agent.get("role", "信息管理智能体"),
            "description": configured_agent.get("description", configured_agent.get("purpose", "用于记录和查询结构化信息。")),
            "knowledge_namespace": configured_agent.get("knowledge_namespace", "agent_knowledge/information_agent"),
            "knowledge_entity_label": configured_agent.get("knowledge_entity_label", "信息条目"),
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
            return f"如果没有，请回答：没有了，完成创建。系统会根据“{purpose}”自动补全采集结构。"
        return "如果没有，请回答：没有了，完成创建。系统会自动补全采集结构。"

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
        task_topic, task_session = self._resolve_task_session(state, task, text)
        configured_agent = task_session.get("configured_agent") or {}
        setup = task_session.get("agent_setup") or {}
        collection = task_session.get("knowledge_collection") or {}

        if task.intent == "create_information_agent" and not setup.get("active") and configured_agent.get("status") != "active":
            workflow_state = self._advance_agent_creation_workflow(self._default_agent_workflow_state(text), text)
            task_session["agent_setup"] = {
                "active": True,
                "stage": "ai_workflow",
                "draft": {"name": "information_agent"},
                "workflow_state": workflow_state,
            }
            updated = self.session_store.patch(
                context.session_id,
                self._build_task_session_patch(state, task_topic, task_session),
            )
            return {
                "message": str(workflow_state.get("next_question") or "这个智能体需要收集什么信息？"),
                "dialog_state": {"stage": "ai_workflow", "next_action": workflow_state.get("next_action", "ask_user")},
                "agent": self.build_configured_agent_payload(updated),
                "workflow_state": workflow_state,
            }

        if task.intent in {"refine_information_agent", "finalize_information_agent"} and setup.get("active"):
            previous_workflow_state = setup.get("workflow_state") or self._default_agent_workflow_state()
            workflow_state = self._advance_agent_creation_workflow(
                previous_workflow_state,
                text,
                finalize_requested=task.intent == "finalize_information_agent",
            )

            if workflow_state.get("completion_ready"):
                blueprint = self._build_blueprint_from_workflow_state(workflow_state)
                task_session["configured_agent"] = {
                    **blueprint,
                    "purpose": workflow_state.get("purpose", blueprint.get("description", "")),
                    "specification": workflow_state.get("summary", ""),
                    "status": "active",
                    "knowledge_records": configured_agent.get("knowledge_records", {}),
                }
                task_session["agent_setup"] = {
                    "active": False,
                    "stage": "completed",
                    "draft": {
                        **(setup.get("draft") or {}),
                        "purpose": workflow_state.get("purpose", ""),
                        "specification": workflow_state.get("summary", ""),
                    },
                    "workflow_state": workflow_state,
                }
                updated = self.session_store.patch(
                    context.session_id,
                    self._build_task_session_patch(state, task_topic, task_session),
                )
                return {
                    "message": f"已完成创建{blueprint['role']}。启动关键字：{', '.join(blueprint.get('activation_keywords', []))}",
                    "dialog_state": {"stage": "completed", "next_action": "activate_agent"},
                    "agent": self.build_configured_agent_payload(updated),
                    "workflow_state": workflow_state,
                }

            task_session["agent_setup"] = {
                "active": True,
                "stage": "ai_workflow",
                "draft": {
                    **(setup.get("draft") or {}),
                    "purpose": workflow_state.get("purpose", ""),
                    "specification": workflow_state.get("summary", ""),
                },
                "workflow_state": workflow_state,
            }
            updated = self.session_store.patch(
                context.session_id,
                self._build_task_session_patch(state, task_topic, task_session),
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
                    "message": "当前还没有完成信息型智能体的创建，请先完成创建。",
                    "dialog_state": {"stage": "configured_agent_missing"},
                }

            field_defs = configured_agent.get("knowledge_schema") or self.default_information_field_definitions()
            completion_phrase = str(configured_agent.get("completion_phrase") or "完成添加")
            if not collection.get("active") and configured_agent.get("capture_mode") == "direct_record_extraction":
                direct_records = self._extract_direct_knowledge_records(text, extract_records, configured_agent)
                if direct_records:
                    records, vector_records = self._persist_knowledge_records(configured_agent, direct_records)
                    task_session["configured_agent"] = {**configured_agent, "knowledge_records": records, "status": "active"}
                    task_session["knowledge_collection"] = {"active": False, "field_index": 0, "fields": field_defs, "data": {}}
                    updated = self.session_store.patch(
                        context.session_id,
                        self._build_task_session_patch(state, task_topic, task_session),
                    )
                    base_message = str(configured_agent.get("knowledge_added_message") or "已完成添加，并已记录该信息。")
                    message = base_message if len(direct_records) == 1 else f"已完成添加，并记录了{len(direct_records)}条{configured_agent.get('knowledge_entity_label', '信息')}。"
                    return {
                        "message": message,
                        "dialog_state": {"stage": "knowledge_added"},
                        "knowledge": direct_records[0] if len(direct_records) == 1 else direct_records,
                        "knowledge_vector_record": vector_records[0] if len(vector_records) == 1 else vector_records,
                        "agent": self.build_configured_agent_payload(updated),
                    }

            if not collection.get("active"):
                task_session["knowledge_collection"] = {
                    "active": True,
                    "field_index": 0,
                    "fields": field_defs,
                    "data": {},
                }
                updated = self.session_store.patch(
                    context.session_id,
                    self._build_task_session_patch(state, task_topic, task_session),
                )
                return {
                    "message": field_defs[0]["prompt"],
                    "dialog_state": {"stage": "collecting_knowledge", "current_field": field_defs[0]["key"]},
                    "agent": self.build_configured_agent_payload(updated),
                }

            current_index = int(collection.get("field_index", 0))
            current_field = field_defs[current_index]
            data = dict(collection.get("data") or {})
            value = sanitize_member_value(current_field["key"], text)
            if current_field["key"] == field_defs[-1]["key"] and completion_phrase in text:
                if value:
                    data[current_field["key"]] = value
                records, vector_records = self._persist_knowledge_records(configured_agent, [data])
                record = list(records.values())[-1]
                task_session["configured_agent"] = {**configured_agent, "knowledge_records": records, "status": "active"}
                task_session["knowledge_collection"] = {"active": False, "field_index": 0, "fields": field_defs, "data": {}}
                updated = self.session_store.patch(
                    context.session_id,
                    self._build_task_session_patch(state, task_topic, task_session),
                )
                return {
                    "message": str(configured_agent.get("knowledge_added_message") or "已完成添加，并已记录该信息。"),
                    "dialog_state": {"stage": "knowledge_added"},
                    "knowledge": record,
                    "knowledge_vector_record": vector_records[0],
                    "agent": self.build_configured_agent_payload(updated),
                }

            data[current_field["key"]] = value
            next_index = current_index + 1
            if next_index >= len(field_defs):
                records, vector_records = self._persist_knowledge_records(configured_agent, [data])
                record = list(records.values())[-1]
                task_session["configured_agent"] = {**configured_agent, "knowledge_records": records, "status": "active"}
                task_session["knowledge_collection"] = {"active": False, "field_index": 0, "fields": field_defs, "data": {}}
                updated = self.session_store.patch(
                    context.session_id,
                    self._build_task_session_patch(state, task_topic, task_session),
                )
                return {
                    "message": str(configured_agent.get("knowledge_added_message") or "已完成添加，并已记录该信息。"),
                    "dialog_state": {"stage": "knowledge_added"},
                    "knowledge": record,
                    "knowledge_vector_record": vector_records[0],
                    "agent": self.build_configured_agent_payload(updated),
                }

            task_session["knowledge_collection"] = {
                "active": True,
                "field_index": next_index,
                "fields": field_defs,
                "data": data,
            }
            updated = self.session_store.patch(
                context.session_id,
                self._build_task_session_patch(state, task_topic, task_session),
            )
            next_field = field_defs[next_index]
            return {
                "message": next_field["prompt"],
                "dialog_state": {"stage": "collecting_knowledge", "current_field": next_field["key"]},
                "partial_knowledge": data,
                "agent": self.build_configured_agent_payload(updated),
            }

        return {"message": "当前没有可执行的信息型智能体操作。"}

    def query_information_knowledge(self, *, text: str, context: CoreContextSchema) -> dict[str, Any]:
        state = self.session_store.get(context.session_id)
        probe_task = TaskSchema(task_id="query_information_knowledge", intent="query_agent_knowledge", input_text=text, domain="knowledge_ops")
        _task_topic, task_session = self._resolve_task_session(state, probe_task, text)
        configured_agent = task_session.get("configured_agent") or {}
        records = configured_agent.get("knowledge_records") or {}
        if configured_agent.get("status") != "active":
            return {"message": "当前还没有完成信息型智能体的创建。", "answer": None, "knowledge_hits": []}
        schema_fields = configured_agent.get("knowledge_schema") or self.default_information_field_definitions()
        entity_label = str(configured_agent.get("knowledge_entity_label") or "信息条目")
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
            return {"message": f"当前没有找到对应的{entity_label}信息。", "answer": None, "knowledge_hits": knowledge_hits}
        answer = self.answer_record_field(text, record, configured_agent.get("query_aliases") or {}, entity_label)
        return {"message": answer, "answer": answer, "knowledge": record, "knowledge_hits": knowledge_hits}
