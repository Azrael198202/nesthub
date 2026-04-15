from __future__ import annotations

import asyncio

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
