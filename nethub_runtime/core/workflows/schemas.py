"""
LangGraph Workflow - State and schema definitions.
Reference: docs/03_workflow/langgraph_agent_framework.md
"""

from __future__ import annotations

from typing import TypedDict, Optional, List, Any
from dataclasses import dataclass, field
from enum import Enum


class WorkflowState(TypedDict):
    """LangGraph 工作流状态"""
    
    # 输入
    user_input: str
    task_id: str
    context: dict
    
    # 中间状态
    intent: Optional[dict]
    plan: Optional[list]
    current_step: int
    
    # 执行结果
    results: list
    errors: list
    
    # 控制
    should_continue: bool
    retry_count: int
    
    # 审计
    timestamp: str
    trace_id: str


class AgentState(TypedDict):
    """LangGraph Agent 状态"""
    
    # Agent信息
    agent_id: str
    agent_name: str
    
    # 消息历史
    messages: List[dict]
    
    # 工具调用
    tool_calls: list
    tool_results: list
    
    # 思考过程
    thoughts: list
    actions_taken: list
    
    # 状态
    is_final: bool
    iterations: int
    max_iterations: int


@dataclass
class WorkflowStep:
    """工作流步骤定义"""
    step_id: str
    name: str
    step_type: str  # 'llm', 'tool', 'code', 'conditional'
    depends_on: list[str] = field(default_factory=list)
    input_from: Optional[str] = None
    output: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowPlan:
    """工作流执行计划"""
    workflow_id: str
    task_id: str
    steps: list[WorkflowStep]
    entry_point: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCapability:
    """Agent能力定义"""
    name: str
    description: str
    required_models: List[str]
    required_tools: List[str]
    required_blueprints: List[str]


@dataclass
class AgentSpec:
    """Agent规范"""
    agent_id: str
    name: str
    role: str
    description: str
    
    # 目标与范围
    goals: List[str]
    constraints: List[str]
    scope: str
    
    # 能力
    capabilities: List[AgentCapability]
    
    # 模型策略
    model_policy: dict[str, str]  # task_type -> model
    
    # 工具策略
    tool_policy: List[str]
    
    # 内存策略
    memory_type: str  # "short_term" / "long_term" / "hybrid"
    memory_capacity: int = 100
    
    # 执行策略
    max_iterations: int = 10
    timeout_sec: int = 300
    retry_policy: str = "exponential_backoff"
