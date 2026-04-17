from __future__ import annotations

import json
from pathlib import Path
from datetime import UTC, datetime

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator


def _sample_semantic_policy() -> dict:
    policy = ExecutionCoordinator.default_semantic_policy()
    policy["semantic_matching"]["embedding_model"] = ""
    policy["model_semantic_parser"]["enabled"] = False
    policy["model_semantic_parser"]["prefer_model_for_query_parsing"] = False
    policy["model_semantic_parser"]["prefer_model_for_record_extraction"] = False
    policy["external_semantic_router"]["enabled"] = False
    policy["policy_memory"]["enabled"] = False
    policy["normalization"]["synonyms"] = {
        "self": ["我", "我个人", "本人"],
    }
    policy["entity_aliases"]["actor"] = {
        "self": ["我", "我个人", "本人"],
        "家人": ["家人", "家庭成员"],
        "朋友": ["朋友", "好友"],
    }
    policy["ignored_query_tokens"] = ["多少", "一共", "总额", "是多少", "吗"]
    policy["label_taxonomy"] = {
        "transportation": {"description": "travel and transportation expenses", "examples": ["打车", "出租车", "地铁", "公交", "车费", "机场"]},
        "healthcare": {"description": "healthcare and medicine expenses", "examples": ["医院", "看病", "买药", "药店", "诊所"]},
        "utilities": {"description": "utility and network expenses", "examples": ["网费", "水费", "电费", "燃气费"]},
    }
    policy["record_type_rules"] = {
        "schedule": {"require_time": True, "required_any": ["去", "前往", "开会", "安排", "日程"]},
        "generic": {"default": True, "default_label": "other"},
    }
    policy["segment_split_patterns"] = ["[。；;\\n]", "还有", "并且", "\\band\\b"]
    policy["location_markers"] = ["在", "去", "于", "at", "in"]
    policy["location_keyword_patterns"] = ["([\\u4e00-\\u9fffA-Za-z0-9]{2,})地区"]
    policy["participant_pattern"] = "(\\d+)\\s*人"
    policy["participant_aliases"] = {"两个人": 2, "三个人": 3}
    policy["group_by_aliases"] = {
        "按时间": "time",
        "按类别": "label",
        "按地点": "location",
        "按人员": "actor",
        "按人": "actor",
        "by time": "time",
        "by label": "label",
        "by location": "location",
        "by actor": "actor",
    }
    policy["actor_extract_patterns"] = [
        "^(?:记录|添加|保存)?([\\u4e00-\\u9fffA-Za-z]{2,4})(?=今天|昨天|本周|下周|\\d{1,2}月\\d{1,2}[号日]|去|到|前往)",
        "^([A-Za-z][A-Za-z0-9_-]{1,20})(?=\\s+\\d{4}-\\d{2}-\\d{2}|\\s+\\d{1,2}/\\d{1,2})",
    ]
    policy["explicit_date_patterns"] = [
        {"pattern": "(\\d{1,2})月(\\d{1,2})[号日]", "month_group": 1, "day_group": 2},
        {"pattern": "(\\d{4})-(\\d{2})-(\\d{2})", "year_group": 1, "month_group": 2, "day_group": 3},
    ]
    policy["relative_week_rules"] = [
        {
            "pattern": "本周([一二三四五六日天])",
            "weekday_group": 1,
            "weekday_map": {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6},
            "week_start": "monday",
        }
    ]
    policy["boolean_aliases"] = {"truthy": ["是", "参与", "需要", "yes", "true", "y", "1"], "falsy": ["否", "不", "no", "false", "n", "0"]}
    policy["time_marker_rules"] = {
        "today": {"aliases": ["今天", "今日", "today"], "match_mode": "same_day", "record_aliases": ["今天", "今日", "today"]},
        "current_month": {"aliases": ["这个月", "本月", "this month"], "match_mode": "same_month", "record_aliases": ["今天", "今日", "这个月", "本月", "today", "this month", "unspecified"]},
        "previous_week": {"aliases": ["上周", "上周末", "last week"], "match_mode": "prefix", "prefixes": ["上周", "last week"]},
    }
    policy["policy_memory"]["learning"]["blocked_terms"] = [
        "多少", "一共", "总额", "统计", "查询", "花了", "今天", "这个月", "上周", "类别", "地点", "人员",
        "total", "count", "query", "today", "this month", "last week", "label", "location", "actor",
    ]
    return policy


def _build_coordinator(tmp_path: Path) -> ExecutionCoordinator:
    policy = _sample_semantic_policy()

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


def test_query_stopwords_come_from_semantic_policy_not_intent_policy(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    coordinator.intent_policy = {"numeric_value_patterns": coordinator.intent_policy.get("numeric_value_patterns", [])}

    query = coordinator._parse_query("4月份一共花了多少钱？", existing_records=[])

    assert "一共" not in query["terms"]
    assert "多少" not in query["terms"]
    assert "4月份" in query["terms"]


def test_time_markers_come_from_semantic_policy_rules(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    coordinator.intent_policy = {"numeric_value_patterns": coordinator.intent_policy.get("numeric_value_patterns", [])}

    assert coordinator._extract_time("今天买了咖啡") == "今天"


def test_group_by_markers_come_from_semantic_policy_aliases(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    coordinator.intent_policy = {"numeric_value_patterns": coordinator.intent_policy.get("numeric_value_patterns", [])}

    query = coordinator._parse_query("今天按类别统计花了多少钱？", existing_records=[])

    assert query["group_by"] == ["label"]


def test_actor_extract_pattern_can_be_supplied_by_runtime_overlay(tmp_path: Path) -> None:
    policy = _sample_semantic_policy()
    policy["policy_memory"]["enabled"] = True
    policy["actor_extract_patterns"] = []

    semantic_policy_path = tmp_path / "semantic_policy_actor_overlay.json"
    semantic_policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
    coordinator = ExecutionCoordinator(semantic_policy_path=semantic_policy_path)
    coordinator.semantic_policy_store.record_candidate(
        "actor_extract_patterns",
        r"^([\u4e00-\u9fff]{2})(?=今天)",
        confidence=0.9,
        source="test",
        evidence="爸爸今天",
    )
    coordinator.semantic_policy_store.record_candidate(
        "actor_extract_patterns",
        r"^([\u4e00-\u9fff]{2})(?=今天)",
        confidence=0.95,
        source="test",
        evidence="妈妈今天",
    )
    coordinator._refresh_semantic_policy()

    assert coordinator._extract_named_actor("爸爸今天去了超市") == "爸爸"


def test_boolean_aliases_can_be_supplied_by_runtime_overlay(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    coordinator.semantic_policy_store.record_candidate(
        "boolean_aliases",
        {"truthy": ["参与"], "falsy": ["不参与"]},
        confidence=0.9,
        source="test",
        evidence="参与",
    )
    coordinator.semantic_policy_store.record_candidate(
        "boolean_aliases",
        {"truthy": ["参与"], "falsy": ["不参与"]},
        confidence=0.95,
        source="test",
        evidence="不参与",
    )
    coordinator._refresh_semantic_policy()

    assert coordinator._normalize_yes_no("我参与") is True


def test_explicit_date_pattern_can_be_supplied_by_runtime_overlay(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    coordinator.semantic_policy_store.record_candidate(
        "explicit_date_patterns",
        {"pattern": r"(\d{1,2})月(\d{1,2})号", "month_group": 1, "day_group": 2},
        confidence=0.9,
        source="test",
        evidence="4月21号",
    )
    coordinator.semantic_policy_store.record_candidate(
        "explicit_date_patterns",
        {"pattern": r"(\d{1,2})月(\d{1,2})号", "month_group": 1, "day_group": 2},
        confidence=0.95,
        source="test",
        evidence="4月22号",
    )
    coordinator._refresh_semantic_policy()

    expected = f"{datetime.now(UTC).year:04d}-04-21"
    assert coordinator._extract_explicit_date("爸爸4月21号去大阪") == expected


def test_schedule_records_are_extracted_without_amounts(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)

    records = coordinator._extract_records("爸爸4月21号去大阪。妈妈4月20号PTA开会。")

    assert len(records) == 2
    assert records[0]["record_type"] == "schedule"
    assert records[0]["actor"] == "爸爸"
    assert records[0]["time"] == "2026-04-21"
    assert "大阪" in str(records[0]["location"])
    assert records[1]["record_type"] == "schedule"
    assert records[1]["actor"] == "妈妈"
    assert records[1]["time"] == "2026-04-20"


def test_schedule_query_uses_list_metric_when_records_exist(tmp_path: Path) -> None:
    coordinator = _build_coordinator(tmp_path)
    existing_records = coordinator._extract_records("爸爸4月21号去大阪。妈妈4月20号PTA开会。")

    query = coordinator._parse_query("4月21号爸爸有什么安排？", existing_records=existing_records)

    assert query["metric"] == "list"
    assert query["time_marker"] == "2026-04-21"
    assert "爸爸" in query["terms"]


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


def test_schema_only_semantic_policy_seed_can_boot(tmp_path: Path) -> None:
    policy = ExecutionCoordinator.default_semantic_policy()
    policy["semantic_matching"]["embedding_model"] = ""
    policy["model_semantic_parser"]["enabled"] = False
    policy["model_semantic_parser"]["prefer_model_for_query_parsing"] = False
    policy["model_semantic_parser"]["prefer_model_for_record_extraction"] = False
    policy["external_semantic_router"]["enabled"] = False
    policy["policy_memory"]["enabled"] = False

    semantic_policy_path = tmp_path / "semantic_policy_seed.json"
    semantic_policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")

    coordinator = ExecutionCoordinator(semantic_policy_path=semantic_policy_path)
    records = coordinator._extract_records("today paid 20 usd")
    query = coordinator._parse_query("what did I spend", existing_records=records)

    assert records
    assert query["filters"] == {}