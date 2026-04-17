from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


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
    assert create_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "awaiting_purpose"

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
    assert purpose_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "awaiting_confirmation"

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
    assert "member_name" in agent_payload["schema_fields"]
    assert agent_payload["knowledge_namespace"] == "agent_knowledge/family_member_info_agent"

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
    assert add_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["current_field"] == "member_name"

    conversation_inputs = [
        ("章三", "role"),
        ("爸爸", "nickname"),
        ("老爸", "default_currency"),
        ("JPY", "include_expense"),
        ("是", "include_schedule"),
        ("是", "special_constraints"),
        ("无", "phone"),
        ("1234567890", "email"),
        ("abc@gmail.com", "extra_notes"),
    ]

    for user_input, expected_next_field in conversation_inputs:
        response = client.post(
            "/core/handle",
            json={
                "input_text": user_input,
                "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )
        result = response.json()["result"]
        assert result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["current_field"] == expected_next_field

    finish_response = client.post(
        "/core/handle",
        json={
            "input_text": "公司是ABC株式会社，公司的联系电话是12345678，line的账号是abcd123 完成添加",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    finish_result = finish_response.json()["result"]
    member_payload = finish_result["execution_result"]["final_output"]["manage_information_agent"]["knowledge"]
    assert finish_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "knowledge_added"
    assert member_payload["member_name"] == "章三"
    assert member_payload["role"] == "爸爸"
    assert member_payload["phone"] == "1234567890"
    assert member_payload["email"] == "abc@gmail.com"
    assert "ABC株式会社" in member_payload["extra_notes"]
    trace_path = Path(finish_result["execution_result"]["generated_trace_path"])
    assert trace_path.exists()
    assert "generated_artifacts" in str(trace_path)


def test_family_member_agent_can_answer_saved_phone_query(isolated_generated_artifacts) -> None:
    session_id = "family-member-agent-query"
    inputs = [
        "帮我创建家庭成员的智能体",
        "主要记录家庭成员的信息。",
        "完成创建家庭成员信息智能体",
        "将爸爸信息添加到家庭成员智能体中",
        "章三",
        "爸爸",
        "老爸",
        "JPY",
        "是",
        "是",
        "无",
        "1234567890",
        "abc@gmail.com",
        "公司是ABC株式会社，公司的联系电话是12345678，line的账号是abcd123 完成添加",
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
    payload = query_result["execution_result"]["final_output"]["query_information_knowledge"]
    assert query_result["task"]["intent"] == "query_agent_knowledge"
    assert payload["answer"] == "爸爸的手机号是1234567890。"
    assert payload["knowledge_hits"]
    trace_path = Path(query_result["execution_result"]["generated_trace_path"])
    assert trace_path.exists()
    assert "generated_artifacts" in str(trace_path)