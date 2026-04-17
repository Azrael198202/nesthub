from __future__ import annotations

import asyncio

from nethub_runtime.core.schemas.task_schema import SubTask, TaskSchema
from nethub_runtime.core.services.workflow_planner import WorkflowPlanner


def test_workflow_planner_adds_framework_composition_and_support_steps() -> None:
    planner = WorkflowPlanner()
    task = TaskSchema(
        task_id="task_framework_workflow",
        intent="prepare_trip_brief",
        input_text="根据爸爸下周出差大阪的日程，整理联系人，生成提醒文档，并保存结果。",
        domain="general",
        constraints={"need_agent": True},
        output_requirements=["analysis", "artifact", "summary"],
    )
    subtasks = [
        SubTask(subtask_id="subtask_1", name="query_information_knowledge", goal="Read schedule knowledge."),
        SubTask(subtask_id="subtask_2", name="single_step", goal="Prepare execution context."),
    ]

    workflow = asyncio.run(planner.plan(task, subtasks))

    step_names = [step.name for step in workflow.steps]
    assert "query_information_knowledge" in step_names
    assert "analyze_workflow_context" in step_names
    assert "generate_workflow_artifact" in step_names
    assert "persist_workflow_output" in step_names

    composition = workflow.composition
    assert composition["knowledge_agents"] == []
    assert composition["execution_agents"] == ["execution_agent"]
    assert composition["analysis_agents"] == ["analysis_agent"]
    assert composition["tools"] == ["file_builder"]
    assert composition["io_operations"] == ["file_write"]
    component_types = {component["name"]: component["component_type"] for component in composition["components"]}
    assert component_types["execution_agent"] == "agent"
    assert component_types["analysis_module"] == "analyzer"
    assert component_types["document_tool"] == "tool"
    assert component_types["io_operation"] == "io"
    assert component_types["workflow_orchestrator"] == "workflow"


def test_workflow_planner_marks_knowledge_agent_for_agent_management_tasks() -> None:
    planner = WorkflowPlanner()
    task = TaskSchema(
        task_id="task_framework_knowledge",
        intent="query_agent_knowledge",
        input_text="查询爸爸的手机号并生成摘要。",
        domain="knowledge_ops",
        output_requirements=["summary"],
    )
    subtasks = [
        SubTask(subtask_id="subtask_1", name="query_information_knowledge", goal="Query stored knowledge."),
    ]

    workflow = asyncio.run(planner.plan(task, subtasks))

    assert workflow.composition["knowledge_agents"] == ["information_agent"]
    component_names = [component["name"] for component in workflow.composition["components"]]
    assert "knowledge_agent" in component_names
    assert "analysis_module" in component_names
