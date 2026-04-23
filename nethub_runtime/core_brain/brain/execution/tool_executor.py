from __future__ import annotations

from typing import Any


class ToolExecutor:
    def run_tools(self, tool_names: list[str], payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "tool_name": tool_name,
                "status": "skipped",
                "input_ref": None,
                "output_ref": None,
                "error_reason": None,
            }
            for tool_name in tool_names
        ]
