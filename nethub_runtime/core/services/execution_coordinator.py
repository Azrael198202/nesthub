from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from nethub_runtime.core.config.settings import INTENT_POLICY_PATH, SEMANTIC_POLICY_PATH
from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


class ExecutionCoordinator:
    """Executes workflow nodes with semantic filtering and model-routed fallback aggregation."""

    def __init__(
        self,
        session_store: SessionStore | None = None,
        intent_policy_path: Path | None = None,
        semantic_policy_path: Path | None = None,
    ) -> None:
        self.session_store = session_store or SessionStore()
        self.intent_policy_path = intent_policy_path or INTENT_POLICY_PATH
        self.semantic_policy_path = semantic_policy_path or SEMANTIC_POLICY_PATH
        self.intent_policy = self._load_intent_policy()
        self.semantic_policy = self._load_semantic_policy()
        self._embedding_model = self._init_embedding_model()

    def _load_intent_policy(self) -> dict[str, Any]:
        if self.intent_policy_path.exists():
            return json.loads(self.intent_policy_path.read_text(encoding="utf-8"))
        return {"time_markers": [], "stopwords": [], "group_by_markers": [], "numeric_value_patterns": []}

    def _load_semantic_policy(self) -> dict[str, Any]:
        if self.semantic_policy_path.exists():
            return json.loads(self.semantic_policy_path.read_text(encoding="utf-8"))
        return {
            "tokenizer": {"preferred": "regex", "fallback": "regex", "min_token_length": 2},
            "semantic_matching": {
                "method": "embedding_or_token",
                "embedding_model": "",
                "similarity_threshold": 0.62,
                "fallback_to_external_threshold": 0.35,
            },
            "normalization": {"text_replace": {}, "synonyms": {}},
            "entity_aliases": {"actor": {}, "label": {}},
            "ignored_query_tokens": [],
            "external_semantic_router": {"enabled": False},
        }

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
                            "status": "completed",
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
                            {"step_id": step["step_id"], "name": step["name"], "status": "failed", "error": last_error}
                        )
        results["final_output"] = step_outputs
        return results

    def _run_step(self, step: dict[str, Any], task: TaskSchema, context: CoreContextSchema, step_outputs: dict[str, Any]) -> dict[str, Any]:
        step_name = step["name"]
        if step_name == "extract_records":
            records = self._extract_records(task.input_text)
            return {"records": records, "count": len(records)}
        if step_name == "persist_records":
            records = step_outputs.get("extract_records", {}).get("records", [])
            state = self.session_store.append_records(context.session_id, records)
            return {"saved": len(records), "total_records": len(state.get("records", []))}
        if step_name == "parse_query":
            state = self.session_store.get(context.session_id)
            return {"query": self._parse_query(task.input_text, state.get("records", []))}
        if step_name == "aggregate_query":
            query = step_outputs.get("parse_query", {}).get("query", {})
            state = self.session_store.get(context.session_id)
            model_choice = ((step.get("capability") or {}).get("model_choice") or {})
            return {"aggregation": self._aggregate_records(state.get("records", []), query, model_choice)}
        if step_name == "ocr_extract":
            return {"artifact_type": "text", "status": "dispatched", "task": "ocr", "message": "OCR dispatch prepared."}
        if step_name == "stt_transcribe":
            return {"artifact_type": "text", "status": "dispatched", "task": "stt", "message": "STT dispatch prepared."}
        if step_name == "tts_synthesize":
            return {"artifact_type": "audio", "status": "dispatched", "task": "tts", "message": "TTS dispatch prepared."}
        if step_name == "image_generate":
            return {"artifact_type": "image", "status": "dispatched", "task": "image_generation"}
        if step_name == "video_generate":
            return {"artifact_type": "video", "status": "dispatched", "task": "video_generation"}
        if step_name == "file_generate":
            return {"artifact_type": "file", "status": "dispatched", "task": "file_generation"}
        if step_name == "web_retrieve":
            return {"artifact_type": "web_content", "status": "dispatched", "task": "web_research"}
        if step_name == "web_summarize":
            return {"artifact_type": "summary", "status": "dispatched", "task": "web_summary"}
        return {"message": "no-op"}

    def _extract_records(self, text: str) -> list[dict[str, Any]]:
        segments = [segment.strip() for segment in re.split(r"[。；;\n]|还有|并且|and", text) if segment.strip()]
        records: list[dict[str, Any]] = []
        for segment in segments:
            amount = self._extract_amount(segment)
            if amount is None:
                continue
            records.append(
                {
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
        for marker in self.intent_policy.get("time_markers", []):
            if marker in text:
                return marker
        return "unspecified"

    def _extract_location(self, text: str) -> str | None:
        for marker in ("在", "去", "于", "at", "in"):
            if marker in text:
                candidate = text.split(marker, 1)[-1].strip()
                return re.split(r"[，,。 ]", candidate)[0] or None
        return None

    def _extract_content(self, text: str) -> str:
        cleaned = re.sub(r"\d+(?:\.\d+)?\s*(日元|円|yen|usd|rmb|元|块|美元|￥|\$)?", "", text, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" ，,.。")
        return cleaned or "entry"

    def _extract_participants(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*人", text)
        if match:
            return int(match.group(1))
        if "两个人" in text:
            return 2
        return None

    def _extract_actor(self, text: str) -> str:
        alias = self.semantic_policy.get("entity_aliases", {}).get("actor", {})
        normalized = self._normalize_text(text)
        for canonical, aliases in alias.items():
            if any(self._normalize_text(a) in normalized for a in aliases):
                return canonical
        return "self"

    def _infer_label(self, text: str) -> str:
        alias = self.semantic_policy.get("entity_aliases", {}).get("label", {})
        normalized = self._normalize_text(text)
        for canonical, aliases in alias.items():
            if any(self._normalize_text(a) in normalized for a in aliases):
                return canonical
        return "other"

    def _parse_query(self, text: str, existing_records: list[dict[str, Any]]) -> dict[str, Any]:
        stopwords = set(self.intent_policy.get("stopwords", []))
        ignored_tokens = set(self.semantic_policy.get("ignored_query_tokens", []))
        normalized = text
        for stopword in stopwords:
            normalized = normalized.replace(stopword, " ")
        tokens = self._tokenize(normalized)
        terms = [tok for tok in tokens if tok not in stopwords and tok not in ignored_tokens]

        filters = self._infer_alias_filters(text)
        m = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,})地区", text)
        if m:
            filters["location_keyword"] = m.group(1)

        record_matched_terms = self._find_terms_from_records(text, existing_records)
        dynamic_terms = record_matched_terms or self._extract_dynamic_terms(terms, existing_records)
        group_by = self._extract_group_by(text)
        return {
            "metric": "sum",
            "terms": dynamic_terms,
            "group_by": group_by,
            "time_marker": self._extract_time(text),
            "filters": filters,
            "query_text": text,
        }

    def _find_terms_from_records(self, query_text: str, existing_records: list[dict[str, Any]]) -> list[str]:
        terms: list[str] = []
        query_tokens = self._tokenize(query_text)
        norm_query = self._normalize_text(query_text)
        for item in existing_records:
            for field in ("content", "location", "label", "actor"):
                value = self._normalize_text(str(item.get(field, "")).strip())
                if len(value) < 2:
                    continue
                if value in norm_query and value not in terms:
                    terms.append(value)
                    continue
                for token in query_tokens:
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
        marker_map = {
            "按时间": "time",
            "按类别": "label",
            "按地点": "location",
            "按人员": "actor",
        }
        for marker in self.intent_policy.get("group_by_markers", []):
            if marker in text and marker in marker_map:
                results.append(marker_map[marker])
        return results

    def _aggregate_records(self, records: list[dict[str, Any]], query: dict[str, Any], model_choice: dict[str, Any]) -> dict[str, Any]:
        # 只要涉及归属相关的聚合请求，直接 fallback 到外部模型
        filters = query.get("filters", {})
        group_by = query.get("group_by", [])
        time_marker = query.get("time_marker")
        # 只要 filters 里有任意归属相关字段且有值，或 group_by 非空，或 time_marker 有值且非 unspecified，则强制 fallback
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
            print(f"[归属fallback触发] filters={filters}, group_by={group_by}, time_marker={time_marker}")
            prompt_query = dict(query)
            prompt_query["_aggregation_belonging"] = True
            external = self._external_semantic_aggregate(prompt_query, records, model_choice)
            if external is not None:
                print("[归属fallback] 外部模型聚合成功")
                return external
            else:
                print("[归属fallback] 外部模型未返回结果，降级本地")
        # 否则走本地逻辑
        filtered = list(records)
        time_marker = query.get("time_marker")
        if time_marker and time_marker != "unspecified":
            filtered = [item for item in filtered if item.get("time") == time_marker or time_marker in str(item.get("time"))]
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
        return {
            "total_amount": total_amount,
            "count": len(filtered),
            "grouped": grouped,
            "semantic_mode": "local",
            "semantic_confidence": round(confidence, 4),
        }

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
            for canonical, alias_list in mapping.items():
                if any(self._normalize_text(alias) in normalized_query for alias in alias_list):
                    filters[field] = canonical
                    break
        return filters

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
            "instruction": "请根据 records 和 query 的归属关系进行聚合，输出 total_amount/count/grouped。归属包括家庭、企业组织、时间、地区等。",
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
