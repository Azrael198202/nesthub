from __future__ import annotations

import asyncio
import json
from pathlib import Path

from nethub_runtime.core.services.core_engine import AICore
from nethub_runtime.core.services import core_engine as core_engine_module
from nethub_runtime.core.services import execution_handler_registry as execution_handler_registry_module


def test_core_engine_handle_workflow_path() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    assert core.execution_coordinator._handler_registry is not None
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


def test_execution_handler_registry_can_load_plugins(tmp_path, monkeypatch) -> None:
    plugin_config = tmp_path / "plugin_config.json"
    plugin_config.write_text(
        json.dumps(
            {
                "intent_analyzer_plugins": [],
                "task_decomposer_plugins": [],
                "workflow_planner_plugins": [],
                "execution_handler_registry_plugins": [
                    "nethub_runtime.core.services.demo_execution_handler_plugin:demo_execution_handler_plugin"
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(execution_handler_registry_module, "PLUGIN_CONFIG_PATH", plugin_config)

    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")

    assert "demo_executor" in core.execution_coordinator._executor_handlers
    assert "demo_step" in core.execution_coordinator._step_handlers["demo_executor"]
    manifests = core.execution_coordinator._handler_registry.get_plugin_manifests()
    assert manifests
    assert manifests[0]["name"] == "demo_execution_handler_plugin"
    assert manifests[0]["executors"] == ["demo_executor"]
    assert manifests[0]["steps"] == ["demo_executor.demo_step"]
    assert manifests[0]["requirements_satisfied"] is True
    assert manifests[0]["requirements"] == [
        {
            "type": "dispatcher",
            "name": "llm",
            "description": "Requires the coordinator LLM dispatcher.",
            "required": True,
            "satisfied": True,
        },
        {
            "type": "service",
            "name": "information_agent_service",
            "description": "Verifies domain services can be surfaced as runtime requirements.",
            "required": False,
            "satisfied": True,
        },
    ]


def test_runtime_blueprint_generation_does_not_persist_to_static_registry(tmp_path, monkeypatch) -> None:
    model_registry_path = tmp_path / "models.json"
    blueprint_registry_path = tmp_path / "blueprints.json"
    agent_registry_path = tmp_path / "agents.json"
    monkeypatch.setattr(core_engine_module, "MODEL_REGISTRY_PATH", model_registry_path)
    monkeypatch.setattr(core_engine_module, "BLUEPRINT_REGISTRY_PATH", blueprint_registry_path)
    monkeypatch.setattr(core_engine_module, "AGENT_REGISTRY_PATH", agent_registry_path)

    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    core.blueprint_resolver.resolve = lambda task, workflow: []

    result = asyncio.run(
        core.handle(
            input_text="记录一下今天中午吃饭花了50元",
            context={"user_id": "u_registry", "use_langgraph_runtime": False},
            fmt="dict",
            use_langraph=False,
        )
    )

    assert Path(result["blueprints"][0]["metadata"]["generated_artifact_path"]).exists()
    assert json.loads(model_registry_path.read_text(encoding="utf-8")) == {}
    assert json.loads(blueprint_registry_path.read_text(encoding="utf-8")) == {}
    assert json.loads(agent_registry_path.read_text(encoding="utf-8")) == {}


def test_runtime_blueprint_generation_contains_synthesis_metadata() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    core.blueprint_resolver.resolve = lambda task, workflow: []

    result = asyncio.run(
        core.handle(
            input_text="帮我生成一个文件处理流程",
            context={"user_id": "u_synthesis", "use_langgraph_runtime": False},
            fmt="dict",
            use_langraph=False,
        )
    )

    synthesis = result["blueprints"][0]["metadata"].get("synthesis")
    assert isinstance(synthesis, dict)
    assert synthesis["purpose_summary"]
    assert synthesis["reasoning"]
    assert isinstance(synthesis["execution_profile"], dict)
