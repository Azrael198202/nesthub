from __future__ import annotations

from typing import Any


class CodeGenEngine:
    """Phase-1 compatible placeholder for artifact/code generation capability."""

    async def generate_all(self, intent: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": False,
            "intent": intent,
            "message": "Code generation is disabled in foundation execution mode.",
        }
