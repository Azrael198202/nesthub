"""
Progress message formatter.

Produces human-readable, emoji-annotated status strings from NestHub
stream events.  Inspired by the Todo-list UI (✅ done / 🔄 running / ○ pending).

Usage::

    formatter = ProgressFormatter()
    # Call as each event arrives
    text = formatter.format_event(event)
    # text is a complete snapshot of the current state (suitable for LINE push)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------
_ICON_DONE    = "✅"
_ICON_RUNNING = "🔄"
_ICON_PENDING = "○"
_ICON_REPAIR  = "🔧"
_ICON_ERROR   = "❌"
_ICON_FINAL   = "🎉"


# ---------------------------------------------------------------------------
# Intent / domain labels
# ---------------------------------------------------------------------------
_INTENT_LABELS: dict[str, str] = {
    "data_record":                "记录数据",
    "data_query":                 "查询数据",
    "record_expense":             "记录消费",
    "create_information_agent":   "创建信息智能体",
    "refine_information_agent":   "优化智能体配置",
    "finalize_information_agent": "完成智能体创建",
    "capture_agent_knowledge":    "添加知识条目",
    "query_agent_knowledge":      "查询智能体知识",
    "image_generation_task":      "生成图片",
    "file_generate":              "生成文件",
    "file_read":                  "读取文件",
    "general_task":               "执行任务",
}

_STEP_LABELS: dict[str, str] = {
    "extract_records":            "提取记录",
    "persist_records":            "保存记录",
    "parse_query":                "解析查询",
    "aggregate_query":            "汇总统计",
    "manage_information_agent":   "智能体管理",
    "query_information_knowledge":"查询知识库",
    "image_generate":             "图片生成",
    "file_generate":              "文件生成",
    "file_read":                  "文件读取",
    "single_step":                "单步执行",
    "generate_workflow_artifact": "生成工件",
}


def _intent_label(intent: str) -> str:
    return _INTENT_LABELS.get(intent, intent)


def _step_label(step: str) -> str:
    return _STEP_LABELS.get(step, step)


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

@dataclass
class _StepState:
    name: str
    status: str = "pending"   # pending | running | done | failed


@dataclass
class ProgressFormatter:
    """Stateful formatter: call format_event() for each event in the stream."""

    _intent: str = field(default="", init=False)
    _steps: list[_StepState] = field(default_factory=list, init=False)
    _repair_count: int = field(default=0, init=False)
    _final_reply: str = field(default="", init=False)
    _error: str = field(default="", init=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format_event(self, event: dict[str, Any]) -> str | None:
        """Update internal state and return the current full-snapshot text.

        Returns ``None`` for events that do not need a visible update
        (e.g. ``lifecycle_start``).
        """
        etype = event.get("event", "")

        if etype == "lifecycle_start":
            return None

        if etype == "intent_analyzed":
            self._intent = str(event.get("intent", ""))
            # Mark all steps pending (they are not yet known)
            return self._render()

        if etype == "workflow_planned":
            steps = event.get("steps") or []
            self._steps = [_StepState(name=s) for s in steps]
            return self._render()

        if etype == "step_completed":
            step_name = str(event.get("step_name", ""))
            status = str(event.get("status", "done"))
            icon_status = "done" if status in ("completed", "done", "ok", "success") else (
                "failed" if status in ("failed", "error") else "done"
            )
            matched = False
            for s in self._steps:
                if s.name == step_name:
                    s.status = icon_status
                    matched = True
                    break
            if not matched:
                self._steps.append(_StepState(name=step_name, status=icon_status))
            # Mark the next pending step as running
            for s in self._steps:
                if s.status == "pending":
                    s.status = "running"
                    break
            return self._render()

        if etype == "repair_started":
            self._repair_count += 1
            return self._render()

        if etype == "final":
            result = event.get("result") or {}
            self._final_reply = _extract_reply(result)
            # Mark any still-pending/running steps as done
            for s in self._steps:
                if s.status in ("pending", "running"):
                    s.status = "done"
            return self._render()

        if etype == "lifecycle_end":
            return None

        if etype == "lifecycle_error":
            self._error = str(event.get("error", "未知错误"))
            return self._render()

        return None

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> str:
        lines: list[str] = []

        # Header
        if self._intent:
            lines.append(f"NestHub 正在处理：{_intent_label(self._intent)}")
        else:
            lines.append("NestHub 处理中…")

        lines.append("─" * 20)

        # Step list
        if self._steps:
            for i, s in enumerate(self._steps):
                if s.status == "done":
                    icon = _ICON_DONE
                elif s.status == "running":
                    icon = _ICON_RUNNING
                elif s.status == "failed":
                    icon = _ICON_ERROR
                else:
                    icon = _ICON_PENDING
                lines.append(f"{icon} {_step_label(s.name)}")
        else:
            lines.append(f"{_ICON_RUNNING} 分析中…")

        # Repair notice
        if self._repair_count:
            lines.append("")
            lines.append(f"{_ICON_REPAIR} 自动修复中（第 {self._repair_count} 次）")

        # Error
        if self._error:
            lines.append("")
            lines.append(f"{_ICON_ERROR} 错误：{self._error}")

        # Final reply
        if self._final_reply:
            lines.append("")
            lines.append(f"{_ICON_FINAL} {self._final_reply}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper: extract final reply text from a result dict
# ---------------------------------------------------------------------------

def _extract_reply(result: dict[str, Any]) -> str:
    execution_result = result.get("execution_result") or {}
    final_output = execution_result.get("final_output") or {}

    for key in ("manage_information_agent", "query_information_knowledge",
                "query_agent_knowledge", "file_read", "file_generate",
                "generate_workflow_artifact", "single_step"):
        payload = final_output.get(key) or {}
        for field in ("message", "answer", "summary"):
            value = str(payload.get(field) or "").strip()
            if value:
                return value

    img = final_output.get("image_generate") or {}
    if img.get("status") == "generated":
        return "图片已生成。"

    records = (final_output.get("extract_records") or {}).get("records") or []
    if records:
        return f"已记录 {len(records)} 条数据。"

    task = result.get("task") or {}
    intent = str(task.get("intent") or "")
    return f"已完成：{_intent_label(intent)}" if intent else "已完成。"
