from __future__ import annotations

import json
from pathlib import Path

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator


def _build_coordinator(tmp_path: Path) -> ExecutionCoordinator:
    policy = json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))
    policy["semantic_matching"]["embedding_model"] = ""
    policy["model_semantic_parser"]["enabled"] = False
    policy["model_semantic_parser"]["prefer_model_for_query_parsing"] = False
    policy["model_semantic_parser"]["prefer_model_for_record_extraction"] = False
    policy["external_semantic_router"]["enabled"] = False
    policy["policy_memory"]["enabled"] = False

    semantic_policy_path = tmp_path / "semantic_policy.json"
    semantic_policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    return ExecutionCoordinator(semantic_policy_path=semantic_policy_path)


def test_generic_chinese_query_does_not_infer_label(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)

    query = coordinator._parse_query("4月份一共花了多少钱？", existing_records=[])

    assert "label" not in query["filters"]
    assert query["query_text"] == "4月份一共花了多少钱？"


def test_transportation_label_is_inferred_from_chinese_text(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)

    label = coordinator._infer_label("今天打车去机场花了120元")

    assert label == "transportation"


def test_healthcare_label_is_inferred_from_chinese_text(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)

    label = coordinator._infer_label("昨天去医院看病买药一共花了260元")

    assert label == "healthcare"


def test_category_group_query_matches_existing_records_without_false_label(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    records = [
        {
            "time": "今天",
            "location": "公司附近",
            "content": "地铁通勤",
            "amount": 12,
            "participants": 1,
            "actor": "self",
            "label": "transportation",
            "raw_text": "今天坐地铁花了12元",
            "created_at": "2026-04-16T08:00:00+00:00",
        },
        {
            "time": "今天",
            "location": "药店",
            "content": "感冒药",
            "amount": 45,
            "participants": 1,
            "actor": "self",
            "label": "healthcare",
            "raw_text": "今天买药花了45元",
            "created_at": "2026-04-16T09:00:00+00:00",
        },
    ]

    query = coordinator._parse_query("今天按类别统计花了多少钱？", existing_records=records)

    assert query["group_by"] == ["label"]
    assert "label" not in query["filters"]


def test_actor_query_does_not_pick_up_spurious_label_filter(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)

    query = coordinator._parse_query("我个人花了多少？", existing_records=[])

    assert query["filters"] == {"actor": "self"}


def test_location_query_does_not_pick_up_spurious_label_filter(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)

    query = coordinator._parse_query("博多地区消费总额是多少？", existing_records=[])

    assert query["filters"] == {"location_keyword": "博多"}


def test_extract_records_assigns_new_category_labels(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)

    records = coordinator._extract_records("今天打车花了80元。下午去医院买药花了35元。这个月交网费120元")

    labels = [item["label"] for item in records]
    assert labels == ["transportation", "healthcare", "utilities"]


def test_learning_guard_rejects_generic_terms_and_disallowed_keys(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    learning_cfg = coordinator.semantic_policy["policy_memory"]["learning"]

    assert not coordinator._should_accept_learning_candidate("label_taxonomy", {"misc": {}}, learning_cfg)
    assert not coordinator._should_accept_learning_candidate("ignored_query_tokens", "多少", learning_cfg)
    assert coordinator._should_accept_learning_candidate("ignored_query_tokens", "报销", learning_cfg)


def test_learning_guard_allows_new_actor_aliases(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    learning_cfg = coordinator.semantic_policy["policy_memory"]["learning"]

    candidate = {"roommate": ["室友", "合租人"]}

    assert coordinator._should_accept_learning_candidate("entity_aliases.actor", candidate, learning_cfg)


def test_learning_guard_rejects_conflicting_actor_aliases_and_existing_canonical(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    learning_cfg = coordinator.semantic_policy["policy_memory"]["learning"]

    duplicate_alias_candidate = {"friend_circle": ["朋友"]}
    duplicate_canonical_candidate = {"家人": ["亲属"]}

    assert not coordinator._should_accept_learning_candidate("entity_aliases.actor", duplicate_alias_candidate, learning_cfg)
    assert not coordinator._should_accept_learning_candidate("entity_aliases.actor", duplicate_canonical_candidate, learning_cfg)


def test_learning_guard_blocks_existing_location_marker_but_accepts_new_one(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    learning_cfg = coordinator.semantic_policy["policy_memory"]["learning"]

    assert not coordinator._should_accept_learning_candidate("location_markers", "在", learning_cfg)
    assert coordinator._should_accept_learning_candidate("location_markers", "途经", learning_cfg)