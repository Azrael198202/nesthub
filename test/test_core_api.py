from fastapi.testclient import TestClient
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
    assert len(data["workflow"]["steps"]) >= 2
    assert "execution_result" in data
    print("Test passed. Result:", data)

if __name__ == "__main__":
    test_core_handle_budget()
