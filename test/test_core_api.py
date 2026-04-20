from fastapi.testclient import TestClient
from pathlib import Path

from nethub_runtime.core.main import app
from nethub_runtime.core.routers import core_api
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema, WorkflowStepSchema

client = TestClient(app)

def test_core_handle_budget(isolated_generated_artifacts, budget_semantic_runtime):
    payload = {
        "input_text": "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元",
        "context": {},
        "output_format": "dict"
    }
    resp = client.post("/core/handle", json=payload)
    assert resp.status_code == 200
    data = resp.json()["result"]
    assert data["task"]["intent"] in ("data_record", "record_expense")
    assert "execution_result" in data
    assert data["workflow"]
    assert data["workflow"]["steps"]
    assert data["workflow"]["steps"][0]["executor_type"]
    assert data["workflow"]["steps"][0]["inputs"]
    assert data["workflow"]["steps"][0]["outputs"]
    assert data["execution_result"]["execution_plan"]
    assert data["execution_result"]["execution_plan"][0]["executor_type"]
    assert data["execution_result"]["execution_plan"][0]["inputs"]
    assert data["execution_result"]["execution_plan"][0]["outputs"]
    assert data["execution_result"]["execution_plan"][0]["selector"]["reason"]
    assert data["execution_result"]["steps"][0]["inputs"]
    assert data["execution_result"]["steps"][0]["outputs"]
    trace = data["execution_result"]["autonomous_implementation_trace"]
    assert trace["autonomous_implementation_supported"] is True
    assert trace["capability_gap_detected"] is False
    generated_trace_path = data["execution_result"].get("generated_trace_path")
    assert generated_trace_path
    assert Path(generated_trace_path).exists()
    artifacts = data.get("artifacts", [])
    assert any(item["artifact_type"] == "trace" for item in artifacts)
    assert any(item["artifact_type"] == "trace" for item in data.get("artifact_index", {}).get("trace", []))


def test_core_handle_can_generate_html_file_from_language_instruction(isolated_generated_artifacts, monkeypatch):
    workspace = Path.cwd()
    target_dir = workspace / "tmp_test_outputs"
    monkeypatch.chdir(workspace)
    payload = {
        "input_text": "帮我写一个 html 文件，内容是点击一个按钮 Submit 能执行一个 js，弹出 hello,world!，保存到 tmp_test_outputs/hello_world_button.html",
        "context": {},
        "output_format": "dict"
    }

    try:
        resp = client.post("/core/handle", json=payload)
        assert resp.status_code == 200
        data = resp.json()["result"]
        assert data["task"]["intent"] == "file_generation_task"
        file_output = data["execution_result"]["final_output"]["file_generate"]
        target_path = Path(file_output["artifact_path"])
        assert target_path.exists()
        content = target_path.read_text(encoding="utf-8")
        assert "<button id=\"submitButton\"" in content
        assert 'alert("hello,world!")' in content
        assert file_output["status"] == "generated"
        assert any(item["artifact_type"] == "file" for item in data.get("artifacts", []))
        assert any(item["artifact_type"] == "file" for item in data.get("artifact_index", {}).get("file", []))
    finally:
        if target_dir.exists():
            for path in target_dir.glob("*"):
                if path.is_file():
                    path.unlink()
            target_dir.rmdir()


def test_core_handle_can_return_existing_file_content_from_language_instruction(isolated_generated_artifacts, monkeypatch):
    workspace = Path.cwd()
    target_dir = workspace / "tmp_test_outputs"
    target_dir.mkdir(exist_ok=True)
    target_path = target_dir / "hello_world_button.html"
    target_path.write_text("<html><body>Hello existing file</body></html>", encoding="utf-8")
    monkeypatch.chdir(workspace)
    payload = {
        "input_text": "把tmp_test_outputs/hello_world_button.html文件发给我",
        "context": {},
        "output_format": "dict"
    }

    try:
        resp = client.post("/core/handle", json=payload)
        assert resp.status_code == 200
        data = resp.json()["result"]
        assert data["task"]["intent"] == "file_delivery_task"
        file_output = data["execution_result"]["final_output"]["file_read"]
        assert file_output["status"] == "read"
        assert Path(file_output["artifact_path"]).resolve() == target_path.resolve()
        assert "Hello existing file" in file_output["content"]
        assert not (workspace / "把tmp_test_outputs/hello_world_button.html").exists()
        assert any(item["artifact_type"] == "file" for item in data.get("artifacts", []))
    finally:
        if target_path.exists():
            target_path.unlink()
        if target_dir.exists():
            target_dir.rmdir()


def test_core_handle_triggers_runtime_patch_pipeline_via_repair(isolated_generated_artifacts, monkeypatch):
    workspace_root = Path.cwd() / "tmp_runtime_patch_workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NETHUB_RUNTIME_WORKSPACE_ROOT", str(workspace_root))

    coordinator = core_api.core_engine.execution_coordinator
    intent_analyzer = core_api.core_engine.intent_analyzer
    task_decomposer = core_api.core_engine.task_decomposer
    workflow_planner = core_api.core_engine.workflow_planner
    capability_router = core_api.core_engine.capability_router
    outcome_evaluator = core_api.core_engine.runtime_outcome_evaluator
    goal_evaluator = core_api.core_engine.user_goal_evaluator
    failure_classifier = core_api.core_engine.runtime_failure_classifier

    async def _analyze(_input_text, _ctx):
        return TaskSchema(
            task_id="task_runtime_patch_api",
            intent="file_generation_task",
            input_text="修复运行时文件并验证",
            domain="general",
            output_requirements=["artifact", "file"],
            constraints={},
        )

    async def _decompose(_task):
        return []

    async def _plan(task, _subtasks):
        return WorkflowSchema(
            workflow_id="workflow_runtime_patch_api",
            task_id=task.task_id,
            steps=[
                WorkflowStepSchema(
                    step_id="step_1",
                    name="file_generate",
                    task_type=task.intent,
                    executor_type="tool",
                    inputs=["input_text"],
                    outputs=["artifact", "artifact_path", "status"],
                )
            ],
            composition={"metadata": {}},
        )

    def _route_workflow(_task, workflow):
        tool_map = {
            "file_generate": "file_builder",
            "analyze_workflow_context": "none",
            "generate_runtime_patch": "file_builder",
            "validate_runtime_patch": "shell_runner",
            "verify_runtime_patch": "session_store",
            "persist_workflow_output": "session_store",
        }
        routed = []
        for step in workflow.steps:
            payload = step.model_dump()
            payload["selector"] = {"executor_type": step.executor_type, "reason": "test_runtime_patch_flow"}
            payload["capability"] = {
                "tool": tool_map.get(step.name, "none"),
                "model_choice": {"provider": "test", "model": "test-model", "available": True},
            }
            payload["runtime_capabilities"] = {}
            routed.append(payload)
        return routed

    evaluation_state = {"calls": 0}
    step_state = {"file_generate_calls": 0}

    def _evaluate(*, task, workflow, execution_result):
        evaluation_state["calls"] += 1
        if evaluation_state["calls"] == 1:
            return {
                "status": "needs_repair",
                "failed_steps": ["file_generate"],
                "unmet_requirements": [],
                "available_outputs": [],
                "should_repair": True,
            }
        return {
            "status": "satisfied",
            "failed_steps": [],
            "unmet_requirements": [],
            "available_outputs": ["artifact", "artifact_path", "file", "verified"],
            "should_repair": False,
        }

    def _goal_evaluate(*, task, execution_result):
        return {"satisfied": True, "matched_terms": [], "missing_terms": []}

    def _classify(*, workflow, evaluation, dependency_status=None, execution_result=None):
        return {
            "missing_steps": [],
            "missing_tools": [],
            "missing_outputs": [],
            "execution_failures": ["file_generate"],
            "should_repair": True,
        }

    def _invoke_model_text(*args, **kwargs):
        return json.dumps(
            {
                "summary": "Repair runtime target",
                "target_file": "runtime_repaired.py",
                "updated_content": "value = 2\n",
                "validation_commands": [
                    'python -c "ns = {}; exec(open(\'runtime_repaired.py\').read(), ns); assert ns[\'value\'] == 2"'
                ],
            },
            ensure_ascii=False,
        )

    def _run_step(step, task, context, step_outputs):
        if step["name"] == "generate_runtime_patch":
            return coordinator._generate_runtime_patch(task=task, context=context, step_outputs=step_outputs)
        if step["name"] == "validate_runtime_patch":
            patch_payload = step_outputs.get("generate_runtime_patch", {})
            return coordinator._run_runtime_validation(context=context, patch_payload=patch_payload)
        if step["name"] == "verify_runtime_patch":
            patch_payload = step_outputs.get("generate_runtime_patch", {})
            validation_payload = step_outputs.get("validate_runtime_patch", {})
            return coordinator._verify_runtime_patch(
                context=context,
                patch_payload=patch_payload,
                validation_payload=validation_payload,
            )
        if step["name"] == "analyze_workflow_context":
            return {"status": "completed", "analysis": "Need runtime patch", "summary": "Need runtime patch"}
        if step["name"] == "file_generate":
            step_state["file_generate_calls"] += 1
            if step_state["file_generate_calls"] == 1:
                return {"status": "failed", "message": "simulated runtime failure"}
            return {"status": "generated", "artifact": "placeholder", "artifact_path": str(workspace_root / "placeholder.txt")}
        if step["name"] == "persist_workflow_output":
            return {"delivery_status": "stored", "stored_output": "runtime_repaired.py"}
        return {"status": "completed", "message": f"stubbed step: {step['name']}"}

    monkeypatch.setattr(intent_analyzer, "analyze", _analyze)
    monkeypatch.setattr(task_decomposer, "decompose", _decompose)
    monkeypatch.setattr(workflow_planner, "plan", _plan)
    monkeypatch.setattr(capability_router, "route_workflow", _route_workflow)
    monkeypatch.setattr(outcome_evaluator, "evaluate", _evaluate)
    monkeypatch.setattr(goal_evaluator, "evaluate", _goal_evaluate)
    monkeypatch.setattr(failure_classifier, "classify", _classify)
    monkeypatch.setattr(coordinator, "_invoke_model_text", _invoke_model_text)
    monkeypatch.setattr(coordinator, "_run_step", _run_step)

    try:
        resp = client.post(
            "/core/handle",
            json={
                "input_text": "触发运行时修补",
                "context": {},
                "output_format": "dict",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["result"]
        execution_result = data["execution_result"]
        trace = execution_result["autonomous_implementation_trace"]
        step_names = [step["name"] for step in execution_result["steps"]]

        assert trace["runtime_repair_triggered"] is True
        assert "generate_runtime_patch" in step_names
        assert "validate_runtime_patch" in step_names
        assert "verify_runtime_patch" in step_names
    finally:
        if workspace_root.exists():
            for path in workspace_root.glob("*"):
                if path.is_file():
                    path.unlink()
            workspace_root.rmdir()

if __name__ == "__main__":
    test_core_handle_budget()
