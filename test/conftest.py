from __future__ import annotations

import copy

import pytest

from nethub_runtime.core.routers import core_api
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator


def build_budget_semantic_policy() -> dict:
    policy = ExecutionCoordinator.default_semantic_policy()
    policy["semantic_matching"]["embedding_model"] = ""
    policy["model_semantic_parser"]["enabled"] = False
    policy["model_semantic_parser"]["prefer_model_for_query_parsing"] = False
    policy["model_semantic_parser"]["prefer_model_for_record_extraction"] = False
    policy["external_semantic_router"]["enabled"] = False
    policy["policy_memory"]["enabled"] = False
    policy["normalization"]["synonyms"] = {"self": ["我", "我个人", "本人"]}
    policy["entity_aliases"]["actor"] = {"self": ["我", "我个人", "本人"]}
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
    policy["content_cleanup_patterns"] = ["\\d+(?:\\.\\d+)?\\s*(日元|円|yen|usd|rmb|元|块|美元|￥|\\$)?"]
    policy["content_strip_chars"] = " ，,.。"
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
    ]
    policy["explicit_date_patterns"] = [{"pattern": "(\\d{1,2})月(\\d{1,2})[号日]", "month_group": 1, "day_group": 2}]
    policy["relative_week_rules"] = [{"pattern": "本周([一二三四五六日天])", "weekday_group": 1, "weekday_map": {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}, "week_start": "monday"}]
    policy["boolean_aliases"] = {"truthy": ["是", "参与", "需要", "yes", "true", "y", "1"], "falsy": ["否", "不", "no", "false", "n", "0"]}
    policy["time_marker_rules"] = {
        "today": {"aliases": ["今天", "今日", "today"], "match_mode": "same_day", "record_aliases": ["今天", "今日", "today"]},
        "current_month": {"aliases": ["这个月", "本月", "this month"], "match_mode": "same_month", "record_aliases": ["今天", "今日", "这个月", "本月", "today", "this month", "unspecified"]},
        "previous_week": {"aliases": ["上周", "上周末", "last week"], "match_mode": "prefix", "prefixes": ["上周", "last week"]},
    }
    return policy


@pytest.fixture
def isolated_generated_artifacts(tmp_path, monkeypatch) -> None:
    generated_root = tmp_path / "generated_artifacts"
    generated_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(generated_root))
    # Clear the in-memory session store and any SQLite persistence so that
    # test runs are fully isolated from each other regardless of previous state.
    store = core_api.core_engine.context_manager.session_store
    with store._lock:
        store._state.clear()
    try:
        store._persistence.clear_all()
    except AttributeError:
        pass


@pytest.fixture
def budget_semantic_runtime() -> None:
    coordinator = core_api.core_engine.execution_coordinator
    original_policy = copy.deepcopy(coordinator.semantic_policy)
    original_embedding_model = coordinator._embedding_model
    coordinator.semantic_policy = build_budget_semantic_policy()
    coordinator._embedding_model = None
    try:
        yield
    finally:
        coordinator.semantic_policy = original_policy
        coordinator._embedding_model = original_embedding_model