from __future__ import annotations

import asyncio

from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.core_engine import AICore


class DummyAgent:
    async def think_and_act(self, input_text: str, context: dict):
        return {
            "final_answer": f"done:{input_text}",
            "success": True,
            "iterations": 1,
        }


async def _fake_analyze(*args, **kwargs):
    return TaskSchema(
        task_id="task_agent_test",
        intent="general_task",
        input_text="please use agent",
        domain="general",
        constraints={"need_agent": True},
        output_requirements=["text"],
        metadata={},
    )


async def _fake_generate_agent_spec(*args, **kwargs):
    from nethub_runtime.core.workflows.schemas import AgentSpec

    return AgentSpec(
        agent_id="agent_test",
        name="agent_test",
        role="tester",
        description="test agent",
        goals=["test"],
        constraints=[],
        scope="task",
        capabilities=[],
        model_policy={"default": "groq:llama-3-70b"},
        tool_policy=[],
        memory_type="short_term",
        memory_capacity=10,
        max_iterations=2,
        timeout_sec=30,
        retry_policy="exponential_backoff",
    )


async def _fake_build_agent(*args, **kwargs):
    return DummyAgent()


def test_core_engine_handle_agent_path() -> None:
    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")

    core.intent_analyzer.analyze = _fake_analyze
    core.agent_builder.generate_agent_spec = _fake_generate_agent_spec
    core.agent_builder.build_agent = _fake_build_agent

    result = asyncio.run(
        core.handle(
            input_text="请使用agent执行",
            context={"user_id": "u_agent"},
            fmt="dict",
            use_langraph=True,
        )
    )

    assert isinstance(result, dict)
    assert result["execution_result"]["execution_type"] == "agent"
    assert result["execution_result"]["agent_result"]["success"] is True
