from __future__ import annotations

from typing import Any

from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.plugin_base import PluginBase
from nethub_runtime.core.utils.id_generator import generate_id


class ExpenseIntentPlugin:
    priority = 100

    def match(self, text: str, _context: CoreContextSchema) -> bool:
        markers = ("花了", "买了", "日元", "多少钱", "消费", "一共")
        return any(marker in text for marker in markers)

    def run(self, text: str, _context: CoreContextSchema) -> dict[str, Any]:
        has_amount = "日元" in text and any(char.isdigit() for char in text)
        query_markers = ("多少", "统计", "总额", "查询", "花费", "花销")
        is_question = "？" in text or "?" in text
        intent = "expense_record"
        if any(m in text for m in query_markers) or is_question:
            intent = "expense_query"
        if has_amount and not ("多少" in text or "总额" in text):
            intent = "expense_record"
        return {
            "intent": intent,
            "domain": "household_budget",
            "output_requirements": ["records"] if intent == "expense_record" else ["aggregation"],
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
        }


class IntentAnalyzer:
    """Analyzes intent, goals, constraints, and output forms via plugins."""

    def __init__(self) -> None:
        self.plugins: list[PluginBase] = []
        self.register_plugin(ExpenseIntentPlugin())
        self.register_plugin(DefaultIntentPlugin())

    def register_plugin(self, plugin: PluginBase) -> None:
        self.plugins.append(plugin)
        self.plugins.sort(key=lambda item: getattr(item, "priority", 0), reverse=True)

    async def analyze(self, text: str, context: CoreContextSchema) -> TaskSchema:
        for plugin in self.plugins:
            if plugin.match(text, context):
                result = plugin.run(text, context)
                return TaskSchema(
                    task_id=generate_id("task"),
                    intent=result["intent"],
                    input_text=text,
                    domain=result.get("domain", "general"),
                    constraints=result.get("constraints", {}),
                    output_requirements=result.get("output_requirements", []),
                    metadata={
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                    },
                )
        raise RuntimeError("No intent plugin matched the request.")
