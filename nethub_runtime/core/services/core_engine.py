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
from nethub_runtime.core.services.runtime_failure_classifier import RuntimeFailureClassifier
from nethub_runtime.core.services.runtime_outcome_evaluator import RuntimeOutcomeEvaluator
from nethub_runtime.core.services.runtime_repair_service import RuntimeRepairService
from nethub_runtime.core.services.security_guard import SecurityGuard
from nethub_runtime.core.services.task_decomposer import TaskDecomposer
from nethub_runtime.core.services.workflow_planner import WorkflowPlanner
from nethub_runtime.core.utils.logger import get_logger
from nethub_runtime.models.model_router import ModelRouter
from nethub_runtime.core.workflows.executor import WorkflowExecutor
from nethub_runtime.core.workflows.base_workflow import SimpleWorkflow
from nethub_runtime.core.agents.agent_builder import AgentBuilder
from nethub_runtime.core.tools.registry import ToolRegistry
from nethub_runtime.core.services.user_goal_evaluator import UserGoalEvaluator
from nethub_runtime.core.services.runtime_keyword_signal_analyzer import RuntimeKeywordSignalAnalyzer
from nethub_runtime.generated.store import GeneratedArtifactStore


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
        self.generated_artifact_store = GeneratedArtifactStore()
        
        # ========== 传统插件-based 服务 ==========
        self.intent_analyzer = IntentAnalyzer()
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.blueprint_resolver = BlueprintResolver(registry=self.blueprint_registry)
        self.blueprint_generator = BlueprintGenerator(registry=self.blueprint_registry)
        self.agent_designer = AgentDesigner()
        self.capability_router = CapabilityRouter()

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

        keyword_signal_analyzer = RuntimeKeywordSignalAnalyzer(model_router=self.model_router)
        self.intent_analyzer = IntentAnalyzer(keyword_analyzer=keyword_signal_analyzer)

        self.execution_coordinator = ExecutionCoordinator(
            session_store=self.context_manager.session_store,
            vector_store=self.vector_store,
            generated_artifact_store=self.generated_artifact_store,
            model_router=self.model_router,
        )
        self.result_integrator = ResultIntegrator()
        self.runtime_failure_classifier = RuntimeFailureClassifier()
        self.runtime_outcome_evaluator = RuntimeOutcomeEvaluator()
        self.runtime_repair_service = RuntimeRepairService()
        self.user_goal_evaluator = UserGoalEvaluator(keyword_analyzer=keyword_signal_analyzer)
        
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

    def _autonomous_implementation_capability(self) -> dict[str, Any]:
        capability = self.capability_router._capabilities.get("autonomous_implementation", {})
        return capability if isinstance(capability, dict) else {}

    def _build_autonomous_trace(
        self,
        *,
        capability_gap_detected: bool,
        trigger_reason: str | None = None,
        generated_artifact: str | None = None,
        runtime_repair_triggered: bool = False,
        runtime_repair_reason: str | None = None,
    ) -> dict[str, Any]:
        capability = self._autonomous_implementation_capability()
        enabled = bool(capability.get("enabled", False))
        triggered = bool(capability_gap_detected and enabled and generated_artifact)
        return {
            "capability_gap_detected": capability_gap_detected,
            "autonomous_implementation_supported": enabled,
            "autonomous_implementation_triggered": triggered,
            "generated_patch_registered": bool(generated_artifact),
            "generated_artifact_type": generated_artifact,
            "trigger_reason": trigger_reason,
            "runtime_repair_triggered": runtime_repair_triggered,
            "runtime_repair_reason": runtime_repair_reason,
            "supports": capability.get("supports", []),
        }

    def _persist_runtime_trace(
        self,
        *,
        trace_id: str,
        status: str,
        input_text: str,
        task: dict[str, Any] | None = None,
        execution_result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> str:
        trace_path = self.generated_artifact_store.persist(
            "trace",
            trace_id,
            {
                "trace_id": trace_id,
                "status": status,
                "input_text": input_text,
                "task": task or {},
                "execution_result": execution_result or {},
                "error": error,
            },
        )
        return str(trace_path)

    def _max_runtime_repair_iterations(self) -> int:
        capability = self._autonomous_implementation_capability()
        return int(capability.get("max_runtime_repair_iterations", 2) or 2)

    def _should_apply_goal_repair(self, task: Any) -> bool:
        return task.domain not in {"agent_management", "knowledge_ops"}


    def reload_plugins(self) -> dict[str, Any]:
        """Reload plugin-enabled services from config without restarting process."""
        keyword_signal_analyzer = RuntimeKeywordSignalAnalyzer(model_router=self.model_router)
        self.intent_analyzer = IntentAnalyzer(keyword_analyzer=keyword_signal_analyzer)
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.capability_router = CapabilityRouter()
        self.user_goal_evaluator = UserGoalEvaluator(keyword_analyzer=keyword_signal_analyzer)
        return {
            "status": "reloaded",
            "intent_analyzer_plugins": len(self.intent_analyzer.plugins),
            "task_decomposer_plugins": len(self.task_decomposer.plugins),
            "workflow_planner_plugins": len(self.workflow_planner.plugins),
        }

    def inspect_semantic_memory(self, *, policy_key: str | None = None, status: str | None = None) -> dict[str, Any]:
        return self.execution_coordinator.semantic_policy_store.inspect_memory(policy_key=policy_key, status=status)

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
        workflow_payload = None
        blueprints_payload: list[dict[str, Any]] = []
        agent_payload = None
        execution_plan: list[dict[str, Any]] = []
        autonomous_trace = self._build_autonomous_trace(capability_gap_detected=False)
        
        try:
            # ========== Step 1: 意图分析 ==========
            task = await self.intent_analyzer.analyze(input_text, ctx)
            self.logger.info(f"  Intent: {task.intent}, Domain: {task.domain}")

            # ========== Step 2: 统一生成工作流与节点能力计划 ==========
            subtasks = await self.task_decomposer.decompose(task)
            workflow = await self.workflow_planner.plan(task, subtasks)
            workflow_payload = workflow

            blueprints = self.blueprint_resolver.resolve(task, workflow)
            if not blueprints:
                autonomous_trace = self._build_autonomous_trace(
                    capability_gap_detected=True,
                    trigger_reason="no_reusable_blueprint_resolved",
                    generated_artifact="blueprint",
                )
                blueprints = [self.blueprint_generator.generate(task, workflow)]
                for blueprint in blueprints:
                    generated_path = self.generated_artifact_store.persist(
                        "blueprint",
                        blueprint.blueprint_id,
                        {
                            **blueprint.model_dump(),
                            "source": "runtime_blueprint_generation",
                            "task": task.model_dump(),
                            "workflow": workflow.model_dump(),
                            "context": {"trace_id": ctx.trace_id, "session_id": ctx.session_id},
                        },
                    )
                    blueprint.metadata["generated_artifact_path"] = str(generated_path)
            else:
                autonomous_trace = self._build_autonomous_trace(capability_gap_detected=False)
            blueprints_payload = [item.model_dump() for item in blueprints]

            for blueprint in blueprints:
                self.blueprint_registry.register(blueprint.name, blueprint)

            execution_plan = self.capability_router.route_workflow(task, workflow)
            self.security_guard.validate_plan(execution_plan)
            for step in execution_plan:
                model_choice = (step.get("capability") or {}).get("model_choice", {})
                provider = model_choice.get("provider", "unknown")
                model = model_choice.get("model", "unknown")
                self.model_registry.register(f"{provider}:{model}", model_choice)
            
            # ========== Step 3: 决策 - Agent 还是 Workflow? ==========
            need_agent = task.constraints.get("need_agent", False)
            
            if need_agent and use_langraph:
                # ========== Path A: 使用 Agent（推理型） ==========
                self.logger.info("📌 Using Agent (reasoning loop)")
                
                # 生成 Agent 规范
                agent_spec = await self.agent_builder.generate_agent_spec(
                    task=task.model_dump(),
                    workflow=workflow.model_dump()
                )
                
                # 构建 Agent
                agent = await self.agent_builder.build_agent(agent_spec)
                generated_agent_path = self.generated_artifact_store.persist(
                    "agent",
                    agent_spec.agent_id,
                    {
                        **agent_spec.__dict__,
                        "source": "runtime_agent_generation",
                        "task": task.model_dump(),
                        "context": {"trace_id": ctx.trace_id, "session_id": ctx.session_id},
                    },
                )
                
                # 运行 Agent 推理循环
                agent_result = await agent.think_and_act(input_text, ctx.model_dump())
                
                # 注册 Agent
                self.agent_registry.register(agent_spec.name, agent_spec)
                agent_payload = {
                    "agent_id": agent_spec.agent_id,
                    "name": agent_spec.name,
                    "role": agent_spec.role,
                    "description": agent_spec.description,
                    "generated_artifact_path": str(generated_agent_path),
                }
                
                execution_result = {
                    "execution_type": "agent",
                    "execution_plan": execution_plan,
                    "agent_result": agent_result,
                    "autonomous_implementation_trace": autonomous_trace,
                }
                
            else:
                # ========== Path B: 使用 Workflow（任务编排） ==========
                self.logger.info("📌 Using Workflow (task orchestration)")
                execution_result = self.execution_coordinator.execute(execution_plan, task, ctx)
                execution_result["execution_type"] = "workflow"
                execution_result["execution_plan"] = execution_plan
                execution_result["autonomous_implementation_trace"] = autonomous_trace
                outcome_evaluation = self.runtime_outcome_evaluator.evaluate(
                    task=task,
                    workflow=workflow,
                    execution_result=execution_result,
                )
                goal_evaluation = self.user_goal_evaluator.evaluate(
                    task=task,
                    execution_result=execution_result,
                )
                if self._should_apply_goal_repair(task) and not goal_evaluation.get("satisfied", False):
                    outcome_evaluation["should_repair"] = True
                    unmet_requirements = list(outcome_evaluation.get("unmet_requirements", []))
                    if "goal_alignment" not in unmet_requirements:
                        unmet_requirements.append("goal_alignment")
                    outcome_evaluation["unmet_requirements"] = unmet_requirements
                execution_result["outcome_evaluation"] = outcome_evaluation
                execution_result["goal_evaluation"] = goal_evaluation
                repair_history: list[dict[str, Any]] = []
                current_workflow = workflow
                max_iterations = self._max_runtime_repair_iterations()
                repair_iteration = 0
                while outcome_evaluation.get("should_repair") and repair_iteration < max_iterations:
                    repair_classification = self.runtime_failure_classifier.classify(
                        workflow=current_workflow,
                        evaluation=outcome_evaluation,
                        dependency_status=dependency_status if isinstance(dependency_status, dict) else {},
                        execution_result=execution_result,
                    )
                    repaired_workflow = self.runtime_repair_service.build_repair_workflow(
                        task=task,
                        workflow=current_workflow,
                        repair_classification=repair_classification,
                    )
                    repaired_plan = self.capability_router.route_workflow(task, repaired_workflow)
                    self.security_guard.validate_plan(repaired_plan)
                    repaired_execution_result = self.execution_coordinator.execute(repaired_plan, task, ctx)
                    repair_iteration += 1
                    repaired_execution_result["execution_type"] = "workflow"
                    repaired_execution_result["execution_plan"] = repaired_plan
                    repaired_execution_result["repair_iteration"] = repair_iteration
                    repaired_execution_result["repair_source_evaluation"] = outcome_evaluation
                    repaired_execution_result["repair_classification"] = repair_classification
                    repaired_execution_result["autonomous_implementation_trace"] = self._build_autonomous_trace(
                        capability_gap_detected=autonomous_trace.get("capability_gap_detected", False),
                        trigger_reason=autonomous_trace.get("trigger_reason"),
                        generated_artifact=autonomous_trace.get("generated_artifact_type"),
                        runtime_repair_triggered=True,
                        runtime_repair_reason="unmet_requirements_or_failed_steps",
                    )
                    outcome_evaluation = self.runtime_outcome_evaluator.evaluate(
                        task=task,
                        workflow=repaired_workflow,
                        execution_result=repaired_execution_result,
                    )
                    goal_evaluation = self.user_goal_evaluator.evaluate(
                        task=task,
                        execution_result=repaired_execution_result,
                    )
                    if self._should_apply_goal_repair(task) and not goal_evaluation.get("satisfied", False):
                        outcome_evaluation["should_repair"] = True
                        unmet_requirements = list(outcome_evaluation.get("unmet_requirements", []))
                        if "goal_alignment" not in unmet_requirements:
                            unmet_requirements.append("goal_alignment")
                        outcome_evaluation["unmet_requirements"] = unmet_requirements
                    repaired_execution_result["outcome_evaluation"] = outcome_evaluation
                    repaired_execution_result["goal_evaluation"] = goal_evaluation
                    repair_history.append(
                        {
                            "iteration": repair_iteration,
                            "repair_classification": repair_classification,
                            "outcome_evaluation": outcome_evaluation,
                            "workflow_id": repaired_workflow.workflow_id,
                        }
                    )
                    execution_result = repaired_execution_result
                    current_workflow = repaired_workflow
                    workflow_payload = repaired_workflow

                execution_result["repair_history"] = repair_history
                execution_result["repair_stop_reason"] = (
                    "requirements_satisfied" if not outcome_evaluation.get("should_repair") else "max_iterations_reached"
                )
                configured_agent_output = execution_result.get("final_output", {}).get("manage_information_agent", {}).get("agent")
                if configured_agent_output:
                    agent_payload = {
                        "agent_id": configured_agent_output.get("agent_id", "information_agent"),
                        "name": configured_agent_output.get("name", "information_agent"),
                        "role": configured_agent_output.get("role", "信息管理智能体"),
                        "description": configured_agent_output.get("description", configured_agent_output.get("role", "信息管理智能体")),
                        "status": configured_agent_output.get("status", "active"),
                    }
            
            # ========== Step 3: 结果整合 ==========
            vector_backend = self.vector_store.active_store()
            
            final_result = self.result_integrator.build_response(
                task=task,
                workflow=workflow_payload,
                blueprints=blueprints_payload,
                agent=agent_payload,
                execution_result={
                    **execution_result,
                    "vector_store": vector_backend,
                    "dependency_status": dependency_status
                },
                context=ctx,
                fmt=fmt,
            )

            trace_artifact_path = self._persist_runtime_trace(
                trace_id=ctx.trace_id,
                status="completed",
                input_text=input_text,
                task=task.model_dump(),
                execution_result=final_result.get("execution_result", {}),
            )
            if isinstance(final_result, dict):
                final_result.setdefault("execution_result", {})["generated_trace_path"] = trace_artifact_path
                final_result.setdefault("artifacts", []).append(
                    {
                        "artifact_type": "trace",
                        "artifact_id": ctx.trace_id,
                        "path": trace_artifact_path,
                        "name": Path(trace_artifact_path).name,
                        "source": "runtime_execution_trace",
                        "metadata": {
                            "execution_type": final_result.get("execution_result", {}).get("execution_type", ""),
                        },
                    }
                )
                final_result["artifact_index"] = self.result_integrator.build_artifact_index(
                    final_result.get("artifacts", [])
                )
            
            self.logger.info(f"✅ Request completed trace={ctx.trace_id}")
            
            return final_result
            
        except Exception as exc:
            self._persist_runtime_trace(
                trace_id=ctx.trace_id,
                status="failed",
                input_text=input_text,
                error=str(exc),
            )
            self.logger.error(f"❌ Core handle failed trace={ctx.trace_id} error={exc}")
            raise

