from __future__ import annotations

import asyncio
from typing import Any

from nethub_runtime.core.services.core_engine_provider import active_core_engine_variant, create_core_engine


class _FakeModelRouter:
    def active_local_profile_info(self) -> dict[str, Any]:
        return {
            "name": "lora_sft",
            "enabled": True,
            "adapter_hint": {"training_profile": "lora_sft", "mode": "lora"},
            "task_routing_overrides": {},
        }


class _FakeLegacyCore:
    def __init__(self) -> None:
        self.model_router = _FakeModelRouter()
        self.last_context: dict[str, Any] | None = None

    async def handle(self, input_text: str, context: dict[str, Any] | None = None, fmt: str = "dict", use_langraph: bool = True) -> dict[str, Any]:
        self.last_context = dict(context or {})
        return {
            "task": {
                "task_id": "task_1",
                "intent": "data_record",
                "input_text": input_text,
                "domain": "data_ops",
                "output_requirements": ["text"],
            },
            "workflow": {"workflow_id": "wf_1", "steps": [{"name": "extract_records"}]},
            "execution_result": {
                "steps": [{"name": "extract_records", "status": "success"}],
                "final_output": {"extract_records": {"count": 1}},
            },
        }

    async def handle_stream(self, input_text: str, context: dict[str, Any] | None = None, fmt: str = "dict"):
        self.last_context = dict(context or {})
        yield {"event": "intent_analyzed", "intent": "data_record"}
        yield {
            "event": "final",
            "result": {
                "task": {
                    "task_id": "task_1",
                    "intent": "data_record",
                    "input_text": input_text,
                    "domain": "data_ops",
                    "output_requirements": ["text"],
                },
                "workflow": {"workflow_id": "wf_1", "steps": [{"name": "extract_records"}]},
                "execution_result": {
                    "steps": [{"name": "extract_records", "status": "success"}],
                    "final_output": {"extract_records": {"count": 1}},
                },
            },
        }


class _FakeSessionStore:
    def __init__(self, payloads: dict[str, dict[str, Any]] | None = None) -> None:
        self._payloads = payloads or {}

    def get(self, session_id: str) -> dict[str, Any]:
        return dict(self._payloads.get(session_id, {}))

    def patch(self, session_id: str, patch_data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(self._payloads.get(session_id, {}))
        payload.update(patch_data)
        self._payloads[session_id] = payload
        return dict(payload)


class _FakeContextManager:
    def __init__(self, session_store: _FakeSessionStore) -> None:
        self.session_store = session_store


class _FakeLegacyCoreWithSession(_FakeLegacyCore):
    def __init__(self, payloads: dict[str, dict[str, Any]] | None = None) -> None:
        super().__init__()
        self.context_manager = _FakeContextManager(_FakeSessionStore(payloads=payloads))


def test_core_engine_provider_defaults_to_legacy(monkeypatch) -> None:
    monkeypatch.delenv("NETHUB_CORE_ENGINE_VARIANT", raising=False)
    engine = create_core_engine()
    assert active_core_engine_variant() == "legacy"
    assert engine.__class__.__name__ == "AICore"


def test_core_plus_engine_enriches_handle_result(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_CORE_ENGINE_VARIANT", "core_plus")
    engine = create_core_engine()
    wrapped = engine.__class__(base_core=_FakeLegacyCore())

    result = asyncio.run(wrapped.handle("今天买菜花了2000日元", context={"metadata": {}}, fmt="dict"))

    assert result["core_version"] == "core_plus_v2"
    core_plus = result["execution_result"]["core_plus"]
    assert core_plus["request_plan"]["rule_prejudge"]["rule_hit"] is True
    assert core_plus["request_plan"]["intent_router"]["local_profile"]["name"] == "lora_sft"
    assert core_plus["evaluation"]["pass"] is True
    assert core_plus["training_signal"]["profile"] == "lora_sft"
    assert core_plus["runtime_stats"]["local_profile"]["name"] == "lora_sft"
    assert core_plus["data_routing"]["sinks"]["training_pool"] is True


def test_core_plus_engine_enriches_final_stream_event(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_CORE_ENGINE_VARIANT", "core_plus")
    engine = create_core_engine()
    wrapped = engine.__class__(base_core=_FakeLegacyCore())

    async def _collect_events() -> list[dict[str, Any]]:
        return [event async for event in wrapped.handle_stream("整理文档并总结", context={"metadata": {}}, fmt="dict")]

    events = asyncio.run(_collect_events())

    assert events[0]["event"] == "core_plus_planned"
    final_event = next(event for event in events if event["event"] == "final")
    assert final_event["result"]["execution_result"]["core_plus"]["training_signal"]["eligible"] is True


def test_core_plus_engine_injects_forced_task_from_request_plan(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_CORE_ENGINE_VARIANT", "core_plus")
    engine = create_core_engine()
    fake_core = _FakeLegacyCore()
    wrapped = engine.__class__(base_core=fake_core)

    text = "看看我的日程安排，如果4月22号没有预约，给我制定一个1天的大阪观光计划。6点到了之后，提醒我去坐6点30的飞机。"
    asyncio.run(wrapped.handle(text, context={"metadata": {}}, fmt="dict"))

    metadata = dict((fake_core.last_context or {}).get("metadata") or {})
    forced_task = dict(metadata.get("core_plus_forced_task") or {})
    assert forced_task["intent"] == "schedule_create"
    assert forced_task["domain"] == "data_ops"
    assert forced_task["constraints"]["need_agent"] is False


def test_core_plus_engine_maps_agent_create_forced_task_to_agent_management(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_CORE_ENGINE_VARIANT", "core_plus")
    engine = create_core_engine()
    fake_core = _FakeLegacyCore()
    wrapped = engine.__class__(base_core=fake_core)

    text = "创建一个日程和提醒智能体"
    asyncio.run(wrapped.handle(text, context={"metadata": {}}, fmt="dict"))

    metadata = dict((fake_core.last_context or {}).get("metadata") or {})
    forced_task = dict(metadata.get("core_plus_forced_task") or {})
    assert forced_task["intent"] == "create_information_agent"
    assert forced_task["domain"] == "agent_management"
    assert forced_task["constraints"]["need_agent"] is False


def test_core_plus_engine_skips_forced_task_when_information_agent_session_active(monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_CORE_ENGINE_VARIANT", "core_plus")
    engine = create_core_engine()
    fake_core = _FakeLegacyCoreWithSession(
        payloads={
            "s-agent": {
                "configured_agent": {
                    "status": "active",
                    "name": "schedule_agent",
                    "role": "日程和提醒智能体",
                    "knowledge_entity_label": "日程",
                    "activation_keywords": ["加日程", "查日程"],
                    "query_aliases": {"查日程": "date"},
                }
            }
        }
    )
    wrapped = engine.__class__(base_core=fake_core)

    asyncio.run(wrapped.handle("查日程 4月21号和4月22号", context={"session_id": "s-agent", "metadata": {}}, fmt="dict"))

    metadata = dict((fake_core.last_context or {}).get("metadata") or {})
    assert "core_plus_forced_task" not in metadata
