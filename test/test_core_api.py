from fastapi.testclient import TestClient
from pathlib import Path

from nethub_runtime.core.main import app

client = TestClient(app)

def test_core_handle_budget(isolated_generated_artifacts, budget_semantic_runtime):
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


def test_core_handle_can_generate_html_file_from_language_instruction(isolated_generated_artifacts, monkeypatch):
    workspace = Path.cwd()
    target_dir = workspace / "tmp_test_outputs"
    monkeypatch.chdir(workspace)
    payload = {
        "input_text": "帮我写一个 html 文件，内容是点击一个按钮 Submit 能执行一个 js，弹出 hello,world!，保存到 tmp_test_outputs/hello_world_button.html",
        "context": {},
        "output_format": "dict"
    }

    try:
        resp = client.post("/core/handle", json=payload)
        assert resp.status_code == 200
        data = resp.json()["result"]
        assert data["task"]["intent"] == "file_generation_task"
        file_output = data["execution_result"]["final_output"]["file_generate"]
        target_path = Path(file_output["artifact_path"])
        assert target_path.exists()
        content = target_path.read_text(encoding="utf-8")
        assert "<button id=\"submitButton\"" in content
        assert 'alert("hello,world!")' in content
        assert file_output["status"] == "generated"
        assert any(item["artifact_type"] == "file" for item in data.get("artifacts", []))
        assert any(item["artifact_type"] == "file" for item in data.get("artifact_index", {}).get("file", []))
    finally:
        if target_dir.exists():
            for path in target_dir.glob("*"):
                if path.is_file():
                    path.unlink()
            target_dir.rmdir()


def test_core_handle_can_return_existing_file_content_from_language_instruction(isolated_generated_artifacts, monkeypatch):
    workspace = Path.cwd()
    target_dir = workspace / "tmp_test_outputs"
    target_dir.mkdir(exist_ok=True)
    target_path = target_dir / "hello_world_button.html"
    target_path.write_text("<html><body>Hello existing file</body></html>", encoding="utf-8")
    monkeypatch.chdir(workspace)
    payload = {
        "input_text": "把tmp_test_outputs/hello_world_button.html文件发给我",
        "context": {},
        "output_format": "dict"
    }

    try:
        resp = client.post("/core/handle", json=payload)
        assert resp.status_code == 200
        data = resp.json()["result"]
        assert data["task"]["intent"] == "file_delivery_task"
        file_output = data["execution_result"]["final_output"]["file_read"]
        assert file_output["status"] == "read"
        assert Path(file_output["artifact_path"]).resolve() == target_path.resolve()
        assert "Hello existing file" in file_output["content"]
        assert not (workspace / "把tmp_test_outputs/hello_world_button.html").exists()
        assert any(item["artifact_type"] == "file" for item in data.get("artifacts", []))
    finally:
        if target_path.exists():
            target_path.unlink()
        if target_dir.exists():
            target_dir.rmdir()

if __name__ == "__main__":
    test_core_handle_budget()
