from __future__ import annotations

import asyncio
from pathlib import Path

from nethub_runtime.core.services.core_engine import AICore


def test_core_engine_handle_workflow_path() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")

    result = asyncio.run(
        core.handle(
            input_text="记录一下今天中午吃饭花了50元",
            context={"user_id": "u1", "use_langgraph_runtime": False},
            fmt="dict",
            use_langraph=True,
        )
    )

    assert isinstance(result, dict)
    assert "execution_result" in result
    trace = result["execution_result"]["autonomous_implementation_trace"]
    assert trace["autonomous_implementation_supported"] is True
    assert trace["capability_gap_detected"] is False
    assert trace["autonomous_implementation_triggered"] is False


def test_core_engine_reports_capability_gap_when_blueprint_is_generated() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")

    core.blueprint_resolver.resolve = lambda task, workflow: []

    result = asyncio.run(
        core.handle(
            input_text="记录一下今天中午吃饭花了50元",
            context={"user_id": "u2", "use_langgraph_runtime": False},
            fmt="dict",
            use_langraph=False,
        )
    )

    trace = result["execution_result"]["autonomous_implementation_trace"]
    assert trace["capability_gap_detected"] is True
    assert trace["autonomous_implementation_supported"] is True
    assert trace["generated_patch_registered"] is True
    assert trace["generated_artifact_type"] == "blueprint"
    assert trace["trigger_reason"] == "no_reusable_blueprint_resolved"
    generated_path = result["blueprints"][0]["metadata"].get("generated_artifact_path")
    assert generated_path
    assert Path(generated_path).exists()
