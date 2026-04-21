from __future__ import annotations

import json
import importlib
import threading
from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, TypedDict

from nethub_runtime.core.config.settings import CORE_ROOT
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


class LayeredExecutionState(TypedDict):
	session_state: dict[str, Any]
	user_long_term_state: dict[str, Any]
	task_execution_state: dict[str, Any]
	knowledge_context: dict[str, Any]
	review_state: dict[str, Any]
	control_state: dict[str, Any]


StateNode = Callable[[LayeredExecutionState], Awaitable[LayeredExecutionState]]


class PipelineKnowledgeBase:
	"""Builds a usable knowledge view from current runtime config and stores."""

	def __init__(self, *, profile: dict[str, Any], vector_store: Any | None = None, root_path: Path | None = None) -> None:
		self.profile = profile
		self.vector_store = vector_store
		self.root_path = root_path or CORE_ROOT.parent.parent
		self._seeded_ids: set[str] = set()

	def _load_json_document(self, source: dict[str, Any]) -> list[dict[str, Any]]:
		path = self.root_path / str(source.get("path") or "")
		if not path.exists():
			return []
		payload = json.loads(path.read_text(encoding="utf-8"))
		namespace = str(source.get("namespace") or "core_plus_runtime")
		if isinstance(payload, dict) and "documents" in payload:
			documents = payload.get("documents") or []
			return [
				{
					"id": str(item.get("id") or f"{source.get('source_id', 'doc')}_{index}"),
					"content": str(item.get("content") or json.dumps(item, ensure_ascii=False)),
					"metadata": {**(item.get("metadata") or {}), "title": item.get("title", ""), "source": source.get("source_id", "")},
					"namespace": namespace,
				}
				for index, item in enumerate(documents)
				if isinstance(item, dict)
			]
		return [
			{
				"id": str(source.get("source_id") or path.stem),
				"content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
				"metadata": {"source": source.get("source_id", ""), "path": str(path)},
				"namespace": namespace,
			}
		]

	def bootstrap(self) -> dict[str, Any]:
		documents: list[dict[str, Any]] = []
		for source in self.profile.get("knowledge_sources", []):
			if not isinstance(source, dict) or source.get("type") != "json_file":
				continue
			documents.extend(self._load_json_document(source))

		indexed = 0
		namespaces: set[str] = set()
		if self.vector_store is not None:
			for document in documents:
				document_id = document["id"]
				namespaces.add(document["namespace"])
				if document_id in self._seeded_ids:
					continue
				self.vector_store.add_knowledge(
					namespace=document["namespace"],
					content=document["content"],
					metadata=document["metadata"],
					item_id=document_id,
				)
				self._seeded_ids.add(document_id)
				indexed += 1
		return {
			"document_count": len(documents),
			"indexed_count": indexed,
			"namespaces": sorted(namespaces),
			"providers": deepcopy(self.profile.get("retrieval", {}).get("providers", {})),
			"default_backends": deepcopy(self.profile.get("retrieval", {}).get("default_backends", {})),
		}

	def retrieve(self, query: str, *, top_k: int = 5) -> dict[str, Any]:
		if self.vector_store is None:
			return {"hits": [], "query": query, "namespaces": []}
		hits: list[dict[str, Any]] = []
		namespaces = self.profile.get("retrieval", {}).get("knowledge_namespaces", []) or []
		for namespace in namespaces:
			hits.extend(self.vector_store.search(query, top_k=top_k, namespace=namespace))
		return {"query": query, "hits": hits[:top_k], "namespaces": namespaces}


class ExecutionUpgradePipeline:
	"""Configuration-driven orchestration layer for the upgraded core."""

	def __init__(self, *, base_core: Any | None = None, profile_path: str | Path | None = None) -> None:
		self.base_core = base_core
		self.session_store = getattr(getattr(base_core, "context_manager", None), "session_store", None)
		self.profile_path = Path(profile_path) if profile_path else (CORE_ROOT.parent / "config" / "core_plus_runtime_profile.json")
		self.profile = self._load_profile()
		self.knowledge_base = PipelineKnowledgeBase(profile=self.profile, vector_store=getattr(base_core, "vector_store", None))
		self._graph_nodes: dict[str, list[StateNode]] = self._build_graph_nodes()
		self._compiled_graphs: dict[str, Any] = {}

	def _load_profile(self) -> dict[str, Any]:
		return json.loads(self.profile_path.read_text(encoding="utf-8"))

	def bootstrap_knowledge_base(self) -> dict[str, Any]:
		return self.knowledge_base.bootstrap()

	def build_layered_state(self, input_text: str, context: dict[str, Any] | None, task: dict[str, Any] | None = None) -> LayeredExecutionState:
		next_context = dict(context or {})
		metadata = dict(next_context.get("metadata") or {})
		return {
			"session_state": {
				"session_id": next_context.get("session_id", ""),
				"trace_id": next_context.get("trace_id", ""),
				"dialog_turns": list(next_context.get("dialog_turns") or []),
				"queued_review": metadata.get("human_review_response"),
			},
			"user_long_term_state": {
				"preferences": deepcopy(next_context.get("preferences") or {}),
				"memory_profile": deepcopy(next_context.get("memory_profile") or {}),
				"knowledge_refs": [],
			},
			"task_execution_state": {
				"input_text": input_text,
				"intent": (task or {}).get("intent", ""),
				"workflow": "",
				"selected_graph": "intent_router_graph",
				"evaluation": {},
				"pending_review": None
			},
			"knowledge_context": {
				"bootstrap": self.bootstrap_knowledge_base(),
				"retrieval": {"query": input_text, "hits": [], "namespaces": []},
			},
			"review_state": {
				"status": "clear",
				"reason_codes": [],
				"resume_payload": metadata.get("human_review_response") or {},
			},
			"control_state": {
				"selected_graph": "intent_router_graph",
				"next_graph": None,
				"halted": False,
				"used_langgraph": False,
				"checkpoint_key": "",
			},
		}

	def _checkpoint_key(self, session_id: str, graph_name: str) -> str:
		return f"core_plus_checkpoint:{graph_name}"

	def _persist_review_checkpoint(self, state: LayeredExecutionState) -> None:
		if self.session_store is None:
			return
		session_id = str(state["session_state"].get("session_id") or "").strip()
		if not session_id:
			return
		pending = state["task_execution_state"].get("pending_review")
		selected_graph = str(state["task_execution_state"].get("selected_graph") or state["control_state"].get("next_graph") or "human_review_graph")
		checkpoint_key = self._checkpoint_key(session_id, selected_graph)
		state["control_state"]["checkpoint_key"] = checkpoint_key
		self.session_store.patch(
			session_id,
			{
				"core_plus_review_checkpoint": {
					"checkpoint_key": checkpoint_key,
					"graph": selected_graph,
					"pending_review": deepcopy(pending),
					"review_state": deepcopy(state["review_state"]),
					"task_execution_state": deepcopy(state["task_execution_state"]),
				},
			},
		)

	def _clear_review_checkpoint(self, state: LayeredExecutionState) -> None:
		if self.session_store is None:
			return
		session_id = str(state["session_state"].get("session_id") or "").strip()
		if not session_id:
			return
		self.session_store.patch(session_id, {"core_plus_review_checkpoint": None})

	def load_review_checkpoint(self, session_id: str) -> dict[str, Any] | None:
		if self.session_store is None:
			return None
		payload = self.session_store.get(session_id)
		checkpoint = payload.get("core_plus_review_checkpoint")
		return checkpoint if isinstance(checkpoint, dict) else None

	def _compile_langgraph(self, graph_name: str) -> Any | None:
		if graph_name in self._compiled_graphs:
			return self._compiled_graphs[graph_name]
		if graph_name == "core_plus_execution_graph":
			compiled = self._compile_execution_supergraph()
			self._compiled_graphs[graph_name] = compiled
			return compiled
		try:
			graph_module = importlib.import_module("langgraph.graph")
			END = getattr(graph_module, "END")
			StateGraph = getattr(graph_module, "StateGraph")
		except Exception:
			self._compiled_graphs[graph_name] = None
			return None

		graph = StateGraph(LayeredExecutionState)
		nodes = self._graph_nodes.get(graph_name, [])
		if not nodes:
			self._compiled_graphs[graph_name] = None
			return None

		node_names: list[str] = []
		for index, node in enumerate(nodes):
			node_name = f"{graph_name}_node_{index}"
			node_names.append(node_name)
			graph.add_node(node_name, node)

		graph.set_entry_point(node_names[0])
		for index, node_name in enumerate(node_names[:-1]):
			graph.add_edge(node_name, node_names[index + 1])
		graph.add_edge(node_names[-1], END)
		compiled = graph.compile()
		self._compiled_graphs[graph_name] = compiled
		return compiled

	def _route_after_intent_router(self, state: LayeredExecutionState) -> str:
		next_graph = str(state["control_state"].get("next_graph") or "intent_router_graph")
		if next_graph in self._graph_nodes and next_graph != "intent_router_graph":
			return next_graph
		return "external_search_graph"

	def _route_after_domain_graph(self, state: LayeredExecutionState) -> str:
		if state["control_state"].get("halted") or state["review_state"].get("status") == "awaiting_user":
			return "human_review_graph"
		fallback_graph = str(state["task_execution_state"].get("fallback_graph") or "")
		if fallback_graph:
			return "external_search_graph"
		return "end"

	def _route_after_human_review(self, state: LayeredExecutionState) -> str:
		if state["review_state"].get("status") == "awaiting_user":
			return "end"
		fallback_graph = str(state["task_execution_state"].get("fallback_graph") or "")
		if fallback_graph:
			return "external_search_graph"
		return "end"

	def _compile_execution_supergraph(self) -> Any | None:
		try:
			graph_module = importlib.import_module("langgraph.graph")
			END = getattr(graph_module, "END")
			StateGraph = getattr(graph_module, "StateGraph")
		except Exception:
			return None

		graph = StateGraph(LayeredExecutionState)
		for graph_name in [
			"intent_router_graph",
			"rag_qa_graph",
			"expense_record_graph",
			"schedule_graph",
			"document_summary_graph",
			"external_search_graph",
			"human_review_graph",
		]:
			graph.add_node(graph_name, self._make_graph_runner(graph_name))

		graph.set_entry_point("intent_router_graph")
		graph.add_conditional_edges(
			"intent_router_graph",
			self._route_after_intent_router,
			{
				"rag_qa_graph": "rag_qa_graph",
				"expense_record_graph": "expense_record_graph",
				"schedule_graph": "schedule_graph",
				"document_summary_graph": "document_summary_graph",
				"external_search_graph": "external_search_graph",
			},
		)
		for graph_name in ["rag_qa_graph", "expense_record_graph", "schedule_graph", "document_summary_graph"]:
			graph.add_conditional_edges(
				graph_name,
				self._route_after_domain_graph,
				{
					"human_review_graph": "human_review_graph",
					"external_search_graph": "external_search_graph",
					"end": END,
				},
			)
		graph.add_conditional_edges(
			"human_review_graph",
			self._route_after_human_review,
			{
				"external_search_graph": "external_search_graph",
				"end": END,
			},
		)
		graph.add_edge("external_search_graph", END)
		return graph.compile()

	def _make_graph_runner(self, graph_name: str) -> StateNode:
		async def _runner(state: LayeredExecutionState) -> LayeredExecutionState:
			return await self._run_graph_nodes(graph_name, state)

		return _runner

	def _match_rule(self, input_text: str) -> dict[str, Any]:
		lowered = input_text.lower()
		# High-priority guard: "create agent" requests must not be swallowed
		# by domain marker rules such as schedule_rule.
		agent_create_markers = ("创建", "新建", "建立", "create", "build")
		agent_noun_markers = ("智能体", "助手", "agent", "bot")
		if any(marker in input_text or marker in lowered for marker in agent_create_markers) and any(
			marker in input_text or marker in lowered for marker in agent_noun_markers
		):
			return {
				"rule_hit": True,
				"rule_id": "agent_create_rule",
				"intent": "create_information_agent",
				"workflow": "intent_router_graph",
				"confidence": 0.95,
				"markers": [marker for marker in [*agent_create_markers, *agent_noun_markers] if marker in input_text or marker in lowered],
			}
		for rule in self.profile.get("intent_rules", []):
			markers = [str(item) for item in rule.get("markers", [])]
			if any(marker.lower() in lowered or marker in input_text for marker in markers):
				return {
					"rule_hit": True,
					"rule_id": rule.get("rule_id", ""),
					"intent": rule.get("intent", ""),
					"workflow": rule.get("workflow", ""),
					"confidence": float(rule.get("confidence", 0.0)),
					"markers": [marker for marker in markers if marker.lower() in lowered or marker in input_text],
				}
		return {"rule_hit": False, "rule_id": "", "intent": "", "workflow": "", "confidence": 0.0, "markers": []}

	def _invoke_model_json(self, *, task_type: str, system_prompt: str, prompt: str, timeout_sec: int = 20) -> dict[str, Any] | None:
		model_router = getattr(self.base_core, "model_router", None)
		if model_router is None:
			return None

		holder: dict[str, Any] = {}

		def _runner() -> None:
			try:
				holder["response"] = asyncio.run(
					model_router.invoke(
						task_type=task_type,
						prompt=prompt,
						system_prompt=system_prompt,
						temperature=0.2,
					)
				)
			except Exception as exc:
				holder["error"] = exc

		thread = threading.Thread(target=_runner, daemon=True)
		thread.start()
		thread.join(timeout=timeout_sec)
		raw = holder.get("response")
		if not isinstance(raw, str):
			return None
		cleaned = raw.strip()
		if cleaned.startswith("```"):
			cleaned = cleaned.split("\n", 1)[-1]
			if cleaned.endswith("```"):
				cleaned = cleaned[:-3]
			cleaned = cleaned.strip()
		if cleaned.startswith("json\n"):
			cleaned = cleaned.replace("json\n", "", 1).strip()
		if cleaned.startswith("Model response (mock):"):
			return None
		try:
			payload = json.loads(cleaned)
		except Exception:
			return None
		return payload if isinstance(payload, dict) else None

	def _generate_workflow_plan(
		self,
		*,
		input_text: str,
		local_capabilities: list[str],
		external_capabilities: list[str],
		matched_markers: list[str] | None = None,
	) -> list[dict[str, Any]]:
		ordered = [(name, "local") for name in local_capabilities] + [(name, "external") for name in external_capabilities]
		base_steps = [
			{"name": str(name).strip(), "kind": kind}
			for name, kind in ordered
			if str(name).strip()
		]
		lowered = input_text.lower()
		reminder_markers = ("提醒", "航班", "飞机", "机场", "闹钟", "起飞", "到点", "remind", "flight", "airport")
		has_reminder_signal = any(marker in input_text or marker in lowered for marker in reminder_markers)
		if not has_reminder_signal:
			base_steps = [step for step in base_steps if step.get("name") != "reminder_create_trigger"]
		if not base_steps:
			return []

		default_plan = [
			{
				"name": step["name"],
				"kind": step["kind"],
				"label": step["name"].replace("_", " ").strip().title(),
				"preview": "执行外部能力" if step["kind"] == "external" else "执行本地能力",
			}
			for step in base_steps
		]

		model_payload = self._invoke_model_json(
			task_type="task_planning",
			system_prompt=(
				"You are NestHub workflow planner. Return JSON only.\n"
				"Generate concise, user-facing workflow step labels and previews."
			),
			prompt=(
				"Build workflow steps for the current user request.\n"
				f"input_text={json.dumps(input_text, ensure_ascii=False)}\n"
				f"matched_markers={json.dumps(list(matched_markers or []), ensure_ascii=False)}\n"
				f"available_steps={json.dumps(base_steps, ensure_ascii=False)}\n"
				"Return JSON with key steps, where steps is an array of objects:\n"
				"{\"name\": string, \"kind\": \"local\"|\"external\", \"label\": string, \"preview\": string}\n"
				"Rules:\n"
				"1) name must come from available_steps;\n"
				"2) preserve execution order;\n"
				"3) label/preview should be specific to this user input."
			),
		)
		if not isinstance(model_payload, dict):
			return default_plan

		raw_steps = model_payload.get("steps")
		if not isinstance(raw_steps, list):
			return default_plan

		allowed = {step["name"]: step["kind"] for step in base_steps}
		generated_by_name: dict[str, dict[str, Any]] = {}
		for item in raw_steps:
			if not isinstance(item, dict):
				continue
			name = str(item.get("name") or "").strip()
			if name not in allowed:
				continue
			kind = str(item.get("kind") or allowed[name]).strip().lower()
			if kind not in {"local", "external"}:
				kind = allowed[name]
			label = str(item.get("label") or "").strip() or name.replace("_", " ").strip().title()
			preview = str(item.get("preview") or "").strip() or ("执行外部能力" if kind == "external" else "执行本地能力")
			generated_by_name[name] = {"name": name, "kind": kind, "label": label, "preview": preview}

		merged: list[dict[str, Any]] = []
		for step in base_steps:
			name = step["name"]
			merged.append(generated_by_name.get(name, {
				"name": name,
				"kind": step["kind"],
				"label": name.replace("_", " ").strip().title(),
				"preview": "执行外部能力" if step["kind"] == "external" else "执行本地能力",
			}))
		return merged

	def _match_capability_orchestration(self, input_text: str) -> dict[str, Any]:
		lowered = input_text.lower()
		patterns = list((self.profile.get("capability_orchestration", {}) or {}).get("patterns", []))
		for item in patterns:
			if not isinstance(item, dict):
				continue
			markers = [str(marker) for marker in item.get("markers", []) if str(marker).strip()]
			matched_markers = [marker for marker in markers if marker.lower() in lowered or marker in input_text]
			if len(matched_markers) >= max(2, min(len(markers), 2)):
				local_capabilities = [str(item_name).strip() for item_name in list(item.get("local_capabilities", []) or []) if str(item_name).strip()]
				external_capabilities = [str(item_name).strip() for item_name in list(item.get("external_capabilities", []) or []) if str(item_name).strip()]
				workflow_plan = self._generate_workflow_plan(
					input_text=input_text,
					local_capabilities=local_capabilities,
					external_capabilities=external_capabilities,
					matched_markers=matched_markers,
				)
				return {
					"matched": True,
					"pattern_id": str(item.get("pattern_id") or ""),
					"matched_markers": matched_markers,
					"local_capabilities": local_capabilities,
					"external_capabilities": external_capabilities,
					"workflow_plan": workflow_plan,
					"force_need_external": bool(item.get("force_need_external", False)),
					"trigger_autonomous_implementation": bool(item.get("trigger_autonomous_implementation", False)),
				}
		return {
			"matched": False,
			"pattern_id": "",
			"matched_markers": [],
			"local_capabilities": [],
			"external_capabilities": [],
			"workflow_plan": [],
			"force_need_external": False,
			"trigger_autonomous_implementation": False,
		}

	def build_request_plan(self, input_text: str, context: dict[str, Any] | None, task: dict[str, Any] | None = None) -> dict[str, Any]:
		rule = self._match_rule(input_text)
		capability_orchestration = self._match_capability_orchestration(input_text)
		lowered = input_text.lower()
		signals = self.profile.get("signal_sets", {})
		metadata = dict((context or {}).get("metadata") or {})
		model_router = getattr(self.base_core, "model_router", None)
		active_local_profile = model_router.active_local_profile_info() if model_router and hasattr(model_router, "active_local_profile_info") else {"name": "base_local", "enabled": False}
		need_external = any(str(marker).lower() in lowered or str(marker) in input_text for marker in signals.get("needs_external", [])) or bool(capability_orchestration.get("force_need_external"))
		need_rag = any(str(marker).lower() in lowered or str(marker) in input_text for marker in signals.get("needs_rag", []))
		need_planning = any(str(marker).lower() in lowered or str(marker) in input_text for marker in signals.get("needs_planning", []))
		complexity = "high" if need_planning or len(input_text) > 120 else "medium" if len(input_text) > 40 else "low"
		selected_graph = self.select_graph(task_intent=(task or {}).get("intent", rule.get("intent", "")), rule_workflow=rule.get("workflow", ""), need_external=need_external, need_rag=need_rag)
		return {
			"version": self.profile.get("version", "core_plus"),
			"rule_prejudge": rule,
			"capability_orchestration": capability_orchestration,
			"intent_router": {
				"need_rag": need_rag,
				"need_external": need_external,
				"complexity": complexity,
				"local_first": not bool(metadata.get("force_external")),
				"local_profile": deepcopy(active_local_profile),
				"preferred_execution_mode": "external_fallback" if need_external else "local_composite",
				"selected_graph": selected_graph,
			},
			"retrieval_plan": deepcopy(self.profile.get("retrieval", {})),
			"human_review": deepcopy(self.profile.get("human_review", {})),
			"fallback_policy": deepcopy(self.profile.get("fallback", {})),
		}

	def select_graph(self, *, task_intent: str, rule_workflow: str, need_external: bool, need_rag: bool) -> str:
		if rule_workflow:
			return rule_workflow
		routes = self.profile.get("graph_routes", {})
		for graph_name, intents in routes.items():
			if task_intent and task_intent in intents:
				return graph_name
		if need_external:
			return "external_search_graph"
		if need_rag:
			return "rag_qa_graph"
		return "intent_router_graph"

	def _graph_intent(self, graph_name: str) -> str:
		mapping = {
			"document_summary_graph": "document_summary",
			"external_search_graph": "web_research_task",
			"expense_record_graph": "record_expense",
			"schedule_graph": "schedule_create",
			"rag_qa_graph": "faq_answer",
		}
		return mapping.get(graph_name, "general_task")

	def _build_runtime_context(self, state: LayeredExecutionState) -> CoreContextSchema:
		return CoreContextSchema(
			session_id=str(state["session_state"].get("session_id") or "default"),
			trace_id=str(state["session_state"].get("trace_id") or "core_plus_trace"),
			session_state=deepcopy(state["task_execution_state"].get("session_snapshot") or {}),
			metadata={
				"core_plus": True,
				"graph": str(state["task_execution_state"].get("selected_graph") or state["control_state"].get("next_graph") or ""),
				**deepcopy(state["knowledge_context"].get("bootstrap") or {}),
			},
		)

	def _build_runtime_task(self, state: LayeredExecutionState, graph_name: str) -> TaskSchema:
		input_text = str(state["task_execution_state"].get("input_text") or "")
		constraints: dict[str, Any] = {}
		if graph_name == "document_summary_graph":
			constraints["document_action"] = "summarize"
			if state["review_state"].get("resume_payload"):
				constraints["document_reference"] = state["review_state"].get("resume_payload", {}).get("document_reference", "")
		return TaskSchema(
			task_id=f"core_plus_{graph_name}",
			intent=self._graph_intent(graph_name),
			input_text=input_text,
			domain="general",
			constraints=constraints,
			output_requirements=["summary"] if graph_name == "document_summary_graph" else ["text"],
			metadata={"graph": graph_name},
		)

	def _extract_schedule_fields(self, records: list[dict[str, Any]]) -> dict[str, Any]:
		if not records:
			return {}
		record = dict(records[0] or {})
		time_value = str(record.get("time") or "").strip()
		fields: dict[str, Any] = {
			"content": record.get("content"),
			"location": record.get("location"),
		}
		if time_value and time_value != "unspecified":
			fields["time_marker"] = time_value
			if "T" in time_value:
				date_part, time_part = time_value.split("T", 1)
				fields["date"] = date_part.strip()
				fields["time"] = time_part.strip()
			elif len(time_value) >= 10 and time_value[4] == "-" and time_value[7] == "-":
				parts = time_value.split()
				fields["date"] = parts[0].strip()
				if len(parts) > 1:
					fields["time"] = " ".join(parts[1:]).strip()
			elif ":" in time_value:
				fields["time"] = time_value
			else:
				fields["date"] = time_value
		return {key: value for key, value in fields.items() if value not in (None, "", "unspecified")}

	def _apply_schedule_review_fields(self, records: list[dict[str, Any]], review_fields: dict[str, Any]) -> list[dict[str, Any]]:
		if not records or not review_fields:
			return records
		normalized = [dict(item or {}) for item in records]
		primary = normalized[0]
		date_value = str(review_fields.get("date") or "").strip()
		time_value = str(review_fields.get("time") or "").strip()
		if date_value and time_value:
			primary["time"] = f"{date_value} {time_value}".strip()
		elif date_value:
			primary["time"] = date_value
		elif time_value:
			primary["time"] = time_value
		if review_fields.get("location"):
			primary["location"] = review_fields.get("location")
		if review_fields.get("content"):
			primary["content"] = review_fields.get("content")
		normalized[0] = primary
		return normalized

	def _extract_expense_fields(self, records: list[dict[str, Any]]) -> dict[str, Any]:
		if not records:
			return {}
		record = dict(records[0] or {})
		fields: dict[str, Any] = {
			"amount": record.get("amount"),
			"content": record.get("content"),
			"location": record.get("location"),
			"label": record.get("label"),
		}
		time_value = str(record.get("time") or "").strip()
		if time_value and time_value != "unspecified":
			fields["date"] = time_value.split()[0].strip()
		return {key: value for key, value in fields.items() if value not in (None, "", "unspecified")}

	def _apply_expense_review_fields(self, records: list[dict[str, Any]], review_fields: dict[str, Any]) -> list[dict[str, Any]]:
		if not records or not review_fields:
			return records
		normalized = [dict(item or {}) for item in records]
		primary = normalized[0]
		amount_value = review_fields.get("amount")
		if amount_value not in (None, ""):
			try:
				primary["amount"] = int(float(amount_value))
			except (TypeError, ValueError):
				pass
		date_value = str(review_fields.get("date") or "").strip()
		if date_value:
			primary["time"] = date_value
		if review_fields.get("location"):
			primary["location"] = review_fields.get("location")
		if review_fields.get("content"):
			primary["content"] = review_fields.get("content")
		normalized[0] = primary
		return normalized

	async def _node_retrieve_knowledge(self, state: LayeredExecutionState) -> LayeredExecutionState:
		query = str(state["task_execution_state"].get("input_text") or "")
		retrieval = self.knowledge_base.retrieve(query)
		state["knowledge_context"]["retrieval"] = retrieval
		state["user_long_term_state"]["knowledge_refs"] = [item.get("id") for item in retrieval.get("hits", [])]
		return state

	async def _node_route_intent(self, state: LayeredExecutionState) -> LayeredExecutionState:
		input_text = str(state["task_execution_state"].get("input_text") or "")
		request_plan = self.build_request_plan(input_text, {"metadata": {}, "session_id": state["session_state"].get("session_id", "")}, task={"intent": state["task_execution_state"].get("intent", "")})
		state["task_execution_state"]["workflow"] = request_plan["intent_router"]["selected_graph"]
		state["task_execution_state"]["selected_graph"] = request_plan["intent_router"]["selected_graph"]
		state["task_execution_state"]["fallback_graph"] = self.profile.get("fallback", {}).get("graph", "external_search_graph") if request_plan["intent_router"].get("need_external") else None
		state["control_state"]["selected_graph"] = "intent_router_graph"
		state["control_state"]["next_graph"] = request_plan["intent_router"]["selected_graph"]
		state["task_execution_state"]["request_plan"] = request_plan
		return state

	async def _node_prepare_rag(self, state: LayeredExecutionState) -> LayeredExecutionState:
		retrieval = state["knowledge_context"].get("retrieval", {})
		hits = retrieval.get("hits", []) if isinstance(retrieval, dict) else []
		state["task_execution_state"]["rag_ready"] = bool(hits)
		return state

	async def _node_execute_document_summary(self, state: LayeredExecutionState) -> LayeredExecutionState:
		graph_name = "document_summary_graph"
		coordinator = getattr(self.base_core, "execution_coordinator", None)
		if coordinator is None:
			state["task_execution_state"]["document_result"] = {
				"status": "unavailable",
				"message": "document_runtime_unavailable",
			}
			return state
		from nethub_runtime.core.services.document_runtime_plugin import handle_analyze_document_step

		task = self._build_runtime_task(state, graph_name)
		context = self._build_runtime_context(state)
		result = handle_analyze_document_step(coordinator, {}, task, context, {})
		state["task_execution_state"]["document_result"] = result
		if str(result.get("status") or "") == "awaiting_document":
			state["review_state"]["status"] = "awaiting_user"
			state["review_state"]["reason_codes"] = ["missing_information"]
			state["task_execution_state"]["pending_review"] = {
				"graph": graph_name,
				"missing_fields": ["document_reference"],
				"reason_codes": ["missing_information"],
			}
			state["control_state"]["halted"] = True
			self._persist_review_checkpoint(state)
		return state

	async def _node_execute_external_retrieval(self, state: LayeredExecutionState) -> LayeredExecutionState:
		coordinator = getattr(self.base_core, "execution_coordinator", None)
		if coordinator is None:
			state["task_execution_state"]["external_retrieval"] = {
				"status": "unavailable",
				"content": "",
			}
			return state
		from nethub_runtime.core.services.execution_step_handlers import handle_web_retrieve_step

		task = self._build_runtime_task(state, "external_search_graph")
		context = self._build_runtime_context(state)
		result = handle_web_retrieve_step(coordinator, {}, task, context, {})
		state["task_execution_state"]["external_retrieval"] = result
		return state

	async def _node_execute_external_summary(self, state: LayeredExecutionState) -> LayeredExecutionState:
		coordinator = getattr(self.base_core, "execution_coordinator", None)
		if coordinator is None:
			state["task_execution_state"]["external_summary"] = {
				"status": "unavailable",
				"summary": "",
			}
			return state
		from nethub_runtime.core.services.execution_step_handlers import handle_web_summarize_step

		task = self._build_runtime_task(state, "external_search_graph")
		context = self._build_runtime_context(state)
		step_outputs = {"web_retrieve": deepcopy(state["task_execution_state"].get("external_retrieval") or {})}
		result = handle_web_summarize_step(coordinator, {}, task, context, step_outputs)
		state["task_execution_state"]["external_summary"] = result
		return state

	async def _node_execute_schedule(self, state: LayeredExecutionState) -> LayeredExecutionState:
		coordinator = getattr(self.base_core, "execution_coordinator", None)
		if coordinator is None:
			state["task_execution_state"]["schedule_result"] = {
				"status": "unavailable",
				"message": "schedule_runtime_unavailable",
			}
			return state
		from nethub_runtime.core.services.execution_step_handlers import handle_extract_records_step, handle_persist_records_step

		task = self._build_runtime_task(state, "schedule_graph")
		context = self._build_runtime_context(state)
		extract_result = handle_extract_records_step(coordinator, {}, task, context, {})
		records = list(extract_result.get("records") or [])
		records = self._apply_schedule_review_fields(records, dict(state["task_execution_state"].get("extracted_fields") or {}))
		extract_result["records"] = records
		persist_result = handle_persist_records_step(coordinator, {}, task, context, {"extract_records": extract_result})
		extracted_fields = dict(state["task_execution_state"].get("extracted_fields") or {})
		extracted_fields.update(self._extract_schedule_fields(records))
		state["task_execution_state"]["extracted_fields"] = extracted_fields
		state["task_execution_state"]["session_snapshot"] = coordinator.session_store.get(context.session_id)
		state["task_execution_state"]["schedule_extract_result"] = extract_result
		state["task_execution_state"]["schedule_persist_result"] = persist_result
		state["task_execution_state"]["schedule_result"] = {
			"status": "completed",
			"records_saved": persist_result.get("saved", 0),
			"extracted_fields": extracted_fields,
		}
		return state

	async def _node_execute_expense_record(self, state: LayeredExecutionState) -> LayeredExecutionState:
		coordinator = getattr(self.base_core, "execution_coordinator", None)
		if coordinator is None:
			state["task_execution_state"]["expense_result"] = {
				"status": "unavailable",
				"message": "expense_runtime_unavailable",
			}
			return state
		from nethub_runtime.core.services.execution_step_handlers import handle_extract_records_step, handle_persist_records_step

		task = self._build_runtime_task(state, "expense_record_graph")
		context = self._build_runtime_context(state)
		extract_result = handle_extract_records_step(coordinator, {}, task, context, {})
		records = list(extract_result.get("records") or [])
		records = self._apply_expense_review_fields(records, dict(state["task_execution_state"].get("extracted_fields") or {}))
		extract_result["records"] = records
		persist_result = handle_persist_records_step(coordinator, {}, task, context, {"extract_records": extract_result})
		extracted_fields = dict(state["task_execution_state"].get("extracted_fields") or {})
		extracted_fields.update(self._extract_expense_fields(records))
		state["task_execution_state"]["extracted_fields"] = extracted_fields
		state["task_execution_state"]["session_snapshot"] = coordinator.session_store.get(context.session_id)
		state["task_execution_state"]["expense_extract_result"] = extract_result
		state["task_execution_state"]["expense_persist_result"] = persist_result
		state["task_execution_state"]["expense_result"] = {
			"status": "completed",
			"records_saved": persist_result.get("saved", 0),
			"extracted_fields": extracted_fields,
		}
		return state

	async def _node_prepare_graph_requirements(self, state: LayeredExecutionState) -> LayeredExecutionState:
		graph_name = str(state["task_execution_state"].get("selected_graph") or state["control_state"].get("next_graph") or "intent_router_graph")
		required = list((self.profile.get("human_review", {}).get("required_fields", {}) or {}).get(graph_name, []))
		state["task_execution_state"]["required_fields"] = required
		return state

	async def _node_detect_review_need(self, state: LayeredExecutionState) -> LayeredExecutionState:
		required = list(state["task_execution_state"].get("required_fields") or [])
		extracted = dict(state["task_execution_state"].get("extracted_fields") or {})
		missing = [field for field in required if not extracted.get(field)]
		reason_codes = list(state["review_state"].get("reason_codes") or [])
		if state["review_state"].get("resume_payload"):
			return state
		if missing and "missing_information" not in reason_codes:
			reason_codes.append("missing_information")
		state["review_state"]["reason_codes"] = reason_codes
		if missing and not state["review_state"].get("resume_payload"):
			state["review_state"]["status"] = "awaiting_user"
			state["task_execution_state"]["pending_review"] = {
				"graph": state["task_execution_state"].get("selected_graph") or state["control_state"].get("next_graph"),
				"missing_fields": missing,
				"reason_codes": reason_codes,
			}
			state["control_state"]["halted"] = True
			self._persist_review_checkpoint(state)
		return state

	async def _node_apply_review_response(self, state: LayeredExecutionState) -> LayeredExecutionState:
		response = dict(state["review_state"].get("resume_payload") or {})
		if response:
			extracted = dict(state["task_execution_state"].get("extracted_fields") or {})
			extracted.update(response)
			state["task_execution_state"]["extracted_fields"] = extracted
			state["review_state"]["status"] = "resumed"
			state["task_execution_state"]["pending_review"] = None
			state["control_state"]["halted"] = False
			self._clear_review_checkpoint(state)
		return state

	async def _node_plan_fallback(self, state: LayeredExecutionState) -> LayeredExecutionState:
		request_plan = dict(state["task_execution_state"].get("request_plan") or {})
		need_external = bool(request_plan.get("intent_router", {}).get("need_external"))
		state["task_execution_state"]["fallback_graph"] = self.profile.get("fallback", {}).get("graph", "external_search_graph") if need_external else state["task_execution_state"].get("fallback_graph")
		return state

	def _build_graph_nodes(self) -> dict[str, list[StateNode]]:
		return {
			"intent_router_graph": [self._node_retrieve_knowledge, self._node_route_intent],
			"rag_qa_graph": [self._node_retrieve_knowledge, self._node_prepare_rag],
			"expense_record_graph": [self._node_prepare_graph_requirements, self._node_apply_review_response, self._node_execute_expense_record, self._node_detect_review_need],
			"schedule_graph": [self._node_prepare_graph_requirements, self._node_apply_review_response, self._node_execute_schedule, self._node_detect_review_need],
			"document_summary_graph": [self._node_prepare_graph_requirements, self._node_detect_review_need, self._node_apply_review_response, self._node_execute_document_summary],
			"external_search_graph": [self._node_plan_fallback, self._node_execute_external_retrieval, self._node_execute_external_summary],
			"human_review_graph": [self._node_detect_review_need, self._node_apply_review_response],
		}

	async def _run_graph_nodes(self, graph_name: str, state: LayeredExecutionState) -> LayeredExecutionState:
		compiled = self._compile_langgraph(graph_name)
		if compiled is not None:
			state["control_state"]["used_langgraph"] = True
			result = await compiled.ainvoke(state)
			return result
		for node in self._graph_nodes.get(graph_name, []):
			state = await node(state)
			if state["control_state"].get("halted"):
				break
		return state

	async def run_graph(self, graph_name: str, state: LayeredExecutionState) -> LayeredExecutionState:
		if graph_name == "core_plus_execution_graph":
			compiled = self._compile_langgraph(graph_name)
			if compiled is not None:
				state["control_state"]["used_langgraph"] = True
				return await compiled.ainvoke(state)
			state = await self._run_graph_nodes("intent_router_graph", state)
			next_graph = self._route_after_intent_router(state)
			if next_graph in self._graph_nodes and next_graph != "external_search_graph":
				state = await self._run_graph_nodes(next_graph, state)
				after_domain = self._route_after_domain_graph(state)
				if after_domain == "human_review_graph":
					state = await self._run_graph_nodes("human_review_graph", state)
					after_review = self._route_after_human_review(state)
					if after_review == "external_search_graph":
						state = await self._run_graph_nodes("external_search_graph", state)
				elif after_domain == "external_search_graph":
					state = await self._run_graph_nodes("external_search_graph", state)
			else:
				state = await self._run_graph_nodes("external_search_graph", state)
			return state
		return await self._run_graph_nodes(graph_name, state)

	async def prepare(self, input_text: str, context: dict[str, Any] | None, task: dict[str, Any] | None = None) -> dict[str, Any]:
		state = self.build_layered_state(input_text, context, task)
		state = await self.run_graph("core_plus_execution_graph", state)
		next_graph = str(state["task_execution_state"].get("selected_graph") or state["control_state"].get("next_graph") or "intent_router_graph")
		return {
			"selected_graph": next_graph,
			"state": state,
			"request_plan": state["task_execution_state"].get("request_plan") or self.build_request_plan(input_text, context, task),
			"knowledge_bootstrap": state["knowledge_context"].get("bootstrap", {}),
			"review_state": state["review_state"],
		}

	async def resume_review(self, input_text: str, context: dict[str, Any] | None, task: dict[str, Any] | None = None) -> dict[str, Any]:
		next_context = dict(context or {})
		session_id = str(next_context.get("session_id") or "")
		checkpoint = self.load_review_checkpoint(session_id) if session_id else None
		if checkpoint is None:
			return await self.prepare(input_text, next_context, task)

		state = self.build_layered_state(input_text, next_context, task)
		state["task_execution_state"].update(deepcopy(checkpoint.get("task_execution_state") or {}))
		state["review_state"].update(deepcopy(checkpoint.get("review_state") or {}))
		state["review_state"]["resume_payload"] = dict(next_context.get("metadata", {}).get("human_review_response") or {})
		graph_name = str(checkpoint.get("graph") or "human_review_graph")
		state = await self.run_graph(graph_name, state)
		if self._route_after_human_review(state) == "external_search_graph":
			state = await self.run_graph("external_search_graph", state)
		return {
			"selected_graph": graph_name,
			"state": state,
			"request_plan": state["task_execution_state"].get("request_plan") or self.build_request_plan(input_text, next_context, task),
			"knowledge_bootstrap": state["knowledge_context"].get("bootstrap", {}),
			"review_state": state["review_state"],
		}

	def evaluate_result(self, result: dict[str, Any], request_plan: dict[str, Any], preparation: dict[str, Any] | None = None) -> dict[str, Any]:
		execution_result = dict(result.get("execution_result") or {})
		raw_final_output = execution_result.get("final_output")
		final_output = dict(raw_final_output) if isinstance(raw_final_output, dict) else {}
		output_requirements = list((result.get("task") or {}).get("output_requirements") or [])
		thresholds = self.profile.get("data_routing", {})
		preparation_state = dict((preparation or {}).get("state") or {})
		task_state = dict(preparation_state.get("task_execution_state") or {})
		knowledge_context = dict(preparation_state.get("knowledge_context") or {})
		issues: list[str] = []
		score = 1.0

		if not execution_result.get("steps"):
			issues.append("no_steps_executed")
			score -= 0.35
		if raw_final_output not in (None, {}) and not isinstance(raw_final_output, dict):
			issues.append("output_format_invalid")
			score -= 0.25
		if not final_output:
			issues.append("empty_final_output")
			score -= 0.4
		failed_steps = [step.get("name", "") for step in execution_result.get("steps", []) if step.get("status") not in {None, "success", "completed", "ok"}]
		if failed_steps:
			issues.append("step_failures")
			score -= min(0.25, 0.08 * len(failed_steps))
		if output_requirements and not final_output:
			issues.append("missing_required_output")
			score -= 0.2
		non_strict_requirements = {"text", "message", "artifact", "document", "file", "analysis"}
		strict_output_fields = [str(field) for field in output_requirements if str(field) and str(field) not in non_strict_requirements]
		missing_output_fields = [field for field in strict_output_fields if not final_output.get(field)]
		if missing_output_fields:
			issues.append("missing_required_fields")
			score -= min(0.25, 0.08 * len(missing_output_fields))
		pending_review = dict(task_state.get("pending_review") or {})
		if pending_review.get("missing_fields") and not final_output and "missing_required_fields" not in issues:
			issues.append("missing_required_fields")
			score -= min(0.2, 0.06 * len(list(pending_review.get("missing_fields") or [])))
		retrieval = dict(knowledge_context.get("retrieval") or {})
		retrieval_hits = list(retrieval.get("hits") or [])
		if request_plan.get("intent_router", {}).get("need_rag") and not retrieval_hits:
			issues.append("insufficient_knowledge_retrieval")
			score -= 0.18
		if request_plan.get("intent_router", {}).get("need_external"):
			issues.append("need_latest_external_information")
			score -= 0.1
		if request_plan.get("intent_router", {}).get("complexity") == "high":
			issues.append("planning_complexity_high")
			score -= 0.05

		normalized_score = max(0.0, min(1.0, round(score, 3)))
		if normalized_score < float(thresholds.get("fallback_threshold", 0.72)):
			issues.append("low_confidence")
		fallback_conditions = set(self.profile.get("fallback", {}).get("conditions", []))
		should_fallback = any(issue in fallback_conditions for issue in issues)
		return {
			"pass": not should_fallback and "empty_final_output" not in issues,
			"score": normalized_score,
			"issues": issues,
			"failed_steps": failed_steps,
			"missing_output_fields": missing_output_fields,
			"should_fallback_external": should_fallback,
			"can_store_to_kb": normalized_score >= float(thresholds.get("knowledge_base_threshold", 0.9)) and not should_fallback,
			"can_store_to_training_pool": normalized_score >= float(thresholds.get("training_pool_threshold", 0.65)),
		}

	def build_data_routing(self, result: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
		task = dict(result.get("task") or {})
		intent = str(task.get("intent") or "general")
		stable_intents = set(self.profile.get("data_routing", {}).get("stable_intents", []))
		if evaluation["can_store_to_kb"]:
			primary_sink = "knowledge_base"
		elif evaluation["can_store_to_training_pool"]:
			primary_sink = "training_pool"
		elif evaluation["should_fallback_external"]:
			primary_sink = "review_pool"
		else:
			primary_sink = "discard"
		return {
			"primary_sink": primary_sink,
			"sinks": {
				"knowledge_base": primary_sink == "knowledge_base" and intent in stable_intents,
				"training_pool": primary_sink in {"knowledge_base", "training_pool"},
				"review_pool": primary_sink == "review_pool",
				"discard": primary_sink == "discard"
			},
			"reason": ",".join(evaluation["issues"]) if evaluation["issues"] else "high_quality_result"
		}

	def build_training_signal(self, result: dict[str, Any], evaluation: dict[str, Any], routing: dict[str, Any], request_plan: dict[str, Any]) -> dict[str, Any]:
		task = dict(result.get("task") or {})
		local_profile = dict(request_plan.get("intent_router", {}).get("local_profile") or {})
		return {
			"eligible": routing["sinks"].get("training_pool", False),
			"profile": str(local_profile.get("adapter_hint", {}).get("training_profile") or local_profile.get("name") or "lora_sft"),
			"local_profile": local_profile,
			"sample_type": "user_execution_trace",
			"quality_score": evaluation["score"],
			"intent": task.get("intent", "general"),
			"version_tag": self.profile.get("version", "core_plus")
		}

	def build_runtime_stats(self, request_plan: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
		local_first = bool(request_plan.get("intent_router", {}).get("local_first"))
		local_profile = dict(request_plan.get("intent_router", {}).get("local_profile") or {})
		capability_orchestration = dict(request_plan.get("capability_orchestration") or {})
		fallback = bool(evaluation["should_fallback_external"])
		return {
			"local_first_request": local_first,
			"local_profile": local_profile,
			"autonomous_capability_requested": bool(capability_orchestration.get("trigger_autonomous_implementation")),
			"local_capability_targets": list(capability_orchestration.get("local_capabilities") or []),
			"external_capability_targets": list(capability_orchestration.get("external_capabilities") or []),
			"external_direct_request": not local_first,
			"local_success": local_first and not fallback,
			"local_failed_to_external": local_first and fallback,
			"final_adopted_mode": "external_fallback" if fallback else "local_composite"
		}

	def build_review_checkpoint(self, request_plan: dict[str, Any], evaluation: dict[str, Any], execution_result: dict[str, Any]) -> dict[str, Any] | None:
		if not self.profile.get("human_review", {}).get("pause_on_missing_fields", True):
			return None
		if not evaluation["issues"]:
			return None
		reviewable = set(self.profile.get("human_review", {}).get("reviewable_issue_codes", [])) | {"missing_required_output", "need_latest_external_information", "missing_required_fields"}
		reason_codes = [issue for issue in evaluation["issues"] if issue in reviewable]
		if reason_codes:
			return {
				"status": "awaiting_user",
				"graph": "human_review_graph",
				"reason_codes": reason_codes,
				"failed_steps": execution_result.get("steps", [])
			}
		return None

	def enrich_result(self, result: dict[str, Any], request_plan: dict[str, Any], preparation: dict[str, Any] | None = None) -> dict[str, Any]:
		evaluation = self.evaluate_result(result, request_plan, preparation=preparation)
		routing = self.build_data_routing(result, evaluation)
		training_signal = self.build_training_signal(result, evaluation, routing, request_plan)
		stats = self.build_runtime_stats(request_plan, evaluation)
		execution_result = dict(result.get("execution_result") or {})
		execution_result["core_plus"] = {
			"request_plan": request_plan,
			"preparation": preparation or {},
			"evaluation": evaluation,
			"data_routing": routing,
			"training_signal": training_signal,
			"runtime_stats": stats,
			"human_review_checkpoint": self.build_review_checkpoint(request_plan, evaluation, execution_result)
		}
		result["execution_result"] = execution_result
		result["core_version"] = self.profile.get("version", "core_plus")
		return result
