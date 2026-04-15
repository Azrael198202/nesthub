from __future__ import annotations


class ToolAdapter:
    def __init__(self, allowed_tools: list[str] | None = None) -> None:
        self.allowed_tools = set(allowed_tools or ["parser", "query_engine"])

    def is_allowed(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools
