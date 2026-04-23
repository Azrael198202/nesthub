from __future__ import annotations

from typing import Any
from uuid import uuid4

from nethub_runtime.core_brain.brain.agents.registry.service import AgentRegistryService
from nethub_runtime.core_brain.brain.agents.state.store import AgentStateStore


class AgentManagerService:
    def __init__(self, registry: AgentRegistryService, state_store: AgentStateStore) -> None:
        self.registry = registry
        self.state_store = state_store

    def ensure_agent(self, *, agent_type: str, workflow_id: str, blueprint_id: str | None = None) -> dict[str, Any]:
        agent_id = f"agent_{agent_type}_{uuid4().hex[:8]}"
        agent = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "workflow_id": workflow_id,
            "blueprint_id": blueprint_id,
            "status": "active",
        }
        self.registry.register(agent)
        self.state_store.put(agent_id, {"status": "active", "last_workflow_id": workflow_id})
        return agent
