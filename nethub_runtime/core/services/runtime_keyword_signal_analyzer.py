from __future__ import annotations

import asyncio
import json
import re
import threading
from typing import Any

from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore


class RuntimeKeywordSignalAnalyzer:
    """Generate runtime semantic action signals via model-first analysis with a generic fallback."""

    def __init__(self, model_router: Any | None = None, semantic_policy_store: SemanticPolicyStore | None = None) -> None:
        self.model_router = model_router
        self.semantic_policy_store = semantic_policy_store
        self._cache: dict[str, dict[str, Any]] = {}

    def analyze(self, text: str) -> dict[str, Any]:
        normalized = " ".join(text.strip().split())
        cache_key = normalized.lower()
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        fallback_payload = self._fallback_analysis(normalized)
        memory_payload = self._lookup_runtime_knowledge(normalized)
        payload = self._invoke_model(normalized)
        if payload is None:
            payload = memory_payload or fallback_payload
        else:
            payload = self._merge_payloads(self._normalize_payload(payload), memory_payload or fallback_payload)

        if memory_payload is not None and payload is not memory_payload:
            payload = self._merge_payloads(payload, memory_payload)

        normalized_payload = self._normalize_payload(payload)
        if isinstance(payload, dict) and isinstance(payload.get("knowledge_match"), dict):
            normalized_payload["knowledge_match"] = dict(payload["knowledge_match"])
        self._cache[cache_key] = normalized_payload
        return dict(normalized_payload)

    def _merge_payloads(self, primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for key in ("query_markers", "record_markers", "agent_markers", "goal_terms", "intent_hints"):
            merged[key] = list(dict.fromkeys((primary.get(key, []) or []) + (fallback.get(key, []) or [])))

        primary_flags = primary.get("action_flags", {}) if isinstance(primary.get("action_flags"), dict) else {}
        fallback_flags = fallback.get("action_flags", {}) if isinstance(fallback.get("action_flags"), dict) else {}
        merged["action_flags"] = {
            "query_like": bool(primary_flags.get("query_like") or fallback_flags.get("query_like")),
            "record_like": bool(primary_flags.get("record_like") or fallback_flags.get("record_like")),
            "agent_create_like": bool(primary_flags.get("agent_create_like") or fallback_flags.get("agent_create_like")),
            "finalize_like": bool(primary_flags.get("finalize_like") or fallback_flags.get("finalize_like")),
            "knowledge_capture_like": bool(primary_flags.get("knowledge_capture_like") or fallback_flags.get("knowledge_capture_like")),
            "multimodal_like": bool(primary_flags.get("multimodal_like") or fallback_flags.get("multimodal_like")),
        }
        return merged

    def _invoke_model(self, text: str) -> dict[str, Any] | None:
        if self.model_router is None:
            return None

        prompt = (
            "Analyze the user input and return JSON only. "
            "Infer semantic action signals without assuming a fixed language or fixed keywords. "
            "Return keys: query_markers, record_markers, agent_markers, goal_terms, intent_hints, action_flags. "
            "intent_hints must be a list of high-level intents such as create_information_agent, refine_information_agent, finalize_information_agent, capture_agent_knowledge, query_agent_knowledge, data_query, data_record, general_task. "
            "action_flags must be an object with boolean keys query_like, record_like, agent_create_like, finalize_like, knowledge_capture_like, multimodal_like. "
            f"user_input: {text}"
        )
        holder: dict[str, Any] = {}

        def _runner() -> None:
            try:
                response = asyncio.run(
                    self.model_router.invoke(
                        task_type="intent_analysis",
                        prompt=prompt,
                        system_prompt="Return valid JSON only.",
                        temperature=0,
                    )
                )
                holder["response"] = response
            except Exception as exc:
                holder["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=15)
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

    def _lookup_runtime_knowledge(self, text: str) -> dict[str, Any] | None:
        if self.semantic_policy_store is None:
            return None
        knowledge = self.semantic_policy_store.match_intent_knowledge(text)
        if not knowledge:
            return None
        normalized = self._normalize_payload(
            {
                "query_markers": knowledge.get("query_markers", []),
                "record_markers": knowledge.get("record_markers", []),
                "agent_markers": knowledge.get("agent_markers", []),
                "goal_terms": knowledge.get("goal_terms", []),
                "intent_hints": knowledge.get("intent_hints", []),
                "action_flags": knowledge.get("action_flags", {}),
            }
        )
        normalized["knowledge_match"] = {
            "intent": knowledge.get("intent"),
            "domain": knowledge.get("domain"),
            "match_score": knowledge.get("match_score"),
            "match_type": knowledge.get("match_type"),
            "source": knowledge.get("source"),
        }
        return normalized

    def _runtime_query_markers(self) -> list[str]:
        if self.semantic_policy_store is None:
            return []
        try:
            policy = self.semantic_policy_store.load_runtime_policy()
        except Exception:
            return []
        if not isinstance(policy, dict):
            return []
        markers: list[str] = []
        for item in list(policy.get("query_markers", []) or []):
            value = str(item).strip()
            if value and value not in markers:
                markers.append(value)
        intent_detection = policy.get("intent_detection", {})
        if isinstance(intent_detection, dict):
            for item in list(intent_detection.get("query_markers", []) or []):
                value = str(item).strip()
                if value and value not in markers:
                    markers.append(value)
        info_collection = policy.get("information_collection", {})
        if isinstance(info_collection, dict):
            for item in list(info_collection.get("list_query_markers", []) or []):
                value = str(item).strip()
                if value and value not in markers:
                    markers.append(value)
        return markers

    def _fallback_analysis(self, text: str) -> dict[str, Any]:
        tokens = self._tokenize(text)
        lowered = text.lower()
        query_markers = self._runtime_query_markers()
        question_like = any(symbol in text for symbol in ("?", "？")) or any(marker in text or marker.lower() in lowered for marker in query_markers)
        numeric_like = bool(re.search(r"\d", text))
        create_like = any(token.lower() in {"agent", "create", "build", "assistant"} for token in tokens)
        finalize_like = any(token.lower() in {"done", "finish", "complete", "finalize"} for token in tokens)
        capture_like = numeric_like and not question_like
        if "智能体" in text:
            create_like = True
        if "完成创建" in text or "完成智能体" in text:
            finalize_like = True
        if configured_capture := any(marker in text for marker in ("添加", "记录", "保存", "录入")):
            capture_like = True
        return {
            "query_markers": tokens[:4] if question_like else [],
            "record_markers": tokens[:4] if numeric_like else [],
            "agent_markers": tokens[:4] if create_like else [],
            "goal_terms": tokens[:6],
            "intent_hints": [
                "query_agent_knowledge" if question_like else "",
                "data_record" if numeric_like else "",
                "create_information_agent" if create_like else "",
                "finalize_information_agent" if finalize_like else "",
                "capture_agent_knowledge" if configured_capture else "",
            ],
            "action_flags": {
                "query_like": question_like,
                "record_like": numeric_like,
                "agent_create_like": create_like,
                "finalize_like": finalize_like,
                "knowledge_capture_like": capture_like,
                "multimodal_like": False,
            },
        }

    def _tokenize(self, text: str) -> list[str]:
        raw_tokens = re.split(r"[^\w\u4e00-\u9fff\-]+", text.lower())
        deduped: list[str] = []
        for token in raw_tokens:
            normalized = token.strip("_-")
            if len(normalized) < 2:
                continue
            if normalized not in deduped:
                deduped.append(normalized)
        return deduped

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in ("query_markers", "record_markers", "agent_markers", "goal_terms", "intent_hints"):
            values = payload.get(key, [])
            if not isinstance(values, list):
                values = []
            normalized: list[str] = []
            for item in values:
                item_text = str(item).strip()
                if len(item_text) < 2:
                    continue
                if item_text not in normalized:
                    normalized.append(item_text)
            result[key] = normalized
        action_flags = payload.get("action_flags", {})
        if not isinstance(action_flags, dict):
            action_flags = {}
        result["action_flags"] = {
            "query_like": bool(action_flags.get("query_like", False)),
            "record_like": bool(action_flags.get("record_like", False)),
            "agent_create_like": bool(action_flags.get("agent_create_like", False)),
            "finalize_like": bool(action_flags.get("finalize_like", False)),
            "knowledge_capture_like": bool(action_flags.get("knowledge_capture_like", False)),
            "multimodal_like": bool(action_flags.get("multimodal_like", False)),
        }
        return result
