from __future__ import annotations

import json
import re
from typing import Any
from pathlib import Path

from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


def handle_extract_records_step(
    coordinator: Any,
    _step: dict[str, Any],
    task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    records = coordinator._extract_records(task.input_text)
    return {"records": records, "count": len(records)}


def handle_persist_records_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    context: CoreContextSchema,
    step_outputs: dict[str, Any],
) -> dict[str, Any]:
    records = step_outputs.get("extract_records", {}).get("records", [])
    state = coordinator.session_store.append_records(context.session_id, records)
    return {"saved": len(records), "total_records": len(state.get("records", []))}


def handle_parse_query_step(
    coordinator: Any,
    _step: dict[str, Any],
    task: TaskSchema,
    context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    state = coordinator.session_store.get(context.session_id)
    return {"query": coordinator._parse_query(task.input_text, state.get("records", []))}


def handle_aggregate_query_step(
    coordinator: Any,
    step: dict[str, Any],
    _task: TaskSchema,
    context: CoreContextSchema,
    step_outputs: dict[str, Any],
) -> dict[str, Any]:
    query = step_outputs.get("parse_query", {}).get("query", {})
    state = coordinator.session_store.get(context.session_id)
    model_choice = ((step.get("capability") or {}).get("model_choice") or {})
    return {"aggregation": coordinator._aggregate_records(state.get("records", []), query, model_choice)}


def handle_ocr_extract_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "text", "status": "dispatched", "task": "ocr", "message": "OCR dispatch prepared."}


def handle_stt_transcribe_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "text", "status": "dispatched", "task": "stt", "message": "STT dispatch prepared."}


def handle_tts_synthesize_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "audio", "status": "dispatched", "task": "tts", "message": "TTS dispatch prepared."}


def handle_image_generate_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "image", "status": "dispatched", "task": "image_generation"}


def handle_video_generate_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "video", "status": "dispatched", "task": "video_generation"}


def handle_file_generate_step(
    coordinator: Any,
    _step: dict[str, Any],
    task: TaskSchema,
    context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    target_path = _resolve_requested_file_path(task.input_text)
    extension = target_path.suffix.lower() if target_path else _infer_file_extension(task.input_text)
    generated_content = _generate_file_content(coordinator, task, context, extension)

    if target_path is None:
        artifact_id = _artifact_id_from_trace(context.trace_id, extension)
        persisted_path = coordinator.generated_artifact_store.persist(
            "code",
            artifact_id,
            generated_content,
            extension=extension,
        )
        target_path = Path(str(persisted_path))
        storage = "generated_artifact_store"
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(generated_content, encoding="utf-8")
        storage = "workspace"

    return {
        "artifact_type": "file",
        "artifact_path": str(target_path),
        "status": "generated",
        "task": "file_generation",
        "content": generated_content,
        "storage": storage,
        "file_name": target_path.name,
    }


def handle_file_read_step(
    coordinator: Any,
    _step: dict[str, Any],
    task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    target_path = _resolve_existing_file_path(task.input_text)
    if target_path is None:
        return {
            "artifact_type": "file",
            "status": "not_found",
            "message": "Requested file path was not found in the workspace.",
            "content": "",
        }

    content = target_path.read_text(encoding="utf-8")
    return {
        "artifact_type": "file",
        "artifact_path": str(target_path),
        "status": "read",
        "message": f"File content from {target_path}",
        "content": content,
        "file_name": target_path.name,
        "storage": "workspace",
    }


def _resolve_requested_file_path(text: str) -> Path | None:
    patterns = [
        r"(?:保存到|保存为|写入到|写到|输出到)\s*[:：]?\s*([A-Za-z0-9_./\\-]+\.[A-Za-z0-9]+)",
        r"([A-Za-z0-9_./\\-]+\.(?:html?|js|css|json|md|txt|py|ya?ml))",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip().strip("\"'")
        if not candidate:
            continue
        return Path(candidate).expanduser()
    return None


def _resolve_existing_file_path(text: str) -> Path | None:
    match = re.search(r"([A-Za-z0-9_./\\-]+\.(?:html?|js|css|json|md|txt|py|ya?ml))", text, flags=re.IGNORECASE)
    if not match:
        return None
    candidate = match.group(1).strip().strip('"\'')
    if not candidate:
        return None
    path = Path(candidate).expanduser()
    candidates = [path]
    if not path.is_absolute():
        candidates.append((Path.cwd() / path).resolve())
        candidates.append((Path(__file__).resolve().parents[3] / path).resolve())
    for candidate_path in candidates:
        if candidate_path.exists() and candidate_path.is_file():
            return candidate_path
    return None


def _infer_file_extension(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("html", "网页", "web page")):
        return ".html"
    if any(marker in lowered for marker in ("javascript", " js", ".js")):
        return ".js"
    if any(marker in lowered for marker in ("css", ".css")):
        return ".css"
    if any(marker in lowered for marker in ("json", ".json")):
        return ".json"
    if any(marker in lowered for marker in ("markdown", ".md")):
        return ".md"
    return ".txt"


def _artifact_id_from_trace(trace_id: str, extension: str) -> str:
    suffix = extension.lstrip(".") or "file"
    return f"{trace_id}_{suffix}"


def _generate_file_content(coordinator: Any, task: TaskSchema, context: CoreContextSchema, extension: str) -> str:
    generated = _normalize_model_file_content(_generate_file_content_via_model(coordinator, task, context, extension), extension)
    if generated:
        return generated
    if extension == ".html":
        return _fallback_html_content(task.input_text)
    return task.input_text


def _generate_file_content_via_model(coordinator: Any, task: TaskSchema, context: CoreContextSchema, extension: str) -> str | None:
    if coordinator.model_router is None or not hasattr(coordinator, "_invoke_model_text"):
        return None
    return coordinator._invoke_model_text(
        task_type="code_generation",
        prompt=(
            "Generate only the final file content. Do not use markdown fences.\n"
            f"task_intent: {task.intent}\n"
            f"session_id: {context.session_id}\n"
            f"target_extension: {extension}\n"
            f"user_request: {task.input_text}"
        ),
        system_prompt=(
            "You are the NestHub runtime code generation engine. "
            "Return only valid file content for the requested file type."
        ),
        temperature=0.2,
    )


def _normalize_model_file_content(cleaned: str | None, extension: str) -> str | None:
    if not cleaned or cleaned.startswith("Model response (mock):"):
        return None
    cleaned = _strip_code_fences(cleaned)
    if extension == ".json":
        try:
            return json.dumps(json.loads(cleaned), ensure_ascii=False, indent=2)
        except Exception:
            return None
    return cleaned


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", stripped)
    stripped = re.sub(r"\n```$", "", stripped)
    return stripped.strip()


def _fallback_html_content(request_text: str) -> str:
    alert_message = _extract_alert_message(request_text)
    button_label = _extract_button_label(request_text)
    title = _extract_html_title(request_text)
    return """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{title}</title>
</head>
<body>
  <button id=\"submitButton\" type=\"button\">{button_label}</button>
  <script>
    document.getElementById(\"submitButton\").addEventListener(\"click\", function () {{
      alert(\"{alert_message}\");
    }});
  </script>
</body>
</html>
""".format(title=title, button_label=button_label, alert_message=alert_message)


def _extract_alert_message(text: str) -> str:
    match = re.search(r"(?:弹出|提示|alert)\s*[:：]?\s*([A-Za-z0-9 ,.!?-]+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if "hello" in text.lower() and "world" in text.lower():
        return "hello,world!"
    return "hello,world!"


def _extract_button_label(text: str) -> str:
    match = re.search(r"(?:按钮|button)\s*[:：]?\s*([A-Za-z][A-Za-z0-9 _-]{0,20})", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if "submit" in text.lower():
        return "Submit"
    return "Submit"


def _extract_html_title(text: str) -> str:
    if "hello" in text.lower() and "world" in text.lower():
        return "Hello World"
    return "NestHub Generated Page"


def handle_web_retrieve_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "web_content", "status": "dispatched", "task": "web_research"}


def handle_web_summarize_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "summary", "status": "dispatched", "task": "web_summary"}


def handle_prepare_runtime_tools_step(
    coordinator: Any,
    step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    repair_metadata = step.get("metadata") or {}
    missing_items = list(repair_metadata.get("missing_tools", []))
    install_plan = coordinator._build_runtime_install_plan(missing_items)
    execution_result = None
    if coordinator._allow_runtime_auto_install() and install_plan.get("auto_install"):
        execution_result = coordinator._execute_runtime_install_plan(install_plan)
    return {
        "status": "executed" if execution_result else "prepared",
        "missing_items": missing_items,
        "install_plan": install_plan,
        "install_execution": execution_result,
        "message": "Runtime tool preparation plan generated.",
    }


def handle_generate_workflow_artifact_step(
    coordinator: Any,
    step: dict[str, Any],
    task: TaskSchema,
    context: CoreContextSchema,
    step_outputs: dict[str, Any],
) -> dict[str, Any]:
    analysis_output = step_outputs.get("analyze_workflow_context", {})
    summary = analysis_output.get("summary") or analysis_output.get("analysis") or task.input_text
    content_lines = [
        f"task_intent: {task.intent}",
        f"session_id: {context.session_id}",
        "",
        str(summary),
    ]
    artifact_id = f"artifact_{context.trace_id}"
    artifact_path = coordinator.generated_artifact_store.persist(
        "feature",
        artifact_id,
        "\n".join(content_lines),
        extension=".md",
    )
    return {
        "artifact": str(artifact_path),
        "artifact_type": "document",
        "artifact_path": str(artifact_path),
        "status": "generated",
        "summary": str(summary),
    }


def handle_persist_workflow_output_step(
    coordinator: Any,
    _step: dict[str, Any],
    _task: TaskSchema,
    _context: CoreContextSchema,
    step_outputs: dict[str, Any],
) -> dict[str, Any]:
    artifact_payload = step_outputs.get("generate_workflow_artifact", {})
    artifact_path = artifact_payload.get("artifact_path")
    if not artifact_path:
        return {
            "delivery_status": "skipped",
            "stored_output": None,
            "message": "No artifact available for persistence.",
        }
    path = Path(str(artifact_path))
    return {
        "delivery_status": "stored",
        "stored_output": str(path),
        "message": f"Workflow output stored at {path.name}.",
    }