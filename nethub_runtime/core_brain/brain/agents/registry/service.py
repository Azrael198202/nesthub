from __future__ import annotations

from typing import Any


class AgentRegistryService:
    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}

    def register(self, agent: dict[str, Any]) -> None:
        agent_id = str(agent.get("agent_id") or "")
        if agent_id:
            self._agents[agent_id] = dict(agent)

    def get(self, agent_id: str) -> dict[str, Any]:
        return dict(self._agents.get(agent_id) or {})
