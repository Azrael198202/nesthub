"""
Workflow Executor - LangGraph workflow execution engine.
Reference: docs/03_workflow/langgraph_agent_framework.md
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from datetime import datetime

from nethub_runtime.core.workflows.schemas import WorkflowPlan, WorkflowState
from nethub_runtime.core.utils.id_generator import generate_id

LOGGER = logging.getLogger("nethub_runtime.core.workflows")


class WorkflowExecutor:
    """
    工作流执行引擎
    
    职责：
    - 执行 LangGraph 工作流
    - 管理执行状态
    - 处理错误和重试
    """
    
    def __init__(self):
        """初始化工作流执行器"""
        self.active_executions: dict[str, dict[str, Any]] = {}
        self.execution_history: list[dict[str, Any]] = []
    
    async def execute_workflow(
        self,
        workflow,
        user_input: str,
        context: dict[str, Any],
        execution_id: Optional[str] = None
    ) -> dict[str, Any]:
        """
        执行工作流
        
        Args:
            workflow: 工作流实例 (BaseWorkflow 或其子类)
            user_input: 用户输入
            context: 执行上下文
            execution_id: 执行ID
        
        Returns:
            执行结果
        """
        execution_id = execution_id or generate_id("execution")
        
        LOGGER.info(f"🚀 Starting workflow execution: {execution_id}")
        
        start_time = datetime.now()
        
        try:
            use_langgraph_runtime = bool(context.get("use_langgraph_runtime", True)) if isinstance(context, dict) else True

            final_state = None
            if use_langgraph_runtime and hasattr(workflow, "build_langgraph"):
                compiled_graph = workflow.build_langgraph()
                if compiled_graph is not None:
                    LOGGER.info("Using LangGraph runtime for execution: %s", execution_id)
                    initial_state = workflow.build_initial_state(
                        user_input=user_input,
                        context=context,
                        trace_id=execution_id,
                    )
                    final_state = await compiled_graph.ainvoke(initial_state)

            if final_state is None:
                LOGGER.info("Using native workflow runner for execution: %s", execution_id)
                final_state = await workflow.run(
                    user_input=user_input,
                    context=context,
                    trace_id=execution_id,
                )
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            self.active_executions[execution_id] = {
                "status": "completed",
                "state": final_state,
                "duration_ms": duration_ms,
                "result": {
                    "success": len(final_state["errors"]) == 0,
                    "results": final_state["results"],
                    "errors": final_state["errors"],
                }
            }
            
            # 记录到历史
            self.execution_history.append({
                "execution_id": execution_id,
                "status": "completed",
                "timestamp": start_time.isoformat(),
                "duration_ms": duration_ms,
            })
            
            LOGGER.info(f"✅ Workflow completed: {execution_id} ({duration_ms:.1f}ms)")
            
            return final_state
            
        except Exception as e:
            LOGGER.error(f"❌ Workflow execution failed: {e}")
            
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            self.active_executions[execution_id] = {
                "status": "failed",
                "error": str(e),
                "duration_ms": duration_ms,
            }
            
            self.execution_history.append({
                "execution_id": execution_id,
                "status": "failed",
                "timestamp": start_time.isoformat(),
                "duration_ms": duration_ms,
                "error": str(e),
            })
            
            raise
    
    def get_execution_status(self, execution_id: str) -> dict[str, Any]:
        """
        获取执行状态
        
        Args:
            execution_id: 执行ID
        
        Returns:
            执行状态信息
        """
        return self.active_executions.get(execution_id, {
            "status": "unknown",
            "message": f"Execution {execution_id} not found"
        })
    
    def list_executions(self, limit: int = 10) -> list[dict[str, Any]]:
        """列出最近的执行历史"""
        return self.execution_history[-limit:]
    
    def clear_execution_history(self) -> None:
        """清除执行历史"""
        self.active_executions.clear()
        self.execution_history.clear()
        LOGGER.info("Execution history cleared")
