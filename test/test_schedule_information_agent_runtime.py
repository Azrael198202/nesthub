from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def test_schedule_information_agent_creation_and_direct_record_flow(isolated_generated_artifacts) -> None:
    session_id = "schedule-information-agent-flow"

    create_response = client.post(
        "/core/handle",
        json={
            "input_text": "完成创建日程信息智能体。",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert create_response.status_code == 200
    create_result = create_response.json()["result"]
    assert create_result["task"]["intent"] == "create_information_agent"
    assert create_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "awaiting_purpose"

    purpose_response = client.post(
        "/core/handle",
        json={
            "input_text": "主要记录日程安排，进行创建。",
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
            "input_text": "没有了，完成创建",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    finalize_result = finalize_response.json()["result"]
    agent_payload = finalize_result["execution_result"]["final_output"]["manage_information_agent"]["agent"]
    assert finalize_result["task"]["intent"] == "finalize_information_agent"
    assert agent_payload["status"] == "active"
    assert agent_payload["profile"] == "structured_timeline"
    assert agent_payload["knowledge_entity_label"] == "日程安排"
    assert agent_payload["knowledge_namespace"].startswith("agent_knowledge/")
    assert agent_payload["schema_fields"] == ["actor", "time", "content", "location", "details"]

    first_record_response = client.post(
        "/core/handle",
        json={
            "input_text": "记录爸爸4月21号出差大阪",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    first_record_result = first_record_response.json()["result"]
    first_payload = first_record_result["execution_result"]["final_output"]["manage_information_agent"]
    assert first_record_result["task"]["intent"] == "capture_agent_knowledge"
    assert first_payload["dialog_state"]["stage"] == "knowledge_added"
    assert "记录" in first_payload["message"]
    assert "日程" in first_payload["message"]
    assert first_payload["knowledge"]["actor"] == "爸爸"
    assert first_payload["knowledge"]["time"] == "2026-04-21"
    assert "大阪" in str(first_payload["knowledge"]["location"])
    first_trace_path = Path(first_record_result["execution_result"]["generated_trace_path"])
    assert first_trace_path.exists()
    assert "generated_artifacts" in str(first_trace_path)

    second_record_response = client.post(
        "/core/handle",
        json={
            "input_text": "记录朱棣4月18日远足交友",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    second_record_result = second_record_response.json()["result"]
    second_payload = second_record_result["execution_result"]["final_output"]["manage_information_agent"]
    assert second_record_result["task"]["intent"] == "capture_agent_knowledge"
    assert second_payload["dialog_state"]["stage"] == "knowledge_added"
    assert "记录" in second_payload["message"]
    assert "日程" in second_payload["message"]
    assert second_payload["knowledge"]["actor"] == "朱棣"
    assert second_payload["knowledge"]["time"] == "2026-04-18"
    assert "远足" in str(second_payload["knowledge"]["content"])
    second_trace_path = Path(second_record_result["execution_result"]["generated_trace_path"])
    assert second_trace_path.exists()
    assert "generated_artifacts" in str(second_trace_path)

    final_agent_payload = second_payload["agent"]
    assert len(final_agent_payload["knowledge_records"]) == 2
