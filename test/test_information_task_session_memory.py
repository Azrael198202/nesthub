from __future__ import annotations

from pathlib import Path

from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.memory.vector_store import VectorStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.information_agent_service import InformationAgentService


def test_session_store_persists_to_disk(tmp_path: Path) -> None:
    storage_path = tmp_path / "session_store.json"
    store = SessionStore(storage_path=storage_path)
    store.patch("s1", {"configured_agent": {"name": "agent_a"}})

    reloaded = SessionStore(storage_path=storage_path)
    state = reloaded.get("s1")
    assert state["configured_agent"]["name"] == "agent_a"


def test_vector_store_persists_to_disk(tmp_path: Path) -> None:
    policy_path = tmp_path / "vector_store_policy.json"
    storage_path = tmp_path / "vector_store.json"
    store = VectorStore(policy_path=policy_path, storage_path=storage_path)
    store.add_knowledge(namespace="agent_knowledge/topic_a", content="项目甲 节点A 交付", metadata={"record_id": "k1"}, item_id="k1")

    reloaded = VectorStore(policy_path=policy_path, storage_path=storage_path)
    hits = reloaded.search("项目甲", namespace="agent_knowledge/topic_a")
    assert hits
    assert hits[0]["id"] == "k1"


def test_information_agent_uses_topic_task_sessions_and_trims_context(tmp_path: Path) -> None:
    session_store = SessionStore(storage_path=tmp_path / "session_store.json")
    vector_store = VectorStore(policy_path=tmp_path / "vector_store_policy.json", storage_path=tmp_path / "vector_store.json")
    service = InformationAgentService(session_store=session_store, vector_store=vector_store)

    context = CoreContextSchema(session_id="topic-session", trace_id="trace-1")
    create_task = TaskSchema(task_id="t1", intent="create_information_agent", input_text="创建客户档案智能体", domain="agent_management")
    service.manage_information_agent(
        text="创建客户档案智能体",
        task=create_task,
        context=context,
        normalize_yes_no=lambda text: text,
        sanitize_member_value=lambda _key, value: value,
        extract_records=lambda _text: [],
    )

    create_task_2 = TaskSchema(task_id="t2", intent="create_information_agent", input_text="创建供应商档案智能体", domain="agent_management")
    service.manage_information_agent(
        text="创建供应商档案智能体",
        task=create_task_2,
        context=context,
        normalize_yes_no=lambda text: text,
        sanitize_member_value=lambda _key, value: value,
        extract_records=lambda _text: [],
    )

    state = session_store.get("topic-session")
    topic_a = service.normalize_slug("创建客户档案智能体")[:64]
    topic_b = service.normalize_slug("创建供应商档案智能体")[:64]
    assert topic_a in state["task_sessions"]
    assert topic_b in state["task_sessions"]
    assert state["task_sessions"][topic_a]["agent_setup"]["active"] is True
    assert state["task_sessions"][topic_b]["agent_setup"]["active"] is True

    workflow_state = service._default_agent_workflow_state("初始化")
    for i in range(40):
        workflow_state = service._advance_agent_creation_workflow(workflow_state, f"第{i}条消息")

    assert len(workflow_state["conversation"]) == service.CONTEXT_WINDOW_MESSAGES
    assert workflow_state["conversation"][-1]["content"] == "第39条消息"
