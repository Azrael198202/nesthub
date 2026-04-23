from __future__ import annotations

from typing import Any


class ProgressFormatter:
    """Formats stream events into short progress messages for bridge channels."""

    def format_event(self, event: dict[str, Any]) -> str:
        event_name = str((event or {}).get("event") or "").strip()
        if not event_name:
            return ""

        if event_name == "intent_analyzed":
            intent = (event.get("intent") or {}).get("intent_name")
            return f"正在分析意图：{intent or 'general_chat'}"
        if event_name == "workflow_planned":
            return "已完成任务规划，正在执行。"
        if event_name == "step_completed":
            step = event.get("step") or {}
            name = str(step.get("name") or "step")
            return f"执行步骤：{name}"
        if event_name == "final":
            return "执行完成，正在整理结果。"
        return ""
