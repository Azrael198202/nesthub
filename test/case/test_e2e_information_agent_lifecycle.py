from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def _post_handle(input_text: str, session_id: str) -> dict:
    response = client.post(
        "/core/handle",
        json={
            "input_text": input_text,
            "context": {"session_id": session_id, "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert response.status_code == 200
    return response.json()["result"]


def _value_for_field(field_name: str) -> str:
    mapping = {
        "item_name": "科技甲株式会社",
        "item_type": "供应商",
        "summary": "主要供应半导体元件",
        "contact": "田中太郎 / tanaka@tech.co.jp",
        "details": "供货品类：半导体元件，完成添加",
        "member_name": "科技甲株式会社",
        "role": "供应商",
        "nickname": "科技甲",
        "phone": "+81-90-1234-5678",
        "email": "tanaka@tech.co.jp",
        "extra_notes": "供货品类：半导体元件，完成添加",
    }
    return mapping.get(field_name, "补充说明，完成添加")


def _complete_collection(session_id: str, current_result: dict) -> dict:
    result = current_result
    for _ in range(12):
        payload = result["execution_result"]["final_output"]["manage_information_agent"]
        dialog_state = payload["dialog_state"]
        if dialog_state["stage"] == "knowledge_added":
            return result
        result = _post_handle(_value_for_field(dialog_state.get("current_field", "details")), session_id)
    raise AssertionError("supplier knowledge collection did not finish within expected turns")


def test_supplier_information_agent_lifecycle_e2e(isolated_case_runtime) -> None:
    session_id = f"supplier-agent-{uuid.uuid4().hex}"

    create_result = _post_handle("帮我创建供应商资料智能体", session_id)
    assert create_result["task"]["intent"] == "create_information_agent"
    create_payload = create_result["execution_result"]["final_output"]["manage_information_agent"]
    assert create_payload["dialog_state"]["stage"] == "ai_workflow"

    refine_result = _post_handle("主要记录供应商名称、联系人、邮箱和供货品类。", session_id)
    assert refine_result["task"]["intent"] == "refine_information_agent"
    refine_payload = refine_result["execution_result"]["final_output"]["manage_information_agent"]
    assert refine_payload["dialog_state"]["stage"] in {"ai_workflow", "completed"}

    finalize_result = refine_result
    if refine_payload["dialog_state"]["stage"] != "completed":
        finalize_result = _post_handle("没有了，完成创建。", session_id)

    assert finalize_result["task"]["intent"] in {"finalize_information_agent", "refine_information_agent"}
    configured_agent = finalize_result["execution_result"]["final_output"]["manage_information_agent"]["agent"]
    assert configured_agent["status"] == "active"
    assert configured_agent["activation_keywords"]

    inputs = [
        "供应商名称：科技甲株式会社",
        "联系人：田中太郎",
        "邮箱：tanaka@tech.co.jp",
        "供货品类：半导体元件，完成添加",
    ]
    last_result = finalize_result
    for text in inputs:
        last_result = _post_handle(text, session_id)

    assert last_result["task"]["intent"] == "capture_agent_knowledge"
    last_result = _complete_collection(session_id, last_result)
    knowledge_payload = last_result["execution_result"]["final_output"]["manage_information_agent"]
    assert knowledge_payload["dialog_state"]["stage"] == "knowledge_added"
    assert knowledge_payload["agent"]["knowledge_records"]

    email_query = _post_handle("科技甲的邮箱是什么？", session_id)
    assert email_query["task"]["intent"] in {"query_agent_knowledge", "capture_agent_knowledge"}
    query_output = email_query["execution_result"]["final_output"]
    knowledge_query = query_output.get("query_information_knowledge") or query_output.get("query_agent_knowledge")
    assert knowledge_query is not None
    assert "tanaka@tech.co.jp" in str(knowledge_query.get("answer") or knowledge_query)

    list_query = _post_handle("有哪些供应商？", session_id)
    assert list_query["task"]["intent"] in {"query_agent_knowledge", "capture_agent_knowledge"}
    list_output = list_query["execution_result"]["final_output"]
    list_payload = list_output.get("query_information_knowledge") or list_output.get("query_agent_knowledge")
    assert list_payload is not None
    hits = list_payload.get("knowledge_hits") or []
    assert len(hits) >= 1

    trace_path = Path(list_query["execution_result"]["generated_trace_path"])
    assert trace_path.exists()
