from __future__ import annotations

import json
import os
import re
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from nethub_runtime.core.config.settings import INTENT_POLICY_PATH, SEMANTIC_POLICY_PATH
from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.memory.vector_store import VectorStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.execution_handler_registry import build_executor_handlers, build_step_handlers


LOGGER = logging.getLogger("nethub_runtime.core.execution_coordinator")


class ExecutionCoordinator:
    """Executes workflow nodes with semantic filtering and model-routed fallback aggregation."""

    def __init__(
        self,
        session_store: SessionStore | None = None,
        vector_store: VectorStore | None = None,
        intent_policy_path: Path | None = None,
        semantic_policy_path: Path | None = None,
    ) -> None:
        self.session_store = session_store or SessionStore()
        self.vector_store = vector_store or VectorStore()
        self.intent_policy_path = intent_policy_path or INTENT_POLICY_PATH
        self.semantic_policy_path = semantic_policy_path or SEMANTIC_POLICY_PATH
        self.semantic_policy_store = SemanticPolicyStore(policy_path=self.semantic_policy_path)
        self.intent_policy = self._load_intent_policy()
        self.semantic_policy = self._load_semantic_policy()
        self._embedding_model = self._init_embedding_model()
        self._executor_handlers = build_executor_handlers(self)
        self._step_handlers = build_step_handlers(self)

    def _load_intent_policy(self) -> dict[str, Any]:
        if self.intent_policy_path.exists():
            return json.loads(self.intent_policy_path.read_text(encoding="utf-8"))
        return {"time_markers": [], "stopwords": [], "group_by_markers": [], "numeric_value_patterns": []}

    def _load_semantic_policy(self) -> dict[str, Any]:
        policy = self.semantic_policy_store.load_runtime_policy()
        if not policy:
            policy = {
            "tokenizer": {"preferred": "regex", "fallback": "regex", "min_token_length": 2},
            "semantic_matching": {
                "method": "embedding_or_token",
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                "similarity_threshold": 0.62,
                "fallback_to_external_threshold": 0.35,
            },
            "normalization": {"text_replace": {}, "synonyms": {}},
            "entity_aliases": {"actor": {}},
            "label_taxonomy": {},
            "semantic_label_threshold": 0.32,
            "ignored_query_tokens": [],
            "policy_memory": {"enabled": False},
            "external_semantic_router": {"enabled": False},
        }
        try:
            self._validate_semantic_policy(policy)
            return policy
        except ValueError as exc:
            rolled_back = self.semantic_policy_store.record_runtime_failure(reason=str(exc))
            if rolled_back:
                refreshed = self.semantic_policy_store.load_runtime_policy()
                self._validate_semantic_policy(refreshed)
                return refreshed
            raise

    def _validate_semantic_policy(self, policy: dict[str, Any]) -> None:
        required_top_level = (
            "location_markers",
            "participant_pattern",
            "participant_aliases",
            "group_by_aliases",
            "location_keyword_patterns",
            "segment_split_patterns",
            "content_cleanup_patterns",
            "time_marker_rules",
        )
        missing = [key for key in required_top_level if key not in policy]
        if missing:
            raise ValueError(f"semantic policy missing required keys: {', '.join(missing)}")
        if not isinstance(policy.get("location_markers"), list) or not policy["location_markers"]:
            raise ValueError("semantic policy location_markers must be a non-empty list")
        if not isinstance(policy.get("participant_aliases"), dict):
            raise ValueError("semantic policy participant_aliases must be a dict")
        if not isinstance(policy.get("group_by_aliases"), dict) or not policy["group_by_aliases"]:
            raise ValueError("semantic policy group_by_aliases must be a non-empty dict")
        if not isinstance(policy.get("location_keyword_patterns"), list):
            raise ValueError("semantic policy location_keyword_patterns must be a list")
        if not isinstance(policy.get("segment_split_patterns"), list) or not policy["segment_split_patterns"]:
            raise ValueError("semantic policy segment_split_patterns must be a non-empty list")
        if not isinstance(policy.get("content_cleanup_patterns"), list):
            raise ValueError("semantic policy content_cleanup_patterns must be a list")
        if not isinstance(policy.get("time_marker_rules"), dict) or not policy["time_marker_rules"]:
            raise ValueError("semantic policy time_marker_rules must be a non-empty dict")

    def _refresh_semantic_policy(self) -> None:
        self.semantic_policy = self.semantic_policy_store.load_runtime_policy()
        self._validate_semantic_policy(self.semantic_policy)

    def _require_semantic_value(self, key: str, expected_type: type[Any]) -> Any:
        value = self.semantic_policy.get(key)
        if not isinstance(value, expected_type):
            raise ValueError(f"semantic policy key '{key}' must be {expected_type.__name__}")
        return value

    def _init_embedding_model(self) -> Any | None:
        model_name = self.semantic_policy.get("semantic_matching", {}).get("embedding_model")
        if not model_name:
            return None
        try:
            from sentence_transformers import SentenceTransformer

            return SentenceTransformer(model_name)
        except Exception:
            return None

    def execute(self, plan: list[dict[str, Any]], task: TaskSchema, context: CoreContextSchema) -> dict[str, Any]:
        results: dict[str, Any] = {"steps": [], "task_intent": task.intent}
        step_outputs: dict[str, Any] = {}
        for step in plan:
            retries = step.get("retry", 0)
            attempt = 0
            last_error: str | None = None
            while attempt <= retries:
                try:
                    output = self._run_step(step, task, context, step_outputs)
                    step_outputs[step["name"]] = output
                    results["steps"].append(
                        {
                            "step_id": step["step_id"],
                            "name": step["name"],
                            "executor_type": step.get("executor_type", "unknown"),
                            "status": "completed",
                            "inputs": step.get("inputs", []),
                            "outputs": step.get("outputs", []),
                            "selector": step.get("selector", {}),
                            "capability": step.get("capability", {}),
                            "runtime_capabilities": step.get("runtime_capabilities", {}),
                            "output": output,
                        }
                    )
                    break
                except Exception as exc:  # pragma: no cover
                    last_error = str(exc)
                    attempt += 1
                    if attempt > retries:
                        results["steps"].append(
                            {
                                "step_id": step["step_id"],
                                "name": step["name"],
                                "executor_type": step.get("executor_type", "unknown"),
                                "status": "failed",
                                "inputs": step.get("inputs", []),
                                "outputs": step.get("outputs", []),
                                "selector": step.get("selector", {}),
                                "error": last_error,
                            }
                        )
        results["final_output"] = step_outputs
        return results

    def _run_step(self, step: dict[str, Any], task: TaskSchema, context: CoreContextSchema, step_outputs: dict[str, Any]) -> dict[str, Any]:
        executor_type = step.get("executor_type", "tool")
        executor_handler = self._executor_handlers.get(executor_type)
        if not executor_handler:
            return {"message": f"unsupported executor type: {executor_type}"}
        return executor_handler(step, task, context, step_outputs)

    def _dispatch_agent_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        _step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._step_handlers.get("agent", {}).get(step["name"])
        if not handler:
            return {"message": f"unsupported agent step: {step['name']}"}
        return handler(step, task, context, _step_outputs)

    def _dispatch_knowledge_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        _step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._step_handlers.get("knowledge_retrieval", {}).get(step["name"])
        if not handler:
            return {"message": f"unsupported knowledge step: {step['name']}"}
        return handler(step, task, context, _step_outputs)

    def _dispatch_tool_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._step_handlers.get("tool", {}).get(step["name"])
        if not handler:
            return {"message": f"unsupported tool step: {step['name']}"}
        return handler(step, task, context, step_outputs)

    def _dispatch_llm_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return self._run_llm_step(step["name"], task, context)

    def _dispatch_code_step(
        self,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return self._run_code_step(step["name"], task, context, step_outputs)

    def _handle_manage_information_agent_step(
        self,
        _step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        _step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return self._manage_information_agent(task.input_text, task, context)

    def _handle_query_information_knowledge_step(
        self,
        _step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        _step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return self._query_information_knowledge(task.input_text, context)

    def _run_llm_step(self, step_name: str, task: TaskSchema, context: CoreContextSchema) -> dict[str, Any]:
        return {"message": f"llm step placeholder for {step_name}", "input_text": task.input_text, "session_id": context.session_id}

    def _run_code_step(
        self,
        step_name: str,
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "message": f"code step placeholder for {step_name}",
            "input_text": task.input_text,
            "session_id": context.session_id,
            "available_step_outputs": list(step_outputs.keys()),
        }

    def _default_information_field_definitions(self) -> list[dict[str, str]]:
        return [
            {"key": "item_name", "prompt": "好的，请问要记录的对象名称是什么？"},
            {"key": "item_type", "prompt": "它属于什么类型或角色？"},
            {"key": "summary", "prompt": "请给出一句简要说明。"},
            {"key": "details", "prompt": "还有什么需要记录的？如果没有了，请回答 完成添加。"},
        ]

    def _family_member_field_definitions(self) -> list[dict[str, str]]:
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

    def _family_agent_schema_fields(self) -> list[str]:
        return [item["key"] for item in self._family_member_field_definitions()]

    def _normalize_slug(self, text: str) -> str:
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", text.lower()).strip("_")
        return normalized or "information_agent"

    def _infer_agent_blueprint(self, purpose: str, specification: str = "") -> dict[str, Any]:
        combined = f"{purpose} {specification}".strip()
        if any(keyword in combined for keyword in ("家庭成员", "成员信息", "家庭信息", "爸爸", "妈妈", "孩子")):
            return {
                "agent_id": "family_member_info_agent",
                "name": "family_member_info_agent",
                "role": "家庭成员信息管理智能体",
                "description": purpose or "主要记录家庭成员的信息。",
                "knowledge_namespace": "agent_knowledge/family_member_info_agent",
                "knowledge_entity_label": "家庭成员",
                "knowledge_schema": self._family_member_field_definitions(),
                "query_aliases": {
                    "手机号": "phone",
                    "电话": "phone",
                    "邮箱": "email",
                    "line": "extra_notes",
                    "公司": "extra_notes",
                    "联系电话": "extra_notes",
                },
                "completion_phrase": "完成添加",
            }
        slug = self._normalize_slug(purpose or specification or "information_agent")
        return {
            "agent_id": slug,
            "name": slug,
            "role": "信息管理智能体",
            "description": purpose or "用于记录和查询结构化信息。",
            "knowledge_namespace": f"agent_knowledge/{slug}",
            "knowledge_entity_label": "信息条目",
            "knowledge_schema": self._default_information_field_definitions(),
            "query_aliases": {},
            "completion_phrase": "完成添加",
        }

    def _normalize_yes_no(self, text: str) -> bool:
        lowered = self._normalize_text(text)
        return any(token in lowered for token in ("是", "参与", "需要", "yes", "true", "y"))

    def _sanitize_member_value(self, key: str, text: str) -> Any:
        value = text.strip()
        if key in {"include_expense", "include_schedule"}:
            return self._normalize_yes_no(value)
        if key == "extra_notes":
            value = value.replace("完成添加", "").strip()
            return value
        return value

    def _find_record_by_text(self, text: str, records: dict[str, Any], schema_fields: list[dict[str, str]]) -> dict[str, Any] | None:
        candidate_keys = [item.get("key", "") for item in schema_fields]
        for record in records.values():
            for key in candidate_keys:
                token = str(record.get(key, ""))
                if token and token in text:
                    return record
        return None

    def _answer_record_field(self, text: str, record: dict[str, Any], field_aliases: dict[str, str], entity_label: str) -> str:
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

    def _build_configured_agent_payload(self, state: dict[str, Any]) -> dict[str, Any]:
        configured_agent = state.get("configured_agent") or {}
        return {
            "agent_id": configured_agent.get("agent_id", "information_agent"),
            "name": configured_agent.get("name", "information_agent"),
            "role": configured_agent.get("role", "信息管理智能体"),
            "description": configured_agent.get("description", configured_agent.get("purpose", "用于记录和查询结构化信息。")),
            "knowledge_namespace": configured_agent.get("knowledge_namespace", "agent_knowledge/information_agent"),
            "knowledge_entity_label": configured_agent.get("knowledge_entity_label", "信息条目"),
            "schema_fields": [item.get("key") for item in configured_agent.get("knowledge_schema", self._default_information_field_definitions())],
            "knowledge_records": list((configured_agent.get("knowledge_records") or {}).values()),
            "status": configured_agent.get("status", "draft"),
        }

    def _manage_information_agent(self, text: str, task: TaskSchema, context: CoreContextSchema) -> dict[str, Any]:
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
                "agent": self._build_configured_agent_payload(updated),
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
                    "message": "好的，还有什么需要特别指定的。如果没有，请回答：完成创建家庭成员信息智能体。",
                    "dialog_state": {"stage": "awaiting_confirmation"},
                    "agent": self._build_configured_agent_payload(updated),
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
                    "message": "好的。如果已经没有补充要求，请回答：完成创建家庭成员信息智能体。",
                    "dialog_state": {"stage": "awaiting_confirmation"},
                    "agent": self._build_configured_agent_payload(updated),
                }

        if task.intent == "finalize_information_agent" and setup.get("active"):
            draft = setup.get("draft") or {}
            blueprint = self._infer_agent_blueprint(draft.get("purpose", ""), draft.get("specification", ""))
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
                "agent": self._build_configured_agent_payload(updated),
            }

        if task.intent == "capture_agent_knowledge":
            if configured_agent.get("status") != "active" and not collection.get("active"):
                return {
                    "message": "当前还没有完成信息型智能体的创建，请先完成创建。",
                    "dialog_state": {"stage": "configured_agent_missing"},
                }

            field_defs = configured_agent.get("knowledge_schema") or self._default_information_field_definitions()
            completion_phrase = str(configured_agent.get("completion_phrase") or "完成添加")
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
                    "agent": self._build_configured_agent_payload(updated),
                }

            current_index = int(collection.get("field_index", 0))
            current_field = field_defs[current_index]
            data = dict(collection.get("data") or {})
            value = self._sanitize_member_value(current_field["key"], text)
            if current_field["key"] == field_defs[-1]["key"] and completion_phrase in text:
                if value:
                    data[current_field["key"]] = value
                record_id = f"knowledge_{len((configured_agent.get('knowledge_records') or {})) + 1}"
                record = {"record_id": record_id, **data}
                records = {**(configured_agent.get("knowledge_records") or {}), record_id: record}
                content = "\n".join(f"{item['key']}: {record.get(item['key'], '')}" for item in field_defs)
                vector_record = self.vector_store.add_knowledge(
                    namespace=str(configured_agent.get("knowledge_namespace") or "agent_knowledge/information_agent"),
                    content=content,
                    metadata={
                        "agent_id": configured_agent.get("agent_id"),
                        "record_id": record_id,
                        "record": record,
                        "entity_label": configured_agent.get("knowledge_entity_label", "信息条目"),
                    },
                    item_id=record_id,
                )
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                        "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                    },
                )
                return {
                    "message": "已完成添加，并已记录该家庭成员信息。",
                    "dialog_state": {"stage": "knowledge_added"},
                    "knowledge": record,
                    "knowledge_vector_record": vector_record,
                    "agent": self._build_configured_agent_payload(updated),
                }

            data[current_field["key"]] = value
            next_index = current_index + 1
            if next_index >= len(field_defs):
                record_id = f"knowledge_{len((configured_agent.get('knowledge_records') or {})) + 1}"
                record = {"record_id": record_id, **data}
                records = {**(configured_agent.get("knowledge_records") or {}), record_id: record}
                content = "\n".join(f"{item['key']}: {record.get(item['key'], '')}" for item in field_defs)
                vector_record = self.vector_store.add_knowledge(
                    namespace=str(configured_agent.get("knowledge_namespace") or "agent_knowledge/information_agent"),
                    content=content,
                    metadata={
                        "agent_id": configured_agent.get("agent_id"),
                        "record_id": record_id,
                        "record": record,
                        "entity_label": configured_agent.get("knowledge_entity_label", "信息条目"),
                    },
                    item_id=record_id,
                )
                updated = self.session_store.patch(
                    context.session_id,
                    {
                        "configured_agent": {**configured_agent, "knowledge_records": records, "status": "active"},
                        "knowledge_collection": {"active": False, "field_index": 0, "fields": field_defs, "data": {}},
                    },
                )
                return {
                    "message": "已完成添加，并已记录该家庭成员信息。",
                    "dialog_state": {"stage": "knowledge_added"},
                    "knowledge": record,
                    "knowledge_vector_record": vector_record,
                    "agent": self._build_configured_agent_payload(updated),
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
                "agent": self._build_configured_agent_payload(updated),
            }

        return {"message": "当前没有可执行的信息型智能体操作。"}

    def _query_information_knowledge(self, text: str, context: CoreContextSchema) -> dict[str, Any]:
        state = self.session_store.get(context.session_id)
        configured_agent = state.get("configured_agent") or {}
        records = configured_agent.get("knowledge_records") or {}
        if configured_agent.get("status") != "active":
            return {"message": "当前还没有完成信息型智能体的创建。", "answer": None, "knowledge_hits": []}
        schema_fields = configured_agent.get("knowledge_schema") or self._default_information_field_definitions()
        entity_label = str(configured_agent.get("knowledge_entity_label") or "信息条目")
        record = self._find_record_by_text(text, records, schema_fields)
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
        answer = self._answer_record_field(text, record, configured_agent.get("query_aliases") or {}, entity_label)
        return {"message": answer, "answer": answer, "knowledge": record, "knowledge_hits": knowledge_hits}

    def _extract_records(self, text: str) -> list[dict[str, Any]]:
        model_records = self._model_parse_records(text)
        if model_records is not None:
            return model_records

        split_patterns = self._require_semantic_value("segment_split_patterns", list)
        split_regex = "|".join(f"(?:{pattern})" for pattern in split_patterns)
        segments = [segment.strip() for segment in re.split(split_regex, text) if segment.strip()]
        records: list[dict[str, Any]] = []
        for segment in segments:
            record_type = self._infer_record_type(segment)
            if record_type != "expense":
                type_rule = self.semantic_policy.get("record_type_rules", {}).get(record_type, {})
                records.append(
                    {
                        "record_type": record_type,
                        "time": self._extract_time(segment),
                        "location": self._extract_location(segment),
                        "content": self._extract_content(segment),
                        "amount": int(type_rule.get("default_amount", 0)),
                        "participants": self._extract_participants(segment),
                        "actor": self._extract_actor(segment),
                        "label": str(type_rule.get("default_label", record_type)),
                        "raw_text": segment,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
                continue
            amount = self._extract_amount(segment)
            if amount is not None:
                records.append(
                    {
                        "record_type": "expense",
                        "time": self._extract_time(segment),
                        "location": self._extract_location(segment),
                        "content": self._extract_content(segment),
                        "amount": amount,
                        "participants": self._extract_participants(segment),
                        "actor": self._extract_actor(segment),
                        "label": self._infer_label(segment),
                        "raw_text": segment,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
                continue
        self._learn_semantic_candidates(text, stage="record_extraction")
        return records

    def _extract_amount(self, text: str) -> int | None:
        for pattern in self.intent_policy.get("numeric_value_patterns", []):
            matched = re.search(pattern, text, flags=re.IGNORECASE)
            if matched:
                value = matched.group(1)
                if value:
                    return int(float(value))
        fallback = re.search(r"(\d+(?:\.\d+)?)", text)
        if fallback:
            return int(float(fallback.group(1)))
        return None

    def _extract_time(self, text: str) -> str:
        explicit_date = self._extract_explicit_date(text)
        if explicit_date:
            return explicit_date
        relative_week_date = self._extract_relative_week_date(text)
        if relative_week_date:
            return relative_week_date
        for marker in self.intent_policy.get("time_markers", []):
            if marker in text:
                return marker
        return "unspecified"

    def _extract_location(self, text: str) -> str | None:
        markers = self._require_semantic_value("location_markers", list)
        for marker in markers:
            if marker in text:
                candidate = text.split(marker, 1)[-1].strip()
                return re.split(r"[，,。 ]", candidate)[0] or None
        return None

    def _extract_content(self, text: str) -> str:
        cleaned = text
        for pattern in self._require_semantic_value("content_cleanup_patterns", list):
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(str(self.semantic_policy.get("content_strip_chars", " ")))
        return cleaned or "entry"

    def _extract_participants(self, text: str) -> int | None:
        participant_pattern = self._require_semantic_value("participant_pattern", str)
        match = re.search(participant_pattern, text)
        if match:
            return int(match.group(1))
        participant_aliases = self._require_semantic_value("participant_aliases", dict)
        for alias, count in participant_aliases.items():
            if alias in text:
                return int(count)
        return None

    def _extract_actor(self, text: str) -> str:
        named_actor = self._extract_named_actor(text)
        if named_actor:
            return named_actor
        alias = self.semantic_policy.get("entity_aliases", {}).get("actor", {})
        normalized = self._normalize_text(text)
        for canonical, aliases in alias.items():
            if any(self._normalize_text(a) in normalized for a in aliases):
                return canonical
        return "self"

    def _extract_named_actor(self, text: str) -> str | None:
        match = re.match(r"^([\u4e00-\u9fffA-Za-z]{2,4})(?=今天|昨天|本周|下周|\d{1,2}月\d{1,2}号|去|开会|远足|安排)", text.strip())
        if match:
            return match.group(1)
        return None

    def _extract_explicit_date(self, text: str) -> str | None:
        match = re.search(r"(\d{1,2})月(\d{1,2})号", text)
        if not match:
            return None
        now = datetime.now(UTC)
        month = int(match.group(1))
        day = int(match.group(2))
        return f"{now.year:04d}-{month:02d}-{day:02d}"

    def _extract_relative_week_date(self, text: str) -> str | None:
        match = re.search(r"本周([一二三四五六日天])", text)
        if not match:
            return None
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        target_weekday = weekday_map[match.group(1)]
        now = datetime.now(UTC)
        monday = now - timedelta(days=now.weekday())
        target = monday + timedelta(days=target_weekday)
        return target.date().isoformat()

    def _infer_record_type(self, text: str) -> str:
        record_type_rules = self.semantic_policy.get("record_type_rules", {})
        if not isinstance(record_type_rules, dict):
            return "expense"

        default_type = "expense"
        for record_type, rule in record_type_rules.items():
            if isinstance(rule, dict) and rule.get("default"):
                default_type = str(record_type)
                break

        for record_type, rule in record_type_rules.items():
            if record_type == default_type or not isinstance(rule, dict):
                continue
            if self._rule_matches_text(text, rule):
                return str(record_type)
        return default_type

    def _rule_matches_text(self, text: str, rule: dict[str, Any]) -> bool:
        if rule.get("require_time") and self._extract_time(text) == "unspecified":
            return False
        required_any = [str(item) for item in rule.get("required_any", []) if str(item).strip()]
        reject_any = [str(item) for item in rule.get("reject_any", []) if str(item).strip()]
        if required_any and not any(marker in text for marker in required_any):
            return False
        if reject_any and any(marker in text for marker in reject_any):
            return False
        return True

    def _infer_label(self, text: str) -> str:
        semantic_label = self._semantic_label_from_text(text)
        if semantic_label:
            return semantic_label
        return "other"

    def _parse_query(self, text: str, existing_records: list[dict[str, Any]]) -> dict[str, Any]:
        model_query = self._model_parse_query(text, existing_records)
        if model_query is not None:
            return model_query

        stopwords = set(self.intent_policy.get("stopwords", []))
        ignored_tokens = set(self.semantic_policy.get("ignored_query_tokens", []))
        normalized = text
        for stopword in stopwords:
            normalized = normalized.replace(stopword, " ")
        tokens = self._tokenize(normalized)
        terms = [tok for tok in tokens if tok not in stopwords and tok not in ignored_tokens]

        filters = self._infer_alias_filters(text)
        semantic_label = self._semantic_label_from_text(text)
        if semantic_label and self._query_has_explicit_label_signal(text, semantic_label):
            filters["label"] = semantic_label
        for pattern in self._require_semantic_value("location_keyword_patterns", list):
            matched = re.search(pattern, text)
            if matched:
                filters["location_keyword"] = matched.group(1)
                break

        record_matched_terms = self._find_terms_from_records(text, existing_records)
        dynamic_terms = record_matched_terms or self._extract_dynamic_terms(terms, existing_records)
        group_by = self._extract_group_by(text)
        query = {
            "metric": self._infer_query_metric(text, existing_records),
            "terms": dynamic_terms,
            "group_by": group_by,
            "time_marker": self._extract_time(text),
            "filters": filters,
            "query_text": text,
        }
        self._learn_semantic_candidates(text, stage="query_parsing")
        return query

    def _infer_query_metric(self, text: str, existing_records: list[dict[str, Any]]) -> str:
        metric_rules = self.semantic_policy.get("query_metric_rules", {})
        if isinstance(metric_rules, dict):
            for metric, rule in metric_rules.items():
                if not isinstance(rule, dict):
                    continue
                required_type = rule.get("requires_record_type")
                if required_type and not any(item.get("record_type") == required_type for item in existing_records):
                    continue
                if self._rule_matches_text(text, rule):
                    return str(metric)
        return "sum"

    def _query_has_explicit_label_signal(self, text: str, label: str) -> bool:
        normalized_text = self._normalize_text(text)
        synonym_map = self.semantic_policy.get("normalization", {}).get("synonyms", {})
        taxonomy = self.semantic_policy.get("label_taxonomy", {})
        label_config = taxonomy.get(label, {}) if isinstance(taxonomy, dict) else {}
        examples = label_config.get("examples", []) if isinstance(label_config, dict) else []
        lexical_hints = {
            self._normalize_text(str(item))
            for item in [*synonym_map.get(label, []), *examples]
            if len(self._normalize_text(str(item))) >= 2
        }
        return any(hint in normalized_text for hint in lexical_hints)

    def _find_terms_from_records(self, query_text: str, existing_records: list[dict[str, Any]]) -> list[str]:
        terms: list[str] = []
        query_tokens = self._tokenize(query_text)
        ignored_tokens = {
            self._normalize_text(token)
            for token in self.semantic_policy.get("ignored_query_tokens", [])
        }
        norm_query = self._normalize_text(query_text)
        for item in existing_records:
            for field in ("content", "location", "label", "actor"):
                value = self._normalize_text(str(item.get(field, "")).strip())
                if len(value) < 2:
                    continue
                if value in norm_query and value not in terms:
                    if value in ignored_tokens:
                        continue
                    terms.append(value)
                    continue
                for token in query_tokens:
                    normalized_token = self._normalize_text(token)
                    if normalized_token in ignored_tokens:
                        continue
                    if token in value and token not in terms:
                        terms.append(token)
        return terms

    def _extract_dynamic_terms(self, terms: list[str], existing_records: list[dict[str, Any]]) -> list[str]:
        if not existing_records:
            return terms
        corpus = " ".join(
            self._normalize_text(
                f"{item.get('content','')} {item.get('location','')} {item.get('label','')} {item.get('actor','')}"
            )
            for item in existing_records
        )
        return [self._normalize_text(term) for term in terms if self._normalize_text(term) in corpus]

    def _extract_group_by(self, text: str) -> list[str]:
        results: list[str] = []
        marker_map = self._require_semantic_value("group_by_aliases", dict)
        for marker in self.intent_policy.get("group_by_markers", []):
            if marker in text and marker in marker_map:
                results.append(marker_map[marker])
        return results

    def _model_parse_records(self, text: str) -> list[dict[str, Any]] | None:
        parser_cfg = self.semantic_policy.get("model_semantic_parser", {})
        if not parser_cfg.get("enabled", True) or not parser_cfg.get("prefer_model_for_record_extraction", True):
            return None

        payload = {
            "instruction": "Extract structured records from input_text and return a records array with time, location, content, amount, participants, actor, label, and raw_text.",
            "input_text": text,
            "schema": {
                "records": [
                    {
                        "time": "string",
                        "location": "string|null",
                        "content": "string",
                        "amount": "number",
                        "participants": "number|null",
                        "actor": "string",
                        "label": "string",
                        "raw_text": "string",
                    }
                ]
            },
        }
        data = self._call_external_semantic_parser(payload)
        if not data:
            return None

        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            return None

        normalized_records: list[dict[str, Any]] = []
        for item in raw_records:
            if not isinstance(item, dict):
                continue
            try:
                amount = int(float(item.get("amount", 0)))
            except Exception:
                continue
            normalized_records.append(
                {
                    "time": str(item.get("time") or "unspecified"),
                    "location": item.get("location"),
                    "content": str(item.get("content") or "entry"),
                    "amount": amount,
                    "participants": item.get("participants"),
                    "actor": str(item.get("actor") or "self"),
                    "label": str(item.get("label") or "other"),
                    "raw_text": str(item.get("raw_text") or text),
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        return normalized_records or None

    def _model_parse_query(self, text: str, existing_records: list[dict[str, Any]]) -> dict[str, Any] | None:
        parser_cfg = self.semantic_policy.get("model_semantic_parser", {})
        if not parser_cfg.get("enabled", True) or not parser_cfg.get("prefer_model_for_query_parsing", True):
            return None

        payload = {
            "instruction": "Parse query_text into an aggregate query and return metric, terms, group_by, time_marker, filters, and query_text.",
            "query_text": text,
            "existing_records": existing_records,
            "schema": {
                "metric": "sum",
                "terms": ["string"],
                "group_by": ["time|label|location|actor"],
                "time_marker": "string",
                "filters": {"actor": "string", "label": "string", "location_keyword": "string"},
                "query_text": "string",
            },
        }
        data = self._call_external_semantic_parser(payload)
        if not data:
            return None

        required = ("metric", "terms", "group_by", "time_marker", "filters", "query_text")
        if not all(key in data for key in required):
            return None
        if not isinstance(data.get("terms"), list) or not isinstance(data.get("group_by"), list):
            return None
        if not isinstance(data.get("filters"), dict):
            return None
        return {
            "metric": data.get("metric") or "sum",
            "terms": [self._normalize_text(str(t)) for t in data.get("terms", []) if str(t).strip()],
            "group_by": [str(dim) for dim in data.get("group_by", []) if str(dim).strip()],
            "time_marker": str(data.get("time_marker") or "unspecified"),
            "filters": {str(k): v for k, v in data.get("filters", {}).items() if v not in (None, "")},
            "query_text": str(data.get("query_text") or text),
        }

    def _call_external_semantic_parser(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        router = self.semantic_policy.get("external_semantic_router", {})
        if not router.get("enabled", False):
            return None

        endpoint = os.getenv(router.get("generic_endpoint_env", "NETHUB_LLM_ROUTER_ENDPOINT"), "").strip()
        if not endpoint:
            return None

        request_body = {
            "task": "semantic_parse",
            "provider_priority": router.get("provider_priority", []),
            "payload": payload,
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(endpoint, json=request_body)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            LOGGER.debug("External semantic parse failed: %s", exc)
            return None
        return None

    def _aggregate_records(self, records: list[dict[str, Any]], query: dict[str, Any], model_choice: dict[str, Any]) -> dict[str, Any]:
        filters = query.get("filters", {})
        group_by = query.get("group_by", [])
        time_marker = query.get("time_marker")
        metric = str(query.get("metric", "sum"))
        belonging_keys = ["actor", "label", "location_keyword"]
        has_belonging = False
        for k in belonging_keys:
            if k in filters and filters[k]:
                has_belonging = True
        if group_by:
            has_belonging = True
        if time_marker and time_marker != "unspecified":
            has_belonging = True
        if has_belonging:
            LOGGER.debug("Semantic aggregate fallback triggered: filters=%s group_by=%s time_marker=%s", filters, group_by, time_marker)
            prompt_query = dict(query)
            prompt_query["_aggregation_belonging"] = True
            external = self._external_semantic_aggregate(prompt_query, records, model_choice)
            if external is not None:
                return external
        filtered = list(records)
        time_marker = query.get("time_marker")
        if time_marker and time_marker != "unspecified":
            filtered = [item for item in filtered if self._record_matches_time_marker(item, str(time_marker))]
        if "actor" in filters:
            filtered = [item for item in filtered if str(item.get("actor", "")) == str(filters["actor"])]
        if "label" in filters:
            filtered = [item for item in filtered if str(item.get("label", "")) == str(filters["label"])]
        if "location_keyword" in filters:
            keyword = self._normalize_text(str(filters["location_keyword"]))
            filtered = [item for item in filtered if keyword in self._normalize_text(str(item.get("location", "")))]
        terms = query.get("terms", [])
        confidence = 1.0
        if terms:
            strict_filtered = self._strict_term_filter(filtered, terms)
            if strict_filtered:
                filtered = strict_filtered
                confidence = 1.0
            else:
                semantic_filtered, confidence = self._semantic_filter_records(filtered, terms)
                filtered = semantic_filtered
                fallback_threshold = float(self.semantic_policy.get("semantic_matching", {}).get("fallback_to_external_threshold", 0.35))
                if confidence < fallback_threshold:
                    external = self._external_semantic_aggregate(query, records, model_choice)
                    if external is not None:
                        return external
        total_amount = sum(int(item.get("amount", 0)) for item in filtered)
        grouped: dict[str, dict[str, int]] = {}
        for dim in query.get("group_by", []):
            grouped[dim] = {}
            for item in filtered:
                key = str(item.get(dim, "unknown"))
                grouped[dim][key] = grouped[dim].get(key, 0) + int(item.get("amount", 0))
        response = {
            "total_amount": total_amount,
            "count": len(filtered),
            "grouped": grouped,
            "semantic_mode": "local",
            "semantic_confidence": round(confidence, 4),
        }
        if metric == "list":
            response["matched_records"] = [
                {
                    "record_type": item.get("record_type", "expense"),
                    "actor": item.get("actor"),
                    "time": item.get("time"),
                    "location": item.get("location"),
                    "content": item.get("content"),
                    "label": item.get("label"),
                }
                for item in filtered
            ]
        return response

    def _strict_term_filter(self, records: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
        normalized_terms = [self._normalize_text(term) for term in terms if self._normalize_text(term)]
        if not normalized_terms:
            return []
        strict: list[dict[str, Any]] = []
        for item in records:
            blob = self._normalize_text(
                f"{item.get('content','')} {item.get('location','')} {item.get('label','')} {item.get('actor','')}"
            )
            if all(term in blob for term in normalized_terms):
                strict.append(item)
        return strict

    def _normalize_text(self, text: str) -> str:
        normalized = text.lower().strip()
        replace_map = self.semantic_policy.get("normalization", {}).get("text_replace", {})
        for src, target in replace_map.items():
            normalized = normalized.replace(src.lower(), target.lower())
        return normalized

    def _tokenize(self, text: str) -> list[str]:
        text = self._normalize_text(text)
        preferred = self.semantic_policy.get("tokenizer", {}).get("preferred", "regex")
        min_len = int(self.semantic_policy.get("tokenizer", {}).get("min_token_length", 2))
        if preferred == "jieba":
            try:
                import jieba

                tokens = [tok.strip() for tok in jieba.lcut(text) if tok.strip()]
                return [tok for tok in tokens if len(tok) >= min_len]
            except Exception:
                pass
        tokens = [tok for tok in re.split(r"[\s，,。；;！？!?]+", text) if tok]
        return [tok for tok in tokens if len(tok) >= min_len]

    def _infer_alias_filters(self, query_text: str) -> dict[str, str]:
        filters: dict[str, str] = {}
        aliases = self.semantic_policy.get("entity_aliases", {})
        normalized_query = self._normalize_text(query_text)
        for field, mapping in aliases.items():
            if field == "label":
                continue
            for canonical, alias_list in mapping.items():
                if any(self._normalize_text(alias) in normalized_query for alias in alias_list):
                    filters[field] = canonical
                    break
        return filters

    def _semantic_label_from_text(self, text: str) -> str | None:
        taxonomy = self.semantic_policy.get("label_taxonomy", {})
        if not isinstance(taxonomy, dict) or not taxonomy:
            return None

        normalized_text = self._normalize_text(text)
        scored_labels: list[tuple[float, str]] = []
        threshold = float(self.semantic_policy.get("semantic_label_threshold", 0.32))
        margin_threshold = float(self.semantic_policy.get("semantic_label_margin", 0.08))
        synonym_map = self.semantic_policy.get("normalization", {}).get("synonyms", {})

        for label, config in taxonomy.items():
            if not isinstance(config, dict):
                continue
            description = str(config.get("description", "")).strip()
            examples = config.get("examples", [])
            synonyms = synonym_map.get(str(label), [])
            profile_text = " ".join([description, *[str(item) for item in examples], *[str(item) for item in synonyms]])
            if not profile_text.strip():
                continue
            score = self._embedding_similarity(normalized_text, self._normalize_text(profile_text))
            lexical_hints = {
                self._normalize_text(str(item))
                for item in [*examples, *synonyms]
                if len(self._normalize_text(str(item))) >= 2
            }
            synonym_hints = {
                self._normalize_text(str(item))
                for item in synonyms
                if len(self._normalize_text(str(item))) >= 2
            }
            synonym_hits = sum(1 for hint in synonym_hints if hint and hint in normalized_text)
            lexical_hits = sum(1 for hint in lexical_hints if hint and hint in normalized_text)
            if lexical_hits or synonym_hits:
                score = min(1.0, score + min(0.5, 0.28 * synonym_hits + 0.08 * max(0, lexical_hits - synonym_hits)))
            scored_labels.append((score, str(label)))

        if not scored_labels:
            return None

        scored_labels.sort(reverse=True)
        best_score, best_label = scored_labels[0]
        second_score = scored_labels[1][0] if len(scored_labels) > 1 else 0.0
        if best_score >= threshold and (best_score - second_score) >= margin_threshold:
            return best_label
        return None

    def _record_matches_time_marker(self, item: dict[str, Any], time_marker: str) -> bool:
        normalized_marker = self._normalize_text(time_marker)
        record_time = self._normalize_text(str(item.get("time", "")))

        if not normalized_marker or normalized_marker == "unspecified":
            return True
        if normalized_marker in record_time:
            return True

        created_at_raw = str(item.get("created_at", "")).strip()
        created_at = None
        if created_at_raw:
            try:
                created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            except Exception:
                created_at = None

        now = datetime.now(UTC)
        for rule in self._require_semantic_value("time_marker_rules", dict).values():
            aliases = {self._normalize_text(alias) for alias in rule.get("aliases", [])}
            if normalized_marker not in aliases:
                continue
            record_aliases = {self._normalize_text(alias) for alias in rule.get("record_aliases", [])}
            if record_time in record_aliases:
                return True
            match_mode = str(rule.get("match_mode", "exact"))
            if match_mode == "same_day":
                return created_at.date() == now.date() if created_at else False
            if match_mode == "same_month":
                return bool(created_at and created_at.year == now.year and created_at.month == now.month)
            if match_mode == "prefix":
                prefixes = [self._normalize_text(prefix) for prefix in rule.get("prefixes", [])]
                return any(record_time.startswith(prefix) for prefix in prefixes)
            return record_time == normalized_marker
        return False

    def _token_similarity(self, left: str, right: str) -> float:
        left_tokens = set(self._tokenize(left))
        right_tokens = set(self._tokenize(right))
        if not left_tokens or not right_tokens:
            return 0.0
        inter = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return inter / union if union else 0.0

    def _embedding_similarity(self, left: str, right: str) -> float:
        if self._embedding_model is None:
            return self._token_similarity(left, right)
        try:
            vectors = self._embedding_model.encode([left, right], normalize_embeddings=True)
            dot = float(sum(a * b for a, b in zip(vectors[0], vectors[1])))
            return max(0.0, min(1.0, dot))
        except Exception:
            return self._token_similarity(left, right)

    def _semantic_filter_records(self, records: list[dict[str, Any]], terms: list[str]) -> tuple[list[dict[str, Any]], float]:
        if not records or not terms:
            return records, 1.0
        threshold = float(self.semantic_policy.get("semantic_matching", {}).get("similarity_threshold", 0.62))
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in records:
            text_blob = self._normalize_text(
                f"{item.get('content','')} {item.get('location','')} {item.get('label','')} {item.get('actor','')}"
            )
            similarities = [self._embedding_similarity(self._normalize_text(term), text_blob) for term in terms]
            score = max(similarities) if similarities else 0.0
            scored.append((score, item))
        filtered = [item for score, item in scored if score >= threshold]
        confidence = max([score for score, _ in scored], default=0.0)
        # If no semantic hit, keep current filtered set; fallback logic handles low confidence.
        return (filtered if filtered else records, confidence)

    def _external_semantic_aggregate(
        self,
        query: dict[str, Any],
        records: list[dict[str, Any]],
        model_choice: dict[str, Any],
    ) -> dict[str, Any] | None:
        router = self.semantic_policy.get("external_semantic_router", {})
        if not router.get("enabled", False):
            return None
        endpoint = os.getenv(router.get("generic_endpoint_env", "NETHUB_LLM_ROUTER_ENDPOINT"), "").strip()
        if not endpoint:
            return None
        prompt = {
            "instruction": "Aggregate records according to query relationships and return total_amount, count, and grouped.",
            "query": query,
            "records": records,
            "model_choice": model_choice,
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=prompt)
                resp.raise_for_status()
                data = resp.json()
                if all(k in data for k in ("total_amount", "count", "grouped")):
                    data["semantic_mode"] = "external_fallback"
                    return data
        except Exception:
            return None
        return None

    def _learn_semantic_candidates(self, text: str, *, stage: str) -> None:
        policy_memory = self.semantic_policy.get("policy_memory", {})
        learning_cfg = policy_memory.get("learning", {})
        if not policy_memory.get("enabled", False) or not learning_cfg.get("enabled", False):
            return

        payload = {
            "instruction": "Analyze input_text and propose semantic policy candidate deltas for the current runtime. Return only additions for supported keys and skip anything already present.",
            "stage": stage,
            "input_text": text,
            "runtime_policy": {
                "location_markers": self.semantic_policy.get("location_markers", []),
                "participant_aliases": self.semantic_policy.get("participant_aliases", {}),
                "group_by_aliases": self.semantic_policy.get("group_by_aliases", {}),
                "entity_aliases": self.semantic_policy.get("entity_aliases", {}),
                "ignored_query_tokens": self.semantic_policy.get("ignored_query_tokens", []),
                "time_markers": self.intent_policy.get("time_markers", []),
                "record_type_rules": self.semantic_policy.get("record_type_rules", {}),
                "query_metric_rules": self.semantic_policy.get("query_metric_rules", {}),
            },
            "schema": {
                "candidates": [
                    {
                        "policy_key": "string",
                        "value": "json",
                        "confidence": "number",
                    }
                ]
            },
        }
        data = self._call_external_semantic_parser(payload)
        if not isinstance(data, dict):
            return

        candidates = data.get("candidates", [])
        if not isinstance(candidates, list):
            return

        max_updates = int(learning_cfg.get("max_updates_per_text", 8))
        default_confidence = float(learning_cfg.get("default_confidence", 0.82))
        applied = 0
        for item in candidates:
            if applied >= max_updates or not isinstance(item, dict):
                break
            policy_key = str(item.get("policy_key") or "").strip()
            value = item.get("value")
            confidence = float(item.get("confidence", default_confidence))
            if not policy_key:
                continue
            if not self._should_accept_learning_candidate(policy_key, value, learning_cfg):
                continue
            self.semantic_policy_store.record_candidate(
                policy_key,
                value,
                confidence=confidence,
                source=stage,
                evidence=text,
                metadata={"stage": stage},
            )
            applied += 1

        if applied:
            try:
                self._refresh_semantic_policy()
            except ValueError as exc:
                self.semantic_policy_store.record_runtime_failure(reason=str(exc))
                self._refresh_semantic_policy()

    def _should_accept_learning_candidate(self, policy_key: str, value: Any, learning_cfg: dict[str, Any]) -> bool:
        allowed_keys = set(learning_cfg.get("allowed_policy_keys", []))
        if allowed_keys and policy_key not in allowed_keys:
            return False

        flattened_values = self._flatten_learning_candidate_values(value)
        min_length = int(learning_cfg.get("min_candidate_text_length", 2))
        blocked_terms = {self._normalize_text(term) for term in learning_cfg.get("blocked_terms", [])}
        reject_existing_conflicts = bool(learning_cfg.get("reject_existing_conflicts", True))
        existing_values = self._existing_learning_values(policy_key) if reject_existing_conflicts else set()

        if not flattened_values:
            return False
        for item in flattened_values:
            normalized_item = self._normalize_text(item)
            if len(normalized_item) < min_length:
                return False
            if normalized_item in blocked_terms:
                return False
            if reject_existing_conflicts and normalized_item in existing_values:
                return False
        return True

    def _flatten_learning_candidate_values(self, value: Any) -> list[str]:
        flattened: list[str] = []

        def _collect(item: Any) -> None:
            if isinstance(item, str):
                if item.strip():
                    flattened.append(item)
                return
            if isinstance(item, list):
                for nested in item:
                    _collect(nested)
                return
            if isinstance(item, dict):
                for key, nested_value in item.items():
                    if str(key).strip():
                        flattened.append(str(key))
                    _collect(nested_value)
                return
            if item not in (None, ""):
                flattened.append(str(item))

        _collect(value)
        return flattened

    def _existing_learning_values(self, policy_key: str) -> set[str]:
        existing: set[str] = set()

        def _collect(item: Any) -> None:
            if isinstance(item, str):
                existing.add(self._normalize_text(item))
                return
            if isinstance(item, list):
                for nested in item:
                    _collect(nested)
                return
            if isinstance(item, dict):
                for key, nested_value in item.items():
                    existing.add(self._normalize_text(str(key)))
                    _collect(nested_value)
                return
            if item not in (None, ""):
                existing.add(self._normalize_text(str(item)))

        if policy_key == "entity_aliases.actor":
            actor_aliases = self.semantic_policy.get("entity_aliases", {}).get("actor", {})
            _collect(actor_aliases)
            return existing

        current_value = self.semantic_policy.get(policy_key)
        _collect(current_value)
        return existing
