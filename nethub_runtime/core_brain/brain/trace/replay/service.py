from __future__ import annotations

from typing import Any


class TraceReplayService:
    def replay(self, traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(item) for item in traces]
