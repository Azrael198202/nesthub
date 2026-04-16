from __future__ import annotations

from typing import Any

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