from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import Any

from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH


class InformationProfileSignalAnalyzer:
    def __init__(self, model_router: Any | None = None, semantic_policy_store: SemanticPolicyStore | None = None) -> None:
        self.model_router = model_router
        self.semantic_policy_store = semantic_policy_store or SemanticPolicyStore(policy_path=SEMANTIC_POLICY_PATH)
        self._cache: dict[str, dict[str, Any]] = {}

    def _runtime_semantic_policy(self) -> dict[str, Any]:
        try:
            return self.semantic_policy_store.load_runtime_policy()
        except Exception:
            return {}

    def _information_collection_policy(self) -> dict[str, Any]:
        payload = self._runtime_semantic_policy().get("information_collection", {})
        return payload if isinstance(payload, dict) else {}

    def _default_completion_phrase(self) -> str:
        collection_policy = self._information_collection_policy()
        configured = str(collection_policy.get("default_completion_phrase") or "").strip()
        if configured:
            return configured
        phrases = [str(item).strip() for item in collection_policy.get("completion_phrases", []) if str(item).strip()]
        return phrases[0] if phrases else ""

    def _entity_information_field_definitions(self) -> list[dict[str, str]]:
        return [
            {"key": "item_name", "prompt": "好的，请先告诉我要记录的对象名称。"},
            {"key": "item_type", "prompt": "它属于什么类型、身份或角色？"},
            {"key": "summary", "prompt": "请给出一句简要说明。"},
            {"key": "contact", "prompt": "如果有联系方式、地址或入口信息，请补充；没有可回答 无。"},
            {"key": "details", "prompt": "还有什么补充信息？如果没有了，请回答 完成添加。"},
        ]

    def analyze(self, purpose: str, specification: str = "") -> dict[str, Any]:
        combined = f"{purpose} {specification}".strip()
        cache_key = " ".join(combined.lower().split())
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        fallback_result = self._fallback_analysis(combined)

        remembered = self.semantic_policy_store.get_profile_signal(combined)
        if remembered:
            normalized = self._normalize_result(combined, self._merge_results(remembered, fallback_result))
            self._cache[cache_key] = normalized
            return dict(normalized)

        result = self._invoke_model_analysis(combined)
        if result:
            result = self._merge_results(result, fallback_result)
            self.semantic_policy_store.record_profile_signal(
                combined,
                result,
                confidence=0.85,
                source="model_router",
                evidence=combined,
            )
        if not result:
            result = fallback_result

        normalized = self._normalize_result(combined, result)
        self._cache[cache_key] = normalized
        return dict(normalized)

    def _merge_results(self, primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        raw_schema = primary.get("knowledge_schema")
        normalized_schema = [item for item in raw_schema if isinstance(item, dict)] if isinstance(raw_schema, list) else []
        raw_aliases = primary.get("query_aliases")
        normalized_aliases = {str(key): str(value) for key, value in raw_aliases.items()} if isinstance(raw_aliases, dict) else {}
        fallback_profile_seed = str(fallback.get("profile_seed") or "generic_information")
        prefer_fallback_schema = fallback_profile_seed != "generic_information"
        return {
            "profile_seed": fallback_profile_seed if prefer_fallback_schema else str(primary.get("profile_seed") or fallback_profile_seed),
            "entity_label": str(primary.get("entity_label") or fallback.get("entity_label") or "信息条目"),
            "role_name": str(fallback.get("role_name") or primary.get("role_name") or "信息管理智能体") if prefer_fallback_schema else str(primary.get("role_name") or fallback.get("role_name") or "信息管理智能体"),
            "knowledge_added_message": str(fallback.get("knowledge_added_message") or primary.get("knowledge_added_message") or "已完成添加，并已记录该信息。") if prefer_fallback_schema else str(primary.get("knowledge_added_message") or fallback.get("knowledge_added_message") or "已完成添加，并已记录该信息。"),
            "query_aliases": dict(fallback.get("query_aliases") or {}) if prefer_fallback_schema else (normalized_aliases or dict(fallback.get("query_aliases") or {})),
            "knowledge_schema": list(fallback.get("knowledge_schema") or []) if prefer_fallback_schema else (normalized_schema or list(fallback.get("knowledge_schema") or [])),
        }

    def _invoke_model_analysis(self, combined: str) -> dict[str, Any] | None:
        if self.model_router is None:
            return None

        prompt = (
            "Analyze the user request for an information-management agent and return JSON only.\n"
            "Infer an abstract profile instead of hardcoding business words in application logic.\n"
            "Return keys: profile_seed, entity_label, role_name, knowledge_added_message, query_aliases, knowledge_schema.\n"
            "Allowed profile_seed values: entity_directory, generic_information.\n"
            "knowledge_schema must be a list of objects with key and prompt.\n"
            f"user_request: {combined}"
        )

        holder: dict[str, Any] = {}

        def _runner() -> None:
            try:
                response = asyncio.run(
                    self.model_router.invoke(
                        task_type="intent_analysis",
                        prompt=prompt,
                        system_prompt="You are a schema planner for NestHub runtime. Return only valid JSON.",
                        temperature=0,
                    )
                )
                holder["response"] = response
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

    def _fallback_analysis(self, combined: str) -> dict[str, Any]:
        collection_policy = self._information_collection_policy()
        base_aliases = {
            str(key): str(value)
            for key, value in dict(collection_policy.get("field_aliases") or {}).items()
        }
        default_completion_phrase = self._default_completion_phrase()
        entity_label = self._extract_entity_label(combined)
        profile_seed = self._infer_profile_seed(combined, entity_label)

        if profile_seed == "entity_directory":
            normalized_label = entity_label or "信息对象"
            return {
                "profile_seed": "entity_directory",
                "entity_label": normalized_label,
                "role_name": f"{normalized_label}信息管理智能体",
                "knowledge_added_message": f"已完成添加，并已记录该{normalized_label}信息。",
                "query_aliases": base_aliases,
                "knowledge_schema": self._entity_information_field_definitions(),
                "completion_phrase": default_completion_phrase,
            }

        return {
            "profile_seed": "generic_information",
            "entity_label": entity_label or "信息条目",
            "role_name": "信息管理智能体",
            "knowledge_added_message": "已完成添加，并已记录该信息。",
            "query_aliases": {},
            "knowledge_schema": self._entity_information_field_definitions(),
            "completion_phrase": default_completion_phrase,
        }

    def _extract_entity_label(self, combined: str) -> str:
        text = re.sub(r"\s+", " ", combined).strip()
        patterns = (
            r"(?:创建|完成创建|建立|生成|添加)([\u4e00-\u9fffA-Za-z0-9_-]{2,20}?)(?:的)?(?:信息)?智能体",
            r"([\u4e00-\u9fffA-Za-z0-9_-]{2,20}?)(?:信息)?智能体",
            r"记录([\u4e00-\u9fffA-Za-z0-9_-]{2,20}?)的信息",
            r"主要记录([\u4e00-\u9fffA-Za-z0-9_-]{2,20}?)的信息",
            r"主要记录([\u4e00-\u9fffA-Za-z0-9_-]{2,20}?)(?:，|,|。|\s|进行创建|创建)",
            r"主要记录(.{2,40}?)(?:的)?(?:联系方式|联系信息|通讯信息)",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = self._normalize_entity_label(match.group(1))
                if candidate:
                    return candidate
        return ""

    def _infer_profile_seed(self, combined: str, entity_label: str) -> str:
        if entity_label:
            return "entity_directory"
        return "generic_information"

    def _normalize_entity_label(self, raw: str) -> str:
        candidate = re.sub(r"[。；;，,、]+$", "", raw).strip(" 的")
        candidate = re.sub(r"^(?:老师|医生|同事)这类", "", candidate)
        candidate = candidate.replace("这类", "")
        candidate = candidate.strip()
        return candidate

    def _normalize_result(self, combined: str, payload: dict[str, Any]) -> dict[str, Any]:
        schema = payload.get("knowledge_schema")
        normalized_schema = [item for item in schema if isinstance(item, dict)] if isinstance(schema, list) else []
        raw_aliases = payload.get("query_aliases")
        normalized_aliases = {str(key): str(value) for key, value in raw_aliases.items()} if isinstance(raw_aliases, dict) else {}
        return {
            "combined_text": combined,
            "profile_seed": str(payload.get("profile_seed") or "generic_information"),
            "entity_label": str(payload.get("entity_label") or "信息条目"),
            "role_name": str(payload.get("role_name") or "信息管理智能体"),
            "knowledge_added_message": str(payload.get("knowledge_added_message") or "已完成添加，并已记录该信息。"),
            "completion_phrase": str(payload.get("completion_phrase") or self._default_completion_phrase()),
            "query_aliases": normalized_aliases,
            "knowledge_schema": normalized_schema,
        }