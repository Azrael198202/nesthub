from __future__ import annotations

import json

import pytest

from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator


def _write_policy(path, overrides=None):
    policy = {
        "tokenizer": {"preferred": "regex", "fallback": "regex", "min_token_length": 2},
        "semantic_matching": {
            "method": "embedding_or_token",
            "embedding_model": "",
            "similarity_threshold": 0.62,
            "fallback_to_external_threshold": 0.35,
        },
        "normalization": {"text_replace": {}, "synonyms": {}},
        "entity_aliases": {"actor": {"self": ["me"]}},
        "label_taxonomy": {},
        "semantic_label_threshold": 0.2,
        "semantic_label_margin": 0.08,
        "ignored_query_tokens": ["total"],
        "segment_split_patterns": ["[.;\\n]", "\\band\\b"],
        "location_markers": ["at", "in"],
        "location_keyword_patterns": ["([A-Za-z0-9]{2,})\\s+region"],
        "participant_pattern": "(\\d+)\\s*people",
        "participant_aliases": {"two people": 2},
        "content_cleanup_patterns": ["\\d+(?:\\.\\d+)?\\s*(usd|\\$)?"],
        "content_strip_chars": " .,",
        "group_by_aliases": {"by time": "time", "by actor": "actor"},
        "model_semantic_parser": {
            "enabled": False,
            "prefer_model_for_query_parsing": False,
            "prefer_model_for_record_extraction": False,
            "strict_schema_validation": True,
        },
        "time_marker_rules": {
            "today": {
                "aliases": ["today"],
                "match_mode": "same_day",
                "record_aliases": ["today"],
            }
        },
        "policy_memory": {
            "enabled": True,
            "backend": "sqlite",
            "read_only_main_policy": True,
            "auto_candidate_zone": True,
            "auto_activate": {"enabled": True, "min_hits": 2, "min_confidence": 0.75},
            "learning": {"enabled": False, "extractor": "model", "max_updates_per_text": 8, "default_confidence": 0.82},
            "self_heal": {"enabled": True, "max_failures": 2, "rollback_batch_size": 2},
        },
        "external_semantic_router": {"enabled": False},
    }
    if overrides:
        policy.update(overrides)
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")


def test_semantic_policy_requires_configured_business_keys(tmp_path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    _write_policy(policy_path)
    broken = json.loads(policy_path.read_text(encoding="utf-8"))
    broken.pop("location_markers")
    policy_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="location_markers"):
        ExecutionCoordinator(semantic_policy_path=policy_path)


def test_semantic_policy_candidate_overlay_stays_outside_main_policy(tmp_path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)

    store.record_candidate("location_markers", "near", confidence=0.9, source="test", evidence="near office")
    store.record_candidate("location_markers", "near", confidence=0.95, source="test", evidence="near station")

    runtime_policy = store.load_runtime_policy()
    main_policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert "near" in runtime_policy["location_markers"]
    assert "near" not in main_policy["location_markers"]


def test_semantic_policy_self_heal_rolls_back_active_candidate(tmp_path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)

    store.record_candidate("location_markers", "near", confidence=0.9, source="test", evidence="near office")
    store.record_candidate("location_markers", "near", confidence=0.95, source="test", evidence="near station")
    assert "near" in store.load_runtime_policy()["location_markers"]

    assert store.record_runtime_failure(reason="bad candidate", policy_key="location_markers") == 0
    assert store.record_runtime_failure(reason="bad candidate", policy_key="location_markers") == 1
    assert "near" not in store.load_runtime_policy()["location_markers"]


def test_semantic_policy_inspection_exposes_candidate_and_rollback_state(tmp_path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)

    store.record_candidate("location_markers", "near", confidence=0.9, source="query_parsing", evidence="near office")
    store.record_candidate("location_markers", "near", confidence=0.95, source="query_parsing", evidence="near station")
    store.record_runtime_failure(reason="bad candidate", policy_key="location_markers")
    store.record_runtime_failure(reason="bad candidate", policy_key="location_markers")

    snapshot = store.inspect_memory()
    assert snapshot["backend"] == "sqlite"
    assert snapshot["summary"]["rolled_back"] == 1
    assert snapshot["latest_rollback"] is not None
    assert snapshot["latest_rollback"]["reason"] == "bad candidate"
    assert any(item["status"] == "rolled_back" for item in snapshot["candidates"])
    assert snapshot["recent_versions"]


def test_semantic_policy_inspection_supports_policy_key_and_status_filters(tmp_path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)

    store.record_candidate("location_markers", "near", confidence=0.9, source="query_parsing", evidence="near office")
    store.record_candidate("location_markers", "near", confidence=0.95, source="query_parsing", evidence="near station")
    store.record_candidate("ignored_query_tokens", "expense", confidence=0.91, source="query_parsing", evidence="expense total")

    active_snapshot = store.inspect_memory(policy_key="location_markers", status="active")
    assert active_snapshot["filters"] == {"policy_key": "location_markers", "status": "active"}
    assert active_snapshot["summary"]["active"] == 1
    assert len(active_snapshot["candidates"]) == 1
    assert active_snapshot["candidates"][0]["policy_key"] == "location_markers"
    assert active_snapshot["candidates"][0]["status"] == "active"

    pending_snapshot = store.inspect_memory(policy_key="ignored_query_tokens", status="candidate")
    assert pending_snapshot["summary"]["candidate"] == 1
    assert len(pending_snapshot["candidates"]) == 1
    assert pending_snapshot["candidates"][0]["policy_key"] == "ignored_query_tokens"


def test_semantic_policy_inspection_rejects_invalid_status_filter(tmp_path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)

    with pytest.raises(ValueError, match="unsupported semantic memory status filter"):
        store.inspect_memory(status="invalid")