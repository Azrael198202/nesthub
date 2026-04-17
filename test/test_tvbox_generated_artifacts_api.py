from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from nethub_runtime.generated.store import GeneratedArtifactStore
from nethub_runtime.tvbox import main as tvbox_main
from nethub_runtime.tvbox.main import _create_app


def test_tvbox_generated_artifacts_api_lists_generated_files() -> None:
    store = GeneratedArtifactStore()
    store.persist("blueprint", "tvbox_blueprint_case", {"name": "tvbox-blueprint"})
    client = TestClient(_create_app())

    response = client.get("/api/generated-artifacts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert any(item["artifactId"] == "tvbox_blueprint_case" for item in payload["items"]["blueprint"])


def test_tvbox_generated_artifacts_api_deletes_generated_files() -> None:
    store = GeneratedArtifactStore()
    store.persist("agent", "tvbox_agent_case", {"name": "tvbox-agent"})
    client = TestClient(_create_app())

    response = client.post("/api/generated-artifacts/delete", json={"category": "agent", "artifactId": "tvbox_agent_case"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True


def test_tvbox_generated_artifact_open_returns_file() -> None:
    store = GeneratedArtifactStore()
    path = store.persist("feature", "tvbox_open_case", "hello world", extension=".txt")
    client = TestClient(_create_app())

    response = client.get("/api/generated-artifacts/open/feature/tvbox_open_case")

    assert response.status_code == 200
    assert response.text == path.read_text(encoding="utf-8")


def test_tvbox_voice_chat_uses_runtime_core(monkeypatch) -> None:
    class FakeCore:
        async def handle(self, *args, **kwargs):
            return {
                "task": {"intent": "file_generation_task"},
                "blueprints": [
                    {
                        "blueprint_id": "bp_runtime_test",
                        "name": "runtime:test",
                        "metadata": {
                            "generated_artifact_path": "/tmp/runtime-test.json",
                            "synthesis": {"purpose_summary": "Runtime test blueprint", "reasoning": "generated at runtime"},
                        },
                    }
                ],
                "agent": {
                    "agent_id": "agent_runtime_test",
                    "name": "Runtime Agent",
                    "role": "tester",
                    "generated_artifact_path": "/tmp/agent-runtime-test.json",
                },
                "artifacts": [
                    {
                        "artifact_type": "file",
                        "artifact_id": "hello_world_button",
                        "name": "hello_world_button.html",
                    }
                ],
                "execution_result": {
                    "execution_type": "workflow",
                    "execution_plan": [
                        {"name": "file_generate", "capability": {"model_choice": {"provider": "groq", "model": "llama"}}}
                    ],
                    "final_output": {"file_generate": {"artifact_path": "examples/hello_world_button.html"}},
                },
            }

    monkeypatch.setattr(tvbox_main, "_create_core_engine", lambda: FakeCore())
    client = TestClient(_create_app())

    response = client.post("/api/voice/chat", json={"message": "帮我写一个 html 文件", "locale": "zh-CN"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "Generated artifact" in payload["reply"]
    assert payload["conversation"][-1]["speaker"] == "HomeHub"
    assert payload["artifacts"][0]["url"].endswith("/api/generated-artifacts/open/file/hello_world_button")