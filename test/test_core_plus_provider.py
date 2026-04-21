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

    async def handle(self, input_text: str, context: dict[str, Any] | None = None, fmt: str = "dict", use_langraph: bool = True) -> dict[str, Any]:
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