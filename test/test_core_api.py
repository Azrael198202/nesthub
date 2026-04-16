from fastapi.testclient import TestClient
from pathlib import Path

from nethub_runtime.core.main import app

client = TestClient(app)

def test_core_handle_budget():
    payload = {
        "input_text": "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元",
        "context": {},
        "output_format": "dict"
    }
    resp = client.post("/core/handle", json=payload)
    assert resp.status_code == 200
    data = resp.json()["result"]
    assert data["task"]["intent"] in ("data_record", "record_expense")
    assert "execution_result" in data
    assert data["workflow"]
    assert data["workflow"]["steps"]
    assert data["workflow"]["steps"][0]["executor_type"]
    assert data["workflow"]["steps"][0]["inputs"]
    assert data["workflow"]["steps"][0]["outputs"]
    assert data["execution_result"]["execution_plan"]
    assert data["execution_result"]["execution_plan"][0]["executor_type"]
    assert data["execution_result"]["execution_plan"][0]["inputs"]
    assert data["execution_result"]["execution_plan"][0]["outputs"]
    assert data["execution_result"]["execution_plan"][0]["selector"]["reason"]
    assert data["execution_result"]["steps"][0]["inputs"]
    assert data["execution_result"]["steps"][0]["outputs"]
    trace = data["execution_result"]["autonomous_implementation_trace"]
    assert trace["autonomous_implementation_supported"] is True
    assert trace["capability_gap_detected"] is False
    generated_trace_path = data["execution_result"].get("generated_trace_path")
    assert generated_trace_path
    assert Path(generated_trace_path).exists()
    artifacts = data.get("artifacts", [])
    assert any(item["artifact_type"] == "trace" for item in artifacts)
    assert any(item["artifact_type"] == "trace" for item in data.get("artifact_index", {}).get("trace", []))

if __name__ == "__main__":
    test_core_handle_budget()
