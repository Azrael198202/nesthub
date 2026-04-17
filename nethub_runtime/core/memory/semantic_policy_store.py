from __future__ import annotations

import hashlib
import json
import sqlite3
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_MEMORY_DB_PATH, ensure_core_config_dir


class SemanticPolicyStore:
    """Read-only main policy plus writable local candidate memory."""

    SUPPORTED_POLICY_KEYS = {
        "location_markers": "list",
        "ignored_query_tokens": "list",
        "time_markers": "list",
        "segment_split_patterns": "list",
        "location_keyword_patterns": "list",
        "participant_aliases": "dict",
        "group_by_aliases": "dict",
        "entity_aliases.actor": "dict_list",
        "record_type_rules": "dict",
        "query_metric_rules": "dict",
    }

    def __init__(self, policy_path: Path, db_path: Path | None = None) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path
        self.db_path = db_path or SEMANTIC_POLICY_MEMORY_DB_PATH
        self._init_db()

    def load_main_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            return {}
        policy = json.loads(self.policy_path.read_text(encoding="utf-8"))
        self._snapshot_policy(policy, reason="main_policy_load", source="main")
        return policy

    def load_runtime_policy(self) -> dict[str, Any]:
        policy = self.load_main_policy()
        overlay = self._build_active_overlay()
        return self._merge_policy_overlay(policy, overlay)

    def record_candidate(
        self,
        policy_key: str,
        value: Any,
        *,
        confidence: float,
        source: str,
        evidence: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if policy_key not in self.SUPPORTED_POLICY_KEYS:
            return
        if not self._validate_candidate_shape(policy_key, value):
            return

        now = datetime.now(UTC).isoformat()
        normalized_value = self._normalize_candidate_value(value)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, hit_count, confidence, status
                FROM semantic_policy_candidates
                WHERE policy_key = ? AND normalized_value = ?
                """,
                (policy_key, normalized_value),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE semantic_policy_candidates
                    SET value_json = ?, confidence = ?, hit_count = ?, source = ?, evidence = ?, metadata_json = ?,
                        status = CASE WHEN status = 'rolled_back' THEN 'candidate' ELSE status END,
                        last_seen_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(value, ensure_ascii=False, sort_keys=True),
                        max(float(row[2] or 0.0), float(confidence)),
                        int(row[1] or 0) + 1,
                        source,
                        evidence,
                        json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                        int(row[0]),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO semantic_policy_candidates(
                        policy_key, value_json, normalized_value, confidence, hit_count, status,
                        source, evidence, metadata_json, failure_count, activated_at, first_seen_at, last_seen_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'candidate', ?, ?, ?, 0, NULL, ?, ?, ?)
                    """,
                    (
                        policy_key,
                        json.dumps(value, ensure_ascii=False, sort_keys=True),
                        normalized_value,
                        float(confidence),
                        1,
                        source,
                        evidence,
                        json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                        now,
                    ),
                )
            conn.commit()
        self.activate_eligible_candidates()

    def activate_eligible_candidates(self) -> int:
        policy = self.load_main_policy()
        config = policy.get("policy_memory", {})
        auto_activate = config.get("auto_activate", {})
        if not config.get("enabled", False) or not auto_activate.get("enabled", True):
            return 0

        min_hits = int(auto_activate.get("min_hits", 2))
        min_confidence = float(auto_activate.get("min_confidence", 0.75))
        activated = 0
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, policy_key, value_json
                FROM semantic_policy_candidates
                WHERE status = 'candidate' AND hit_count >= ? AND confidence >= ?
                ORDER BY updated_at ASC
                """,
                (min_hits, min_confidence),
            ).fetchall()
            for candidate_id, policy_key, value_json in rows:
                value = json.loads(value_json)
                if not self._validate_candidate_shape(str(policy_key), value):
                    continue
                conn.execute(
                    """
                    UPDATE semantic_policy_candidates
                    SET status = 'active', activated_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, int(candidate_id)),
                )
                activated += 1
            conn.commit()

        if activated:
            runtime_policy = self.load_runtime_policy()
            self._snapshot_policy(runtime_policy, reason="candidate_activation", source="runtime")
        return activated

    def record_runtime_failure(self, *, reason: str, policy_key: str | None = None) -> int:
        policy = self.load_main_policy()
        self_heal = policy.get("policy_memory", {}).get("self_heal", {})
        if not self_heal.get("enabled", False):
            return 0

        rollback_batch_size = int(self_heal.get("rollback_batch_size", 3))
        max_failures = int(self_heal.get("max_failures", 2))
        now = datetime.now(UTC).isoformat()
        rolled_back = 0
        with sqlite3.connect(self.db_path) as conn:
            if policy_key:
                rows = conn.execute(
                    """
                    SELECT id, failure_count
                    FROM semantic_policy_candidates
                    WHERE status = 'active' AND policy_key = ?
                    ORDER BY activated_at DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (policy_key, rollback_batch_size),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, failure_count
                    FROM semantic_policy_candidates
                    WHERE status = 'active'
                    ORDER BY activated_at DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (rollback_batch_size,),
                ).fetchall()
            for candidate_id, failure_count in rows:
                next_failures = int(failure_count or 0) + 1
                next_status = "rolled_back" if next_failures >= max_failures else "active"
                conn.execute(
                    """
                    UPDATE semantic_policy_candidates
                    SET failure_count = ?, status = ?, metadata_json = json_set(COALESCE(metadata_json, '{}'), '$.last_failure_reason', ?), updated_at = ?
                    WHERE id = ?
                    """,
                    (next_failures, next_status, reason, now, int(candidate_id)),
                )
                if next_status == "rolled_back":
                    rolled_back += 1
            conn.commit()

        if rolled_back:
            runtime_policy = self.load_runtime_policy()
            self._snapshot_policy(runtime_policy, reason=f"rollback:{reason}", source="runtime")
        return rolled_back

    def inspect_memory(self, *, policy_key: str | None = None, status: str | None = None) -> dict[str, Any]:
        allowed_statuses = {"candidate", "active", "rolled_back"}
        normalized_status = (status or "").strip() or None
        if normalized_status and normalized_status not in allowed_statuses:
            raise ValueError(f"unsupported semantic memory status filter: {normalized_status}")

        where_clauses: list[str] = []
        params: list[Any] = []
        if policy_key:
            where_clauses.append("policy_key = ?")
            params.append(policy_key)
        if normalized_status:
            where_clauses.append("status = ?")
            params.append(normalized_status)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            candidates = [self._row_to_candidate(dict(row)) for row in conn.execute(
                f"""
                SELECT *
                FROM semantic_policy_candidates
                {where_sql}
                ORDER BY updated_at DESC, id DESC
                """,
                params,
            ).fetchall()]
            latest_rollback_filters = list(where_clauses)
            latest_rollback_params = list(params)
            latest_rollback_filters.append("status = 'rolled_back'")
            latest_rollback_where = f"WHERE {' AND '.join(latest_rollback_filters)}"
            latest_rollback_row = conn.execute(
                f"""
                SELECT id, policy_key, evidence, metadata_json, updated_at
                FROM semantic_policy_candidates
                {latest_rollback_where}
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                latest_rollback_params,
            ).fetchone()
            version_rows = conn.execute(
                """
                SELECT content_hash, source, reason, created_at
                FROM semantic_policy_versions
                ORDER BY created_at DESC, id DESC
                LIMIT 10
                """
            ).fetchall()

        summary = {
            "candidate": sum(1 for item in candidates if item["status"] == "candidate"),
            "active": sum(1 for item in candidates if item["status"] == "active"),
            "rolled_back": sum(1 for item in candidates if item["status"] == "rolled_back"),
        }
        latest_rollback = None
        if latest_rollback_row:
            rollback_payload = dict(latest_rollback_row)
            metadata = json.loads(rollback_payload.get("metadata_json") or "{}")
            latest_rollback = {
                "candidate_id": rollback_payload["id"],
                "policy_key": rollback_payload["policy_key"],
                "reason": metadata.get("last_failure_reason"),
                "evidence": rollback_payload["evidence"],
                "updated_at": rollback_payload["updated_at"],
            }

        return {
            "backend": "sqlite",
            "db_path": str(self.db_path),
            "filters": {"policy_key": policy_key, "status": normalized_status},
            "learning_rules": self._learning_rules_snapshot(),
            "summary": summary,
            "candidates": candidates,
            "latest_rollback": latest_rollback,
            "recent_versions": [dict(row) for row in version_rows],
        }

    def get_profile_signal(self, request_text: str) -> dict[str, Any] | None:
        normalized_request = self._normalize_candidate_value({"request_text": request_text.strip().lower()})
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT value_json
                FROM semantic_policy_candidates
                WHERE policy_key = 'profile_signals' AND normalized_value = ? AND status IN ('candidate', 'active')
                ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, updated_at DESC
                LIMIT 1
                """,
                (normalized_request,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row[0])
        return payload if isinstance(payload, dict) else None

    def record_profile_signal(
        self,
        request_text: str,
        signal_payload: dict[str, Any],
        *,
        confidence: float,
        source: str,
        evidence: str = "",
    ) -> None:
        if not isinstance(signal_payload, dict) or not request_text.strip():
            return
        normalized_request = self._normalize_candidate_value({"request_text": request_text.strip().lower()})
        now = datetime.now(UTC).isoformat()
        payload_json = json.dumps(signal_payload, ensure_ascii=False, sort_keys=True)
        metadata = json.dumps({"request_text": request_text}, ensure_ascii=False, sort_keys=True)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, hit_count, confidence, status
                FROM semantic_policy_candidates
                WHERE policy_key = 'profile_signals' AND normalized_value = ?
                """,
                (normalized_request,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE semantic_policy_candidates
                    SET value_json = ?, confidence = ?, hit_count = ?, source = ?, evidence = ?, metadata_json = ?,
                        status = CASE WHEN status = 'rolled_back' THEN 'candidate' ELSE status END,
                        last_seen_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload_json,
                        max(float(row[2] or 0.0), float(confidence)),
                        int(row[1] or 0) + 1,
                        source,
                        evidence,
                        metadata,
                        now,
                        now,
                        int(row[0]),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO semantic_policy_candidates(
                        policy_key, value_json, normalized_value, confidence, hit_count, status,
                        source, evidence, metadata_json, failure_count, activated_at, first_seen_at, last_seen_at, updated_at
                    ) VALUES ('profile_signals', ?, ?, ?, ?, 'candidate', ?, ?, ?, 0, NULL, ?, ?, ?)
                    """,
                    (
                        payload_json,
                        normalized_request,
                        float(confidence),
                        1,
                        source,
                        evidence,
                        metadata,
                        now,
                        now,
                        now,
                    ),
                )
            conn.commit()

    def match_intent_knowledge(self, request_text: str, *, min_score: float = 0.6) -> dict[str, Any] | None:
        normalized_text = " ".join(request_text.strip().split()).lower()
        if not normalized_text:
            return None
        normalized_request = self._normalize_candidate_value({"request_text": normalized_text})
        request_tokens = self._tokenize_intent_text(normalized_text)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            exact_row = conn.execute(
                """
                SELECT *
                FROM runtime_intent_knowledge
                WHERE normalized_request = ?
                ORDER BY hit_count DESC, confidence DESC, updated_at DESC
                LIMIT 1
                """,
                (normalized_request,),
            ).fetchone()
            if exact_row:
                payload = self._row_to_intent_knowledge(dict(exact_row))
                payload["match_score"] = 1.0
                payload["match_type"] = "exact"
                return payload

            rows = conn.execute(
                """
                SELECT *
                FROM runtime_intent_knowledge
                ORDER BY hit_count DESC, confidence DESC, updated_at DESC
                LIMIT 50
                """
            ).fetchall()

        best_match: dict[str, Any] | None = None
        best_score = 0.0
        request_token_set = set(request_tokens)
        for row in rows:
            payload = self._row_to_intent_knowledge(dict(row))
            candidate_tokens = set(payload.get("tokens", []))
            if not request_token_set or not candidate_tokens:
                continue
            overlap = request_token_set & candidate_tokens
            union = request_token_set | candidate_tokens
            token_score = len(overlap) / len(union) if union else 0.0
            if token_score < min_score:
                continue
            score = min(1.0, token_score + min(float(payload.get("confidence", 0.0)), 1.0) * 0.1)
            if score > best_score:
                best_score = score
                best_match = payload

        if best_match is None:
            return None
        best_match["match_score"] = round(best_score, 4)
        best_match["match_type"] = "token_overlap"
        return best_match

    def record_intent_knowledge(
        self,
        request_text: str,
        knowledge_payload: dict[str, Any],
        *,
        source: str,
        confidence: float,
        evidence: str = "",
    ) -> None:
        normalized_text = " ".join(request_text.strip().split()).lower()
        if not normalized_text or not isinstance(knowledge_payload, dict):
            return

        now = datetime.now(UTC).isoformat()
        normalized_request = self._normalize_candidate_value({"request_text": normalized_text})
        tokens = self._tokenize_intent_text(normalized_text)
        markers = self._extract_runtime_marker_payload(knowledge_payload)
        payload_json = json.dumps(knowledge_payload, ensure_ascii=False, sort_keys=True)
        metadata_json = json.dumps({"request_text": request_text}, ensure_ascii=False, sort_keys=True)

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, hit_count, confidence
                FROM runtime_intent_knowledge
                WHERE normalized_request = ?
                """,
                (normalized_request,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE runtime_intent_knowledge
                    SET payload_json = ?, intent = ?, domain = ?, tokens_json = ?,
                        query_markers_json = ?, record_markers_json = ?, agent_markers_json = ?,
                        goal_terms_json = ?, intent_hints_json = ?, action_flags_json = ?,
                        output_requirements_json = ?, constraints_json = ?, confidence = ?, hit_count = ?,
                        source = ?, evidence = ?, metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        payload_json,
                        str(knowledge_payload.get("intent") or "general_task"),
                        str(knowledge_payload.get("domain") or "general"),
                        json.dumps(tokens, ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["query_markers"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["record_markers"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["agent_markers"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["goal_terms"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["intent_hints"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["action_flags"], ensure_ascii=False, sort_keys=True),
                        json.dumps(knowledge_payload.get("output_requirements") or [], ensure_ascii=False, sort_keys=True),
                        json.dumps(knowledge_payload.get("constraints") or {}, ensure_ascii=False, sort_keys=True),
                        max(float(row[2] or 0.0), float(confidence)),
                        int(row[1] or 0) + 1,
                        source,
                        evidence,
                        metadata_json,
                        now,
                        int(row[0]),
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO runtime_intent_knowledge(
                        normalized_request, payload_json, intent, domain, tokens_json,
                        query_markers_json, record_markers_json, agent_markers_json,
                        goal_terms_json, intent_hints_json, action_flags_json,
                        output_requirements_json, constraints_json, confidence, hit_count,
                        source, evidence, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_request,
                        payload_json,
                        str(knowledge_payload.get("intent") or "general_task"),
                        str(knowledge_payload.get("domain") or "general"),
                        json.dumps(tokens, ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["query_markers"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["record_markers"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["agent_markers"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["goal_terms"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["intent_hints"], ensure_ascii=False, sort_keys=True),
                        json.dumps(markers["action_flags"], ensure_ascii=False, sort_keys=True),
                        json.dumps(knowledge_payload.get("output_requirements") or [], ensure_ascii=False, sort_keys=True),
                        json.dumps(knowledge_payload.get("constraints") or {}, ensure_ascii=False, sort_keys=True),
                        float(confidence),
                        source,
                        evidence,
                        metadata_json,
                        now,
                        now,
                    ),
                )
            conn.commit()

    def _build_active_overlay(self) -> dict[str, Any]:
        overlay: dict[str, Any] = {}
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT policy_key, value_json
                FROM semantic_policy_candidates
                WHERE status = 'active'
                ORDER BY activated_at ASC, updated_at ASC
                """
            ).fetchall()
        for policy_key, value_json in rows:
            self._merge_candidate_into_overlay(overlay, str(policy_key), json.loads(value_json))
        return overlay

    def _merge_policy_overlay(self, base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        merged = json.loads(json.dumps(base, ensure_ascii=False))
        return self._deep_merge(merged, overlay)

    def _merge_candidate_into_overlay(self, overlay: dict[str, Any], policy_key: str, value: Any) -> None:
        mode = self.SUPPORTED_POLICY_KEYS.get(policy_key)
        if mode == "list":
            bucket = overlay.setdefault(policy_key, [])
            values = value if isinstance(value, list) else [value]
            for item in values:
                if item not in bucket:
                    bucket.append(item)
            return
        if mode == "dict":
            bucket = overlay.setdefault(policy_key, {})
            if isinstance(value, dict):
                bucket.update(value)
            return
        if mode == "dict_list":
            field, nested_key = policy_key.split(".", 1)
            nested = overlay.setdefault(field, {})
            bucket = nested.setdefault(nested_key, {})
            if isinstance(value, dict):
                for canonical, aliases in value.items():
                    current = bucket.setdefault(canonical, [])
                    for alias in aliases:
                        if alias not in current:
                            current.append(alias)

    def _deep_merge(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        for key, value in right.items():
            if isinstance(value, dict) and isinstance(left.get(key), dict):
                left[key] = self._deep_merge(left[key], value)
                continue
            if isinstance(value, list) and isinstance(left.get(key), list):
                current = list(left[key])
                for item in value:
                    if item not in current:
                        current.append(item)
                left[key] = current
                continue
            left[key] = value
        return left

    def _snapshot_policy(self, policy: dict[str, Any], *, reason: str, source: str) -> None:
        payload = json.dumps(policy, ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id FROM semantic_policy_versions WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            if existing:
                return
            conn.execute(
                """
                INSERT INTO semantic_policy_versions(content_hash, snapshot_json, source, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (content_hash, payload, source, reason, now),
            )
            conn.commit()

    def _validate_candidate_shape(self, policy_key: str, value: Any) -> bool:
        mode = self.SUPPORTED_POLICY_KEYS.get(policy_key)
        if mode == "list":
            if isinstance(value, str):
                return bool(value.strip())
            return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
        if mode == "dict":
            return isinstance(value, dict) and bool(value)
        if mode == "dict_list":
            return isinstance(value, dict) and all(
                isinstance(name, str) and isinstance(aliases, list) and all(isinstance(alias, str) for alias in aliases)
                for name, aliases in value.items()
            )
        return False

    def _normalize_candidate_value(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _row_to_candidate(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata = json.loads(row.get("metadata_json") or "{}")
        return {
            "id": row["id"],
            "policy_key": row["policy_key"],
            "value": json.loads(row["value_json"]),
            "confidence": row["confidence"],
            "hit_count": row["hit_count"],
            "status": row["status"],
            "source": row["source"],
            "evidence": row["evidence"],
            "metadata": metadata,
            "failure_count": row["failure_count"],
            "activated_at": row["activated_at"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "updated_at": row["updated_at"],
        }

    def _row_to_intent_knowledge(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(row.get("payload_json") or "{}")
        payload.update(
            {
                "intent": row.get("intent") or payload.get("intent") or "general_task",
                "domain": row.get("domain") or payload.get("domain") or "general",
                "tokens": json.loads(row.get("tokens_json") or "[]"),
                "query_markers": json.loads(row.get("query_markers_json") or "[]"),
                "record_markers": json.loads(row.get("record_markers_json") or "[]"),
                "agent_markers": json.loads(row.get("agent_markers_json") or "[]"),
                "goal_terms": json.loads(row.get("goal_terms_json") or "[]"),
                "intent_hints": json.loads(row.get("intent_hints_json") or "[]"),
                "action_flags": json.loads(row.get("action_flags_json") or "{}"),
                "output_requirements": json.loads(row.get("output_requirements_json") or "[]"),
                "constraints": json.loads(row.get("constraints_json") or "{}"),
                "confidence": row.get("confidence") or 0.0,
                "hit_count": row.get("hit_count") or 0,
                "source": row.get("source") or "",
                "evidence": row.get("evidence") or "",
                "metadata": json.loads(row.get("metadata_json") or "{}"),
            }
        )
        return payload

    def _tokenize_intent_text(self, text: str) -> list[str]:
        tokens = re.split(r"[^\w\u4e00-\u9fff\-]+", text.lower())
        deduped: list[str] = []
        for token in tokens:
            normalized = token.strip("_-")
            if len(normalized) < 2:
                continue
            if normalized not in deduped:
                deduped.append(normalized)
            if re.fullmatch(r"[\u4e00-\u9fff]+", normalized):
                for size in (2, 3, 4):
                    if len(normalized) < size:
                        continue
                    for index in range(0, len(normalized) - size + 1):
                        gram = normalized[index : index + size]
                        if gram not in deduped:
                            deduped.append(gram)
        return deduped

    def _extract_runtime_marker_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        action_flags = payload.get("action_flags", {}) if isinstance(payload.get("action_flags"), dict) else {}
        return {
            "query_markers": list(payload.get("query_markers") or []),
            "record_markers": list(payload.get("record_markers") or []),
            "agent_markers": list(payload.get("agent_markers") or []),
            "goal_terms": list(payload.get("goal_terms") or []),
            "intent_hints": list(payload.get("intent_hints") or []),
            "action_flags": {
                "query_like": bool(action_flags.get("query_like", False)),
                "record_like": bool(action_flags.get("record_like", False)),
                "agent_create_like": bool(action_flags.get("agent_create_like", False)),
                "finalize_like": bool(action_flags.get("finalize_like", False)),
                "knowledge_capture_like": bool(action_flags.get("knowledge_capture_like", False)),
                "multimodal_like": bool(action_flags.get("multimodal_like", False)),
            },
        }

    def _learning_rules_snapshot(self) -> dict[str, Any]:
        policy = self.load_main_policy()
        learning_cfg = policy.get("policy_memory", {}).get("learning", {})
        return {
            "allowed_policy_keys": learning_cfg.get("allowed_policy_keys", []),
            "min_candidate_text_length": learning_cfg.get("min_candidate_text_length", 0),
            "blocked_terms": learning_cfg.get("blocked_terms", []),
            "reject_existing_conflicts": learning_cfg.get("reject_existing_conflicts", False),
        }

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_policy_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    normalized_value TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    hit_count INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    source TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    activated_at TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_semantic_policy_candidate_unique
                ON semantic_policy_candidates(policy_key, normalized_value)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_policy_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT NOT NULL UNIQUE,
                    snapshot_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_intent_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_request TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    tokens_json TEXT NOT NULL DEFAULT '[]',
                    query_markers_json TEXT NOT NULL DEFAULT '[]',
                    record_markers_json TEXT NOT NULL DEFAULT '[]',
                    agent_markers_json TEXT NOT NULL DEFAULT '[]',
                    goal_terms_json TEXT NOT NULL DEFAULT '[]',
                    intent_hints_json TEXT NOT NULL DEFAULT '[]',
                    action_flags_json TEXT NOT NULL DEFAULT '{}',
                    output_requirements_json TEXT NOT NULL DEFAULT '[]',
                    constraints_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0,
                    hit_count INTEGER NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()