from __future__ import annotations

from typing import Any


class LiteLLMRuntime:
    """Low-level provider transport boundary used by core_brain semantic layer."""

    def __init__(self, completion_fn: Any | None = None) -> None:
        self.completion_fn = completion_fn

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> Any:
        if self.completion_fn is None:
            raise RuntimeError("LiteLLM completion runtime is unavailable")
        return self.completion_fn(model=model, messages=messages)
