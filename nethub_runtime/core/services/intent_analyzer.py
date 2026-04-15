from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import INTENT_POLICY_PATH, ensure_core_config_dir
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.intent_policy_manager import IntentPolicyManager
from nethub_runtime.core.services.plugin_base import PluginBase
from nethub_runtime.core.utils.id_generator import generate_id


class SemanticIntentPlugin:
    priority = 100

    def __init__(self, policy_path: Path | None = None, policy_manager: IntentPolicyManager | None = None) -> None:
        ensure_core_config_dir()
        self.policy_path = policy_path or INTENT_POLICY_PATH
        self.policy_manager = policy_manager or IntentPolicyManager(policy_path=self.policy_path)
        self.policy = self._load_policy()

    def _default_policy(self) -> dict[str, Any]:
        return {
            "query_markers": ["多少", "总额", "统计", "分析", "查询", "sum", "count", "average", "avg", "total"],
            "record_markers": ["记录", "新增", "添加", "花了", "买了"],
            "agent_markers": ["创建", "设计", "定义", "agent", "智能体", "角色"],
            "numeric_value_patterns": [r"(\d+(?:\.\d+)?)\s*(日元|円|yen|usd|rmb|元|块|美元|￥|\$)?"],
            "time_markers": ["今天", "昨天", "上周", "本周", "这个月", "上个月", "第一周", "第二周"],
            "stopwords": ["一共", "总共", "多少", "花了", "买了", "消费", "金额", "统计", "查询", "是多少", "吗", "？", "?"],
            "group_by_markers": ["按时间", "按类别", "按地点", "按人员"],
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

    def run(self, text: str, _context: CoreContextSchema) -> dict[str, Any]:
        dynamic_policy = self.policy_manager.synthesize(text, persist=False)
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

        multimodal_intent = self._infer_multimodal_intent(text, _context)
        if multimodal_intent:
            intent, domain = multimodal_intent
            return {
                "intent": intent,
                "domain": domain,
                "output_requirements": ["artifact"],
                "constraints": {"need_agent": False},
                "analysis": {"model_routing": analysis_meta, "multimodal": True},
            }

        has_numeric = self._has_numeric_value(text)
        is_query = self._contains_any(text, self.policy.get("query_markers", [])) or ("?" in text or "？" in text)
        is_record = has_numeric or self._contains_any(text, self.policy.get("record_markers", []))
        need_agent = self._contains_any(text, self.policy.get("agent_markers", []))

        if is_query:
            intent = "data_query"
            outputs = ["aggregation", "insight"]
        elif is_record:
            intent = "data_record"
            outputs = ["records"]
        else:
            intent = "general_task"
            outputs = ["text"]

        return {
            "intent": intent,
            "domain": "data_ops" if intent.startswith("data_") else "general",
            "output_requirements": outputs,
            "constraints": {"need_agent": need_agent},
            "analysis": {
                "has_numeric_value": has_numeric,
                "is_query": is_query,
                "is_record": is_record,
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

    def __init__(self) -> None:
        self.plugins: list[PluginBase] = []
        self.register_plugin(SemanticIntentPlugin())
        self.register_plugin(DefaultIntentPlugin())

    def register_plugin(self, plugin: PluginBase) -> None:
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda item: getattr(item, "priority", 0), reverse=True)

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
