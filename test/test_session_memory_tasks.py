"""
Regression tests for Tasks 1, 2, 3:
  - Task 1: Main + task session architecture, context window limiting
  - Task 2: Completed tool logic (web search, filesystem, shell, code execution)
  - Task 3: SQLite session persistence, vector store embedding support
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Task 1: Session architecture
# ---------------------------------------------------------------------------

class TestTaskSessionArchitecture:
    def _make_store(self, **kwargs):
        from nethub_runtime.core.memory.session_store import SessionStore
        return SessionStore(**kwargs)

    def test_create_task_session_returns_prefixed_id(self):
        store = self._make_store()
        tid = store.create_task_session("user_123", "budget_analysis")
        assert tid == "task:user_123:budget_analysis"

    def test_task_session_stores_meta(self):
        store = self._make_store()
        tid = store.create_task_session("user_123", "image_gen")
        payload = store.get(tid)
        assert payload["_meta"]["main_session_id"] == "user_123"
        assert payload["_meta"]["topic"] == "image_gen"
        assert payload["_meta"]["type"] == "task_session"

    def test_create_same_task_session_twice_is_idempotent(self):
        store = self._make_store()
        tid1 = store.create_task_session("user_A", "topic_X")
        store.append_records(tid1, [{"role": "user", "content": "hello"}])
        tid2 = store.create_task_session("user_A", "topic_X")  # same key
        assert tid1 == tid2
        # Records should NOT be wiped on second call
        assert len(store.get(tid2)["records"]) == 1

    def test_task_sessions_are_isolated_from_main(self):
        store = self._make_store()
        tid = store.create_task_session("main_1", "task_a")
        store.append_records(tid, [{"role": "user", "content": "task msg"}])
        store.append_records("main_1", [{"role": "user", "content": "main msg"}])
        task_records = store.get(tid)["records"]
        main_records = store.get("main_1")["records"]
        assert len(task_records) == 1
        assert len(main_records) == 1
        assert task_records[0]["content"] == "task msg"
        assert main_records[0]["content"] == "main msg"

    def test_close_task_session_merges_summary_to_main(self):
        store = self._make_store()
        tid = store.create_task_session("main_2", "reporting")
        store.close_task_session(tid, summary="Generated Q1 report", merge_to_main=True)
        main_records = store.get("main_2")["records"]
        assert len(main_records) == 1
        assert main_records[0]["type"] == "task_summary"
        assert "Q1 report" in main_records[0]["content"]
        # Task session should be gone
        assert store.get(tid) == {"records": []}

    def test_close_task_session_without_merge(self):
        store = self._make_store()
        tid = store.create_task_session("main_3", "ephemeral")
        store.close_task_session(tid, summary="done", merge_to_main=False)
        # Nothing in main
        assert store.get("main_3")["records"] == []

    def test_list_task_sessions(self):
        store = self._make_store()
        store.create_task_session("user_X", "topic_a")
        store.create_task_session("user_X", "topic_b")
        store.create_task_session("user_Y", "topic_a")
        x_sessions = store.list_task_sessions("user_X")
        assert "task:user_X:topic_a" in x_sessions
        assert "task:user_X:topic_b" in x_sessions
        assert "task:user_Y:topic_a" not in x_sessions

    def test_is_task_session(self):
        store = self._make_store()
        tid = store.create_task_session("m", "t")
        assert store.is_task_session(tid) is True
        assert store.is_task_session("m") is False

    def test_main_session_id_from_task(self):
        store = self._make_store()
        tid = store.create_task_session("main_99", "subtask")
        assert store.main_session_id(tid) == "main_99"


class TestContextWindowLimiting:
    def _make_store(self, max_window: int):
        from nethub_runtime.core.memory.session_store import SessionStore
        return SessionStore(max_window_messages=max_window)

    def test_window_trims_oldest_messages(self):
        store = self._make_store(max_window=5)
        for i in range(10):
            store.append_records("s", [{"role": "user", "content": f"msg {i}"}])
        records = store.get("s")["records"]
        assert len(records) == 5
        assert records[0]["content"] == "msg 5"
        assert records[-1]["content"] == "msg 9"

    def test_window_at_exact_limit_no_trim(self):
        store = self._make_store(max_window=3)
        for i in range(3):
            store.append_records("s", [{"role": "user", "content": f"msg {i}"}])
        assert len(store.get("s")["records"]) == 3

    def test_no_window_no_trim(self):
        from nethub_runtime.core.memory.session_store import SessionStore
        store = SessionStore()  # no max_window
        for i in range(30):
            store.append_records("s", [{"role": "user", "content": f"m{i}"}])
        assert len(store.get("s")["records"]) == 30


class TestContextManagerTaskSession:
    def test_load_creates_task_session_when_topic_given(self):
        from nethub_runtime.core.services.context_manager import ContextManager
        cm = ContextManager()
        ctx = cm.load({"session_id": "user_1", "task_topic": "analysis"})
        assert ctx.session_id == "task:user_1:analysis"
        assert ctx.metadata["main_session_id"] == "user_1"
        assert ctx.metadata["task_topic"] == "analysis"

    def test_load_uses_main_session_without_topic(self):
        from nethub_runtime.core.services.context_manager import ContextManager
        cm = ContextManager()
        ctx = cm.load({"session_id": "user_1"})
        assert ctx.session_id == "user_1"
        assert ctx.metadata["main_session_id"] == "user_1"
        assert "task_topic" not in ctx.metadata

    def test_enrich_writes_back_to_store(self):
        from nethub_runtime.core.services.context_manager import ContextManager
        cm = ContextManager()
        ctx = cm.load({"session_id": "user_enrich"})
        cm.enrich(ctx)
        payload = cm.session_store.get("user_enrich")
        assert "_last_enriched_at" in payload
        assert payload["_record_count"] == 0


# ---------------------------------------------------------------------------
# Task 3: Session persistence (SQLite)
# ---------------------------------------------------------------------------

class TestSQLiteSessionPersistence:
    def _make_persistence(self, tmp_path: Path):
        from nethub_runtime.core.memory.session_persistence import SQLiteSessionPersistence
        return SQLiteSessionPersistence(tmp_path / "sessions.db")

    def test_save_and_load_roundtrip(self, tmp_path):
        p = self._make_persistence(tmp_path)
        payload = {"records": [{"role": "user", "content": "hello"}], "counter": 1}
        p.save("sess_1", payload)
        loaded = p.load("sess_1")
        assert loaded is not None
        assert loaded["counter"] == 1
        assert loaded["records"][0]["content"] == "hello"

    def test_load_missing_returns_none(self, tmp_path):
        p = self._make_persistence(tmp_path)
        assert p.load("nonexistent") is None

    def test_upsert_updates_existing(self, tmp_path):
        p = self._make_persistence(tmp_path)
        p.save("sess_u", {"records": [], "v": 1})
        p.save("sess_u", {"records": [{"role": "user", "content": "x"}], "v": 2})
        loaded = p.load("sess_u")
        assert loaded["v"] == 2
        assert len(loaded["records"]) == 1

    def test_delete(self, tmp_path):
        p = self._make_persistence(tmp_path)
        p.save("sess_d", {"records": []})
        p.delete("sess_d")
        assert p.load("sess_d") is None

    def test_list_ids(self, tmp_path):
        p = self._make_persistence(tmp_path)
        p.save("s1", {"records": []})
        p.save("s2", {"records": []})
        ids = p.list_ids()
        assert "s1" in ids
        assert "s2" in ids

    def test_session_store_restores_from_persistence(self, tmp_path):
        from nethub_runtime.core.memory.session_persistence import SQLiteSessionPersistence
        from nethub_runtime.core.memory.session_store import SessionStore
        db_path = tmp_path / "sessions.db"
        # Write once
        p1 = SQLiteSessionPersistence(db_path)
        p1.save("restored", {"records": [{"role": "user", "content": "persisted"}]})
        # New store instance pointing to same DB
        store = SessionStore(persistence=SQLiteSessionPersistence(db_path))
        payload = store.get("restored")
        assert payload["records"][0]["content"] == "persisted"

    def test_append_records_saves_to_persistence(self, tmp_path):
        from nethub_runtime.core.memory.session_persistence import SQLiteSessionPersistence
        from nethub_runtime.core.memory.session_store import SessionStore
        db_path = tmp_path / "sessions.db"
        p = SQLiteSessionPersistence(db_path)
        store = SessionStore(persistence=p)
        store.append_records("persist_test", [{"role": "user", "content": "A"}])
        store.append_records("persist_test", [{"role": "user", "content": "B"}])
        # Read directly from SQLite (bypass in-memory)
        loaded = p.load("persist_test")
        assert loaded is not None
        assert len(loaded["records"]) == 2


# ---------------------------------------------------------------------------
# Task 3: Vector store embeddings
# ---------------------------------------------------------------------------

class TestVectorStoreEmbedding:
    def _make_embedding_fn(self):
        """Fake deterministic embedding: bag-of-chars frequency vector (dim=26)."""
        def embed(text: str) -> list[float]:
            vec = [0.0] * 26
            for ch in text.lower():
                if ch.isalpha():
                    vec[ord(ch) - ord("a")] += 1.0
            total = sum(vec) or 1.0
            return [v / total for v in vec]
        return embed

    def test_search_with_embedding_fn_uses_cosine(self):
        from nethub_runtime.core.memory.vector_store import VectorStore
        store = VectorStore(embedding_fn=self._make_embedding_fn())
        store.add_knowledge(namespace="test", content="apple fruit healthy food")
        store.add_knowledge(namespace="test", content="car engine motor vehicle")
        results = store.search("fruit apple", top_k=2, namespace="test")
        assert results[0]["content"] == "apple fruit healthy food"

    def test_search_fallback_to_keyword_when_no_embedding(self):
        from nethub_runtime.core.memory.vector_store import VectorStore
        store = VectorStore()  # no embedding_fn
        store.add_knowledge(namespace="kw", content="machine learning model")
        store.add_knowledge(namespace="kw", content="cooking recipe pasta")
        results = store.search("machine learning", top_k=2, namespace="kw")
        assert results[0]["content"] == "machine learning model"

    def test_embedding_stored_on_add(self):
        from nethub_runtime.core.memory.vector_store import VectorStore
        store = VectorStore(embedding_fn=self._make_embedding_fn())
        record = store.add_knowledge(namespace="x", content="hello world")
        assert "embedding" in record
        assert len(record["embedding"]) == 26

    def test_no_embedding_stored_without_fn(self):
        from nethub_runtime.core.memory.vector_store import VectorStore
        store = VectorStore()
        record = store.add_knowledge(namespace="x", content="hello world")
        assert "embedding" not in record

    def test_cosine_similarity_ordered_correctly(self):
        from nethub_runtime.core.memory.vector_store import VectorStore
        store = VectorStore(embedding_fn=self._make_embedding_fn())
        store.add_knowledge(namespace="n", content="aaaa bbbb")   # 'a' heavy
        store.add_knowledge(namespace="n", content="zzzz xxxx")   # 'z' heavy
        results = store.search("aaaa aaaa", top_k=2, namespace="n")
        assert results[0]["content"] == "aaaa bbbb"


# ---------------------------------------------------------------------------
# Task 2: Tool logic
# ---------------------------------------------------------------------------

class TestFileSystemTool:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello file", encoding="utf-8")
        from nethub_runtime.core.tools.registry import FileSystemTool
        tool = FileSystemTool()
        result = asyncio.run(
            tool.execute({"operation": "read", "path": str(f)})
        )
        assert result["success"] is True
        assert result["content"] == "hello file"

    def test_write_creates_file(self, tmp_path):
        dest = tmp_path / "out.txt"
        from nethub_runtime.core.tools.registry import FileSystemTool
        tool = FileSystemTool()
        result = asyncio.run(
            tool.execute({"operation": "write", "path": str(dest), "content": "written"})
        )
        assert result["success"] is True
        assert dest.read_text() == "written"

    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        from nethub_runtime.core.tools.registry import FileSystemTool
        tool = FileSystemTool()
        result = asyncio.run(
            tool.execute({"operation": "list", "path": str(tmp_path)})
        )
        assert result["success"] is True
        names = [e["name"] for e in result["entries"]]
        assert "a.txt" in names
        assert "b.txt" in names

    def test_exists_for_present_file(self, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("x")
        from nethub_runtime.core.tools.registry import FileSystemTool
        tool = FileSystemTool()
        result = asyncio.run(
            tool.execute({"operation": "exists", "path": str(f)})
        )
        assert result["exists"] is True
        assert result["is_file"] is True

    def test_delete_file(self, tmp_path):
        f = tmp_path / "del.txt"
        f.write_text("bye")
        from nethub_runtime.core.tools.registry import FileSystemTool
        tool = FileSystemTool()
        result = asyncio.run(
            tool.execute({"operation": "delete", "path": str(f)})
        )
        assert result["success"] is True
        assert not f.exists()

    def test_unknown_operation_returns_error(self, tmp_path):
        from nethub_runtime.core.tools.registry import FileSystemTool
        tool = FileSystemTool()
        result = asyncio.run(
            tool.execute({"operation": "teleport", "path": str(tmp_path)})
        )
        assert result["success"] is False
        assert "unknown" in result["error"]


class TestShellExecutionTool:
    def test_allowed_command_runs(self):
        from nethub_runtime.core.tools.registry import ShellExecutionTool
        tool = ShellExecutionTool()
        result = asyncio.run(
            tool.execute({"command": "echo hello"})
        )
        assert result["success"] is True
        assert "hello" in result["stdout"]

    def test_blocked_command_rejected(self):
        from nethub_runtime.core.tools.registry import ShellExecutionTool
        tool = ShellExecutionTool()
        result = asyncio.run(
            tool.execute({"command": "rm -rf /"})
        )
        assert result["success"] is False
        assert "not in the allowed list" in result["error"]

    def test_missing_command_returns_error(self):
        from nethub_runtime.core.tools.registry import ShellExecutionTool
        tool = ShellExecutionTool()
        result = asyncio.run(
            tool.execute({"command": ""})
        )
        assert result["success"] is False


class TestCodeExecutionTool:
    def test_simple_expression(self):
        from nethub_runtime.core.tools.registry import CodeExecutionTool
        tool = CodeExecutionTool()
        result = asyncio.run(
            tool.execute({"code": "x = 1 + 1"})
        )
        assert result["success"] is True
        assert result["locals"]["x"] == 2

    def test_print_captured(self):
        from nethub_runtime.core.tools.registry import CodeExecutionTool
        tool = CodeExecutionTool()
        result = asyncio.run(
            tool.execute({"code": "print('hello from code')"})
        )
        assert result["success"] is True
        assert "hello from code" in result["stdout"]

    def test_syntax_error_returns_failure(self):
        from nethub_runtime.core.tools.registry import CodeExecutionTool
        tool = CodeExecutionTool()
        result = asyncio.run(
            tool.execute({"code": "def broken(:"})
        )
        assert result["success"] is False
        assert result["error"]

    def test_empty_code_returns_error(self):
        from nethub_runtime.core.tools.registry import CodeExecutionTool
        tool = CodeExecutionTool()
        result = asyncio.run(
            tool.execute({"code": "   "})
        )
        assert result["success"] is False


class TestWebSearchTool:
    def test_empty_query_returns_error(self):
        from nethub_runtime.core.tools.registry import WebSearchTool
        tool = WebSearchTool()
        result = asyncio.run(
            tool.execute({"query": ""})
        )
        assert result["success"] is False

    def test_network_error_handled_gracefully(self):
        from nethub_runtime.core.tools.registry import WebSearchTool
        tool = WebSearchTool()
        with patch("urllib.request.urlopen", side_effect=OSError("network down")):
            result = asyncio.run(
                tool.execute({"query": "test"})
            )
        assert result["success"] is False
        assert "results" in result

    def test_successful_response_parsed(self):
        from nethub_runtime.core.tools.registry import WebSearchTool
        fake_response = json.dumps({
            "Heading": "Python programming",
            "Abstract": "Python is a programming language.",
            "AbstractURL": "https://www.python.org",
            "RelatedTopics": [
                {"Text": "Python tutorial", "FirstURL": "https://docs.python.org"},
            ],
        }).encode()

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = fake_response
        mock_resp.decode = lambda: fake_response.decode()

        tool = WebSearchTool()
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = asyncio.run(
                tool.execute({"query": "Python"})
            )
        assert result["success"] is True
        assert len(result["results"]) >= 1
        assert result["results"][0]["snippet"] == "Python is a programming language."
