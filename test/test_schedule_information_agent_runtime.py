from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def _complete_collection(session_id: str, first_result: dict, field_values: dict[str, str]) -> dict:
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
                "input_text": field_values.get(current_field, "补充说明，完成添加"),
                "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )
        result = response.json()["result"]
    raise AssertionError("knowledge collection did not finish within expected turns")


def test_generic_activity_agent_creation_and_direct_record_flow(isolated_generated_artifacts) -> None:
    session_id = "generic-activity-agent-flow"

    create_response = client.post(
        "/core/handle",
        json={
            "input_text": "完成创建活动记录智能体。",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert create_response.status_code == 200
    create_result = create_response.json()["result"]
    assert create_result["task"]["intent"] == "create_information_agent"
    assert create_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "ai_workflow"

    purpose_response = client.post(
        "/core/handle",
        json={
            "input_text": "主要记录活动记录，进行创建。",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    purpose_result = purpose_response.json()["result"]
    assert purpose_result["task"]["intent"] == "refine_information_agent"
    assert purpose_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] in {"ai_workflow", "completed"}

    if purpose_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] == "completed":
        finalize_result = purpose_result
    else:
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
    assert finalize_result["task"]["intent"] in {"finalize_information_agent", "refine_information_agent"}
    assert agent_payload["status"] == "active"
    assert agent_payload["profile"] in {"structured_timeline", "generic_information", "entity_directory"}
    assert agent_payload["knowledge_entity_label"]
    assert agent_payload["knowledge_namespace"].startswith("agent_knowledge/")
    assert agent_payload["schema_fields"]

    first_record_response = client.post(
        "/core/handle",
        json={
            "input_text": "记录项目甲4月21号前往节点A进行交付",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    first_record_result = first_record_response.json()["result"]
    if first_record_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] != "knowledge_added":
            first_record_result = _complete_collection(
                session_id,
                first_record_result,
                {
                    "item_name": "项目甲",
                    "item_type": "活动记录",
                    "summary": "4月21号前往节点A进行交付",
                    "contact": "节点A",
                    "details": "补充说明，完成添加",
                    "actor": "项目甲",
                    "time": "2026-04-21",
                    "content": "前往节点A进行交付",
                    "location": "节点A",
                },
            )
    first_payload = first_record_result["execution_result"]["final_output"]["manage_information_agent"]
    assert first_record_result["task"]["intent"] == "capture_agent_knowledge"
    assert first_payload["dialog_state"]["stage"] == "knowledge_added"
    assert "记录" in first_payload["message"]
    assert "项目甲" in str(first_payload["knowledge"])
    assert "节点A" in str(first_payload["knowledge"])
    first_trace_path = Path(first_record_result["execution_result"]["generated_trace_path"])
    assert first_trace_path.exists()
    assert "generated_artifacts" in str(first_trace_path)

    second_record_response = client.post(
        "/core/handle",
        json={
            "input_text": "记录样本乙4月18日现场联调",
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    second_record_result = second_record_response.json()["result"]
    if second_record_result["execution_result"]["final_output"]["manage_information_agent"]["dialog_state"]["stage"] != "knowledge_added":
        second_record_result = _complete_collection(
            session_id,
            second_record_result,
            {
                "item_name": "样本乙",
                "item_type": "活动记录",
                "summary": "4月18日现场联调",
                "contact": "现场",
                "details": "联调完成，完成添加",
                "actor": "样本乙",
                "time": "2026-04-18",
                "content": "现场联调",
                "location": "现场",
            },
        )
    second_payload = second_record_result["execution_result"]["final_output"]["manage_information_agent"]
    assert second_record_result["task"]["intent"] == "capture_agent_knowledge"
    assert second_payload["dialog_state"]["stage"] == "knowledge_added"
    assert "记录" in second_payload["message"]
    assert "样本乙" in str(second_payload["knowledge"])
    assert "联调" in str(second_payload["knowledge"])
    second_trace_path = Path(second_record_result["execution_result"]["generated_trace_path"])
    assert second_trace_path.exists()
    assert "generated_artifacts" in str(second_trace_path)

    final_agent_payload = second_payload["agent"]
    assert len(final_agent_payload["knowledge_records"]) == 2
