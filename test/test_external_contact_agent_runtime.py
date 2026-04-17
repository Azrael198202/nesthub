from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def test_external_contact_agent_creation_and_contact_capture_flow(isolated_generated_artifacts) -> None:
    session_id = "external-contact-agent-flow"

    create_response = client.post(
        "/core/handle",
        json={
            "input_text": "帮我创建外部联系人智能体",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert create_response.status_code == 200
    create_result = create_response.json()["result"]
    assert create_result["task"]["intent"] == "create_information_agent"

    purpose_response = client.post(
        "/core/handle",
        json={
            "input_text": "主要记录老师、医生、同事这类外部联系人的联系方式。",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    purpose_result = purpose_response.json()["result"]
    assert purpose_result["task"]["intent"] == "refine_information_agent"

    finalize_response = client.post(
        "/core/handle",
        json={
            "input_text": "没有了，完成创建",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    finalize_result = finalize_response.json()["result"]
    agent_payload = finalize_result["execution_result"]["final_output"]["manage_information_agent"]["agent"]
    assert agent_payload["profile"] == "entity_directory"
    assert agent_payload["knowledge_entity_label"] == "外部联系人"
    assert agent_payload["agent_class"] == "information"
    assert agent_payload["agent_layer"] == "knowledge"
    assert "member_name" in agent_payload["schema_fields"]

    add_response = client.post(
        "/core/handle",
        json={
            "input_text": "添加王老师到外部联系人智能体中",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    add_result = add_response.json()["result"]
    assert add_result["task"]["intent"] == "capture_agent_knowledge"
    assert add_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["current_field"] == "member_name"

    conversation_inputs = [
        ("王老师", "role"),
        ("老师", "nickname"),
        ("班主任", "default_currency"),
        ("CNY", "include_expense"),
        ("否", "include_schedule"),
        ("否", "special_constraints"),
        ("工作日白天联系", "phone"),
        ("13800138000", "email"),
        ("teacher@example.com", "extra_notes"),
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
            "input_text": "负责数学和班级通知，完成添加",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    finish_result = finish_response.json()["result"]
    contact_payload = finish_result["execution_result"]["final_output"]["manage_information_agent"]["knowledge"]
    assert finish_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "knowledge_added"
    assert contact_payload["member_name"] == "王老师"
    assert contact_payload["role"] == "老师"
    assert contact_payload["phone"] == "13800138000"
    assert contact_payload["email"] == "teacher@example.com"
    trace_path = Path(finish_result["execution_result"]["generated_trace_path"])
    assert trace_path.exists()
    assert "generated_artifacts" in str(trace_path)
