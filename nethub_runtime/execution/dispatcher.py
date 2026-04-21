from __future__ import annotations

from typing import Any


class ExecutionGraphDispatcher:
	"""Selects the active subgraph from request-plan metadata."""

	def __init__(self, profile: dict[str, Any]) -> None:
		self.profile = profile

	def dispatch(self, request_plan: dict[str, Any], task: dict[str, Any] | None = None) -> dict[str, Any]:
		task_intent = str((task or {}).get("intent") or "")
		selected_graph = str(request_plan.get("intent_router", {}).get("selected_graph") or "intent_router_graph")
		capability_orchestration = dict(request_plan.get("capability_orchestration") or {})
		routes = self.profile.get("graph_routes", {})
		matched_route = ""
		for graph_name, intents in routes.items():
			if task_intent and task_intent in intents:
				matched_route = graph_name
				break
		return {
			"selected_graph": matched_route or selected_graph,
			"task_intent": task_intent,
			"capability_orchestration": capability_orchestration,
			"autonomous_actions": {
				"trigger_autonomous_implementation": bool(capability_orchestration.get("trigger_autonomous_implementation")),
				"local_capability_targets": list(capability_orchestration.get("local_capabilities") or []),
				"external_capability_targets": list(capability_orchestration.get("external_capabilities") or []),
			},
			"fallback_graph": self.profile.get("fallback", {}).get("graph", "external_search_graph"),
			"local_first": bool(request_plan.get("intent_router", {}).get("local_first", True)),
		}
