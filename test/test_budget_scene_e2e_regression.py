from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def test_budget_scene_category_aggregation_e2e(isolated_generated_artifacts) -> None:
    session_id = f"budget-scene-{uuid.uuid4().hex}"
    record_payload = {
        "input_text": "今天打车花了80元。下午去医院买药花了35元。这个月交网费120元",
        "context": {"session_id": session_id},
        "output_format": "dict",
        "use_langraph": False,
    }
    record_response = client.post("/core/handle", json=record_payload)
    assert record_response.status_code == 200

    record_result = record_response.json()["result"]
    records = record_result["execution_result"]["final_output"]["extract_records"]["records"]
    labels = [item["label"] for item in records]
    assert labels == ["transportation", "healthcare", "utilities"]

    query_payload = {
        "input_text": "今天按类别统计花了多少钱？",
        "context": {"session_id": session_id},
        "output_format": "dict",
        "use_langraph": False,
    }
    query_response = client.post("/core/handle", json=query_payload)
    assert query_response.status_code == 200

    query_result = query_response.json()["result"]
    parsed_query = query_result["execution_result"]["final_output"]["parse_query"]["query"]
    aggregation = query_result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]

    assert parsed_query["group_by"] == ["label"]
    assert "label" not in parsed_query["filters"]
    assert aggregation["grouped"]["label"] == {
        "transportation": 80,
        "healthcare": 35,
        "utilities": 120,
    }
    assert aggregation["total_amount"] == 235


def test_budget_scene_generic_query_not_misclassified_e2e(isolated_generated_artifacts) -> None:
    session_id = f"budget-scene-{uuid.uuid4().hex}"
    record_payload = {
        "input_text": "今天打车花了80元。下午去医院买药花了35元。这个月交网费120元",
        "context": {"session_id": session_id},
        "output_format": "dict",
        "use_langraph": False,
    }
    client.post("/core/handle", json=record_payload)

    query_payload = {
        "input_text": "4月份一共花了多少钱？",
        "context": {"session_id": session_id},
        "output_format": "dict",
        "use_langraph": False,
    }
    query_response = client.post("/core/handle", json=query_payload)
    assert query_response.status_code == 200

    query_result = query_response.json()["result"]
    parsed_query = query_result["execution_result"]["final_output"]["parse_query"]["query"]

    assert parsed_query["filters"] == {}
    assert parsed_query["group_by"] == []