from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def _post_handle(input_text: str, session_id: str) -> dict:
    response = client.post(
        "/core/handle",
        json={
            "input_text": input_text,
            "context": {"session_id": session_id},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert response.status_code == 200
    return response.json()["result"]


def _aggregation_total(aggregation: dict) -> float:
    return float(aggregation.get("total") or aggregation.get("total_amount") or 0)


def _aggregation_groups(aggregation: dict) -> dict:
    return aggregation.get("groups") or aggregation.get("grouped") or {}


def test_budget_record_and_query_e2e(isolated_case_budget_runtime) -> None:
    session_id = f"budget-e2e-{uuid.uuid4().hex}"

    record_result = _post_handle(
        "吃饭花了3000日元，两人，在博多一兰。今天买咖啡500日元，还有书1200日元。",
        session_id,
    )
    assert record_result["task"]["intent"] in {"data_record", "record_expense"}
    final_output = record_result["execution_result"]["final_output"]
    records = final_output["extract_records"]["records"]
    assert len(records) >= 3
    assert all("amount" in item and "content" in item for item in records)

    total_query = _post_handle("这个月一共花了多少？", session_id)
    assert total_query["task"]["intent"] == "data_query"
    total_aggregation = total_query["execution_result"]["final_output"]["aggregate_query"]["aggregation"]
    assert _aggregation_total(total_aggregation) >= 4700

    group_query = _post_handle("按类别统计一下", session_id)
    assert group_query["task"]["intent"] == "data_query"
    group_aggregation = group_query["execution_result"]["final_output"]["aggregate_query"]["aggregation"]
    assert _aggregation_groups(group_aggregation)


def test_budget_single_record_append_is_not_deduplicated(isolated_case_budget_runtime) -> None:
    session_id = f"budget-append-{uuid.uuid4().hex}"

    first_result = _post_handle("今天打车花了800日元", session_id)
    second_result = _post_handle("今天打车花了800日元", session_id)

    assert first_result["task"]["intent"] in {"data_record", "record_expense"}
    assert second_result["task"]["intent"] in {"data_record", "record_expense"}

    first_records = first_result["execution_result"]["final_output"]["extract_records"]["records"]
    second_records = second_result["execution_result"]["final_output"]["extract_records"]["records"]
    assert len(first_records) == 1
    assert len(second_records) == 1

    summary_query = _post_handle("今天一共花了多少？", session_id)
    aggregation = summary_query["execution_result"]["final_output"]["aggregate_query"]["aggregation"]
    assert _aggregation_total(aggregation) >= 1600
