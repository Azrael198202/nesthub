from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def _value_for_field(field_name: str) -> str:
    mapping = {
        "item_name": "资料甲",
        "item_type": "参考条目",
        "summary": "用于对接说明",
        "contact": "13800138000 / reference@example.com",
        "details": "负责说明文档和渠道同步，完成添加",
        "member_name": "资料甲",
        "role": "参考条目",
        "nickname": "说明项",
        "phone": "13800138000",
        "email": "reference@example.com",
        "extra_notes": "负责说明文档和渠道同步，完成添加",
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


def test_generic_reference_agent_creation_and_capture_flow(isolated_generated_artifacts) -> None:
    session_id = "generic-reference-agent-flow"

    create_response = client.post(
        "/core/handle",
        json={
            "input_text": "帮我创建参考资料智能体",
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
            "input_text": "主要记录参考资料条目的说明和联系方式。",
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
    assert agent_payload["profile"] in {"entity_directory", "generic_information"}
    assert agent_payload["knowledge_entity_label"]
    assert agent_payload["agent_class"] == "information"
    assert agent_payload["agent_layer"] == "knowledge"
    assert "item_name" in agent_payload["schema_fields"]

    add_response = client.post(
        "/core/handle",
        json={
            "input_text": "添加资料甲到参考资料智能体中",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    add_result = add_response.json()["result"]
    assert add_result["task"]["intent"] == "capture_agent_knowledge"
    finish_result = _complete_collection(session_id, add_result)
    contact_payload = finish_result["execution_result"]["final_output"]["manage_information_agent"]["knowledge"]
    assert finish_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "knowledge_added"
    assert "资料甲" in str(contact_payload)
    assert "参考条目" in str(contact_payload)
    assert finish_result["execution_result"]["final_output"]["manage_information_agent"]["agent"]["knowledge_records"]
    trace_path = Path(finish_result["execution_result"]["generated_trace_path"])
    assert trace_path.exists()
    assert "generated_artifacts" in str(trace_path)
