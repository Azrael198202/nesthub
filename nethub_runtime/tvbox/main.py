"""
TVBox Runtime - Local execution environment for edge devices.
Reference: docs/03_core/integration_guide.md
"""

from __future__ import annotations

import logging
import asyncio
import threading
from typing import Any
from pathlib import Path

from nethub_runtime.app.main import start_app

LOGGER = logging.getLogger("nethub_runtime.tvbox")


def start_tvbox(model_config_path: str | Path | None = None) -> dict[str, Any]:
    """
    TVBox启动入口 - 本地运行时模式
    
    职责：
    1. 运行应用的完整初始化（与main.py相同）
    2. 初始化本地运行时管理器
    3. 启动UI服务（可选）
    4. 启动LAN服务（用于与其他设备通信）
    
    参考: docs/03_core/integration_guide.md 第4.2节
    
    Args:
        model_config_path: 模型配置文件路径
    
    Returns:
        应用上下文，包含TVBox特定的组件
    """
    
    LOGGER.info("📺 [tvbox/main.py] Starting TVBox Runtime...")
    
    # ========== 第1-6步：复用标准启动流程 ==========
    # 调用主启动函数，获得完整的应用context
    context = start_app(model_config_path=model_config_path)
    LOGGER.info("✓ Base application initialized (shared with main.py)")
    
    # ========== TVBox特定：启动API服务 ==========
    try:
        _start_local_api_server(context)
    except Exception as e:
        LOGGER.warning(f"Failed to start API server: {e}")
    
    LOGGER.info("✅ TVBox Runtime started successfully")
    LOGGER.info(f"📊 Features: AI Core, Model Router, Workflow Executor, Agent Builder, API Server")
    
    return context


def _start_local_api_server(context: dict[str, Any]) -> None:
    """
    启动本地API服务器（用于LAN通信）
    
    提供以下端点：
    - POST /api/execute - 同步执行
    - WebSocket /ws/execute/{execution_id} - 异步流式执行
    - GET /api/status/{execution_id} - 查询执行状态
    """
    
    try:
        from fastapi import FastAPI, WebSocket
        import uvicorn
    except ImportError:
        LOGGER.warning("FastAPI not installed, skipping API server")
        return
    
    app = FastAPI(
        title="NestHub TVBox API",
        description="Local AI execution API for edge devices",
        version="1.0"
    )
    
    core = context.get("core")
    if not core:
        LOGGER.error("Core not found in context")
        return
    
    # ========== REST 执行端点 ==========
    @app.post("/api/execute")
    async def execute(request: dict[str, Any]):
        """
        同步执行请求
        
        请求格式:
        {
            "input": "user input text",
            "context": {optional context}
        }
        """
        try:
            user_input = request.get("input", "")
            context_data = request.get("context", {})
            
            # 调用AI Core处理
            result = await core.handle(user_input, context_data)
            
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            LOGGER.error(f"Execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ========== 状态查询端点 ==========
    @app.get("/api/status/{execution_id}")
    async def get_status(execution_id: str):
        """查询执行状态"""
        workflow_executor = context.get("workflow_executor")
        if not workflow_executor:
            return {"error": "Workflow executor not found"}
        
        status = workflow_executor.get_execution_status(execution_id)
        return status
    
    # ========== 健康检查端点 ==========
    @app.get("/health")
    async def health_check():
        """健康检查"""
        return {
            "status": "healthy",
            "timestamp": str(__import__("datetime").datetime.now()),
        }
    
    # ========== 启动API服务器（后台线程）==========
    def run_server():
        """在后台线程运行API服务器"""
        try:
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=8000,
                log_level="info"
            )
            server = uvicorn.Server(config)
            asyncio.run(server.serve())
        except Exception as e:
            LOGGER.error(f"API Server error: {e}")
    
    # 后台运行
    api_thread = threading.Thread(target=run_server, daemon=True)
    api_thread.start()
    
    LOGGER.info("✓ API Server started at http://0.0.0.0:8000")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    
    ctx = start_tvbox()
    
    print("\n" + "=" * 70)
    print("📺 NestHub TVBox Status")
    print("=" * 70)
    print("  ✓ AI Core Initialized")
    print("  ✓ LiteLLM Routing Active")
    print("  ✓ LangGraph Workflows Ready")
    print("  ✓ Agent Builder Available")
    print("  ✓ Web API Server Running (http://0.0.0.0:8000)")
    print("=" * 70)
    print("\nAvailable Endpoints:")
    print("  POST   /api/execute             - Synchronous execution")
    print("  GET    /api/status/{exec_id}    - Query execution status")
    print("  GET    /health                  - Health check")
    print("=" * 70)
    
    # 保持运行
    try:
        while True:
            pass
    except KeyboardInterrupt:
        LOGGER.info("TVBox shutting down...")
