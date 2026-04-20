from __future__ import annotations

from typing import Any, AsyncGenerator
from pathlib import Path

from nethub_runtime.core.config.settings import (
    AGENT_REGISTRY_PATH,
    BLUEPRINT_REGISTRY_PATH,
    MODEL_REGISTRY_PATH,
    load_local_env,
)
from nethub_runtime.core.memory.vector_store import VectorStore, SQLiteVectorPersistence
from nethub_runtime.core.memory.runtime_learning_store import RuntimeLearningStore
from nethub_runtime.core.memory.session_persistence import SQLiteSessionPersistence
from nethub_runtime.core.services.agent_designer import AgentDesigner
from nethub_runtime.core.services.blueprint_generator import BlueprintGenerator
from nethub_runtime.core.services.blueprint_resolver import BlueprintResolver
from nethub_runtime.core.services.capability_router import CapabilityRouter
from nethub_runtime.core.services.context_manager import ContextManager
from nethub_runtime.core.services.dependency_manager import DependencyManager
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator
from nethub_runtime.core.services.intent_analyzer import IntentAnalyzer
from nethub_runtime.core.services.registry import JsonRegistry, Registry
from nethub_runtime.core.services.result_integrator import ResultIntegrator
from nethub_runtime.core.services.runtime_failure_classifier import RuntimeFailureClassifier
from nethub_runtime.core.services.runtime_outcome_evaluator import RuntimeOutcomeEvaluator
from nethub_runtime.core.services.runtime_repair_service import RuntimeRepairService
from nethub_runtime.core.services.security_guard import SecurityGuard
from nethub_runtime.core.services.capability_acquisition_service import CapabilityAcquisitionService
from nethub_runtime.core.services.runtime_design_synthesizer import RuntimeDesignSynthesizer
from nethub_runtime.core.services.task_decomposer import TaskDecomposer
from nethub_runtime.core.services.workflow_planner import WorkflowPlanner
from nethub_runtime.core.utils.logger import get_logger
from nethub_runtime.models.model_router import ModelRouter
from nethub_runtime.core.workflows.executor import WorkflowExecutor
from nethub_runtime.core.workflows.base_workflow import SimpleWorkflow
from nethub_runtime.core.agents.agent_builder import AgentBuilder
from nethub_runtime.core.tools.registry import ToolRegistry
from nethub_runtime.core.tools.registry import load_skills_from_dirs as _load_skills_from_dirs
from nethub_runtime.core.services.user_goal_evaluator import UserGoalEvaluator
from nethub_runtime.core.services.runtime_keyword_signal_analyzer import RuntimeKeywordSignalAnalyzer
from nethub_runtime.generated.store import GeneratedArtifactStore
from nethub_runtime.core.hooks.registry import get_hook_registry
from nethub_runtime.core.services.bootstrap_loader import BootstrapLoader
from nethub_runtime.core.memory.session_store import SessionCompactor
from nethub_runtime.core.services.session_queue import SessionQueueManager
from nethub_runtime.core.services.memory_promotion_service import MemoryPromotionService
from nethub_runtime.core.services.training_dataset_export_service import TrainingDatasetExportService
from nethub_runtime.core.services.training_fine_tune_runner_service import TrainingFineTuneRunnerService
from nethub_runtime.core.services.training_pipeline_service import TrainingPipelineService


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

        # ========== Task 3: Vector embedding (sentence-transformers, opt-in) ==========
        _embedding_fn = None
        try:
            import importlib.util as _ilu
            if _ilu.find_spec("sentence_transformers") is not None:
                from sentence_transformers import SentenceTransformer  # type: ignore
                _st_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                _embedding_fn = lambda text: _st_model.encode(text, convert_to_numpy=True).tolist()
                self.logger.info("✓ VectorStore: sentence-transformers embeddings enabled")
        except Exception as _e:
            self.logger.debug("sentence-transformers not available, using keyword search: %s", _e)

        self.vector_store = VectorStore(embedding_fn=_embedding_fn)
        # ========== Task 3: VectorStore SQLite persistence (opt-in via policy) ==========
        # Applied after load_runtime_policy is available (post execution_coordinator init).
        # We defer this wiring below so we can read the policy first.
        self.dependency_manager = DependencyManager()
        self.security_guard = SecurityGuard()
        
        # ========== 注册表管理 ==========
        self.static_model_registry = JsonRegistry(MODEL_REGISTRY_PATH)
        self.static_blueprint_registry = JsonRegistry(BLUEPRINT_REGISTRY_PATH)
        self.static_agent_registry = JsonRegistry(AGENT_REGISTRY_PATH)
        self.model_registry = Registry()
        self.blueprint_registry = Registry()
        self.agent_registry = Registry()
        self.generated_artifact_store = GeneratedArtifactStore()
        self.runtime_design_synthesizer = RuntimeDesignSynthesizer()
        self.training_dataset_export_service = TrainingDatasetExportService(
            generated_artifact_store=self.generated_artifact_store,
        )
        self.training_pipeline_service = TrainingPipelineService(
            generated_artifact_store=self.generated_artifact_store,
        )
        
        # ========== 传统插件-based 服务 ==========
        self.intent_analyzer = IntentAnalyzer(vector_store=self.vector_store)
        self.task_decomposer = TaskDecomposer()
        self.workflow_planner = WorkflowPlanner()
        self.blueprint_resolver = BlueprintResolver(registry=Registry())
        self.blueprint_generator = BlueprintGenerator(registry=self.blueprint_registry, synthesizer=self.runtime_design_synthesizer)
        self.agent_designer = AgentDesigner()
        self.capability_router = CapabilityRouter()

        # ========== 新增：LiteLLM 模型路由 ==========
        # 参考: docs/02_router/litellm_routing_design.md
        try:
            if model_config_path is None:
                # 尝试使用默认配置
                model_config_path = Path("nethub_runtime/config/model_config.yaml")
            
            self.model_router = ModelRouter(str(model_config_path))
            self.runtime_design_synthesizer = RuntimeDesignSynthesizer(model_router=self.model_router)
            self.blueprint_generator.synthesizer = self.runtime_design_synthesizer
            self.logger.info("✓ LiteLLM Model Router initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize ModelRouter: {e}, will use plugins only")
            self.model_router = None

        keyword_signal_analyzer = RuntimeKeywordSignalAnalyzer(model_router=self.model_router)
        self.intent_analyzer = IntentAnalyzer(keyword_analyzer=keyword_signal_analyzer, vector_store=self.vector_store)

        self.execution_coordinator = ExecutionCoordinator(
            session_store=self.context_manager.session_store,
            vector_store=self.vector_store,
            generated_artifact_store=self.generated_artifact_store,
            model_router=self.model_router,
        )
        training_semantic_policy_store = getattr(self.execution_coordinator, "semantic_policy_store", None)
        self.training_fine_tune_runner_service = TrainingFineTuneRunnerService(
            generated_artifact_store=self.generated_artifact_store,
            training_pipeline_service=self.training_pipeline_service,
            semantic_policy_store=training_semantic_policy_store,
        )
        self.result_integrator = ResultIntegrator()
        self.runtime_failure_classifier = RuntimeFailureClassifier()
        self.runtime_outcome_evaluator = RuntimeOutcomeEvaluator()
        self.runtime_repair_service = RuntimeRepairService()
        self.user_goal_evaluator = UserGoalEvaluator(keyword_analyzer=keyword_signal_analyzer)
        self.memory_promotion_service = MemoryPromotionService(
            semantic_policy_store=self.execution_coordinator.semantic_policy_store,
            vector_store=self.vector_store,
            generated_artifact_store=self.generated_artifact_store,
        )

        # ========== 自我意识：能力获取 + 运行时学习 ==========
        self.runtime_learning_store = RuntimeLearningStore(
            semantic_policy_store=self.execution_coordinator.semantic_policy_store
        )
        self.capability_acquisition_service = CapabilityAcquisitionService(
            security_guard=self.security_guard,
            learning_store=self.runtime_learning_store,
        )
        self.logger.info("✓ Capability Acquisition + Runtime Learning initialized")

        # ========== Hook Registry (pre/post step interception) ==========
        self.hook_registry = get_hook_registry()
        self.execution_coordinator.hook_registry = self.hook_registry
        self.logger.info("✓ Hook Registry wired into ExecutionCoordinator")

        # ========== Bootstrap Loader (AGENTS.md / SOUL.md injection) ==========
        _bootstrap_cfg = self.execution_coordinator.semantic_policy_store.load_runtime_policy().get(
            "runtime_behavior", {}
        ).get("bootstrap", {})
        self.bootstrap_loader = BootstrapLoader.from_policy(_bootstrap_cfg)
        self.logger.info("✓ Bootstrap Loader initialized (workspace=%s)", self.bootstrap_loader.workspace_path)

        # ========== Session Compaction ==========
        _compaction_cfg = self.execution_coordinator.semantic_policy_store.load_runtime_policy().get(
            "runtime_behavior", {}
        ).get("session", {}).get("compaction", {})
        if _compaction_cfg.get("enabled", True):
            _compactor = SessionCompactor(
                max_records=int(_compaction_cfg.get("max_records", 50)),
                compact_to=int(_compaction_cfg.get("compact_to_records", 5)),
            )
            self.context_manager.session_store._compactor = _compactor
            self.logger.info(
                "✓ Session Compactor enabled (max_records=%d compact_to=%d)",
                _compactor.max_records, _compactor.compact_to,
            )

        # ========== Task 1: Context window limiting (10–20 messages per spec) ==========
        _session_cfg = self.execution_coordinator.semantic_policy_store.load_runtime_policy().get(
            "runtime_behavior", {}
        ).get("session", {})
        _window_cfg = _session_cfg.get("context_window", {})
        _max_messages = int(_window_cfg.get("max_messages", 20))
        self.context_manager.session_store._max_window = _max_messages
        self.logger.info("✓ Session context window: max_messages=%d", _max_messages)

        # ========== Task 3: Session persistence (SQLite, opt-in via policy) ==========
        _persist_cfg = _session_cfg.get("persistence", {})
        if _persist_cfg.get("enabled", False):
            try:
                import os as _os
                _db_raw = _persist_cfg.get("sqlite_path", "~/.nesthub/sessions.db")
                _db_path = _os.path.expandvars(_os.path.expanduser(_db_raw))
                _persistence = SQLiteSessionPersistence(_db_path)
                self.context_manager.session_store._persistence = _persistence
                self.logger.info("✓ Session persistence: SQLite at %s", _db_path)
            except Exception as _pe:
                self.logger.warning("Session persistence init failed: %s", _pe)

        # ========== Task 3: VectorStore SQLite persistence (domain memory) ==========
        if _persist_cfg.get("enabled", False):
            try:
                import os as _os
                _vs_db_raw = _persist_cfg.get("vector_sqlite_path", "~/.nesthub/vector_store.db")
                _vs_db_path = _os.path.expandvars(_os.path.expanduser(_vs_db_raw))
                _vs_persistence = SQLiteVectorPersistence(_vs_db_path)
                # Re-create VectorStore with persistence (loads previously stored items)
                _prev_embedding_fn = self.vector_store._embedding_fn
                self.vector_store = VectorStore(
                    embedding_fn=_prev_embedding_fn,
                    persistence=_vs_persistence,
                )
                # Propagate to ExecutionCoordinator
                self.execution_coordinator.vector_store = self.vector_store
                self.execution_coordinator.information_agent_service.vector_store = self.vector_store
                self.memory_promotion_service.vector_store = self.vector_store
                for plugin in self.intent_analyzer.plugins:
                    if hasattr(plugin, "vector_store"):
                        plugin.vector_store = self.vector_store
                self.logger.info("✓ VectorStore persistence: SQLite at %s (%d items restored)",
                                 _vs_db_path, len(self.vector_store._items))
            except Exception as _vpe:
                self.logger.warning("VectorStore persistence init failed: %s", _vpe)

        # ========== Session Queue (concurrency control) ==========
        _queue_cfg = self.execution_coordinator.semantic_policy_store.load_runtime_policy().get(
            "runtime_behavior", {}
        ).get("session", {}).get("queue", {})
        self.session_queue = SessionQueueManager.from_policy(_queue_cfg)
        self.logger.info("✓ Session Queue initialized (mode=%s)", self.session_queue.mode)

        # ========== Skill Directory Loading (tiered precedence) ==========
        _skill_dirs = self.execution_coordinator.semantic_policy_store.load_runtime_policy().get(
            "runtime_behavior", {}
        ).get("skill_dirs", [])
        if _skill_dirs:
            _workspace = str(self.bootstrap_loader.workspace_path)
            _n = _load_skills_from_dirs(_skill_dirs, workspace_path=_workspace)
            self.logger.info("✓ Skill dirs scanned: %d skill(s) loaded", _n)
        
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
        # Prefer runtime_behavior config; fall back to capability setting.
        runtime_behavior = self.execution_coordinator.semantic_policy_store.load_runtime_policy().get(
            "runtime_behavior", {}
        )
        policy_max = runtime_behavior.get("max_repair_iterations")
        if policy_max is not None:
            return int(policy_max)
        capability = self._autonomous_implementation_capability()
        return int(capability.get("max_runtime_repair_iterations", 2) or 2)

    def _should_apply_goal_repair(self, task: Any) -> bool:
        return task.domain not in {"agent_management", "knowledge_ops"}

    def _build_repair_preferences(self, repair_history: list[dict[str, Any]]) -> dict[str, Any]:
        preferences = {
            "analysis_before_retry": False,
            "prefer_tool_prepare": False,
            "prefer_patch_pipeline": False,
            "prefer_artifact_pipeline": False,
            "guided_repair": False,
        }
        for item in repair_history:
            classification = item.get("repair_classification") or {}
            guidance = classification.get("runtime_learning_guidance") or {}
            guidance_preferences = guidance.get("repair_preferences") if isinstance(guidance, dict) else {}
            if isinstance(guidance_preferences, dict):
                preferences["analysis_before_retry"] = preferences["analysis_before_retry"] or bool(guidance_preferences.get("analysis_before_retry"))
                preferences["prefer_tool_prepare"] = preferences["prefer_tool_prepare"] or bool(guidance_preferences.get("prefer_tool_prepare"))
                preferences["prefer_patch_pipeline"] = preferences["prefer_patch_pipeline"] or bool(guidance_preferences.get("prefer_patch_pipeline"))
                preferences["prefer_artifact_pipeline"] = preferences["prefer_artifact_pipeline"] or bool(guidance_preferences.get("prefer_artifact_pipeline"))
                preferences["guided_repair"] = preferences["guided_repair"] or any(bool(value) for value in guidance_preferences.values())

            workflow_guidance = classification.get("runtime_learning_guidance_signals") or {}
            if isinstance(workflow_guidance, dict):
                preferences["analysis_before_retry"] = preferences["analysis_before_retry"] or bool(workflow_guidance.get("prefer_analysis_before_retry"))
                preferences["prefer_tool_prepare"] = preferences["prefer_tool_prepare"] or bool(workflow_guidance.get("prefer_tool_prepare"))
                preferences["prefer_patch_pipeline"] = preferences["prefer_patch_pipeline"] or bool(workflow_guidance.get("prefer_patch_pipeline"))
                preferences["prefer_artifact_pipeline"] = preferences["prefer_artifact_pipeline"] or bool(workflow_guidance.get("prefer_artifact_pipeline"))
                preferences["guided_repair"] = preferences["guided_repair"] or any(bool(value) for value in workflow_guidance.values())
        return preferences


    def reload_plugins(self) -> dict[str, Any]:
        """Reload plugin-enabled services from config without restarting process."""
        keyword_signal_analyzer = RuntimeKeywordSignalAnalyzer(model_router=self.model_router)
        self.intent_analyzer = IntentAnalyzer(keyword_analyzer=keyword_signal_analyzer, vector_store=self.vector_store)
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

    def inspect_runtime_memory(
        self,
        *,
        query: str | None = None,
        namespace: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        artifacts = self.generated_artifact_store.list_artifacts().get("code", [])
        memory_promotion_artifacts = [
            item for item in artifacts if str(item.get("artifactId") or "").startswith("memory_promotion_")
        ]
        vector_namespaces = [
            "document_analysis",
            "information_agent",
            "information_agent_fact",
        ]
        namespaces = [namespace] if namespace else vector_namespaces
        vector_hits: list[dict[str, Any]] = []
        if query:
            for current_namespace in namespaces:
                for item in self.vector_store.search(query, top_k=top_k, namespace=current_namespace):
                    vector_hits.append(
                        {
                            "id": item.get("id"),
                            "namespace": item.get("namespace"),
                            "content": item.get("content"),
                            "metadata": item.get("metadata") or {},
                        }
                    )
        if not vector_hits:
            recent_items = list(getattr(self.vector_store, "_items", []))
            for current_namespace in namespaces:
                namespace_items = [
                    item for item in recent_items if str(item.get("namespace") or "") == current_namespace
                ]
                for item in namespace_items[-top_k:]:
                    vector_hits.append(
                        {
                            "id": item.get("id"),
                            "namespace": item.get("namespace"),
                            "content": item.get("content"),
                            "metadata": item.get("metadata") or {},
                        }
                    )

        semantic_snapshot = self.execution_coordinator.semantic_policy_store.inspect_memory()
        return {
            "query": query or "",
            "namespace": namespace or "*",
            "promotion_artifacts": memory_promotion_artifacts[-10:],
            "vector_hits": vector_hits,
            "vector_namespaces": namespaces,
            "semantic_memory_summary": semantic_snapshot.get("summary") or {},
            "semantic_memory_latest_rollback": semantic_snapshot.get("latest_rollback"),
        }

    def inspect_private_brain_summary(self) -> dict[str, Any]:
        semantic_snapshot = self.execution_coordinator.semantic_policy_store.inspect_memory()
        generated = self.generated_artifact_store.list_artifacts()
        training_summary = self.runtime_learning_store.get_learning_summary()
        vector_items = list(getattr(self.vector_store, "_items", []))
        namespace_counts: dict[str, int] = {}
        for item in vector_items:
            namespace = str(item.get("namespace") or "unknown")
            namespace_counts[namespace] = namespace_counts.get(namespace, 0) + 1
        information_agent_count = namespace_counts.get("information_agent_fact", 0)
        return {
            "layers": {
                "work_memory": {
                    "session_store_backend": type(self.context_manager.session_store).__name__,
                },
                "procedural_memory": semantic_snapshot.get("summary") or {},
                "structured_fact_memory": {
                    "vector_item_count": len(vector_items),
                    "vector_namespace_counts": namespace_counts,
                    "information_agent_fact_count": information_agent_count,
                },
                "runtime_learning": training_summary,
                "training_assets": {
                    "sft_samples": len(generated.get("dataset_sft", [])),
                    "preference_samples": len(generated.get("dataset_preference", [])),
                    "training_manifests": len(generated.get("dataset_manifest", [])),
                    "training_runs": len(generated.get("dataset_run", [])),
                    "repair_preference_counts": training_summary.get("repair_preference_counts") or {},
                },
            },
            "artifacts": {
                "memory_promotions": len([item for item in generated.get("code", []) if str(item.get("artifactId") or "").startswith("memory_promotion_")]),
                "dataset_sft": generated.get("dataset_sft", []),
                "dataset_preference": generated.get("dataset_preference", []),
                "dataset_manifest": generated.get("dataset_manifest", []),
                "dataset_run": generated.get("dataset_run", []),
            },
        }

    def build_training_manifest(self, *, profile: str = "lora_sft") -> dict[str, Any]:
        return self.training_pipeline_service.build_training_manifest(profile=profile)

    def inspect_training_runner(self, *, profile: str = "lora_sft", backend: str = "mock") -> dict[str, Any]:
        return self.training_fine_tune_runner_service.inspect_runner(profile=profile, backend=backend)

    def start_training_run(
        self,
        *,
        profile: str = "lora_sft",
        backend: str = "mock",
        dry_run: bool = True,
        note: str | None = None,
    ) -> dict[str, Any]:
        return self.training_fine_tune_runner_service.start_run(
            profile=profile,
            backend=backend,
            dry_run=dry_run,
            note=note,
        )

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
        self.static_model_registry.hot_reload()
        self.static_blueprint_registry.hot_reload()
        self.static_agent_registry.hot_reload()
        dependency_status = self.dependency_manager.check()

        ctx = self.context_manager.load(context)
        ctx = self.context_manager.enrich(ctx)
        self.logger.info(f"🔄 Handling request trace={ctx.trace_id} session={ctx.session_id}")
        workflow_payload = None
        blueprints_payload: list[dict[str, Any]] = []
        agent_payload = None
        execution_plan: list[dict[str, Any]] = []
        autonomous_trace = self._build_autonomous_trace(capability_gap_detected=False)

        # Inject bootstrap context into metadata (picked up by model service layers).
        bootstrap_context = self.bootstrap_loader.load()
        if bootstrap_context:
            ctx.metadata["bootstrap_context"] = bootstrap_context

        async with self.session_queue.run_slot(ctx.session_id, input_text) as _slot:
            self.logger.debug(
                "Session slot acquired (mode=%s queued=%d)",
                _slot.mode, len(_slot.queued_inputs),
            )
        
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
                execution_guidance = None
                if outcome_evaluation.get("should_repair"):
                    execution_guidance = self.runtime_learning_store.lookup_execution_guidance(
                        task_type=task.intent,
                        intent=task.intent,
                    )
                    if execution_guidance:
                        execution_result["runtime_learning_guidance"] = execution_guidance
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
                    if execution_guidance:
                        repair_classification["runtime_learning_guidance"] = execution_guidance
                        repair_classification["preferred_repair_iterations"] = int(execution_guidance.get("repair_iterations") or 0)
                        repair_classification["preferred_solution_summary"] = str(execution_guidance.get("solution_summary") or "")

                    # ---- Self-aware capability acquisition ----
                    # When the classifier detects missing tools/models, delegate to
                    # CapabilityAcquisitionService to autonomously acquire them before
                    # retrying.  The acquisition result is recorded to the learning
                    # store regardless of outcome so future runs benefit from it.
                    missing_tools = repair_classification.get("missing_tools") or []
                    if missing_tools:
                        for missing_tool in missing_tools:
                            acq_result = self.capability_acquisition_service.acquire(
                                task_type=task.intent,
                                gap=missing_tool,
                                context={"trace_id": ctx.trace_id, "session_id": ctx.session_id},
                            )
                            self.logger.info(
                                "capability_acquisition %s/%s: success=%s strategy=%s",
                                task.intent, missing_tool,
                                acq_result.success, acq_result.strategy,
                            )

                    repaired_workflow = self.runtime_repair_service.build_repair_workflow(
                        task=task,
                        workflow=current_workflow,
                        repair_classification=repair_classification,
                        enable_autonomous_patch_pipeline=bool(self._autonomous_implementation_capability().get("enabled", False)),
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
                            "runtime_learning_guidance": execution_guidance,
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
                repair_preferences = self._build_repair_preferences(repair_history)
                execution_result["repair_preferences"] = repair_preferences

                # ---- Record execution outcome to learning store ----
                final_outcome = "success" if not outcome_evaluation.get("should_repair") else "partial"
                self.runtime_learning_store.record_execution_outcome(
                    task_type=task.intent,
                    intent=task.intent,
                    input_summary=input_text[:200],
                    outcome=final_outcome,
                    repair_iterations=repair_iteration,
                    unmet_requirements=list(outcome_evaluation.get("unmet_requirements") or []),
                    solution_summary=execution_result.get("repair_stop_reason", ""),
                    repair_preferences=repair_preferences,
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

            if isinstance(final_result, dict):
                promotion_summary = self.memory_promotion_service.promote_execution_result(
                    task=final_result.get("task") or task.model_dump(),
                    context={
                        "trace_id": ctx.trace_id,
                        "session_id": ctx.session_id,
                        "metadata": ctx.metadata,
                    },
                    execution_result=final_result.get("execution_result") or {},
                )
                final_result.setdefault("execution_result", {})["memory_promotion"] = promotion_summary
                dataset_export_summary = self.training_dataset_export_service.export_execution_result(
                    task=final_result.get("task") or task.model_dump(),
                    context={
                        "trace_id": ctx.trace_id,
                        "session_id": ctx.session_id,
                        "metadata": ctx.metadata,
                    },
                    execution_result=final_result.get("execution_result") or {},
                )
                final_result.setdefault("execution_result", {})["training_dataset_export"] = dataset_export_summary

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

    async def handle_stream(
        self,
        input_text: str,
        context: dict[str, Any] | None = None,
        fmt: str = "dict",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Async generator variant of handle() that yields StreamEvent dicts.

        Inspired by claude-agent-sdk-python's ``query()`` async-iterator pattern —
        callers can react to each pipeline stage before the full result is ready.

        Event shapes::

            {"event": "lifecycle_start",   "run_id": str, "session_id": str}
            {"event": "intent_analyzed",   "intent": str, "domain": str, "trace_id": str, "run_id": str}
            {"event": "workflow_planned",  "step_count": int, "steps": [str, ...], "trace_id": str, "run_id": str}
            {"event": "step_completed",    "step_name": str, "status": str,
                                           "executor_type": str, "output": dict | None,
                                           "repair_iteration": int, "run_id": str}
            {"event": "repair_started",    "iteration": int, "reason": str, "run_id": str}
            {"event": "final",             "result": dict, "trace_id": str, "run_id": str}
            {"event": "lifecycle_end",     "run_id": str, "status": "ok"}
            {"event": "lifecycle_error",   "run_id": str, "error": str}

        Usage::

            async for event in core.handle_stream("your input"):
                if event["event"] == "intent_analyzed":
                    print("Intent:", event["intent"])
                elif event["event"] == "step_completed":
                    print("Step done:", event["step_name"], event["status"])
                elif event["event"] == "final":
                    result = event["result"]
        """
        self.security_guard.validate_output_format(fmt)
        self.static_model_registry.hot_reload()
        self.static_blueprint_registry.hot_reload()
        self.static_agent_registry.hot_reload()
        dependency_status = self.dependency_manager.check()

        ctx = self.context_manager.load(context)
        ctx = self.context_manager.enrich(ctx)
        run_id: str = ctx.trace_id

        # Inject bootstrap context into session metadata for first turn.
        bootstrap_context = self.bootstrap_loader.load()
        if bootstrap_context:
            ctx.metadata["bootstrap_context"] = bootstrap_context
            self.logger.debug("Bootstrap context injected (%d chars)", len(bootstrap_context))

        yield {"event": "lifecycle_start", "run_id": run_id, "session_id": ctx.session_id}

        try:
            # --- Stage 1: Intent analysis ---
            task = await self.intent_analyzer.analyze(input_text, ctx)
            yield {
                "event": "intent_analyzed",
                "intent": task.intent,
                "domain": task.domain,
                "trace_id": ctx.trace_id,
                "run_id": run_id,
            }

            # --- Stage 2: Workflow planning ---
            subtasks = await self.task_decomposer.decompose(task)
            workflow = await self.workflow_planner.plan(task, subtasks)
            blueprints = self.blueprint_resolver.resolve(task, workflow)
            if not blueprints:
                blueprints = [self.blueprint_generator.generate(task, workflow)]
            for bp in blueprints:
                self.blueprint_registry.register(bp.name, bp)
            blueprints_payload = [bp.model_dump() for bp in blueprints]
            execution_plan = self.capability_router.route_workflow(task, workflow)
            self.security_guard.validate_plan(execution_plan)
            yield {
                "event": "workflow_planned",
                "step_count": len(workflow.steps),
                "steps": [s.name for s in workflow.steps],
                "trace_id": ctx.trace_id,
                "run_id": run_id,
            }

            # --- Stage 3: Execution ---
            execution_result = self.execution_coordinator.execute(execution_plan, task, ctx)
            execution_result["execution_type"] = "workflow"
            execution_result["execution_plan"] = execution_plan
            for step_result in execution_result.get("steps", []):
                yield {
                    "event": "step_completed",
                    "step_name": step_result["name"],
                    "status": step_result.get("status", "unknown"),
                    "executor_type": step_result.get("executor_type", ""),
                    "output": step_result.get("output"),
                    "repair_iteration": 0,
                    "run_id": run_id,
                }

            # --- Stage 4: Repair loop ---
            outcome_evaluation = self.runtime_outcome_evaluator.evaluate(
                task=task, workflow=workflow, execution_result=execution_result
            )
            goal_evaluation = self.user_goal_evaluator.evaluate(
                task=task, execution_result=execution_result
            )
            if self._should_apply_goal_repair(task) and not goal_evaluation.get("satisfied", False):
                outcome_evaluation["should_repair"] = True
            repair_iteration = 0
            max_iterations = self._max_runtime_repair_iterations()
            current_workflow = workflow
            while outcome_evaluation.get("should_repair") and repair_iteration < max_iterations:
                repair_classification = self.runtime_failure_classifier.classify(
                    workflow=current_workflow,
                    evaluation=outcome_evaluation,
                    dependency_status=dependency_status if isinstance(dependency_status, dict) else {},
                    execution_result=execution_result,
                )
                yield {
                    "event": "repair_started",
                    "iteration": repair_iteration + 1,
                    "reason": repair_classification.get("reason", ""),
                    "run_id": run_id,
                }
                for missing_tool in (repair_classification.get("missing_tools") or []):
                    self.capability_acquisition_service.acquire(
                        task_type=task.intent,
                        gap=missing_tool,
                        context={"trace_id": ctx.trace_id, "session_id": ctx.session_id},
                    )
                repaired_workflow = self.runtime_repair_service.build_repair_workflow(
                    task=task, workflow=current_workflow, repair_classification=repair_classification
                )
                repaired_plan = self.capability_router.route_workflow(task, repaired_workflow)
                self.security_guard.validate_plan(repaired_plan)
                execution_result = self.execution_coordinator.execute(repaired_plan, task, ctx)
                repair_iteration += 1
                execution_result["execution_type"] = "workflow"
                execution_result["repair_iteration"] = repair_iteration
                for step_result in execution_result.get("steps", []):
                    yield {
                        "event": "step_completed",
                        "step_name": step_result["name"],
                        "status": step_result.get("status", "unknown"),
                        "executor_type": step_result.get("executor_type", ""),
                        "output": step_result.get("output"),
                        "repair_iteration": repair_iteration,
                        "run_id": run_id,
                    }
                outcome_evaluation = self.runtime_outcome_evaluator.evaluate(
                    task=task, workflow=repaired_workflow, execution_result=execution_result
                )
                goal_evaluation = self.user_goal_evaluator.evaluate(
                    task=task, execution_result=execution_result
                )
                if self._should_apply_goal_repair(task) and not goal_evaluation.get("satisfied", False):
                    outcome_evaluation["should_repair"] = True
                current_workflow = repaired_workflow

            # --- Stage 5: Final result ---
            final_result = self.result_integrator.build_response(
                task=task,
                workflow=workflow,
                blueprints=blueprints_payload,
                agent=None,
                execution_result={
                    **execution_result,
                    "vector_store": self.vector_store.active_store(),
                    "dependency_status": dependency_status,
                },
                context=ctx,
                fmt=fmt,
            )
            yield {"event": "final", "result": final_result, "trace_id": ctx.trace_id, "run_id": run_id}
            yield {"event": "lifecycle_end", "run_id": run_id, "status": "ok"}

        except Exception as exc:
            self.logger.error("handle_stream error run_id=%s: %s", run_id, exc)
            yield {"event": "lifecycle_error", "run_id": run_id, "error": str(exc)}
