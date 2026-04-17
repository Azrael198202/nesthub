from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import INTENT_POLICY_PATH, PLUGIN_CONFIG_PATH, SEMANTIC_POLICY_PATH, ensure_core_config_dir
from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.intent_policy_manager import IntentPolicyManager
from nethub_runtime.core.services.plugin_loader import load_plugin
from nethub_runtime.core.services.plugin_base import PluginBase
from nethub_runtime.core.services.runtime_keyword_signal_analyzer import RuntimeKeywordSignalAnalyzer
from nethub_runtime.core.utils.id_generator import generate_id


class SemanticIntentPlugin:
    priority = 100

    def __init__(
        self,
        policy_path: Path | None = None,
        policy_manager: IntentPolicyManager | None = None,
        keyword_analyzer: RuntimeKeywordSignalAnalyzer | None = None,
        semantic_policy_store: SemanticPolicyStore | None = None,
    ) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path or INTENT_POLICY_PATH
        self.semantic_policy_store = semantic_policy_store or SemanticPolicyStore(policy_path=SEMANTIC_POLICY_PATH)
        self.policy_manager = policy_manager or IntentPolicyManager(policy_path=self.policy_path)
        self.keyword_analyzer = keyword_analyzer or RuntimeKeywordSignalAnalyzer(semantic_policy_store=self.semantic_policy_store)
        self.policy = self._load_policy()

    def _default_policy(self) -> dict[str, Any]:
        return {
            "query_markers": [],
            "record_markers": [],
            "agent_markers": [],
            "numeric_value_patterns": [r"(\d+(?:\.\d+)?)\s*(日元|円|yen|usd|rmb|元|块|美元|￥|\$)?"],
            "time_markers": [],
            "stopwords": [],
            "group_by_markers": [],
        }

    def _load_policy(self) -> dict[str, Any]:
        if not self.policy_path.exists():
            policy = self._default_policy()
            self.policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")
            return policy
        return json.loads(self.policy_path.read_text(encoding="utf-8"))

    def match(self, _text: str, _context: CoreContextSchema) -> bool:
        return True

    def _contains_any(self, text: str, markers: list[str]) -> bool:
        lowered = text.lower()
        return any(marker.lower() in lowered for marker in markers)

    def _has_numeric_value(self, text: str) -> bool:
        for pattern in self.policy.get("numeric_value_patterns", []):
            if re.search(pattern, text, flags=re.IGNORECASE):
                return True
        return False

    def _infer_multimodal_intent(self, text: str, context: CoreContextSchema) -> tuple[str, str] | None:
        metadata = context.metadata or {}
        input_type = str(metadata.get("input_type", "")).lower()
        lowered = text.lower()

        if input_type in {"image", "screenshot"} or any(k in lowered for k in ("ocr", "识别图片", "图像文字", "票据识别")):
            return ("ocr_task", "multimodal_ops")
        if input_type in {"audio", "voice"} or any(k in lowered for k in ("stt", "语音转文字", "转写")):
            return ("stt_task", "multimodal_ops")
        if any(k in lowered for k in ("tts", "文字转语音", "语音合成")):
            return ("tts_task", "multimodal_ops")
        if any(k in lowered for k in ("生成图片", "图像生成", "海报", "插图")):
            return ("image_generation_task", "multimodal_ops")
        if any(k in lowered for k in ("生成视频", "动画生成", "短视频")):
            return ("video_generation_task", "multimodal_ops")
        if input_type == "file" or any(k in lowered for k in ("生成pdf", "生成word", "生成ppt", "文件生成")):
            return ("file_generation_task", "multimodal_ops")
        if any(k in lowered for k in ("web检索", "网页抓取", "自动查询", "联网查询")):
            return ("web_research_task", "multimodal_ops")
        return None

    def _infer_agent_management_intent(self, text: str, context: CoreContextSchema, keyword_signals: dict[str, Any]) -> tuple[str, str, list[str], dict[str, Any]] | None:
        state = context.session_state or {}
        configured_agent = state.get("configured_agent") or {}
        setup = state.get("agent_setup") or {}
        collection = state.get("knowledge_collection") or {}
        query_aliases = [str(item) for item in dict(configured_agent.get("query_aliases") or {}).keys()]
        activation_keywords = [str(item) for item in list(configured_agent.get("activation_keywords") or [])]
        agent_identity_terms = [
            str(configured_agent.get("name") or ""),
            str(configured_agent.get("role") or ""),
            str(configured_agent.get("knowledge_entity_label") or ""),
        ]
        active_agent_terms = [item for item in [*activation_keywords, *query_aliases, *agent_identity_terms] if item]
        action_flags = keyword_signals.get("action_flags", {}) if isinstance(keyword_signals, dict) else {}
        intent_hints = set(keyword_signals.get("intent_hints", [])) if isinstance(keyword_signals, dict) else set()

        if collection.get("active"):
            return ("capture_agent_knowledge", "agent_management", ["knowledge", "dialog"], {"need_agent": False})

        if setup.get("active"):
            if action_flags.get("finalize_like") or "finalize_information_agent" in intent_hints:
                return ("finalize_information_agent", "agent_management", ["agent", "dialog"], {"need_agent": False})
            return ("refine_information_agent", "agent_management", ["agent", "dialog"], {"need_agent": False})

        if configured_agent.get("status") == "active" and (
            action_flags.get("query_like")
            or "?" in text
            or "？" in text
            or any(keyword in text for keyword in query_aliases)
            or "query_agent_knowledge" in intent_hints
        ):
            return ("query_agent_knowledge", "knowledge_ops", ["answer", "knowledge_hits"], {"need_agent": False})

        if configured_agent.get("status") == "active" and (
            action_flags.get("knowledge_capture_like")
            or "capture_agent_knowledge" in intent_hints
            or any(keyword in text for keyword in activation_keywords)
        ):
            return ("capture_agent_knowledge", "agent_management", ["knowledge", "dialog"], {"need_agent": False})

        if action_flags.get("agent_create_like") or "create_information_agent" in intent_hints:
            return ("create_information_agent", "agent_management", ["agent", "dialog"], {"need_agent": True})

        return None

    def _remember_runtime_intent(
        self,
        text: str,
        *,
        intent: str,
        domain: str,
        output_requirements: list[str],
        constraints: dict[str, Any],
        keyword_signals: dict[str, Any],
        analysis_meta: dict[str, Any],
    ) -> None:
        try:
            self.semantic_policy_store.record_intent_knowledge(
                text,
                {
                    "intent": intent,
                    "domain": domain,
                    "query_markers": keyword_signals.get("query_markers", []),
                    "record_markers": keyword_signals.get("record_markers", []),
                    "agent_markers": keyword_signals.get("agent_markers", []),
                    "goal_terms": keyword_signals.get("goal_terms", []),
                    "intent_hints": list(dict.fromkeys(list(keyword_signals.get("intent_hints", [])) + [intent])),
                    "action_flags": keyword_signals.get("action_flags", {}),
                    "output_requirements": output_requirements,
                    "constraints": constraints,
                    "analysis_meta": analysis_meta,
                },
                source="intent_analyzer",
                confidence=0.92,
                evidence=text,
            )
        except Exception:
            return

    def run(self, text: str, _context: CoreContextSchema) -> dict[str, Any]:
        dynamic_policy = self.policy_manager.synthesize(text, persist=False)
        keyword_signals = self.keyword_analyzer.analyze(text)
        analysis_meta = dynamic_policy.get("_analysis_meta", {})
        merged_policy = dict(self.policy)
        for key, value in dynamic_policy.items():
            if key.startswith("_"):
                continue
            if key not in merged_policy:
                merged_policy[key] = value
            elif isinstance(merged_policy.get(key), list) and isinstance(value, list):
                for item in value:
                    if item not in merged_policy[key]:
                        merged_policy[key].append(item)
        self.policy = merged_policy
        query_markers = list(dict.fromkeys(self.policy.get("query_markers", []) + keyword_signals.get("query_markers", [])))
        record_markers = list(dict.fromkeys(self.policy.get("record_markers", []) + keyword_signals.get("record_markers", [])))
        agent_markers = list(dict.fromkeys(self.policy.get("agent_markers", []) + keyword_signals.get("agent_markers", [])))
        self.policy["query_markers"] = query_markers
        self.policy["record_markers"] = record_markers
        self.policy["agent_markers"] = agent_markers

        multimodal_intent = self._infer_multimodal_intent(text, _context)
        if multimodal_intent:
            intent, domain = multimodal_intent
            self._remember_runtime_intent(
                text,
                intent=intent,
                domain=domain,
                output_requirements=["artifact"],
                constraints={"need_agent": False},
                keyword_signals=keyword_signals,
                analysis_meta=analysis_meta,
            )
            return {
                "intent": intent,
                "domain": domain,
                "output_requirements": ["artifact"],
                "constraints": {"need_agent": False},
                "analysis": {"model_routing": analysis_meta, "multimodal": True},
            }

        agent_intent = self._infer_agent_management_intent(text, _context, keyword_signals)
        if agent_intent:
            intent, domain, outputs, constraints = agent_intent
            self._remember_runtime_intent(
                text,
                intent=intent,
                domain=domain,
                output_requirements=outputs,
                constraints=constraints,
                keyword_signals=keyword_signals,
                analysis_meta=analysis_meta,
            )
            return {
                "intent": intent,
                "domain": domain,
                "output_requirements": outputs,
                "constraints": constraints,
                "analysis": {"model_routing": analysis_meta, "agent_management": True},
            }

        action_flags = keyword_signals.get("action_flags", {}) if isinstance(keyword_signals, dict) else {}
        has_numeric = self._has_numeric_value(text)
        is_query = bool(action_flags.get("query_like")) or self._contains_any(text, query_markers) or ("?" in text or "？" in text)
        is_record = bool(action_flags.get("record_like")) or has_numeric or self._contains_any(text, record_markers)
        need_agent = bool(action_flags.get("agent_create_like")) or self._contains_any(text, agent_markers)

        if is_query:
            intent = "data_query"
            outputs = ["aggregation", "insight"]
        elif is_record:
            intent = "data_record"
            outputs = ["records"]
        else:
            intent = "general_task"
            outputs = ["text"]

        constraints = {"need_agent": need_agent}
        self._remember_runtime_intent(
            text,
            intent=intent,
            domain="data_ops" if intent.startswith("data_") else "general",
            output_requirements=outputs,
            constraints=constraints,
            keyword_signals=keyword_signals,
            analysis_meta=analysis_meta,
        )

        return {
            "intent": intent,
            "domain": "data_ops" if intent.startswith("data_") else "general",
            "output_requirements": outputs,
            "constraints": constraints,
            "analysis": {
                "has_numeric_value": has_numeric,
                "is_query": is_query,
                "is_record": is_record,
                "runtime_keywords": keyword_signals,
                "model_routing": analysis_meta,
            },
        }


class DefaultIntentPlugin:
    priority = 1

    def match(self, _text: str, _context: CoreContextSchema) -> bool:
        return True

    def run(self, _text: str, _context: CoreContextSchema) -> dict[str, Any]:
        return {
            "intent": "general_task",
            "domain": "general",
            "output_requirements": ["text"],
            "constraints": {"need_agent": False},
            "analysis": {},
        }


class IntentAnalyzer:
    """Analyzes intent, goals, constraints, and output forms via plugins."""

    def __init__(self, keyword_analyzer: RuntimeKeywordSignalAnalyzer | None = None, semantic_policy_store: SemanticPolicyStore | None = None) -> None:
        self.plugins: list[PluginBase] = []
        self.register_plugin(SemanticIntentPlugin(keyword_analyzer=keyword_analyzer, semantic_policy_store=semantic_policy_store))
        self.register_plugin(DefaultIntentPlugin())
        self.load_plugins_from_config()

    def register_plugin(self, plugin: PluginBase) -> None:
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda item: getattr(item, "priority", 0), reverse=True)

    def unregister_plugin(self, plugin_type: type[PluginBase]) -> None:
        self.plugins = [item for item in self.plugins if not isinstance(item, plugin_type)]

    def load_plugins_from_config(self) -> None:
        if not PLUGIN_CONFIG_PATH.exists():
            return
        payload = json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
        for plugin_path in payload.get("intent_analyzer_plugins", []):
            plugin = load_plugin(plugin_path)
            self.register_plugin(plugin)

    async def analyze(self, text: str, context: CoreContextSchema) -> TaskSchema:
        for plugin in self.plugins:
            if plugin.match(text, context):
                result = plugin.run(text, context)
                metadata = {
                    "trace_id": context.trace_id,
                    "session_id": context.session_id,
                    "analysis": result.get("analysis", {}),
                }
                return TaskSchema(
                    task_id=generate_id("task"),
                    intent=result["intent"],
                    input_text=text,
                    domain=result.get("domain", "general"),
                    constraints=result.get("constraints", {}),
                    output_requirements=result.get("output_requirements", []),
                    metadata=metadata,
                )
        raise RuntimeError("No intent plugin matched the request.")
