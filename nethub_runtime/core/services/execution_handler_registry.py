from __future__ import annotations

from typing import Any

from nethub_runtime.core.services.execution_step_handlers import (
    handle_aggregate_query_step,
    handle_extract_records_step,
    handle_file_generate_step,
    handle_image_generate_step,
    handle_ocr_extract_step,
    handle_parse_query_step,
    handle_persist_records_step,
    handle_stt_transcribe_step,
    handle_tts_synthesize_step,
    handle_video_generate_step,
    handle_web_retrieve_step,
    handle_web_summarize_step,
)


def build_executor_handlers(coordinator: Any) -> dict[str, Any]:
    return {
        "agent": coordinator._dispatch_agent_step,
        "knowledge_retrieval": coordinator._dispatch_knowledge_step,
        "tool": coordinator._dispatch_tool_step,
        "llm": coordinator._dispatch_llm_step,
        "code": coordinator._dispatch_code_step,
    }


def build_step_handlers(coordinator: Any) -> dict[str, dict[str, Any]]:
    return {
        "agent": {
            "manage_information_agent": coordinator._handle_manage_information_agent_step,
        },
        "knowledge_retrieval": {
            "query_information_knowledge": coordinator._handle_query_information_knowledge_step,
        },
        "tool": {
            "extract_records": lambda step, task, context, step_outputs: handle_extract_records_step(coordinator, step, task, context, step_outputs),
            "persist_records": lambda step, task, context, step_outputs: handle_persist_records_step(coordinator, step, task, context, step_outputs),
            "parse_query": lambda step, task, context, step_outputs: handle_parse_query_step(coordinator, step, task, context, step_outputs),
            "aggregate_query": lambda step, task, context, step_outputs: handle_aggregate_query_step(coordinator, step, task, context, step_outputs),
            "ocr_extract": lambda step, task, context, step_outputs: handle_ocr_extract_step(coordinator, step, task, context, step_outputs),
            "stt_transcribe": lambda step, task, context, step_outputs: handle_stt_transcribe_step(coordinator, step, task, context, step_outputs),
            "tts_synthesize": lambda step, task, context, step_outputs: handle_tts_synthesize_step(coordinator, step, task, context, step_outputs),
            "image_generate": lambda step, task, context, step_outputs: handle_image_generate_step(coordinator, step, task, context, step_outputs),
            "video_generate": lambda step, task, context, step_outputs: handle_video_generate_step(coordinator, step, task, context, step_outputs),
            "file_generate": lambda step, task, context, step_outputs: handle_file_generate_step(coordinator, step, task, context, step_outputs),
            "web_retrieve": lambda step, task, context, step_outputs: handle_web_retrieve_step(coordinator, step, task, context, step_outputs),
            "web_summarize": lambda step, task, context, step_outputs: handle_web_summarize_step(coordinator, step, task, context, step_outputs),
        },
        "llm": {},
        "code": {},
    }