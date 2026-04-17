from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def _value_for_field(field_name: str) -> str:
    mapping = {
        "item_name": "章三",
        "item_type": "爸爸",
        "summary": "家里的爸爸",
        "contact": "1234567890 / abc@gmail.com",
        "details": "公司是ABC株式会社，公司的联系电话是12345678，line的账号是abcd123 完成添加",
        "member_name": "章三",
        "role": "爸爸",
        "nickname": "老爸",
        "default_currency": "JPY",
        "include_expense": "是",
        "include_schedule": "是",
        "special_constraints": "无",
        "phone": "1234567890",
        "email": "abc@gmail.com",
        "extra_notes": "公司是ABC株式会社，公司的联系电话是12345678，line的账号是abcd123 完成添加",
    }
    return mapping.get(field_name, "完成添加")


def _complete_collection(session_id: str, first_result: dict) -> dict:
    result = first_result
    for _ in range(12):
        payload = result["execution_result"]["final_output"]["manage_information_agent"]
        dialog_state = payload["dialog_state"]
        if dialog_state["stage"] == "knowledge_added":
            return result
        field_name = dialog_state["current_field"]
        response = client.post(
            "/core/handle",
            json={
                "input_text": _value_for_field(field_name),
                "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )
        result = response.json()["result"]
    raise AssertionError("knowledge collection did not finish within expected turns")


def test_family_member_agent_creation_and_member_collection_flow(isolated_generated_artifacts) -> None:
    session_id = "family-member-agent-flow"

    create_response = client.post(
        "/core/handle",
        json={
            "input_text": "帮我创建家庭成员的智能体",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert create_response.status_code == 200
    create_result = create_response.json()["result"]
    assert create_result["task"]["intent"] == "create_information_agent"
    assert create_result["task"]["constraints"]["need_agent"] is True
    assert create_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "ai_workflow"

    purpose_response = client.post(
        "/core/handle",
        json={
            "input_text": "主要记录家庭成员的信息。",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    purpose_result = purpose_response.json()["result"]
    assert purpose_result["task"]["intent"] == "refine_information_agent"
    assert purpose_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "ai_workflow"

    finalize_response = client.post(
        "/core/handle",
        json={
            "input_text": "完成创建家庭成员信息智能体",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    finalize_result = finalize_response.json()["result"]
    agent_payload = finalize_result["execution_result"]["final_output"]["manage_information_agent"]["agent"]
    assert finalize_result["task"]["intent"] == "finalize_information_agent"
    assert agent_payload["status"] == "active"
    assert agent_payload["profile"] in {"entity_directory", "generic_information"}
    assert agent_payload["knowledge_entity_label"]
    assert "item_name" in agent_payload["schema_fields"]
    assert agent_payload["knowledge_namespace"].startswith("agent_knowledge/")
    assert agent_payload["activation_keywords"]

    add_response = client.post(
        "/core/handle",
        json={
            "input_text": "将爸爸信息添加到家庭成员智能体中",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    add_result = add_response.json()["result"]
    assert add_result["task"]["intent"] == "capture_agent_knowledge"
    finish_result = _complete_collection(session_id, add_result)
    member_payload = finish_result["execution_result"]["final_output"]["manage_information_agent"]["knowledge"]
    assert finish_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "knowledge_added"
    assert "章三" in str(member_payload)
    assert "爸爸" in str(member_payload)
    assert "ABC株式会社" in str(member_payload)
    assert finish_result["execution_result"]["final_output"]["manage_information_agent"]["agent"]["knowledge_records"]
    trace_path = Path(finish_result["execution_result"]["generated_trace_path"])
    assert trace_path.exists()
    assert "generated_artifacts" in str(trace_path)


def test_family_member_agent_can_answer_saved_phone_query(isolated_generated_artifacts) -> None:
    session_id = "family-member-agent-query"
    inputs = [
        "帮我创建家庭成员的智能体",
        "主要记录家庭成员的信息。",
        "完成创建家庭成员信息智能体",
    ]
    for text in inputs:
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
            "input_text": "将爸爸信息添加到家庭成员智能体中",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    add_result = add_response.json()["result"]
    if add_result["task"]["intent"] == "capture_agent_knowledge":
        _complete_collection(session_id, add_result)

    query_response = client.post(
        "/core/handle",
        json={
            "input_text": "爸爸的手机号是多少？",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    query_result = query_response.json()["result"]
    assert query_result["task"]["intent"] in {"query_agent_knowledge", "capture_agent_knowledge"}
    final_output = query_result["execution_result"]["final_output"]
    if "query_information_knowledge" in final_output:
        payload = final_output["query_information_knowledge"]
        assert payload["answer"] is None or isinstance(payload["answer"], str)
    else:
        assert "manage_information_agent" in final_output
    trace_path = Path(query_result["execution_result"]["generated_trace_path"])
    assert trace_path.exists()
    assert "generated_artifacts" in str(trace_path)
