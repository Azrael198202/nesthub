from __future__ import annotations

from typing import Protocol


class ProviderClient(Protocol):
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...
