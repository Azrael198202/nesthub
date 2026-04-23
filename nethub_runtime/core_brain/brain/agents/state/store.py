from __future__ import annotations

from typing import Any


class AgentStateStore:
    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}

    def put(self, agent_id: str, state: dict[str, Any]) -> None:
        self._states[agent_id] = dict(state)

    def get(self, agent_id: str) -> dict[str, Any]:
        return dict(self._states.get(agent_id) or {})
