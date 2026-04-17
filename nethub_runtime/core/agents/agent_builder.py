"""
Agent Builder - LangGraph Agent construction and generation.
Reference: docs/03_workflow/langgraph_agent_framework.md
"""

from __future__ import annotations

import logging
import json
from typing import Any, Optional

from nethub_runtime.core.workflows.schemas import AgentSpec, AgentCapability, AgentState
from nethub_runtime.core.utils.id_generator import generate_id

LOGGER = logging.getLogger("nethub_runtime.core.agents")


class AgentBuilder:
    """
    Agent构建器
    
    职责：
    - 根据任务生成 Agent 规范
    - 从规范构建可执行的 Agent
    """
    
    def __init__(self, model_router: Optional[Any] = None, tool_registry: Optional[Any] = None):
        """
        初始化 Agent 构建器
        
        Args:
            model_router: LiteLLM 模型路由器
            tool_registry: 工具注册表
        """
        self.model_router = model_router
        self.tool_registry = tool_registry
    
    async def generate_agent_spec(
        self,
        task: dict[str, Any],
        workflow: Optional[dict[str, Any]] = None
    ) -> AgentSpec:
        """
        AI生成Agent规范
        根据任务和工作流自动生成Agent定义
        
        Args:
            task: 任务定义
            workflow: 工作流定义
        
        Returns:
            Agent规范
        """
        agent_id = generate_id("agent")
        
        # 如果没有模型路由器，使用默认规范
        if not self.model_router:
            LOGGER.warning("No model router available, using default agent spec")
            return self._create_default_agent_spec(agent_id, task)
        
        # 使用模型路由器生成规范
        prompt = f"""
        Generate an efficient Agent specification for the following task and workflow.

        Task: {json.dumps(task, ensure_ascii=False, indent=2)}
        Workflow: {json.dumps(workflow or {}, ensure_ascii=False, indent=2)}

        Return JSON with these fields:
        {{
            "name": "agent name",
            "role": "role description",
            "goals": ["goal 1", "goal 2"],
            "model_policy": {{"intent_analysis": "model_name"}},
            "tool_policy": ["tool1", "tool2"],
            "memory_type": "short_term|long_term|hybrid",
            "max_iterations": 10
        }}
        """
        
        try:
            response = await self.model_router.invoke(
                task_type="agent_reasoning",
                prompt=prompt,
                system_prompt="You are an Agent designer. Return JSON only.",
            )
            spec_dict = json.loads(response)
            if not isinstance(spec_dict, dict):
                raise ValueError("Agent spec response is not JSON object")
            
            return self._create_agent_spec_from_dict(agent_id, spec_dict, task)
            
        except Exception as e:
            LOGGER.error(f"Failed to generate agent spec: {e}")
            return self._create_default_agent_spec(agent_id, task)
    
    def _create_default_agent_spec(
        self,
        agent_id: str,
        task: dict[str, Any]
    ) -> AgentSpec:
        """创建默认的Agent规范"""
        return AgentSpec(
            agent_id=agent_id,
            name=f"Agent-{agent_id[:8]}",
            role=task.get("intent", "Generic Agent"),
            description=f"Auto-generated agent for: {task.get('input_text', '')[:100]}",
            goals=[f"Execute: {task.get('intent')}"],
            constraints=["Follow safety guidelines"],
            scope="task",
            capabilities=[],
            model_policy={"default": "default_model"},
            tool_policy=[],
            memory_type="short_term",
            memory_capacity=100,
            max_iterations=5,
            timeout_sec=300,
            retry_policy="exponential_backoff",
        )
    
    def _create_agent_spec_from_dict(
        self,
        agent_id: str,
        spec_dict: dict[str, Any],
        task: dict[str, Any]
    ) -> AgentSpec:
        """从字典创建Agent规范"""
        return AgentSpec(
            agent_id=agent_id,
            name=spec_dict.get("name", f"Agent-{agent_id[:8]}"),
            role=spec_dict.get("role", "Generic Agent"),
            description=f"Agent for: {task.get('intent', 'general')}",
            goals=spec_dict.get("goals", ["Complete task"]),
            constraints=spec_dict.get("constraints", []),
            scope="task",
            capabilities=spec_dict.get("capabilities", []),
            model_policy=spec_dict.get("model_policy", {}),
            tool_policy=spec_dict.get("tool_policy", []),
            memory_type=spec_dict.get("memory_type", "short_term"),
            memory_capacity=spec_dict.get("memory_capacity", 100),
            max_iterations=spec_dict.get("max_iterations", 5),
            timeout_sec=spec_dict.get("timeout_sec", 300),
            retry_policy=spec_dict.get("retry_policy", "exponential_backoff"),
        )
    
    async def build_agent(self, spec: AgentSpec) -> ReasoningAgent:
        """
        根据规范构建Agent
        
        Args:
            spec: Agent规范
        
        Returns:
            可执行的 ReasoningAgent 实例
        """
        agent = ReasoningAgent(
            spec=spec,
            model_router=self.model_router,
            tool_registry=self.tool_registry
        )
        
        await agent.initialize()
        return agent


class ReasoningAgent:
    """
    推理型Agent（ReAct模式）
    
    核心推理循环：
    1. 观察（Observe）- 获取消息
    2. 思考（Think）- 使用LLM推理
    3. 计划（Plan）- 规划行动
    4. 行动（Act）- 执行工具/代码
    5. 评价（Evaluate）- 评价结果
    6. 循环或返回
    """
    
    def __init__(
        self,
        spec: AgentSpec,
        model_router: Optional[Any] = None,
        tool_registry: Optional[Any] = None
    ):
        """初始化推理Agent"""
        self.spec = spec
        self.model_router = model_router
        self.tool_registry = tool_registry
        self.memory: list[dict[str, Any]] = []
        self.available_tools: list[dict[str, Any]] = []
        self.available_model_policies: dict[str, str] = {}
        self.initialized_context: dict[str, Any] = {}
        
        LOGGER.info(f"🤖 Created Agent: {spec.name} ({spec.agent_id})")
    
    async def initialize(self) -> None:
        """初始化Agent"""
        LOGGER.info(f"🤖 Initializing Agent: {self.spec.name}")

        available_tools: list[dict[str, Any]] = []
        if self.tool_registry and hasattr(self.tool_registry, "get"):
            for tool_name in self.spec.tool_policy:
                tool = self.tool_registry.get(tool_name)
                if tool is None:
                    available_tools.append({"name": tool_name, "available": False})
                    continue
                schema_getter = getattr(tool, "get_schema", None)
                tool_schema = schema_getter() if callable(schema_getter) else {"name": tool_name}
                available_tools.append({"name": tool_name, "available": True, "schema": tool_schema})
        self.available_tools = available_tools

        available_model_policies: dict[str, str] = {}
        if self.model_router and hasattr(self.model_router, "get_model_config"):
            for task_type, model_name in self.spec.model_policy.items():
                if not model_name or model_name == "default_model":
                    continue
                model_config = self.model_router.get_model_config(model_name)
                available_model_policies[task_type] = model_config.get("name", model_name) if isinstance(model_config, dict) else str(model_name)
        self.available_model_policies = available_model_policies

        self.memory = [] if self.spec.memory_type == "short_term" else list(self.memory)
        self.initialized_context = {
            "memory_type": self.spec.memory_type,
            "memory_capacity": self.spec.memory_capacity,
            "tool_count": len(self.available_tools),
            "model_policy_count": len(self.available_model_policies),
        }

        LOGGER.debug(f"  Tools available: {len(self.available_tools)}")
        LOGGER.debug(f"  Model policies available: {len(self.available_model_policies)}")
        LOGGER.debug(f"  Memory type: {self.spec.memory_type}")
    
    async def think_and_act(
        self,
        input_text: str,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Agent的核心推理循环
        
        Args:
            input_text: 用户输入
            context: 执行上下文
        
        Returns:
            执行结果
        """
        messages = [{"role": "user", "content": input_text}]
        
        state: AgentState = {
            "agent_id": self.spec.agent_id,
            "agent_name": self.spec.name,
            "messages": messages,
            "tool_calls": [],
            "tool_results": [],
            "thoughts": [],
            "actions_taken": [],
            "is_final": False,
            "iterations": 0,
            "max_iterations": self.spec.max_iterations,
        }
        
        # 运行推理循环
        iteration = 0
        while (
            iteration < self.spec.max_iterations
            and not state["is_final"]
        ):
            LOGGER.debug(f"Iteration {iteration + 1}/{self.spec.max_iterations}")
            
            # 1. 思考
            thought = await self._conduct_reasoning(state)
            state["thoughts"].append(thought)
            
            # 2. 决定行动
            action = await self._plan_action(state, thought)
            state["actions_taken"].append(action)
            
            # 3. 执行行动
            if action["type"] == "tool_call":
                result = await self._execute_tool(action)
                state["tool_calls"].append(action)
                state["tool_results"].append(result)
            
            elif action["type"] == "final_answer":
                state["is_final"] = True
                state["messages"].append({
                    "role": "assistant",
                    "content": action.get("answer", "Task completed.")
                })
            
            iteration += 1
        
        LOGGER.info(
            f"✓ Agent reasoning completed: {self.spec.name} "
            f"({iteration} iterations, final={state['is_final']})"
        )
        
        return {
            "agent_id": self.spec.agent_id,
            "agent_name": self.spec.name,
            "final_answer": state["messages"][-1].get("content", ""),
            "thoughts": state["thoughts"],
            "actions": state["actions_taken"],
            "iterations": iteration,
            "success": state["is_final"],
        }
    
    async def _conduct_reasoning(self, state: AgentState) -> dict[str, Any]:
        """进行推理"""
        
        # 如果没有模型路由器，使用模拟推理
        if not self.model_router:
            return {
                "reasoning": "Simulated reasoning",
                "next_action_type": "final_answer",
                "confidence": 0.5
            }
        
        prompt = (
            f"角色: {self.spec.role}\n"
            f"目标: {', '.join(self.spec.goals)}\n"
            f"用户输入: {state['messages'][-1].get('content', '')}\n"
            f"可用工具: {self.spec.tool_policy}\n"
            "请输出 JSON："
            "{\"reasoning\":\"...\",\"next_action_type\":\"tool_call|final_answer\","
            "\"tool_input\":{},\"confidence\":0~1}"
        )
        try:
            response = await self.model_router.invoke(
                task_type="agent_reasoning",
                prompt=prompt,
                system_prompt="你是 ReAct Agent，严格输出 JSON。",
            )
            parsed = json.loads(response)
            if isinstance(parsed, dict) and parsed.get("next_action_type") in ("tool_call", "final_answer"):
                return parsed
        except Exception:
            LOGGER.debug("Agent reasoning parse failed, fallback to default")

        return {
            "reasoning": "Default reasoning",
            "next_action_type": "final_answer",
            "confidence": 0.8,
        }
    
    async def _plan_action(
        self,
        state: AgentState,
        thought: dict[str, Any]
    ) -> dict[str, Any]:
        """规划行动"""
        
        next_action_type = thought.get("next_action_type", "final_answer")
        
        if next_action_type == "final_answer":
            return {
                "type": "final_answer",
                "answer": thought.get("reasoning", "Task completed")
            }
        
        # 决定使用哪个工具
        tool_name = await self._select_tool(thought)
        
        return {
            "type": "tool_call",
            "tool": tool_name,
            "input": thought.get("tool_input", {})
        }
    
    async def _select_tool(self, thought: dict[str, Any]) -> str:
        """根据思考内容选择工具"""
        if self.spec.tool_policy:
            return self.spec.tool_policy[0]
        return "default_tool"
    
    async def _execute_tool(self, action: dict[str, Any]) -> dict[str, Any]:
        """执行工具"""
        tool_name = action["tool"]
        
        if not self.tool_registry:
            return {
                "success": False,
                "error": "No tool registry available"
            }
        
        try:
            if hasattr(self.tool_registry, "execute"):
                result = await self.tool_registry.execute(tool_name, action.get("input", {}))
                return {
                    "success": True,
                    "result": result,
                }

            return {
                "success": True,
                "result": f"Tool {tool_name} executed"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
