from __future__ import annotations

import re
from typing import Any

from nethub_runtime.core.services.agent_framework_service import AgentFrameworkService
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


class InformationAgentService:
    def __init__(self, session_store: Any, vector_store: Any) -> None:
        self.session_store = session_store
        self.vector_store = vector_store
        self.agent_framework_service = AgentFrameworkService()

    def default_information_field_definitions(self) -> list[dict[str, str]]:
        return [
            {"key": "item_name", "prompt": "好的，请问要记录的对象名称是什么？"},
            {"key": "item_type", "prompt": "它属于什么类型或角色？"},
            {"key": "summary", "prompt": "请给出一句简要说明。"},
            {"key": "details", "prompt": "还有什么需要记录的？如果没有了，请回答 完成添加。"},
        ]

    def directory_field_definitions(self) -> list[dict[str, str]]:
        return [
            {"key": "member_name", "prompt": "好的，请问成员姓名？"},
            {"key": "role", "prompt": "角色是什么呢？例如 爸爸 / 妈妈 / 孩子。"},
            {"key": "nickname", "prompt": "称呼是什么呢？"},
            {"key": "default_currency", "prompt": "默认币种是什么？例如 JPY / CNY / USD。"},
            {"key": "include_expense", "prompt": "是否参与消费统计？请回答 是 或 否。"},
            {"key": "include_schedule", "prompt": "是否参与日程提醒？请回答 是 或 否。"},
            {"key": "special_constraints", "prompt": "有什么特殊约束吗？例如 儿童、学生、老人。如无请回答 无。"},
            {"key": "phone", "prompt": "联系方式呢？请提供手机号或电话。"},
            {"key": "email", "prompt": "有邮箱地址吗？如无请回答 无。"},
            {"key": "extra_notes", "prompt": "还有什么需要记录的？如果没有了，请回答 完成添加。"},
        ]

    def timeline_field_definitions(self) -> list[dict[str, str]]:
        return [
            {"key": "actor", "prompt": "这是谁的日程安排？"},
            {"key": "time", "prompt": "时间是什么时候？"},
            {"key": "content", "prompt": "具体安排是什么？"},
            {"key": "location", "prompt": "地点在哪里？如果没有可回答 无。"},
            {"key": "details", "prompt": "还有什么补充说明？如果没有了，请回答 完成添加。"},
        ]

    def infer_requirement_signals(self, purpose: str, specification: str = "") -> dict[str, Any]:
        combined = f"{purpose} {specification}".strip()
        return {
            "combined_text": combined,
            "is_directory": any(keyword in combined for keyword in ("家庭成员", "成员信息", "家庭信息", "联系人", "通讯录", "爸爸", "妈妈", "孩子")),
            "is_timeline": any(keyword in combined for keyword in ("日程", "安排", "行程", "出差", "远足", "提醒", "计划", "会议")),
            "needs_contact_fields": any(keyword in combined for keyword in ("家庭成员", "成员信息", "联系人", "通讯录", "电话", "邮箱")),
            "needs_expense_flags": any(keyword in combined for keyword in ("家庭成员", "消费", "币种", "统计")),
            "needs_schedule_flags": any(keyword in combined for keyword in ("家庭成员", "提醒", "日程")),
        }

    def build_field_definitions(self, signals: dict[str, Any]) -> list[dict[str, str]]:
        if signals.get("is_timeline"):
            return self.timeline_field_definitions()
        if signals.get("is_directory"):
            return self.directory_field_definitions()
        return self.default_information_field_definitions()

    def build_query_aliases(self, signals: dict[str, Any]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        if signals.get("is_timeline"):
            aliases.update(
                {
                    "时间": "time",
                    "日期": "time",
                    "安排": "content",
                    "行程": "content",
                    "地点": "location",
                    "位置": "location",
                    "说明": "details",
                }
            )
        if signals.get("needs_contact_fields"):
            aliases.update(
                {
                    "手机号": "phone",
                    "电话": "phone",
                    "邮箱": "email",
                    "line": "extra_notes",
                    "公司": "extra_notes",
                    "联系电话": "extra_notes",
                }
            )
        return aliases

    def infer_profile_name(self, signals: dict[str, Any]) -> str:
        if signals.get("is_timeline"):
            return "structured_timeline"
        if signals.get("is_directory"):
            return "entity_directory"
        return "generic_information"

    def infer_entity_label(self, signals: dict[str, Any]) -> str:
        profile = self.agent_framework_service.infer_information_profile(
            purpose=str(signals.get("combined_text") or ""),
            signals=signals,
        )
        return profile.entity_label

    def infer_role_name(self, signals: dict[str, Any]) -> str:
        profile = self.agent_framework_service.infer_information_profile(
            purpose=str(signals.get("combined_text") or ""),
            signals=signals,
        )
        if profile.profile_name == "structured_timeline":
            return "日程信息智能体"
        if profile.entity_label == "外部联系人":
            return "外部联系人信息智能体"
        if profile.profile_name == "entity_directory":
            return "家庭成员信息管理智能体"
        return "信息管理智能体"

    def infer_capture_mode(self, signals: dict[str, Any]) -> str:
        profile = self.agent_framework_service.infer_information_profile(
            purpose=str(signals.get("combined_text") or ""),
            signals=signals,
        )
        return profile.preferred_capture_mode

    def infer_knowledge_added_message(self, signals: dict[str, Any]) -> str:
        if signals.get("is_timeline"):
            return "已经将此信息记录到日程信息智能体。"
        if signals.get("is_directory") and "联系人" in str(signals.get("combined_text") or ""):
            return "已完成添加，并已记录该外部联系人信息。"
        if signals.get("is_directory"):
            return "已完成添加，并已记录该家庭成员信息。"
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

    def _extract_schedule_knowledge_records(self, text: str, extract_records: Any) -> list[dict[str, Any]]:
        extracted = extract_records(text) or []
        schedule_records: list[dict[str, Any]] = []
        for item in extracted:
            if item.get("record_type") != "schedule":
                continue
            location = item.get("location")
            if not location:
                fallback_match = re.search(r"(?:去|到|前往|出差)([\u4e00-\u9fffA-Za-z0-9]{2,})", str(item.get("raw_text") or text))
                if fallback_match:
                    location = fallback_match.group(1)
            schedule_records.append(
                {
                    "actor": item.get("actor") or "未指定",
                    "time": item.get("time") or "",
                    "content": item.get("content") or item.get("raw_text") or text,
                    "location": location or "无",
                    "details": item.get("raw_text") or text,
                }
            )
        return schedule_records

    def find_record_by_text(self, text: str, records: dict[str, Any], schema_fields: list[dict[str, str]]) -> dict[str, Any] | None:
        candidate_keys = [item.get("key", "") for item in schema_fields]
        for record in records.values():
            for key in candidate_keys:
                token = str(record.get(key, ""))
                if token and token in text:
                    return record
        return None

    def answer_record_field(self, text: str, record: dict[str, Any], field_aliases: dict[str, str], entity_label: str) -> str:
        mapping = {
            "手机号": "phone",
            "电话": "phone",
            "邮箱": "email",
            "line": "extra_notes",
            "公司": "extra_notes",
            "联系电话": "extra_notes",
            **field_aliases,
        }
        for keyword, field in mapping.items():
            if keyword in text:
                value = record.get(field)
                if value:
                    subject = record.get("role") or record.get("member_name") or record.get("item_name") or entity_label
                    return f"{subject}的{keyword}是{value}。"
                subject = record.get("role") or record.get("member_name") or record.get("item_name") or entity_label
                return f"当前没有记录{subject}的{keyword}。"
        subject = record.get("role") or record.get("member_name") or record.get("item_name") or entity_label
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
        configured_agent = state.get("configured_agent") or {}
        setup = state.get("agent_setup") or {}
        collection = state.get("knowledge_collection") or {}

        if task.intent == "create_information_agent" and not setup.get("active") and configured_agent.get("status") != "active":
            updated = self.session_store.patch(
                context.session_id,
                {
                    "agent_setup": {"active": True, "stage": "awaiting_purpose", "draft": {"name": "information_agent"}},
                },
            )
            return {
                "message": "好的，这个智能体主要是什么功能呢？",
                "dialog_state": {"stage": "awaiting_purpose"},
                "agent": self.build_configured_agent_payload(updated),
            }

        if task.intent == "refine_information_agent" and setup.get("active"):
            if setup.get("stage") == "awaiting_purpose":
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "agent_setup": {
                            "active": True,
                            "stage": "awaiting_confirmation",
                            "draft": {**(setup.get("draft") or {}), "purpose": text.strip()},
                        }
                    },
                )
                return {
                    "message": f"好的，还有什么需要特别指定的。{self._setup_completion_hint(updated.get('agent_setup', {}).get('draft', {}))}",
                    "dialog_state": {"stage": "awaiting_confirmation"},
                    "agent": self.build_configured_agent_payload(updated),
                }

            if setup.get("stage") == "awaiting_confirmation":
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "agent_setup": {
                            "active": True,
                            "stage": "awaiting_confirmation",
                            "draft": {**(setup.get("draft") or {}), "specification": text.strip()},
                        }
                    },
                )
                return {
                    "message": self._setup_completion_hint(updated.get('agent_setup', {}).get('draft', {})),
                    "dialog_state": {"stage": "awaiting_confirmation"},
                    "agent": self.build_configured_agent_payload(updated),
                }

        if task.intent == "finalize_information_agent" and setup.get("active"):
            draft = setup.get("draft") or {}
            blueprint = self.infer_agent_blueprint(draft.get("purpose", ""), draft.get("specification", ""))
            updated = self.session_store.patch(
                context.session_id,
                {
                    "configured_agent": {
                        **blueprint,
                        "purpose": draft.get("purpose", blueprint.get("description", "")),
                        "specification": draft.get("specification", ""),
                        "status": "active",
                        "knowledge_records": configured_agent.get("knowledge_records", {}),
                    },
                    "agent_setup": {"active": False, "stage": "completed", "draft": draft},
                },
            )
            return {
                "message": f"已完成创建{blueprint['role']}，并建立所需的知识采集结构。",
                "dialog_state": {"stage": "completed"},
                "agent": self.build_configured_agent_payload(updated),
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
                schedule_records = self._extract_schedule_knowledge_records(text, extract_records)
                if schedule_records:
                    records, vector_records = self._persist_knowledge_records(configured_agent, schedule_records)
                    updated = self.session_store.patch(
                        context.session_id,
                        {
                            "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                            "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                        },
                    )
                    base_message = str(configured_agent.get("knowledge_added_message") or "已完成添加，并已记录该信息。")
                    message = base_message if len(schedule_records) == 1 else f"已完成添加，并记录了{len(schedule_records)}条{configured_agent.get('knowledge_entity_label', '信息')}。"
                    return {
                        "message": message,
                        "dialog_state": {"stage": "knowledge_added"},
                        "knowledge": schedule_records[0] if len(schedule_records) == 1 else schedule_records,
                        "knowledge_vector_record": vector_records[0] if len(vector_records) == 1 else vector_records,
                        "agent": self.build_configured_agent_payload(updated),
                    }

            if not collection.get("active"):
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
            value = sanitize_member_value(current_field["key"], text)
            if current_field["key"] == field_defs[-1]["key"] and completion_phrase in text:
                if value:
                    data[current_field["key"]] = value
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
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                        "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                    },
                )
                return {
                    "message": str(configured_agent.get("knowledge_added_message") or "已完成添加，并已记录该信息。"),
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

        return {"message": "当前没有可执行的信息型智能体操作。"}

    def query_information_knowledge(self, *, text: str, context: CoreContextSchema) -> dict[str, Any]:
        state = self.session_store.get(context.session_id)
        configured_agent = state.get("configured_agent") or {}
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