from __future__ import annotations

import json
from pathlib import Path

from nethub_runtime.generated.store import GeneratedArtifactStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema
from nethub_runtime.core.services.execution_step_handlers import (
    handle_generate_workflow_artifact_step,
    handle_persist_workflow_output_step,
)
from nethub_runtime.core.services.dependency_manager import DependencyManager
from nethub_runtime.core.services.runtime_failure_classifier import RuntimeFailureClassifier
from nethub_runtime.core.services.runtime_outcome_evaluator import RuntimeOutcomeEvaluator
from nethub_runtime.core.services.runtime_repair_service import RuntimeRepairService
from nethub_runtime.core.services.user_goal_evaluator import UserGoalEvaluator
from nethub_runtime.core.services.result_integrator import ResultIntegrator


def test_runtime_outcome_evaluator_detects_unmet_outputs_and_failed_steps() -> None:
    evaluator = RuntimeOutcomeEvaluator()
    task = TaskSchema(
        task_id="task_runtime_repair",
        intent="prepare_document",
        input_text="生成一份总结文档",
        domain="general",
        output_requirements=["summary", "artifact"],
    )
    workflow = WorkflowSchema(
        workflow_id="workflow_runtime_repair",
        task_id=task.task_id,
        steps=[
            WorkflowStepSchema(
                step_id="step_1",
                name="single_step",
                task_type=task.intent,
                outputs=["message"],
            )
        ],
    )
    execution_result = {
        "steps": [
            {"name": "single_step", "status": "failed"},
        ],
        "final_output": {"single_step": {"message": "incomplete"}},
    }

    evaluation = evaluator.evaluate(task=task, workflow=workflow, execution_result=execution_result)

    assert evaluation["status"] == "needs_repair"
    assert evaluation["failed_steps"] == ["single_step"]
    assert set(evaluation["unmet_requirements"]) == {"summary", "artifact"}
    assert evaluation["should_repair"] is True


def test_runtime_repair_service_builds_repaired_workflow_from_evaluation() -> None:
    repair_service = RuntimeRepairService()
    task = TaskSchema(
        task_id="task_runtime_repair_build",
        intent="prepare_document",
        input_text="生成一份总结文档",
        domain="general",
        output_requirements=["summary", "artifact"],
    )
    workflow = WorkflowSchema(
        workflow_id="workflow_runtime_repair_build",
        task_id=task.task_id,
        steps=[
            WorkflowStepSchema(
                step_id="step_1",
                name="single_step",
                task_type=task.intent,
                executor_type="tool",
                outputs=["message"],
            )
        ],
        composition={"metadata": {}},
    )

    repaired_workflow = repair_service.build_repair_workflow(
        task=task,
        workflow=workflow,
        repair_classification={
            "execution_failures": ["single_step"],
            "missing_steps": ["summary", "artifact"],
            "missing_outputs": [],
            "missing_tools": [],
        },
    )

    step_names = [step.name for step in repaired_workflow.steps]
    assert step_names.count("single_step") == 2
    assert "analyze_workflow_context" in step_names
    assert "generate_workflow_artifact" in step_names
    assert "persist_workflow_output" in step_names
    assert repaired_workflow.composition["metadata"]["runtime_repair_applied"] is True
    assert repaired_workflow.composition["metadata"]["repair_iteration"] == 1


def test_runtime_failure_classifier_distinguishes_missing_steps_tools_outputs_and_failures() -> None:
    classifier = RuntimeFailureClassifier()
    workflow = WorkflowSchema(
        workflow_id="workflow_failure_classifier",
        task_id="task_failure_classifier",
        steps=[
            WorkflowStepSchema(
                step_id="step_1",
                name="single_step",
                task_type="prepare_document",
                outputs=["message"],
            ),
            WorkflowStepSchema(
                step_id="step_2",
                name="analyze_workflow_context",
                task_type="prepare_document",
                outputs=["analysis", "summary"],
            ),
        ],
    )

    classified = classifier.classify(
        workflow=workflow,
        evaluation={
            "unmet_requirements": ["artifact", "summary"],
            "failed_steps": ["single_step"],
        },
        dependency_status={"missing_tools": ["pandoc"], "missing_packages": ["markdown"]},
        execution_result={
            "steps": [
                {"name": "single_step", "status": "failed", "capability": {"tool": "document_generator"}},
            ]
        },
    )

    assert classified["missing_steps"] == ["artifact"]
    assert classified["missing_outputs"] == ["summary"]
    assert "pandoc" in classified["missing_tools"]
    assert "markdown" in classified["missing_tools"]
    assert "document_generator" in classified["missing_tools"]
    assert classified["execution_failures"] == ["single_step"]


def test_runtime_repair_service_adds_tool_preparation_for_missing_tools() -> None:
    repair_service = RuntimeRepairService()
    task = TaskSchema(
        task_id="task_runtime_tool_repair",
        intent="prepare_document",
        input_text="生成文档",
        domain="general",
        output_requirements=["artifact"],
    )
    workflow = WorkflowSchema(
        workflow_id="workflow_runtime_tool_repair",
        task_id=task.task_id,
        steps=[],
        composition={"metadata": {}},
    )

    repaired_workflow = repair_service.build_repair_workflow(
        task=task,
        workflow=workflow,
        repair_classification={
            "execution_failures": [],
            "missing_steps": ["artifact"],
            "missing_outputs": [],
            "missing_tools": ["pandoc"],
        },
    )

    step_names = [step.name for step in repaired_workflow.steps]
    assert "prepare_runtime_tools" in step_names
    tool_step = next(step for step in repaired_workflow.steps if step.name == "prepare_runtime_tools")
    assert tool_step.metadata["missing_tools"] == ["pandoc"]


def test_runtime_repair_service_prepares_tools_before_retrying_failed_steps() -> None:
    repair_service = RuntimeRepairService()
    task = TaskSchema(
        task_id="task_runtime_tool_retry_order",
        intent="prepare_document",
        input_text="生成文档",
        domain="general",
        output_requirements=["artifact"],
    )
    workflow = WorkflowSchema(
        workflow_id="workflow_runtime_tool_retry_order",
        task_id=task.task_id,
        steps=[
            WorkflowStepSchema(
                step_id="step_1",
                name="single_step",
                task_type=task.intent,
                executor_type="tool",
                outputs=["message"],
            )
        ],
        composition={"metadata": {}},
    )

    repaired_workflow = repair_service.build_repair_workflow(
        task=task,
        workflow=workflow,
        repair_classification={
            "execution_failures": ["single_step"],
            "missing_steps": [],
            "missing_outputs": [],
            "missing_tools": ["pandoc"],
        },
    )

    step_names = [step.name for step in repaired_workflow.steps]
    assert step_names.index("prepare_runtime_tools") < step_names.index("single_step", 1)
    retry_step = repaired_workflow.steps[step_names.index("single_step", 1)]
    prepare_step = repaired_workflow.steps[step_names.index("prepare_runtime_tools")]
    assert retry_step.depends_on == [prepare_step.step_id]


def test_dependency_manager_skips_install_execution_when_auto_install_disabled(tmp_path: Path) -> None:
    config_path = tmp_path / "dependencies.json"
    config_path.write_text(
        json.dumps(
            {
                "python_packages": ["pydantic"],
                "shell_tools": ["bash"],
                "auto_install": False,
            }
        ),
        encoding="utf-8",
    )
    manager = DependencyManager(config_path=config_path)

    result = manager.execute_install_plan(
        {
            "auto_install": False,
            "shell_commands": ["python -m pip install pydantic"],
        }
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "auto_install_disabled"


def test_dependency_manager_builds_mapped_shell_tool_install_plan(tmp_path: Path) -> None:
    config_path = tmp_path / "dependencies.json"
    config_path.write_text(
        json.dumps(
            {
                "python_packages": ["pydantic"],
                "shell_tools": ["pandoc"],
                "shell_tool_installers": {
                    "pandoc": [
                        {"type": "apt-get", "package": "pandoc"},
                    ]
                },
                "auto_install": True,
            }
        ),
        encoding="utf-8",
    )
    manager = DependencyManager(config_path=config_path)

    plan = manager.build_install_plan(["pydantic", "pandoc"])

    assert "python -m pip install pydantic" in plan["shell_commands"]
    assert "apt-get install -y pandoc" in plan["shell_commands"]
    assert plan["unsupported_tools"] == []


def test_dependency_manager_blocks_unallowed_installer_execution(tmp_path: Path) -> None:
    config_path = tmp_path / "dependencies.json"
    config_path.write_text(
        json.dumps(
            {
                "python_packages": ["pydantic"],
                "shell_tools": [],
                "auto_install": True,
            }
        ),
        encoding="utf-8",
    )
    manager = DependencyManager(config_path=config_path)

    result = manager.execute_install_plan(
        {
            "auto_install": True,
            "shell_commands": ["python -m pip install pydantic"],
            "unsupported_tools": [],
        },
        allowed_installers=["apt-get"],
    )

    assert result["status"] == "deferred"
    assert result["executed_commands"] == []
    assert result["blocked_commands"][0]["installer"] == "pip"


def test_dependency_manager_degrades_when_tool_has_no_supported_installer(tmp_path: Path) -> None:
    config_path = tmp_path / "dependencies.json"
    config_path.write_text(
        json.dumps(
            {
                "python_packages": [],
                "shell_tools": ["pandoc"],
                "shell_tool_installers": {},
                "auto_install": True,
            }
        ),
        encoding="utf-8",
    )
    manager = DependencyManager(config_path=config_path)

    plan = manager.build_install_plan(["pandoc"])
    result = manager.execute_install_plan(plan, allowed_installers=["apt-get"])

    assert plan["unsupported_tools"] == ["pandoc"]
    assert result["status"] == "deferred"
    assert result["unsupported_tools"] == ["pandoc"]


def test_runtime_repair_service_increments_repair_iteration_metadata() -> None:
    repair_service = RuntimeRepairService()
    task = TaskSchema(
        task_id="task_runtime_iteration",
        intent="prepare_document",
        input_text="生成文档",
        domain="general",
        output_requirements=["artifact"],
    )
    workflow = WorkflowSchema(
        workflow_id="workflow_runtime_iteration",
        task_id=task.task_id,
        steps=[],
        composition={"metadata": {"repair_iteration": 1}},
    )

    repaired_workflow = repair_service.build_repair_workflow(
        task=task,
        workflow=workflow,
        repair_classification={
            "execution_failures": [],
            "missing_steps": ["artifact"],
            "missing_outputs": [],
            "missing_tools": [],
        },
    )

    assert repaired_workflow.composition["metadata"]["repair_iteration"] == 2


def test_user_goal_evaluator_detects_missing_goal_terms() -> None:
    evaluator = UserGoalEvaluator()
    task = TaskSchema(
        task_id="task_goal_eval",
        intent="prepare_trip_brief",
        input_text="整理大阪联系人并生成提醒文档",
        domain="general",
    )
    execution_result = {
        "final_output": {
            "analyze_workflow_context": {"summary": "这里只整理了联系人，没有提醒文档"},
        }
    }

    evaluation = evaluator.evaluate(task=task, execution_result=execution_result)

    assert evaluation["satisfied"] is False
    assert "大阪联系人并生成提醒文档" not in evaluation["matched_terms"]
    assert evaluation["missing_terms"]


def test_workflow_artifact_handlers_generate_and_persist_real_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(tmp_path / "generated_artifacts"))

    class CoordinatorStub:
        def __init__(self) -> None:
            self.generated_artifact_store = GeneratedArtifactStore()

    coordinator = CoordinatorStub()
    task = TaskSchema(
        task_id="task_artifact",
        intent="prepare_document",
        input_text="生成一份提醒文档",
        domain="general",
    )
    context = CoreContextSchema(session_id="artifact-session", trace_id="artifact-trace")

    generated = handle_generate_workflow_artifact_step(
        coordinator,
        {},
        task,
        context,
        {"analyze_workflow_context": {"summary": "这是提醒文档内容。"}},
    )
    assert generated["status"] == "generated"
    artifact_path = Path(generated["artifact_path"])
    assert artifact_path.exists()
    assert artifact_path.suffix == ".md"
    assert artifact_path.read_text(encoding="utf-8").startswith("task_intent: prepare_document")

    persisted = handle_persist_workflow_output_step(
        coordinator,
        {},
        task,
        context,
        {"generate_workflow_artifact": generated},
    )
    assert persisted["delivery_status"] == "stored"
    assert persisted["stored_output"] == str(artifact_path)


def test_result_integrator_collects_workflow_generated_artifacts(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact_trace.md"
    artifact_path.write_text("artifact body", encoding="utf-8")
    integrator = ResultIntegrator()
    task = TaskSchema(
        task_id="task_result_integrator",
        intent="prepare_document",
        input_text="生成提醒文档",
        domain="general",
    )
    workflow = WorkflowSchema(
        workflow_id="workflow_result_integrator",
        task_id=task.task_id,
        steps=[],
    )
    context = CoreContextSchema(session_id="session-result", trace_id="trace-result")

    response = integrator.build_response(
        task=task,
        workflow=workflow,
        execution_result={
            "final_output": {
                "generate_workflow_artifact": {
                    "artifact_type": "document",
                    "artifact_path": str(artifact_path),
                    "status": "generated",
                    "summary": "artifact summary",
                }
            }
        },
        context=context,
        blueprints=[],
        agent=None,
    )

    artifact_sources = {item["source"] for item in response["artifacts"]}
    assert "workflow_generated_artifact" in artifact_sources
    assert "document" in response["artifact_index"]
