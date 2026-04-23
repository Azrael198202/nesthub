from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.information_agent_service import InformationAgentService


class _FakeSessionStore:
    def __init__(self) -> None:
        self._payloads: dict[str, dict[str, Any]] = {}

    def get(self, session_id: str) -> dict[str, Any]:
        return dict(self._payloads.get(session_id, {}))

    def patch(self, session_id: str, patch_data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(self._payloads.get(session_id, {}))
        payload.update(patch_data)
        self._payloads[session_id] = payload
        return dict(payload)


@dataclass
class _FakeVectorStore:
    def search(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def add_knowledge(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs


def _noop(*_args: Any, **_kwargs: Any) -> Any:
    return []


def test_create_information_agent_resets_stale_collection_state() -> None:
    session_store = _FakeSessionStore()
    service = InformationAgentService(session_store=session_store, vector_store=_FakeVectorStore())
    session_id = "unit-create-reset"
    session_store.patch(
        session_id,
        {
            "configured_agent": {"status": "active"},
            "knowledge_collection": {
                "active": True,
                "field_index": 2,
                "fields": [{"key": "summary", "prompt": "summary"}],
                "data": {"item_name": "legacy"},
            },
            "agent_setup": {"active": False, "stage": "completed"},
        },
    )

    result = service.manage_information_agent(
        text="创建一个日程和提醒智能体",
        task=TaskSchema(
            task_id="t1",
            intent="create_information_agent",
            input_text="创建一个日程和提醒智能体",
            domain="agent_management",
            constraints={},
            output_requirements=["agent", "dialog"],
            metadata={},
        ),
        context=CoreContextSchema(trace_id="trace-unit", session_id=session_id, metadata={}, session_state={}),
        normalize_yes_no=_noop,
        sanitize_member_value=lambda _k, v: v,
        extract_records=_noop,
    )

    assert result["dialog_state"]["stage"] == "ai_workflow"
    state = session_store.get(session_id)
    collection = state.get("knowledge_collection") or {}
    assert collection.get("active") is False
    assert collection.get("field_index") == 0


def test_refine_creation_parses_schema_and_trigger_markers_without_repeating_schema_question() -> None:
    session_store = _FakeSessionStore()
    service = InformationAgentService(session_store=session_store, vector_store=_FakeVectorStore())
    session_id = "unit-create-structured-refine"

    # Start creation workflow.
    service.manage_information_agent(
        text="创建一个日程和提醒智能体",
        task=TaskSchema(
            task_id="t2",
            intent="create_information_agent",
            input_text="创建一个日程和提醒智能体",
            domain="agent_management",
            constraints={},
            output_requirements=["agent", "dialog"],
            metadata={},
        ),
        context=CoreContextSchema(trace_id="trace-unit-2", session_id=session_id, metadata={}, session_state={}),
        normalize_yes_no=_noop,
        sanitize_member_value=lambda _k, v: v,
        extract_records=_noop,
    )

    refined = service.manage_information_agent(
        text="用于管理我的日程和出行提醒。请收集字段：日期、开始时间、结束时间、事项、地点、提醒时间、备注。触发词：查日程、加日程、设提醒、查提醒。",
        task=TaskSchema(
            task_id="t3",
            intent="refine_information_agent",
            input_text="用于管理我的日程和出行提醒。请收集字段：日期、开始时间、结束时间、事项、地点、提醒时间、备注。触发词：查日程、加日程、设提醒、查提醒。",
            domain="agent_management",
            constraints={},
            output_requirements=["agent", "dialog"],
            metadata={},
        ),
        context=CoreContextSchema(trace_id="trace-unit-3", session_id=session_id, metadata={}, session_state={}),
        normalize_yes_no=_noop,
        sanitize_member_value=lambda _k, v: v,
        extract_records=_noop,
    )

    message = str(refined.get("message") or "")
    assert "收集哪些字段" not in message
    assert "完成创建" in message
