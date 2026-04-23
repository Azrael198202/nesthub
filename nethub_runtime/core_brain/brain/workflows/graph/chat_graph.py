from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ChatGraphRunner:
    """Thin workflow runner with optional LangGraph integration."""

    def __init__(self) -> None:
        self._langgraph_available = False
        try:
            import langgraph  # noqa: F401

            self._langgraph_available = True
        except Exception:
            self._langgraph_available = False

    async def run(self, *, state: dict[str, Any], pipeline: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        # Phase-0: keep deterministic pipeline; graph engine can be swapped in later.
        return pipeline(state)
