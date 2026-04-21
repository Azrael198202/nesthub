from __future__ import annotations

import asyncio
from pathlib import Path

from nethub_runtime.execution.pipeline import ExecutionUpgradePipeline
from nethub_runtime.execution.dispatcher import ExecutionGraphDispatcher


class _FakeSessionStore:
    def __init__(self) -> None:
        self.payloads: dict[str, dict] = {}

    def get(self, session_id: str) -> dict:
        return dict(self.payloads.get(session_id, {"records": []}))

    def patch(self, session_id: str, patch_data: dict) -> dict:
        payload = dict(self.payloads.get(session_id, {"records": []}))
        payload.update(patch_data)
        self.payloads[session_id] = payload
        return dict(payload)

    def append_records(self, session_id: str, records: list[dict]) -> dict:
        payload = dict(self.payloads.get(session_id, {"records": []}))
        payload.setdefault("records", [])
        payload["records"].extend(records)
        self.payloads[session_id] = payload
        return dict(payload)


class _FakeContextManager:
    def __init__(self) -> None:
        self.session_store = _FakeSessionStore()


class _FakeVectorStore:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def add_knowledge(self, *, namespace: str, content: str, metadata: dict | None = None, item_id: str | None = None) -> dict:
        record = {"id": item_id or f"{namespace}_{len(self.records) + 1}", "namespace": namespace, "content": content, "metadata": metadata or {}}
        self.records.append(record)
        return record

    def search(self, query: str, top_k: int = 5, namespace: str | None = None) -> list[dict]:
        hits = [item for item in self.records if namespace is None or item["namespace"] == namespace]
        return hits[:top_k]


class _FakeCore:
    def __init__(self, execution_coordinator: object | None = None) -> None:
        self.vector_store = _FakeVectorStore()
        self.context_manager = _FakeContextManager()
        self.execution_coordinator = execution_coordinator


class _FakeScheduleCoordinator:
    def __init__(self, session_store: _FakeSessionStore, records: list[dict]) -> None:
        self.session_store = session_store
        self._records = records

    def _extract_records(self, _text: str) -> list[dict]:
        return [dict(item) for item in self._records]


class _FakeExpenseCoordinator:
    def __init__(self, session_store: _FakeSessionStore, records: list[dict]) -> None:
        self.session_store = session_store
        self._records = records

    def _extract_records(self, _text: str) -> list[dict]:
        return [dict(item) for item in self._records]


def test_pipeline_bootstraps_knowledge_from_runtime_files() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())

    summary = pipeline.bootstrap_knowledge_base()

    assert summary["document_count"] >= 3
    assert "core_plus_capability" in summary["namespaces"]
    assert "vector" in summary["providers"]


def test_pipeline_preparation_selects_subgraph_and_builds_layered_state() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())

    prepared = asyncio.run(pipeline.prepare("请对文档做总结", {"session_id": "s-1", "metadata": {}}))

    assert prepared["selected_graph"] == "document_summary_graph"
    state = prepared["state"]
    assert "session_state" in state
    assert "user_long_term_state" in state
    assert "task_execution_state" in state
    assert state["task_execution_state"]["selected_graph"] == "document_summary_graph"
    assert "used_langgraph" in state["control_state"]


def test_pipeline_execution_supergraph_routes_to_external_fallback() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())

    prepared = asyncio.run(pipeline.prepare("请给我最新文档总结", {"session_id": "s-fallback", "metadata": {}}))

    state = prepared["state"]
    assert state["task_execution_state"]["selected_graph"] == "document_summary_graph"
    assert state["task_execution_state"]["fallback_graph"] == "external_search_graph"
    assert "document_result" in state["task_execution_state"] or state["task_execution_state"].get("pending_review") is not None


def test_pipeline_human_review_pause_checkpoint_is_created_for_missing_outputs() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())
    request_plan = pipeline.build_request_plan("latest official summary", {"metadata": {}})
    result = {
        "task": {"intent": "document_summary", "output_requirements": ["summary"]},
        "execution_result": {
            "steps": [{"name": "analyze_document", "status": "failed"}],
            "final_output": {}
        }
    }

    enriched = pipeline.enrich_result(result, request_plan, preparation={})
    checkpoint = enriched["execution_result"]["core_plus"]["human_review_checkpoint"]

    assert checkpoint is not None
    assert checkpoint["status"] == "awaiting_user"


def test_pipeline_evaluation_falls_back_when_rag_needed_but_no_knowledge_hits() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())
    request_plan = pipeline.build_request_plan("请根据知识库总结这个主题", {"metadata": {}})
    result = {
        "task": {"intent": "faq_answer", "output_requirements": ["summary"]},
        "execution_result": {
            "steps": [{"name": "answer", "status": "completed"}],
            "final_output": {"summary": "本地回答"},
        },
    }
    preparation = {
        "state": {
            "knowledge_context": {"retrieval": {"hits": []}},
            "task_execution_state": {},
        }
    }

    evaluation = pipeline.evaluate_result(result, request_plan, preparation=preparation)

    assert "insufficient_knowledge_retrieval" in evaluation["issues"]
    assert evaluation["should_fallback_external"] is True


def test_pipeline_evaluation_falls_back_on_invalid_output_and_missing_fields() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())
    request_plan = pipeline.build_request_plan("帮我做总结", {"metadata": {}})
    result = {
        "task": {"intent": "document_summary", "output_requirements": ["summary", "title"]},
        "execution_result": {
            "steps": [{"name": "summarize", "status": "completed"}],
            "final_output": "not-a-json-object",
        },
    }
    preparation = {
        "state": {
            "task_execution_state": {
                "pending_review": {"missing_fields": ["title"]},
            },
            "knowledge_context": {"retrieval": {"hits": [{"id": "k1"}]}},
        }
    }

    evaluation = pipeline.evaluate_result(result, request_plan, preparation=preparation)

    assert "output_format_invalid" in evaluation["issues"]
    assert "missing_required_fields" in evaluation["issues"]
    assert "low_confidence" in evaluation["issues"]
    assert evaluation["should_fallback_external"] is True


def test_pipeline_builds_capability_orchestration_for_schedule_trip_and_flight_request() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())

    request_plan = pipeline.build_request_plan(
        "看看我的日程安排，如果4月22号没有预约，给我制定一个1天的大阪观光计划。6点到了之后，提醒我去坐6点30的飞机",
        {"metadata": {}},
    )

    orchestration = request_plan["capability_orchestration"]
    assert orchestration["matched"] is True
    assert "schedule_availability_query" in orchestration["local_capabilities"]
    assert "reminder_create_trigger" in orchestration["local_capabilities"]
    assert "travel_itinerary_generation" in orchestration["external_capabilities"]
    assert request_plan["intent_router"]["need_external"] is True


def test_dispatcher_exposes_autonomous_capability_targets() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())
    request_plan = pipeline.build_request_plan(
        "看看我的日程安排，如果4月22号没有预约，给我制定一个1天的大阪观光计划。6点到了之后，提醒我去坐6点30的飞机",
        {"metadata": {}},
    )
    dispatcher = ExecutionGraphDispatcher(pipeline.profile)

    dispatch = dispatcher.dispatch(request_plan, task={"intent": "schedule_create"})

    assert dispatch["autonomous_actions"]["trigger_autonomous_implementation"] is True
    assert "schedule_availability_query" in dispatch["autonomous_actions"]["local_capability_targets"]
    assert "travel_itinerary_generation" in dispatch["autonomous_actions"]["external_capability_targets"]


def test_pipeline_persists_and_resumes_human_review_checkpoint() -> None:
    core = _FakeCore()
    pipeline = ExecutionUpgradePipeline(base_core=core)
    prepared = asyncio.run(pipeline.prepare("请对文档做总结", {"session_id": "s-2", "metadata": {}}))
    checkpoint = core.context_manager.session_store.get("s-2").get("core_plus_review_checkpoint")

    assert checkpoint is not None
    assert checkpoint["graph"] == "document_summary_graph"

    resumed = asyncio.run(
        pipeline.resume_review(
            "补充文档引用",
            {"session_id": "s-2", "metadata": {"human_review_response": {"document_reference": "received/brief.txt"}}},
        )
    )

    assert resumed["state"]["review_state"]["status"] == "resumed"
    assert resumed["state"]["task_execution_state"]["pending_review"] is None
    assert core.context_manager.session_store.get("s-2").get("core_plus_review_checkpoint") is None


def test_pipeline_routes_from_review_to_fallback_after_resume() -> None:
    core = _FakeCore()
    pipeline = ExecutionUpgradePipeline(base_core=core)

    asyncio.run(pipeline.prepare("请给我最新文档总结", {"session_id": "s-3", "metadata": {}}))
    resumed = asyncio.run(
        pipeline.resume_review(
            "补充文档引用",
            {"session_id": "s-3", "metadata": {"human_review_response": {"document_reference": "received/brief.txt"}}},
        )
    )

    assert resumed["state"]["review_state"]["status"] == "resumed"
    assert resumed["state"]["task_execution_state"]["fallback_graph"] == "external_search_graph"
    assert "external_summary" in resumed["state"]["task_execution_state"]


def test_pipeline_external_graph_executes_runtime_step_placeholders_without_core_runtime() -> None:
    pipeline = ExecutionUpgradePipeline(base_core=_FakeCore())

    prepared = asyncio.run(pipeline.prepare("请给我最新文档总结", {"session_id": "s-4", "metadata": {"human_review_response": {"document_reference": "received/brief.txt"}}}))

    assert prepared["state"]["task_execution_state"]["document_result"]["status"] == "unavailable"
    if prepared["state"]["task_execution_state"].get("fallback_graph"):
        assert prepared["state"]["task_execution_state"]["external_summary"]["status"] == "unavailable"


def test_pipeline_schedule_graph_executes_before_review_and_captures_missing_time() -> None:
    core = _FakeCore()
    coordinator = _FakeScheduleCoordinator(
        core.context_manager.session_store,
        [{"time": "2026-04-22", "content": "项目例会", "location": "会议室A"}],
    )
    core.execution_coordinator = coordinator
    pipeline = ExecutionUpgradePipeline(base_core=core)

    prepared = asyncio.run(pipeline.prepare("明天项目例会", {"session_id": "s-5", "metadata": {}}))

    state = prepared["state"]
    assert state["task_execution_state"]["selected_graph"] == "schedule_graph"
    assert state["task_execution_state"]["schedule_extract_result"]["records"][0]["time"] == "2026-04-22"
    assert state["task_execution_state"]["schedule_persist_result"]["saved"] == 1
    assert state["task_execution_state"]["extracted_fields"]["date"] == "2026-04-22"
    assert state["task_execution_state"]["pending_review"]["missing_fields"] == ["time"]


def test_pipeline_schedule_graph_persists_when_date_and_time_are_available() -> None:
    core = _FakeCore()
    coordinator = _FakeScheduleCoordinator(
        core.context_manager.session_store,
        [{"time": "2026-04-22 09:30", "content": "项目例会", "location": "会议室A"}],
    )
    core.execution_coordinator = coordinator
    pipeline = ExecutionUpgradePipeline(base_core=core)

    prepared = asyncio.run(pipeline.prepare("明天 09:30 项目例会", {"session_id": "s-6", "metadata": {}}))

    state = prepared["state"]
    assert state["review_state"]["status"] != "awaiting_user"
    assert state["task_execution_state"]["schedule_result"]["status"] == "completed"
    assert state["task_execution_state"]["extracted_fields"]["date"] == "2026-04-22"
    assert state["task_execution_state"]["extracted_fields"]["time"] == "09:30"
    assert len(core.context_manager.session_store.get("s-6")["records"]) == 1


def test_pipeline_expense_graph_executes_before_review_and_captures_missing_amount() -> None:
    core = _FakeCore()
    coordinator = _FakeExpenseCoordinator(
        core.context_manager.session_store,
        [{"time": "2026-04-22", "amount": 0, "content": "咖啡", "location": "便利店", "label": "food_and_drink"}],
    )
    core.execution_coordinator = coordinator
    pipeline = ExecutionUpgradePipeline(base_core=core)

    prepared = asyncio.run(pipeline.prepare("今天消费记录一杯咖啡", {"session_id": "s-7", "metadata": {}}))

    state = prepared["state"]
    assert state["task_execution_state"]["selected_graph"] == "expense_record_graph"
    assert state["task_execution_state"]["expense_extract_result"]["records"][0]["content"] == "咖啡"
    assert state["task_execution_state"]["expense_persist_result"]["saved"] == 1
    assert state["task_execution_state"]["extracted_fields"]["date"] == "2026-04-22"
    assert state["task_execution_state"]["pending_review"]["missing_fields"] == ["amount"]


def test_pipeline_expense_graph_persists_when_amount_and_date_are_available() -> None:
    core = _FakeCore()
    coordinator = _FakeExpenseCoordinator(
        core.context_manager.session_store,
        [{"time": "2026-04-22", "amount": 500, "content": "咖啡", "location": "便利店", "label": "food_and_drink"}],
    )
    core.execution_coordinator = coordinator
    pipeline = ExecutionUpgradePipeline(base_core=core)

    prepared = asyncio.run(pipeline.prepare("今天消费记录咖啡500元", {"session_id": "s-8", "metadata": {}}))

    state = prepared["state"]
    assert state["review_state"]["status"] != "awaiting_user"
    assert state["task_execution_state"]["expense_result"]["status"] == "completed"
    assert state["task_execution_state"]["extracted_fields"]["amount"] == 500
    assert state["task_execution_state"]["extracted_fields"]["date"] == "2026-04-22"
    assert len(core.context_manager.session_store.get("s-8")["records"]) == 1


def test_core_plus_engine_file_no_longer_contains_rule_keywords() -> None:
    engine_path = Path("/home/lw-ai/Documents/nesthub/nethub_runtime/core+/engine.py")
    content = engine_path.read_text(encoding="utf-8")

    assert "整理文档" not in content
    assert "查一下" not in content
    assert "买菜" not in content