from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

from nethub_runtime.app.bootstrap import bootstrap_runtime
from nethub_runtime.core_brain.services.core_engine_provider import create_core_engine

LOGGER = logging.getLogger("nethub_runtime.app.main")


def start_app(model_config_path: str | Path | None = None) -> dict[str, Any]:
    """
    应用启动入口：初始化 runtime + core-brain。
    """

    LOGGER.info("Initializing NestHub application...")
    
    # ========== 第1步：Runtime Bootstrap ==========
    context = bootstrap_runtime()
    LOGGER.info("Runtime bootstrapped")

    try:
        core = create_core_engine(model_config_path=model_config_path)
        context["core"] = core
        LOGGER.info("Core-brain initialized")

        # Optional compatibility keys used by legacy UI panels.
        context["model_router"] = core.model_router
        context["workflow_executor"] = core.workflow_executor
        context["agent_builder"] = core.agent_builder
        context["tool_registry"] = core.tool_registry

    except Exception as e:
        LOGGER.error(f"Failed to initialize core-brain: {e}")
        raise

    context["status"] = "ready"

    LOGGER.info("Application initialized successfully")

    return context


# 👉 允许单独调试
if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    ctx = start_app()

    print("\n" + "=" * 60)
    print("🚀 NestHub Application Status")
    print("=" * 60)
    print(f"  Status: {ctx['status']}")
    print(f"  Core available: {ctx.get('core') is not None}")
    print(f"  Model Router: {ctx.get('model_router') is not None}")
    print(f"  Workflow Executor: {ctx.get('workflow_executor') is not None}")
    print(f"  Agent Builder: {ctx.get('agent_builder') is not None}")
    print(f"  Tool Registry: {ctx.get('tool_registry') is not None}")
    print("=" * 60)
