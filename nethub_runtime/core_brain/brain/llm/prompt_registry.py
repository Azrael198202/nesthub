from __future__ import annotations

from typing import Any


class PromptRegistry:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get(self, prompt_id: str) -> str:
        prompts = self.config.get("prompts", {})
        value = prompts.get(prompt_id)
        return str(value or "")
