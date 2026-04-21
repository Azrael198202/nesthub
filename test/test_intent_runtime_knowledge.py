from __future__ import annotations

import json
from pathlib import Path

from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.services.intent_analyzer import IntentAnalyzer
from nethub_runtime.core.services.runtime_keyword_signal_analyzer import RuntimeKeywordSignalAnalyzer


def _write_policy(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "intent_detection": {
                    "query_markers": ["查", "查询", "查看", "看看"]
                },
                "policy_memory": {
                    "enabled": True,
                    "auto_activate": {"enabled": True, "min_hits": 2, "min_confidence": 0.75},
                    "learning": {"enabled": False},
                    "self_heal": {"enabled": False},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_runtime_intent_knowledge_is_persisted_after_analysis(tmp_path: Path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)
    analyzer = IntentAnalyzer(semantic_policy_store=store)

    context = CoreContextSchema(trace_id="trace-1", session_id="session-1", metadata={}, session_state={})
    task = __import__("asyncio").run(analyzer.analyze("请帮我创建供应商资料智能体", context))

    assert task.intent == "create_information_agent"
    remembered = store.match_intent_knowledge("请帮我创建供应商资料智能体")
    assert remembered is not None
    assert remembered["intent"] == "create_information_agent"
    assert "create_information_agent" in remembered["intent_hints"]


def test_runtime_keyword_signal_analyzer_reuses_similar_intent_knowledge(tmp_path: Path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)

    store.record_intent_knowledge(
        "帮我创建供应商资料智能体",
        {
            "intent": "create_information_agent",
            "domain": "agent_management",
            "query_markers": [],
            "record_markers": [],
            "agent_markers": ["供应商资料", "智能体"],
            "goal_terms": ["创建", "供应商资料", "智能体"],
            "intent_hints": ["create_information_agent"],
            "action_flags": {
                "query_like": False,
                "record_like": False,
                "agent_create_like": True,
                "finalize_like": False,
                "knowledge_capture_like": False,
                "multimodal_like": False,
            },
            "output_requirements": ["agent", "dialog"],
            "constraints": {"need_agent": True},
        },
        source="test",
        confidence=0.95,
        evidence="seed",
    )

    analyzer = RuntimeKeywordSignalAnalyzer(model_router=None, semantic_policy_store=store)
    payload = analyzer.analyze("请创建供应商资料智能体")

    assert payload["action_flags"]["agent_create_like"] is True
    assert "create_information_agent" in payload["intent_hints"]
    assert payload["knowledge_match"]["match_type"] in {"exact", "token_overlap"}


def test_runtime_keyword_signal_analyzer_uses_policy_query_markers_for_fallback(tmp_path: Path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    _write_policy(policy_path)
    store = SemanticPolicyStore(policy_path=policy_path, db_path=db_path)

    analyzer = RuntimeKeywordSignalAnalyzer(model_router=None, semantic_policy_store=store)
    payload = analyzer.analyze("查4月21号和4月22号的安排")

    assert payload["action_flags"]["query_like"] is True
