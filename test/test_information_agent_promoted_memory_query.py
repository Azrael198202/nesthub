from __future__ import annotations

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app
from nethub_runtime.core.routers.core_api import core_engine


client = TestClient(app)


def _complete_collection(session_id: str, first_result: dict) -> dict:
    values = {
        "item_name": "供应商甲",
        "item_type": "供应商",
        "summary": "负责样品交付",
        "contact": "vendor@example.com",
        "details": "ABC株式会社，完成添加",
    }
    result = first_result
    for _ in range(12):
        payload = result["execution_result"]["final_output"]["manage_information_agent"]
        dialog_state = payload["dialog_state"]
        if dialog_state["stage"] == "knowledge_added":
            return result
        current_field = dialog_state.get("current_field", "details")
        response = client.post(
            "/core/handle",
            json={
                "input_text": values.get(current_field, "完成添加"),
                "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )
        result = response.json()["result"]
    raise AssertionError("knowledge collection did not finish within expected turns")


def test_query_information_knowledge_falls_back_to_promoted_facts(isolated_generated_artifacts) -> None:
    session_id = "promoted-memory-query-agent"
    for text in [
        "帮我创建供应商资料智能体",
        "主要记录供应商资料的信息。",
        "完成创建供应商资料信息智能体",
    ]:
        response = client.post(
            "/core/handle",
            json={
                "input_text": text,
                "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )
        assert response.status_code == 200

    add_response = client.post(
        "/core/handle",
        json={
            "input_text": "将供应商甲信息添加到供应商资料智能体中",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    add_result = add_response.json()["result"]
    completed_result = _complete_collection(session_id, add_result)
    assert completed_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "knowledge_added"

    state = core_engine.context_manager.session_store.get(session_id)
    configured_agent = state.get("configured_agent") or {}
    core_engine.context_manager.session_store.patch(
        session_id,
        {"configured_agent": {**configured_agent, "knowledge_records": {}}},
    )

    query_response = client.post(
        "/core/handle",
        json={
            "input_text": "供应商甲的联系方式是什么？",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert query_response.status_code == 200
    query_result = query_response.json()["result"]
    payload = query_result["execution_result"]["final_output"]["query_information_knowledge"]
    assert "vendor@example.com" in str(payload.get("answer") or "")
    assert any((hit.get("metadata") or {}).get("record") for hit in payload.get("knowledge_hits") or [])


def test_query_information_knowledge_recovers_agent_from_promoted_facts_when_session_agent_missing(isolated_generated_artifacts) -> None:
    session_id = "promoted-memory-query-agent-recover"
    for text in [
        "帮我创建供应商资料智能体",
        "主要记录供应商资料的信息。",
        "完成创建供应商资料信息智能体",
    ]:
        response = client.post(
            "/core/handle",
            json={
                "input_text": text,
                "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )
        assert response.status_code == 200

    add_response = client.post(
        "/core/handle",
        json={
            "input_text": "将供应商甲信息添加到供应商资料智能体中",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    completed_result = _complete_collection(session_id, add_response.json()["result"])
    assert completed_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "knowledge_added"

    core_engine.context_manager.session_store.patch(session_id, {"configured_agent": {}, "knowledge_collection": {"active": False}})

    query_response = client.post(
        "/core/handle",
        json={
            "input_text": "供应商甲的联系方式是什么？",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert query_response.status_code == 200
    query_result = query_response.json()["result"]
    assert query_result["task"]["intent"] == "query_agent_knowledge"
    payload = query_result["execution_result"]["final_output"]["query_information_knowledge"]
    assert "vendor@example.com" in str(payload.get("answer") or "")


def test_create_information_agent_restarts_workflow_when_agent_already_active(isolated_generated_artifacts) -> None:
    session_id = "promoted-memory-recreate-active-agent"
    for text in [
        "帮我创建供应商资料智能体",
        "主要记录供应商资料的信息。",
        "完成创建供应商资料信息智能体",
    ]:
        response = client.post(
            "/core/handle",
            json={
                "input_text": text,
                "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )
        assert response.status_code == 200

    recreate_response = client.post(
        "/core/handle",
        json={
            "input_text": "创建一个日程和提醒智能体",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert recreate_response.status_code == 200
    recreate_result = recreate_response.json()["result"]
    payload = recreate_result["execution_result"]["final_output"]["manage_information_agent"]
    assert payload["dialog_state"]["stage"] == "ai_workflow"
    assert "当前没有可执行的信息型智能体操作" not in str(payload.get("message") or "")
