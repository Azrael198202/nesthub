from __future__ import annotations

import asyncio
from pathlib import Path

from nethub_runtime.core.services.core_engine import AICore


def test_core_engine_handle_workflow_path() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    assert "tool" in core.execution_coordinator._executor_handlers
    assert "agent" in core.execution_coordinator._executor_handlers
    assert "extract_records" in core.execution_coordinator._step_handlers["tool"]
    assert "manage_information_agent" in core.execution_coordinator._step_handlers["agent"]

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
    assert result["workflow"]
    assert result["workflow"]["steps"]
    assert result["execution_result"]["execution_plan"]
    assert result["workflow"]["steps"][0]["executor_type"]
    assert result["workflow"]["steps"][0]["inputs"]
    assert result["workflow"]["steps"][0]["outputs"]
    assert result["execution_result"]["execution_plan"][0]["executor_type"]
    assert result["execution_result"]["execution_plan"][0]["inputs"]
    assert result["execution_result"]["execution_plan"][0]["outputs"]
    assert result["execution_result"]["execution_plan"][0]["capability"]["model_choice"]
    assert result["execution_result"]["execution_plan"][0]["selector"]["reason"]
    assert result["execution_result"]["steps"][0]["inputs"]
    assert result["execution_result"]["steps"][0]["outputs"]
    trace = result["execution_result"]["autonomous_implementation_trace"]
    assert trace["autonomous_implementation_supported"] is True
    assert trace["capability_gap_detected"] is False
    assert trace["autonomous_implementation_triggered"] is False
    generated_trace_path = result["execution_result"].get("generated_trace_path")
    assert generated_trace_path
    assert Path(generated_trace_path).exists()
    artifacts = result.get("artifacts", [])
    assert any(item["artifact_type"] == "trace" for item in artifacts)
    assert any(item["artifact_type"] == "trace" for item in result.get("artifact_index", {}).get("trace", []))


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
    assert result["workflow"]
    assert result["execution_result"]["execution_plan"]
    assert result["execution_result"]["execution_plan"][0]["selector"]["executor_type"]
    assert result["workflow"]["steps"][0]["inputs"]
    assert result["workflow"]["steps"][0]["outputs"]
    assert trace["capability_gap_detected"] is True
    assert trace["autonomous_implementation_supported"] is True
    assert trace["generated_patch_registered"] is True
    assert trace["generated_artifact_type"] == "blueprint"
    assert trace["trigger_reason"] == "no_reusable_blueprint_resolved"
    generated_path = result["blueprints"][0]["metadata"].get("generated_artifact_path")
    assert generated_path
    assert Path(generated_path).exists()
    generated_trace_path = result["execution_result"].get("generated_trace_path")
    assert generated_trace_path
    assert Path(generated_trace_path).exists()
    artifacts = result.get("artifacts", [])
    assert any(item["artifact_type"] == "blueprint" for item in artifacts)
    assert any(item["artifact_type"] == "trace" for item in artifacts)
    assert any(item["artifact_type"] == "blueprint" for item in result.get("artifact_index", {}).get("blueprint", []))
    assert any(item["artifact_type"] == "trace" for item in result.get("artifact_index", {}).get("trace", []))
