from __future__ import annotations

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
    _task: TaskSchema,
    _context: CoreContextSchema,
    _step_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {"artifact_type": "file", "status": "dispatched", "task": "file_generation"}


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