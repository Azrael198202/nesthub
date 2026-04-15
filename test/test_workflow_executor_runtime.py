from __future__ import annotations

import asyncio

from nethub_runtime.core.workflows.base_workflow import SimpleWorkflow
from nethub_runtime.core.workflows.executor import WorkflowExecutor


def test_workflow_executor_langgraph_runtime() -> None:
    workflow = SimpleWorkflow(model_router=None)
    executor = WorkflowExecutor()

    state = asyncio.run(
        executor.execute_workflow(
            workflow=workflow,
            user_input="帮我规划一个简单任务",
            context={"use_langgraph_runtime": True},
            execution_id="test_exec_langgraph",
        )
    )

    assert isinstance(state, dict)
    assert "results" in state
    assert "errors" in state


def test_workflow_executor_native_runtime() -> None:
    workflow = SimpleWorkflow(model_router=None)
    executor = WorkflowExecutor()

    state = asyncio.run(
        executor.execute_workflow(
            workflow=workflow,
            user_input="再跑一次原生执行器",
            context={"use_langgraph_runtime": False},
            execution_id="test_exec_native",
        )
    )

    assert isinstance(state, dict)
    assert "results" in state
