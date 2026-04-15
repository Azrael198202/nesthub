"""
LangGraph Base Workflow - Foundation for workflow execution.
Reference: docs/03_workflow/langgraph_agent_framework.md
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from datetime import datetime

from nethub_runtime.core.workflows.schemas import WorkflowState, WorkflowPlan, WorkflowStep
from nethub_runtime.core.utils.id_generator import generate_id

LOGGER = logging.getLogger("nethub_runtime.core.workflows")


class BaseWorkflow:
    """
    基础工作流模板
    
    提供LangGraph风格的工作流框架，支持：
    - 节点定义和执行
    - 条件边
    - 状态管理
    """
    
    def __init__(self, name: str = "base_workflow"):
        """初始化工作流"""
        self.name = name
        self.nodes: dict[str, Callable] = {}
        self.edges: list[tuple[str, str]] = []
        self.conditional_edges: dict[str, dict[str, str]] = {}
        self.entry_point: Optional[str] = None
        self.exit_point: str = "END"
    
    def add_node(self, node_id: str, node_func: Callable) -> None:
        """添加节点"""
        self.nodes[node_id] = node_func
        LOGGER.debug(f"Added node: {node_id}")
    
    def add_edge(self, from_node: str, to_node: str) -> None:
        """添加边"""
        self.edges.append((from_node, to_node))
        LOGGER.debug(f"Added edge: {from_node} -> {to_node}")
    
    def add_conditional_edges(
        self,
        source_node: str,
        condition_func: Callable,
        edges: dict[str, str]
    ) -> None:
        """
        添加条件边
        
        Args:
            source_node: 源节点
            condition_func: 条件函数，返回要跳转的边的key
            edges: 条件 -> 目标节点 的映射
        """
        self.conditional_edges[source_node] = {
            "condition": condition_func,
            "edges": edges
        }
        LOGGER.debug(f"Added conditional edges from: {source_node}")
    
    def set_entry_point(self, node_id: str) -> None:
        """设置入口点"""
        self.entry_point = node_id
        LOGGER.debug(f"Set entry point: {node_id}")
    
    def set_exit_point(self, node_id: str) -> None:
        """设置出口点"""
        self.exit_point = node_id
    
    async def _execute_node(
        self,
        node_id: str,
        state: WorkflowState
    ) -> WorkflowState:
        """执行单个节点"""
        if node_id not in self.nodes:
            LOGGER.error(f"Node not found: {node_id}")
            raise ValueError(f"Node {node_id} not found in workflow")
        
        LOGGER.info(f"Executing node: {node_id}")
        
        try:
            node_func = self.nodes[node_id]
            result = await node_func(state)
            return result
        except Exception as e:
            LOGGER.error(f"Node execution failed: {node_id}, error: {e}")
            state["errors"].append(str(e))
            state["retry_count"] += 1
            return state
    
    def _get_next_node(self, current_node: str, state: WorkflowState) -> str:
        """确定下一个要执行的节点"""
        # 检查是否有条件边
        if current_node in self.conditional_edges:
            condition_func = self.conditional_edges[current_node]["condition"]
            condition_key = condition_func(state)
            
            next_node = self.conditional_edges[current_node]["edges"].get(condition_key)
            if next_node:
                return next_node
        
        # 查找直接边
        for from_node, to_node in self.edges:
            if from_node == current_node:
                return to_node
        
        # 没有找到下一个节点，返回退出点
        return self.exit_point
    
    async def run(
        self,
        user_input: str,
        context: dict[str, Any],
        trace_id: Optional[str] = None
    ) -> WorkflowState:
        """
        运行工作流
        
        Args:
            user_input: 用户输入
            context: 执行上下文
            trace_id: 追踪ID
        
        Returns:
            最终状态
        """
        if not self.entry_point:
            raise ValueError("Workflow entry point not set")

        trace_id = trace_id or generate_id("trace")
        state = self.build_initial_state(user_input=user_input, context=context, trace_id=trace_id)
        
        current_node = self.entry_point
        
        # 执行工作流
        while current_node != self.exit_point and state["should_continue"]:
            state = await self._execute_node(current_node, state)
            
            if state["retry_count"] > 3:
                LOGGER.warning(f"Workflow exceeded max retry count: {trace_id}")
                break
            
            current_node = self._get_next_node(current_node, state)
            state["current_step"] += 1
        
        LOGGER.info(
            f"Workflow completed: {trace_id}, "
            f"steps: {state['current_step']}, "
            f"errors: {len(state['errors'])}"
        )
        
        return state

    def build_initial_state(self, user_input: str, context: dict[str, Any], trace_id: str) -> WorkflowState:
        """创建统一的工作流初始状态。"""
        return {
            "user_input": user_input,
            "task_id": generate_id("task"),
            "context": context,
            "intent": None,
            "plan": None,
            "current_step": 0,
            "results": [],
            "errors": [],
            "should_continue": True,
            "retry_count": 0,
            "timestamp": datetime.now().isoformat(),
            "trace_id": trace_id,
        }

    def build_langgraph(self):
        """可选: 编译为 LangGraph StateGraph（依赖存在时启用）。"""
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            return None

        graph = StateGraph(WorkflowState)
        for node_id, node_func in self.nodes.items():
            graph.add_node(node_id, node_func)

        if self.entry_point:
            graph.set_entry_point(self.entry_point)

        for from_node, to_node in self.edges:
            if to_node == self.exit_point:
                graph.add_edge(from_node, END)
            else:
                graph.add_edge(from_node, to_node)

        for source_node, cfg in self.conditional_edges.items():
            graph.add_conditional_edges(source_node, cfg["condition"], cfg["edges"])

        return graph.compile()


class SimpleWorkflow(BaseWorkflow):
    """
    简单工作流示例
    
    流程: analyze_intent -> plan_tasks -> execute -> integrate_results
    """
    
    async def node_analyze_intent(self, state: WorkflowState) -> WorkflowState:
        """节点1：分析意图"""
        LOGGER.info(f"Analyzing intent: {state['user_input'][:50]}...")

        model_router = getattr(self, "model_router", None)
        if model_router:
            prompt = (
                "请分析用户请求，输出 JSON: "
                "{\"type\":\"task_type\",\"confidence\":0~1,\"needs_agent\":bool}\n"
                f"用户输入: {state['user_input']}"
            )
            try:
                response = await model_router.invoke(
                    task_type="intent_analysis",
                    prompt=prompt,
                    system_prompt="你是意图分析器，只返回 JSON。",
                )
                import json

                parsed = json.loads(response)
                state["intent"] = {
                    "type": parsed.get("type", "general_task"),
                    "confidence": float(parsed.get("confidence", 0.8)),
                    "needs_agent": bool(parsed.get("needs_agent", False)),
                }
                return state
            except Exception:
                LOGGER.debug("Intent model parse failed, fallback to rule default")

        state["intent"] = {
            "type": "general_task",
            "confidence": 0.8,
            "needs_agent": False,
        }
        
        return state
    
    async def node_plan_tasks(self, state: WorkflowState) -> WorkflowState:
        """节点2：规划任务"""
        if not state["intent"]:
            state["errors"].append("Intent not analyzed")
            return state
        
        LOGGER.info(f"Planning tasks for intent: {state['intent']['type']}")
        
        model_router = getattr(self, "model_router", None)
        if model_router:
            prompt = (
                "请基于输入和意图生成执行计划，返回 JSON 数组："
                "[{\"step\":1,\"name\":\"...\"}]\n"
                f"输入: {state['user_input']}\n"
                f"意图: {state['intent']}"
            )
            try:
                response = await model_router.invoke(
                    task_type="task_planning",
                    prompt=prompt,
                    system_prompt="你是任务规划器，只返回 JSON 数组。",
                )
                import json

                parsed = json.loads(response)
                if isinstance(parsed, list) and parsed:
                    state["plan"] = [
                        {
                            "step": int(item.get("step", idx + 1)),
                            "name": str(item.get("name", f"task_{idx + 1}")),
                            "status": "pending",
                        }
                        for idx, item in enumerate(parsed)
                        if isinstance(item, dict)
                    ]
                    if state["plan"]:
                        return state
            except Exception:
                LOGGER.debug("Planning model parse failed, fallback to template plan")

        state["plan"] = [
            {"step": 1, "name": "task_1", "status": "pending"},
            {"step": 2, "name": "task_2", "status": "pending"},
        ]
        
        return state
    
    async def node_execute_step(self, state: WorkflowState) -> WorkflowState:
        """节点3：执行步骤"""
        if not state["plan"]:
            state["errors"].append("Plan not created")
            state["should_continue"] = False
            return state
        
        # 执行计划中的所有步骤
        for step in state["plan"]:
            LOGGER.info(f"Executing step: {step['name']}")
            
            # TODO: 执行实际的工作
            result = {"step": step["step"], "result": "success"}
            state["results"].append(result)
            step["status"] = "completed"
        
        state["should_continue"] = False
        return state
    
    async def node_integrate_results(self, state: WorkflowState) -> WorkflowState:
        """节点4：整合结果"""
        LOGGER.info(f"Integrating {len(state['results'])} results")
        
        # 结果已在前面步骤中采集，这里可以进行最终处理
        return state
    
    def __init__(self, model_router: Any | None = None):
        """初始化简单工作流"""
        super().__init__(name="simple_workflow")
        self.model_router = model_router
        
        # 添加节点
        self.add_node("analyze_intent", self.node_analyze_intent)
        self.add_node("plan_tasks", self.node_plan_tasks)
        self.add_node("execute", self.node_execute_step)
        self.add_node("integrate", self.node_integrate_results)
        
        # 添加边
        self.add_edge("analyze_intent", "plan_tasks")
        self.add_edge("plan_tasks", "execute")
        self.add_edge("execute", "integrate")
        self.add_edge("integrate", self.exit_point)
        
        # 设置入口
        self.set_entry_point("analyze_intent")

