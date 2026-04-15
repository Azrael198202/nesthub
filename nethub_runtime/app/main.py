from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

from nethub_runtime.app.bootstrap import bootstrap_runtime
from nethub_runtime.core.services.core_engine import AICore

LOGGER = logging.getLogger("nethub_runtime.app.main")


def start_app(model_config_path: str | Path | None = None) -> dict[str, Any]:
    """
    应用启动入口
    
    初始化流程（集成 LiteLLM + LangGraph）：
    1. 运行时 bootstrap
    2. 初始化 LiteLLM 模型路由器
    3. 初始化 LangGraph 工作流执行器
    4. 初始化 Agent 构建器
    5. 初始化 AI Core 编排器
    
    参考: docs/03_core/integration_guide.md
    
    Args:
        model_config_path: 模型配置文件路径
    
    Returns:
        应用上下文，包含所有初始化的组件
    """
    
    LOGGER.info("🔧 Initializing NestHub application...")
    
    # ========== 第1步：Runtime Bootstrap ==========
    context = bootstrap_runtime()
    LOGGER.info("✓ Runtime bootstrapped")
    
    # ========== 第2-6步：AI Core 完整初始化 ==========
    # (在 AICore.__init__ 中完成)
    try:
        core = AICore(model_config_path=model_config_path)
        context["core"] = core
        LOGGER.info("✓ AI Core initialized")
        
        # 暴露关键组件供外部使用
        context["model_router"] = core.model_router
        context["workflow_executor"] = core.workflow_executor
        context["agent_builder"] = core.agent_builder
        context["tool_registry"] = core.tool_registry
        
    except Exception as e:
        LOGGER.error(f"Failed to initialize AI Core: {e}")
        raise
    
    context["status"] = "ready"
    
    LOGGER.info("✅ Application initialized successfully")
    LOGGER.info(f"📊 Core components available: model_router, workflow_executor, agent_builder, tool_registry")
    
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
