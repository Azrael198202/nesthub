from __future__ import annotations

import asyncio
import base64
from pathlib import Path

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


def test_tvbox_app_starts_with_bridge_worker_when_configured(monkeypatch) -> None:
    class FakeCore:
        async def handle(self, *args, **kwargs):
            return {"task": {"intent": "general_task"}, "execution_result": {"final_output": {"single_step": {"message": "ok"}}}, "artifacts": []}

    monkeypatch.setattr(tvbox_main, "_create_core_engine", lambda: FakeCore())
    monkeypatch.setattr(tvbox_main, "_load_bridge_config", lambda: ("https://bridge.example/api/bridge", "token-123", 5))

    app = _create_app()

    with TestClient(app) as client:
        response = client.get("/api/dashboard")
        assert response.status_code == 200


def test_tvbox_custom_agent_intake_persists_document_attachment(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCore:
        async def handle(self, input_text, context, fmt="dict", use_langraph=True):
            captured["input_text"] = input_text
            captured["context"] = context
            return {
                "task": {"intent": "file_upload_task"},
                "artifacts": [],
                "execution_result": {
                    "execution_type": "workflow",
                    "final_output": {
                        "analyze_document": {
                            "message": "已完成文档总结。",
                            "summary": "文档摘要",
                        }
                    },
                },
            }

    monkeypatch.setattr(tvbox_main, "_create_core_engine", lambda: FakeCore())
    client = TestClient(_create_app())

    response = client.post(
        "/api/custom-agents/intake",
        json={
            "id": "agent-doc-case",
            "locale": "zh-CN",
            "attachments": [
                {
                    "name": "brief.txt",
                    "mimeType": "text/plain",
                    "sizeBytes": 12,
                    "fileBase64": base64.b64encode("项目资料正文".encode("utf-8")).decode("utf-8"),
                    "kind": "file",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["reply"] == "已完成文档总结。"
    assert payload["sessionId"] == "tvbox:studio:agent-doc-case"
    context = captured["context"]
    assert isinstance(context, dict)
    assert context["session_id"] == "tvbox:studio:agent-doc-case"
    attachments = context["metadata"]["attachments"]
    assert attachments[0]["input_type"] == "document"
    received_path = Path(attachments[0]["received_path"])
    assert received_path.exists()
    assert received_path.read_text(encoding="utf-8") == "项目资料正文"


def test_tvbox_voice_chat_accepts_attachment_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCore:
        async def handle(self, input_text, context, fmt="dict", use_langraph=True):
            captured["input_text"] = input_text
            captured["context"] = context
            return {
                "task": {"intent": "file_upload_task"},
                "artifacts": [],
                "execution_result": {
                    "execution_type": "workflow",
                    "final_output": {
                        "analyze_document": {
                            "message": "已完成文档翻译。",
                            "translation": "Translated content",
                        }
                    },
                },
            }

    monkeypatch.setattr(tvbox_main, "_create_core_engine", lambda: FakeCore())
    client = TestClient(_create_app())

    response = client.post(
        "/api/voice/chat",
        json={
            "locale": "zh-CN",
            "agentId": "voice-doc-agent",
            "attachments": [
                {
                    "name": "translate.md",
                    "mimeType": "text/markdown",
                    "sizeBytes": 20,
                    "fileBase64": base64.b64encode("需要翻译的文档内容".encode("utf-8")).decode("utf-8"),
                    "kind": "file",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["reply"] == "已完成文档翻译。"
    assert captured["input_text"] == "收到文档: translate.md"
    context = captured["context"]
    assert isinstance(context, dict)
    assert context["session_id"] == "tvbox:studio:voice-doc-agent"
    attachments = context["metadata"]["attachments"]
    assert attachments[0]["input_type"] == "document"


def test_tvbox_custom_agent_intake_accepts_multipart_upload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCore:
        async def handle(self, input_text, context, fmt="dict", use_langraph=True):
            captured["input_text"] = input_text
            captured["context"] = context
            return {
                "task": {"intent": "file_upload_task"},
                "artifacts": [],
                "execution_result": {
                    "execution_type": "workflow",
                    "final_output": {
                        "analyze_document": {
                            "message": "已完成文档总结。",
                            "summary": "multipart summary",
                        }
                    },
                },
            }

    monkeypatch.setattr(tvbox_main, "_create_core_engine", lambda: FakeCore())
    client = TestClient(_create_app())

    response = client.post(
        "/api/custom-agents/intake",
        data={
            "id": "agent-multipart-case",
            "locale": "zh-CN",
            "message": "",
            "attachment_kind": "file",
        },
        files={
            "attachment": ("upload.md", b"# heading\ncontent body", "text/markdown"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["sessionId"] == "tvbox:studio:agent-multipart-case"
    assert captured["input_text"] == "收到文档: upload.md"
    context = captured["context"]
    assert isinstance(context, dict)
    attachments = context["metadata"]["attachments"]
    assert attachments[0]["input_type"] == "document"
    received_path = Path(attachments[0]["received_path"])
    assert received_path.exists()
    assert received_path.read_text(encoding="utf-8") == "# heading\ncontent body"