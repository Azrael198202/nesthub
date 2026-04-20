from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from api.public_api.app import app
from nethub_runtime.core.services import document_runtime_plugin
from nethub_runtime.core.services.context_manager import ContextManager
from nethub_runtime.core.services.core_engine import AICore
from nethub_runtime.core.services.execution_step_handlers import handle_ocr_extract_step
from nethub_runtime.core.schemas.task_schema import TaskSchema


def test_context_manager_ingests_document_attachments(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("第一行\n第二行\n第三行", encoding="utf-8")

    manager = ContextManager()
    context = manager.load(
        {
            "session_id": "doc-session-case",
            "metadata": {
                "attachments": [
                    {
                        "file_name": "notes.txt",
                        "content_type": "text/plain",
                        "input_type": "document",
                        "stored_path": str(source),
                        "external_message_id": "msg-doc-1",
                    }
                ]
            },
        }
    )

    documents = context.session_state.get("documents") or []
    assert len(documents) == 1
    received_path = Path(documents[0]["received_path"])
    assert received_path.exists()
    assert received_path.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_core_engine_handles_session_document_summary() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    temp_path = Path("/tmp/brief.txt")
    temp_path.write_text("项目进度正常。下周需要完成交付测试。", encoding="utf-8")
    result = asyncio.run(
        core.handle(
            input_text="请对这份文档进行总结，然后发给我",
            context={
                "session_id": "document-summary-session",
                "metadata": {
                    "attachments": [
                        {
                            "file_name": "brief.txt",
                            "content_type": "text/plain",
                            "input_type": "document",
                            "stored_path": str(temp_path),
                        }
                    ]
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    final_output = result["execution_result"]["final_output"]
    assert "analyze_document" in final_output
    assert final_output["analyze_document"]["status"] == "completed"
    assert final_output["analyze_document"]["summary"] or final_output["analyze_document"]["message"]


def test_bridge_service_builds_stable_document_session_id() -> None:
    message = app.state.bridge_service.create_message(
        "line",
        "U-doc",
        "C-doc",
        "M-doc",
        "分析文档: brief.txt",
        {},
        attachments=[],
    )

    session_id = app.state.bridge_service._build_session_id(message)

    assert session_id == "bridge:line:C-doc"


def test_core_engine_waits_for_document_after_request() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    session_id = f"document-pending-request-session-{uuid.uuid4().hex}"

    first = asyncio.run(
        core.handle(
            input_text="帮我分析一下文件，给我总结",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    first_output = first["execution_result"]["final_output"]["analyze_document"]
    assert first_output["status"] == "awaiting_document"
    assert first_output["suppress_reply"] is True

    temp_path = Path("/tmp/pending_request_brief.txt")
    temp_path.write_text("这是后续上传的项目说明。需要总结关键行动项。", encoding="utf-8")
    second = asyncio.run(
        core.handle(
            input_text="收到文档: pending_request_brief.txt",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                    "attachments": [
                        {
                            "file_name": "pending_request_brief.txt",
                            "content_type": "text/plain",
                            "input_type": "document",
                            "stored_path": str(temp_path),
                            "external_message_id": "msg-pending-doc",
                        }
                    ],
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    second_output = second["execution_result"]["final_output"]["analyze_document"]
    assert second_output["status"] == "completed"
    assert second_output["summary"] or second_output["message"]


def test_core_engine_waits_for_request_after_document_upload() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    session_id = f"document-pending-upload-session-{uuid.uuid4().hex}"
    temp_path = Path("/tmp/pending_upload_brief.txt")
    temp_path.write_text("先上传文档，再补发总结需求。", encoding="utf-8")

    first = asyncio.run(
        core.handle(
            input_text="收到文档: pending_upload_brief.txt",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                    "attachments": [
                        {
                            "file_name": "pending_upload_brief.txt",
                            "content_type": "text/plain",
                            "input_type": "document",
                            "stored_path": str(temp_path),
                            "external_message_id": "msg-upload-doc",
                        }
                    ],
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    first_output = first["execution_result"]["final_output"]["analyze_document"]
    assert first_output["status"] == "awaiting_request"
    assert first_output["suppress_reply"] is True

    second = asyncio.run(
        core.handle(
            input_text="请对这份文档进行总结，然后发给我",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    second_output = second["execution_result"]["final_output"]["analyze_document"]
    assert second_output["status"] == "completed"
    assert second_output["summary"] or second_output["message"]


def test_bridge_service_skips_line_message_for_standby_result() -> None:
    messages = app.state.bridge_service._build_line_messages(
        {
            "reply": "",
            "suppress_reply": True,
            "downloads": [],
        }
    )

    assert messages == []


def test_document_plugin_uses_shared_ocr_for_image_followup(monkeypatch) -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    session_id = f"image-followup-session-{uuid.uuid4().hex}"
    image_path = Path("/tmp/followup_image.png")
    image_path.write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(
        document_runtime_plugin,
        "extract_image_text_with_ocr",
        lambda coordinator, path: ("票据金额 100 元\n商户 测试店", "mock_ocr"),
    )

    first = asyncio.run(
        core.handle(
            input_text="收到图片: followup_image.png",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                    "attachments": [
                        {
                            "file_name": "followup_image.png",
                            "content_type": "image/png",
                            "input_type": "image",
                            "stored_path": str(image_path),
                            "external_message_id": "msg-image-doc-1",
                        }
                    ],
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )
    assert first["execution_result"]["final_output"]["analyze_document"]["status"] == "awaiting_request"

    second = asyncio.run(
        core.handle(
            input_text="请对这张图片进行总结，然后发给我",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    output = second["execution_result"]["final_output"]["analyze_document"]
    assert output["status"] == "completed"
    assert "mock_ocr" in output["parsers"]


def test_document_plugin_uses_visual_analysis_for_image_content_questions(monkeypatch) -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    session_id = f"image-visual-session-{uuid.uuid4().hex}"
    image_path = Path("/tmp/visual_image.png")
    image_path.write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(
        document_runtime_plugin,
        "extract_image_text_with_ocr",
        lambda coordinator, path: ("票据 金额 100 元", "mock_ocr"),
    )
    async def _fake_visual(*args, **kwargs):
        return "图片里是一只猫，坐在沙发上。"
    monkeypatch.setattr(document_runtime_plugin, "_invoke_visual_model", _fake_visual)

    first = asyncio.run(
        core.handle(
            input_text="收到图片: visual_image.png",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                    "attachments": [
                        {
                            "file_name": "visual_image.png",
                            "content_type": "image/png",
                            "input_type": "image",
                            "stored_path": str(image_path),
                            "external_message_id": "msg-visual-1",
                        }
                    ],
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )
    assert first["execution_result"]["final_output"]["analyze_document"]["status"] == "awaiting_request"

    second = asyncio.run(
        core.handle(
            input_text="请分析这张图片里面的动物是什么",
            context={
                "session_id": session_id,
                "metadata": {
                    "source_im": "line",
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    output = second["execution_result"]["final_output"]["analyze_document"]
    assert output["status"] == "completed"
    assert output["requested_action"] == "analyze_visual"
    assert "一只猫" in output["summary"]


def test_ocr_extract_step_uses_shared_ocr_helper(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "ocr_case.png"
    image_path.write_bytes(b"fake")

    class _FakeCoordinator:
        capability_acquisition_service = None

    monkeypatch.setattr(
        "nethub_runtime.core.services.execution_step_handlers.extract_image_text_with_ocr",
        lambda coordinator, path: ("图片里的文本", "mock_ocr"),
    )

    context = ContextManager().load(
        {
            "session_id": "ocr-shared-session",
            "metadata": {
                "attachments": [
                    {
                        "file_name": "ocr_case.png",
                        "content_type": "image/png",
                        "input_type": "image",
                        "stored_path": str(image_path),
                    }
                ]
            },
        }
    )
    task = TaskSchema(task_id="task_ocr_case", intent="ocr_task", domain="multimodal_ops", input_text="请识别这张图片")

    result = handle_ocr_extract_step(_FakeCoordinator(), {}, task, context, {})

    assert result["status"] == "completed"
    assert result["method"] == "mock_ocr"
    assert result["content"] == "图片里的文本"