from __future__ import annotations

import json
import os
import mimetypes
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema
from nethub_runtime.core.services.execution_handler_registry import (
    ExecutionHandlerPluginManifest,
    ExecutionHandlerPluginStepSpec,
)
from nethub_runtime.core.services.execution_step_handlers import extract_image_text_with_ocr
from nethub_runtime.core.utils.id_generator import generate_id

_DOCUMENT_SUFFIXES = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".md"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_SUPPORTED_SUFFIXES = _DOCUMENT_SUFFIXES | _IMAGE_SUFFIXES
_POLICY_STORE = SemanticPolicyStore(policy_path=SEMANTIC_POLICY_PATH)


def _document_runtime_policy() -> dict[str, Any]:
    try:
        return _POLICY_STORE.load_runtime_policy().get("document_runtime") or {}
    except Exception:
        return {}


def _policy_markers(key: str) -> tuple[str, ...]:
    value = _document_runtime_policy().get(key) or []
    return tuple(str(item) for item in value if str(item).strip())


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _document_wait_timeout_seconds() -> int:
    raw = str(os.getenv("NESTHUB_DOCUMENT_WAIT_TIMEOUT_SECONDS", "300") or "300").strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 300
    return max(120, min(parsed, 300))


def _is_bridge_line_context(context: CoreContextSchema) -> bool:
    return str((context.metadata or {}).get("source_im") or "").strip().lower() == "line"


def _build_standby_message(wait_state: str, context: CoreContextSchema) -> str:
    if _is_bridge_line_context(context):
        return ""
    if wait_state == "awaiting_document":
        return "已记录文档处理需求，等待文档或图片上传后自动继续。"
    return "已收到文档或图片，等待你的处理要求后继续。"


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _pending_request_is_active(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    request_text = str(payload.get("request_text") or "").strip()
    if not request_text:
        return False
    expires_at = _parse_iso_datetime(payload.get("expires_at"))
    if expires_at is None:
        return False
    return expires_at >= _utc_now()


def _get_active_pending_request(state: dict[str, Any]) -> dict[str, Any] | None:
    payload = state.get("pending_document_request")
    if not isinstance(payload, dict):
        return None
    return payload if _pending_request_is_active(payload) else None


def _looks_like_explicit_document_request(text: str, *, has_context: bool) -> bool:
    lowered = text.lower()
    if not lowered.strip():
        return False
    summary_markers = _policy_markers("summary_markers")
    translate_markers = _policy_markers("translate_markers")
    analyze_markers = _policy_markers("analyze_markers")
    action_requested = (
        any(marker in lowered for marker in summary_markers)
        or any(marker in lowered for marker in translate_markers)
        or any(marker in lowered for marker in analyze_markers)
    )
    if not action_requested:
        return False
    document_reference_markers = _policy_markers("document_reference_markers")
    followup_reference_markers = _policy_markers("followup_reference_markers")
    has_document_reference = (
        any(marker in lowered for marker in document_reference_markers)
        or any(marker in text for marker in followup_reference_markers)
        or any(_looks_like_document_name(token) for token in re.findall(r"[\w.-]+", lowered))
    )
    return has_document_reference or has_context


def _resolve_analysis_targets(text: str, context: CoreContextSchema) -> list[dict[str, Any]]:
    attachments = list((context.session_state or {}).get("analysis_attachments") or [])
    if not attachments:
        attachments = list((context.session_state or {}).get("documents") or [])
    if not attachments:
        return []
    lowered = text.lower()
    if any(marker in lowered for marker in _policy_markers("multi_doc_markers")):
        return attachments
    named_matches = []
    for item in attachments:
        file_name = str(item.get("file_name") or "")
        if file_name and file_name.lower() in lowered:
            named_matches.append(item)
    if named_matches:
        return named_matches
    return [attachments[-1]]


def _looks_like_document_name(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.endswith(suffix) for suffix in _SUPPORTED_SUFFIXES)


def _detect_document_action(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in _policy_markers("translate_markers")):
        return "translate"
    if any(marker in lowered for marker in _policy_markers("summary_markers")):
        return "summarize"
    if any(marker in lowered for marker in _policy_markers("analyze_markers")):
        return "analyze"
    return "summarize"


def _looks_like_visual_analysis_request(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _policy_markers("visual_analyze_markers"))


def _is_image_target(item: dict[str, Any]) -> bool:
    input_type = str(item.get("input_type") or "").lower()
    content_type = str(item.get("content_type") or "").lower()
    file_name = str(item.get("file_name") or "").lower()
    return input_type == "image" or content_type.startswith("image/") or any(file_name.endswith(suffix) for suffix in _IMAGE_SUFFIXES)


def _image_to_data_url(path: Path, content_type: str) -> str:
    resolved_type = content_type or mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = path.read_bytes().hex()
    import base64

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{resolved_type};base64,{encoded}"


def _detect_target_language(text: str, context: CoreContextSchema) -> str:
    lowered = text.lower()
    if "中文" in text or "chinese" in lowered:
        return "Chinese"
    if "英文" in text or "english" in lowered:
        return "English"
    if "日文" in text or "日语" in text or "japanese" in lowered:
        return "Japanese"
    locale = str(context.locale or "").lower()
    if locale.startswith("zh"):
        return "Chinese"
    if locale.startswith("ja"):
        return "Japanese"
    return "English"


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_document_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        return _read_text_file(path), "plain_text"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            content = "\n".join((page.extract_text() or "") for page in reader.pages)
            return content, "pypdf"
        except Exception:
            return "", "pdf_unavailable"
    if suffix in {".docx", ".doc"}:
        try:
            import docx  # type: ignore

            document = docx.Document(str(path))
            return "\n".join(paragraph.text for paragraph in document.paragraphs), "python_docx"
        except Exception:
            return "", "docx_unavailable"
    if suffix in {".xlsx", ".xls"}:
        try:
            from openpyxl import load_workbook  # type: ignore

            workbook = load_workbook(str(path), data_only=True)
            lines: list[str] = []
            for sheet in workbook.worksheets:
                lines.append(f"# Sheet: {sheet.title}")
                for row in sheet.iter_rows(values_only=True):
                    values = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                    if values:
                        lines.append(" | ".join(values))
            return "\n".join(lines), "openpyxl"
        except Exception:
            return "", "excel_unavailable"
    if suffix in _IMAGE_SUFFIXES:
        return extract_image_text_with_ocr(None, path)
    return "", "unsupported"


def _fallback_summary(text: str, file_names: list[str]) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return f"已接收文件 {', '.join(file_names)}，但当前环境缺少可用解析器，暂时无法提取正文。"
    excerpt = cleaned[:400]
    return f"文件 {', '.join(file_names)} 的内容摘录：{excerpt}"


async def _invoke_document_model(coordinator: Any, *, task_type: str, prompt: str, system_prompt: str) -> str:
    router = getattr(coordinator, "model_router", None)
    if router is None:
        return ""
    try:
        return await router.invoke(task_type=task_type, prompt=prompt, system_prompt=system_prompt)
    except Exception:
        return ""


async def _invoke_visual_model(
    coordinator: Any,
    *,
    task_type: str,
    prompt: str,
    system_prompt: str,
    image_path: Path,
    content_type: str,
) -> str:
    router = getattr(coordinator, "model_router", None)
    if router is None:
        return ""
    try:
        return await router.invoke_multimodal(
            task_type=task_type,
            system_prompt=system_prompt,
            user_content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _image_to_data_url(image_path, content_type)}},
            ],
        )
    except Exception:
        return ""


def _run_in_existing_loop(coro: Any) -> Any:
    import asyncio
    import threading

    result: dict[str, Any] = {}
    error: dict[str, Exception] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


def handle_analyze_document_step(
    coordinator: Any,
    _step: dict[str, Any],
    task: TaskSchema,
    context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    pending_request = _get_active_pending_request(context.session_state or {})
    wait_state = str(task.constraints.get("document_wait_state") or "").strip()
    session_store = getattr(coordinator, "session_store", None)

    if wait_state == "awaiting_document":
        now = _utc_now()
        timeout_seconds = _document_wait_timeout_seconds()
        expires_at = now + timedelta(seconds=timeout_seconds)
        if session_store is not None:
            session_store.patch(
                context.session_id,
                {
                    "pending_document_request": {
                        "request_text": str(task.constraints.get("document_request_text") or task.input_text or "").strip(),
                        "document_action": str(task.constraints.get("document_action") or "summarize"),
                        "target_language": str(task.constraints.get("target_language") or ""),
                        "requested_at": now.isoformat(),
                        "expires_at": expires_at.isoformat(),
                    }
                },
            )
        return {
            "artifact_type": "document",
            "status": "awaiting_document",
            "message": _build_standby_message(wait_state, context),
            "standby": True,
            "suppress_reply": _is_bridge_line_context(context),
            "wait_until": expires_at.isoformat(),
        }

    if wait_state == "awaiting_request":
        return {
            "artifact_type": "document",
            "status": "awaiting_request",
            "message": _build_standby_message(wait_state, context),
            "standby": True,
            "suppress_reply": _is_bridge_line_context(context),
        }

    targets = _resolve_analysis_targets(task.input_text, context)
    if not targets:
        return {
            "artifact_type": "document",
            "status": "no_document",
            "message": "当前 session 中没有可分析的文档，请先上传或发送文档。",
        }

    extracted_chunks: list[str] = []
    source_files: list[str] = []
    parsers: list[str] = []
    image_targets: list[tuple[Path, str, str]] = []
    for item in targets:
        path_value = str(item.get("received_path") or item.get("stored_path") or "").strip()
        file_name = str(item.get("file_name") or Path(path_value).name or "document")
        source_files.append(file_name)
        if not path_value or not Path(path_value).exists():
            continue
        if _is_image_target(item):
            image_targets.append((Path(path_value), str(item.get("content_type") or "image/png"), file_name))
        content, parser_name = _extract_document_text(Path(path_value))
        parsers.append(parser_name)
        if content.strip():
            extracted_chunks.append(f"# {file_name}\n{content.strip()}")

    combined_text = "\n\n".join(extracted_chunks).strip()
    operation = str(task.constraints.get("document_action") or (pending_request.get("document_action") if pending_request else "summarize"))
    if operation not in {"summarize", "translate", "analyze"}:
        operation = "summarize"
    target_language = str(task.constraints.get("target_language") or (pending_request or {}).get("target_language") or _detect_target_language(task.input_text, context))
    analysis_text = combined_text[:12000]
    use_visual_analysis = bool(image_targets) and operation == "analyze" and _looks_like_visual_analysis_request(task.input_text)

    if use_visual_analysis:
        system_prompt = (
            "You analyze image content for the user. Identify visible subjects, objects, animals, scenes, and other important details. "
            "Answer in concise plain text and do not fabricate details that are not visible."
        )
        prompt = f"Analyze this image and answer the user's request: {task.input_text.strip()}"
        image_path, content_type, _image_name = image_targets[-1]
        visual_output = _run_in_existing_loop(
            _invoke_visual_model(
                coordinator,
                task_type="image_understanding",
                prompt=prompt,
                system_prompt=system_prompt,
                image_path=image_path,
                content_type=content_type,
            )
        )
        summary = visual_output.strip() or _fallback_summary(analysis_text, source_files)
        if session_store is not None and pending_request is not None:
            session_store.patch(context.session_id, {"pending_document_request": None})
        return {
            "artifact_type": "document",
            "status": "completed",
            "message": f"已完成图片内容分析，共处理 {len(source_files)} 个文件。",
            "summary": summary,
            "translation": "",
            "content": combined_text[:2000] if combined_text else "",
            "source_documents": source_files,
            "parsers": parsers,
            "document_count": len(source_files),
            "requested_action": "analyze_visual",
            "target_language": "",
        }

    if operation == "translate":
        system_prompt = (
            "You translate user-provided documents. Preserve the original meaning, keep structure when useful, "
            "and return plain text only."
        )
        prompt = (
            f"Translate the following document content into {target_language}. "
            f"If the document is long, provide a faithful condensed translation.\n\n{analysis_text}"
        )
        model_output = _run_in_existing_loop(
            _invoke_document_model(coordinator, task_type="document_analysis", prompt=prompt, system_prompt=system_prompt)
        ) if analysis_text else ""
        translation = model_output.strip() or _fallback_summary(analysis_text, source_files)
        message = f"已完成文档翻译，共处理 {len(source_files)} 个文件。"
        summary = ""
    else:
        system_prompt = (
            "You analyze user-provided documents. Return concise, structured plain text focused on the user's request."
        )
        prompt = (
            "Summarize the following document content. Highlight the main points, important facts, and any action items.\n\n"
            f"{analysis_text}"
        )
        model_output = _run_in_existing_loop(
            _invoke_document_model(coordinator, task_type="document_analysis", prompt=prompt, system_prompt=system_prompt)
        ) if analysis_text else ""
        summary = model_output.strip() or _fallback_summary(analysis_text, source_files)
        translation = ""
        message = f"已完成文档总结，共处理 {len(source_files)} 个文件。"

    if session_store is not None and pending_request is not None:
        session_store.patch(context.session_id, {"pending_document_request": None})

    return {
        "artifact_type": "document",
        "status": "completed",
        "message": message,
        "summary": summary,
        "translation": translation,
        "content": combined_text[:2000] if combined_text else "",
        "source_documents": source_files,
        "parsers": parsers,
        "document_count": len(source_files),
        "requested_action": operation,
        "target_language": target_language if operation == "translate" else "",
    }


class DocumentIntentPlugin:
    priority = 110

    def match(self, text: str, context: CoreContextSchema) -> bool:
        current_attachments = list((context.metadata or {}).get("analysis_attachments") or [])
        session_attachments = list((context.session_state or {}).get("analysis_attachments") or [])
        has_context = bool(current_attachments or session_attachments or _get_active_pending_request(context.session_state or {}))
        if current_attachments:
            return True
        return _looks_like_explicit_document_request(text, has_context=has_context)

    def run(self, text: str, context: CoreContextSchema) -> dict[str, Any]:
        current_attachments = list((context.metadata or {}).get("analysis_attachments") or [])
        session_attachments = list((context.session_state or {}).get("analysis_attachments") or [])
        pending_request = _get_active_pending_request(context.session_state or {})
        has_context = bool(current_attachments or session_attachments)
        explicit_request = _looks_like_explicit_document_request(text, has_context=has_context)
        operation = _detect_document_action(text if explicit_request else str((pending_request or {}).get("request_text") or text))
        constraints: dict[str, Any] = {
            "need_agent": False,
            "document_action": operation,
        }
        if explicit_request and operation == "translate":
            constraints["target_language"] = _detect_target_language(text, context)
        elif pending_request and str(pending_request.get("document_action") or "") == "translate":
            constraints["target_language"] = str(pending_request.get("target_language") or _detect_target_language(text, context))

        if explicit_request and not (current_attachments or session_attachments):
            constraints["document_wait_state"] = "awaiting_document"
            constraints["document_request_text"] = text.strip()
            constraints["suppress_reply"] = _is_bridge_line_context(context)
        elif current_attachments and not explicit_request and pending_request:
            constraints["consume_pending_request"] = True
        elif current_attachments and not explicit_request:
            constraints["document_wait_state"] = "awaiting_request"
            constraints["suppress_reply"] = _is_bridge_line_context(context)

        analysis = {
            "document_context": True,
            "document_count": len((context.session_state or {}).get("documents") or []),
            "analysis_attachment_count": len(session_attachments or current_attachments),
            "document_action": operation,
            "wait_state": str(constraints.get("document_wait_state") or ""),
        }
        outputs = ["text", "summary"] if operation != "translate" else ["text", "translation"]
        return {
            "intent": "file_upload_task",
            "domain": "multimodal_ops",
            "output_requirements": outputs,
            "constraints": constraints,
            "analysis": analysis,
        }


class DocumentTaskDecomposerPlugin:
    priority = 110

    def match(self, task: TaskSchema) -> bool:
        return task.intent == "file_upload_task" and "document_action" in task.constraints

    def run(self, _task: TaskSchema) -> list[SubTask]:
        return [
            SubTask(
                subtask_id=generate_id("subtask"),
                name="analyze_document",
                goal="Analyze the latest session document or the referenced uploaded documents.",
            )
        ]


class DocumentWorkflowPlannerPlugin:
    priority = 110

    def match(self, task: TaskSchema, _subtasks: list[SubTask]) -> bool:
        return task.intent == "file_upload_task" and "document_action" in task.constraints

    def run(self, task: TaskSchema, _subtasks: list[SubTask]) -> WorkflowSchema:
        return WorkflowSchema(
            workflow_id=generate_id("workflow"),
            task_id=task.task_id,
            mode="normal",
            steps=[
                WorkflowStepSchema(
                    step_id=generate_id("step"),
                    name="analyze_document",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["input_text", "session_state", "attachments"],
                    outputs=["message", "summary", "translation", "content", "source_documents"],
                    depends_on=[],
                    retry=0,
                    metadata={
                        "goal": "Summarize, analyze, or translate the uploaded document within the current session.",
                        "selection_basis": "document_runtime_plugin",
                    },
                )
            ],
            composition={
                "plugin": "document_runtime_plugin",
                "intent": task.intent,
                "document_action": task.constraints.get("document_action"),
            },
        )


class DocumentExecutionHandlerPlugin:
    def build_manifest(self, _coordinator: Any) -> ExecutionHandlerPluginManifest:
        return ExecutionHandlerPluginManifest(
            name="document_runtime_plugin",
            version="1.0",
            steps=[
                ExecutionHandlerPluginStepSpec(
                    executor_type="tool",
                    step_name="analyze_document",
                    handler=lambda step, task, context, step_outputs: handle_analyze_document_step(
                        _coordinator, step, task, context, step_outputs
                    ),
                    description="Summarize or translate session-bound uploaded documents.",
                )
            ],
        )


def document_intent_plugin() -> DocumentIntentPlugin:
    return DocumentIntentPlugin()


def document_task_decomposer_plugin() -> DocumentTaskDecomposerPlugin:
    return DocumentTaskDecomposerPlugin()


def document_workflow_planner_plugin() -> DocumentWorkflowPlannerPlugin:
    return DocumentWorkflowPlannerPlugin()


def document_execution_handler_plugin() -> DocumentExecutionHandlerPlugin:
    return DocumentExecutionHandlerPlugin()