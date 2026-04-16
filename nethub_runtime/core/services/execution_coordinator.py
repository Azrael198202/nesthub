from __future__ import annotations

import json
import os
import re
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from nethub_runtime.core.config.settings import INTENT_POLICY_PATH, SEMANTIC_POLICY_PATH
from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


LOGGER = logging.getLogger("nethub_runtime.core.execution_coordinator")


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
        self.semantic_policy_store = SemanticPolicyStore(policy_path=self.semantic_policy_path)
        self.intent_policy = self._load_intent_policy()
        self.semantic_policy = self._load_semantic_policy()
        self._embedding_model = self._init_embedding_model()

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
        model_records = self._model_parse_records(text)
        if model_records is not None:
            return model_records

        split_patterns = self._require_semantic_value("segment_split_patterns", list)
        split_regex = "|".join(f"(?:{pattern})" for pattern in split_patterns)
        segments = [segment.strip() for segment in re.split(split_regex, text) if segment.strip()]
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
        alias = self.semantic_policy.get("entity_aliases", {}).get("actor", {})
        normalized = self._normalize_text(text)
        for canonical, aliases in alias.items():
            if any(self._normalize_text(a) in normalized for a in aliases):
                return canonical
        return "self"

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
        if semantic_label:
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
            "metric": "sum",
            "terms": dynamic_terms,
            "group_by": group_by,
            "time_marker": self._extract_time(text),
            "filters": filters,
            "query_text": text,
        }
        self._learn_semantic_candidates(text, stage="query_parsing")
        return query

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
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, dict):
            flattened: list[str] = []
            for key, nested_value in value.items():
                if str(key).strip():
                    flattened.append(str(key))
                if isinstance(nested_value, list):
                    flattened.extend(str(item) for item in nested_value if str(item).strip())
                elif nested_value not in (None, ""):
                    flattened.append(str(nested_value))
            return flattened
        return []

    def _existing_learning_values(self, policy_key: str) -> set[str]:
        existing: set[str] = set()
        if policy_key == "entity_aliases.actor":
            actor_aliases = self.semantic_policy.get("entity_aliases", {}).get("actor", {})
            for canonical, aliases in actor_aliases.items():
                existing.add(self._normalize_text(str(canonical)))
                existing.update(self._normalize_text(str(alias)) for alias in aliases)
            return existing

        current_value = self.semantic_policy.get(policy_key)
        if isinstance(current_value, list):
            existing.update(self._normalize_text(str(item)) for item in current_value)
        elif isinstance(current_value, dict):
            for key, nested_value in current_value.items():
                existing.add(self._normalize_text(str(key)))
                if isinstance(nested_value, list):
                    existing.update(self._normalize_text(str(item)) for item in nested_value)
                elif nested_value not in (None, ""):
                    existing.add(self._normalize_text(str(nested_value)))
        elif current_value not in (None, ""):
            existing.add(self._normalize_text(str(current_value)))
        return existing
