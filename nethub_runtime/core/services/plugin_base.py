from __future__ import annotations

from typing import Any, Protocol


class PluginBase(Protocol):
    priority: int

    def match(self, *args: Any, **kwargs: Any) -> bool:
        ...

    def run(self, *args: Any, **kwargs: Any) -> Any:
        ...
