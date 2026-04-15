from __future__ import annotations

from typing import Any
from pathlib import Path

from nethub_runtime.core.config.settings import (
    AGENT_REGISTRY_PATH,
    BLUEPRINT_REGISTRY_PATH,
    MODEL_REGISTRY_PATH,
    load_local_env,
)
from nethub_runtime.core.memory.vector_store import VectorStore
from nethub_runtime.core.services.agent_designer import AgentDesigner
from nethub_runtime.core.services.blueprint_generator import BlueprintGenerator
from nethub_runtime.core.services.blueprint_resolver import BlueprintResolver
from nethub_runtime.core.services.capability_router import CapabilityRouter
from nethub_runtime.core.services.context_manager import ContextManager
from nethub_runtime.core.services.dependency_manager import DependencyManager
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator
from nethub_runtime.core.services.intent_analyzer import IntentAnalyzer
from nethub_runtime.core.services.registry import JsonRegistry
from nethub_runtime.core.services.result_integrator import ResultIntegrator
from nethub_runtime.core.services.security_guard import SecurityGuard
from nethub_runtime.core.services.task_decomposer import TaskDecomposer
from nethub_runtime.core.services.workflow_planner import WorkflowPlanner
from nethub_runtime.core.utils.logger import get_logger
from nethub_runtime.models.model_router import ModelRouter
from nethub_runtime.core.workflows.executor import WorkflowExecutor
from nethub_runtime.core.workflows.base_workflow import SimpleWorkflow
from nethub_runtime.core.agents.agent_builder import AgentBuilder
from nethub_runtime.core.tools.registry import ToolRegistry


class AICore:
    """
    AI Core - 系统的思考层、决策层和编排层
    
    整合了：
    - LiteLLM 模型路由 (docs/02_router/litellm_routing_design.md)
    - LangGraph 工作流执行 (docs/03_workflow/langgraph_agent_framework.md)
    - Agent 构建与推理
    """
    
    def __init__(self, model_config_path: str | Path | None = None) -> None:
        """
        初始化 AI Core
        
        Args:
            model_config_path: 模型配置文件路径，如不指定则使用默认
        """
        load_local_env()
        self.logger = get_logger("nethub_runtime.core.engine")
        
        # ========== 基础管理器 ==========
        self.context_manager = ContextManager()
        self.vector_store = VectorStore()
        self.dependency_manager = DependencyManager()
        self.security_guard = SecurityGuard()
        
        # ========== 注册表管理 ==========
        self.model_registry = JsonRegistry(MODEL_REGISTRY_PATH)
        self.blueprint_registry = JsonRegistry(BLUEPRINT_REGISTRY_PATH)
        self.agent_registry = JsonRegistry(AGENT_REGISTRY_PATH)
        
        # ========== 传统插件-based 服务 ==========
        self.intent_analyzer = IntentAnalyzer()
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.blueprint_resolver = BlueprintResolver(registry=self.blueprint_registry)
        self.blueprint_generator = BlueprintGenerator(registry=self.blueprint_registry)
        self.agent_designer = AgentDesigner()
        self.capability_router = CapabilityRouter()
        self.execution_coordinator = ExecutionCoordinator(session_store=self.context_manager.session_store)
        self.result_integrator = ResultIntegrator()
        
        # ========== 新增：LiteLLM 模型路由 ==========
        # 参考: docs/02_router/litellm_routing_design.md
        try:
            if model_config_path is None:
                # 尝试使用默认配置
                model_config_path = Path("nethub_runtime/config/model_config.yaml")
            
            self.model_router = ModelRouter(str(model_config_path))
            self.logger.info("✓ LiteLLM Model Router initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize ModelRouter: {e}, will use plugins only")
            self.model_router = None
        
        # ========== 新增：工具注册表 ==========
        self.tool_registry = ToolRegistry()
        self.logger.info("✓ Tool Registry initialized")
        
        # ========== 新增：LangGraph 工作流执行器 ==========
        # 参考: docs/03_workflow/langgraph_agent_framework.md
        self.workflow_executor = WorkflowExecutor()
        self.logger.info("✓ LangGraph Workflow Executor initialized")
        
        # ========== 新增：Agent 构建器 ==========
        self.agent_builder = AgentBuilder(
            model_router=self.model_router,
            tool_registry=self.tool_registry
        )
        self.logger.info("✓ Agent Builder initialized")


    def reload_plugins(self) -> dict[str, Any]:
        """Reload plugin-enabled services from config without restarting process."""
        self.intent_analyzer = IntentAnalyzer()
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.capability_router = CapabilityRouter()
        return {
            "status": "reloaded",
            "intent_analyzer_plugins": len(self.intent_analyzer.plugins),
            "task_decomposer_plugins": len(self.task_decomposer.plugins),
            "workflow_planner_plugins": len(self.workflow_planner.plugins),
        }

    async def handle(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
        fmt: str = "dict",
        use_langraph: bool = True
    ) -> dict[str, Any] | str:
        """
        AI Core 主处理函数
        
        执行流程:
        1. 意图分析 (使用 LiteLLM 或插件)
        2. 判断：是否需要 Agent？
           - Yes: 生成 Agent，运行推理循环
           - No: 使用 Workflow 或传统流程
        3. 结果整合
        
        Args:
            input_text: 用户输入
            context: 执行上下文
            fmt: 输出格式
            use_langraph: 是否使用 LangGraph (默认为是)
        
        Returns:
            处理结果
        """
        self.security_guard.validate_output_format(fmt)
        self.model_registry.hot_reload()
        self.blueprint_registry.hot_reload()
        self.agent_registry.hot_reload()
        dependency_status = self.dependency_manager.check()

        ctx = self.context_manager.load(context)
        ctx = self.context_manager.enrich(ctx)
        self.logger.info(f"🔄 Handling request trace={ctx.trace_id} session={ctx.session_id}")
        
        try:
            # ========== Step 1: 意图分析 ==========
            task = await self.intent_analyzer.analyze(input_text, ctx)
            self.logger.info(f"  Intent: {task.intent}, Domain: {task.domain}")
            
            # ========== Step 2: 决策 - Agent 还是 Workflow? ==========
            need_agent = task.constraints.get("need_agent", False)
            
            if need_agent and use_langraph:
                # ========== Path A: 使用 Agent（推理型） ==========
                self.logger.info("📌 Using Agent (reasoning loop)")
                
                # 生成 Agent 规范
                agent_spec = await self.agent_builder.generate_agent_spec(
                    task=task.model_dump(),
                    workflow=None
                )
                
                # 构建 Agent
                agent = await self.agent_builder.build_agent(agent_spec)
                
                # 运行 Agent 推理循环
                agent_result = await agent.think_and_act(input_text, ctx.model_dump())
                
                # 注册 Agent
                self.agent_registry.register(agent_spec.name, agent_spec)
                
                execution_result = {
                    "execution_type": "agent",
                    "agent_result": agent_result,
                }
                
            else:
                # ========== Path B: 使用 Workflow（任务编排） ==========
                self.logger.info("📌 Using Workflow (task orchestration)")
                
                if use_langraph:
                    # 使用 LangGraph Workflow
                    workflow = SimpleWorkflow(model_router=self.model_router)
                    workflow_context = ctx.model_dump()
                    workflow_context["model_router"] = self.model_router
                    workflow_state = await self.workflow_executor.execute_workflow(
                        workflow=workflow,
                        user_input=input_text,
                        context=workflow_context,
                        execution_id=ctx.trace_id
                    )
                    
                    execution_result = {
                        "execution_type": "workflow",
                        "workflow_state": workflow_state,
                    }
                else:
                    # 回退到传统流程
                    subtasks = await self.task_decomposer.decompose(task)
                    workflow = await self.workflow_planner.plan(task, subtasks)
                    blueprints = self.blueprint_resolver.resolve(task, workflow)
                    
                    if not blueprints:
                        blueprints = [self.blueprint_generator.generate(task, workflow)]
                    
                    for blueprint in blueprints:
                        self.blueprint_registry.register(blueprint.name, blueprint)
                    
                    plan = self.capability_router.route_workflow(task, workflow)
                    self.security_guard.validate_plan(plan)
                    
                    for step in plan:
                        model_choice = (step.get("capability") or {}).get("model_choice", {})
                        provider = model_choice.get("provider", "unknown")
                        model = model_choice.get("model", "unknown")
                        self.model_registry.register(f"{provider}:{model}", model_choice)
                    
                    execution_result = self.execution_coordinator.execute(plan, task, ctx)
            
            # ========== Step 3: 结果整合 ==========
            vector_backend = self.vector_store.active_store()
            
            final_result = self.result_integrator.build_response(
                task=task,
                workflow=None,
                blueprints=[],
                agent=None,
                execution_result={
                    **execution_result,
                    "vector_store": vector_backend,
                    "dependency_status": dependency_status
                },
                context=ctx,
                fmt=fmt,
            )
            
            self.logger.info(f"✅ Request completed trace={ctx.trace_id}")
            
            return final_result
            
        except Exception as exc:
            self.logger.error(f"❌ Core handle failed trace={ctx.trace_id} error={exc}")
            raise

