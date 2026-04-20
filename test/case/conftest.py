from __future__ import annotations

import copy
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from nethub_runtime.core.memory import semantic_policy_store as semantic_policy_store_module
from nethub_runtime.core.routers import core_api
from nethub_runtime.core.services.core_engine import AICore
from test.conftest import build_budget_semantic_policy


REPORTS_ROOT = Path(__file__).resolve().parents[2] / "reports"


def _reset_semantic_policy_memory(db_path: Path) -> None:
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for table_name in tables:
            conn.execute(f'DELETE FROM "{table_name}"')
        conn.commit()


def _reset_runtime_state(engine: AICore) -> None:
    session_store = engine.context_manager.session_store
    with session_store._lock:
        session_store._state.clear()
    try:
        session_store._persistence.clear_all()
    except AttributeError:
        pass

    vector_store = engine.vector_store
    vector_store._items.clear()
    persistence = getattr(vector_store, "_persistence", None)
    if persistence is not None:
        with persistence._lock:
            with persistence._connect() as conn:
                conn.execute("DELETE FROM vector_items")


@pytest.fixture
def isolated_case_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AICore:
    home_root = tmp_path / "home"
    generated_root = tmp_path / "generated_artifacts"
    semantic_db_path = tmp_path / "semantic_policy_memory.sqlite3"

    home_root.mkdir(parents=True, exist_ok=True)
    generated_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home_root))
    monkeypatch.setenv("NETHUB_HOME", str(home_root / ".nethub"))
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(generated_root))
    monkeypatch.setattr(semantic_policy_store_module, "SEMANTIC_POLICY_MEMORY_DB_PATH", semantic_db_path)

    core_api.core_engine = AICore()
    core_api.core_engine.model_router.mock_llm_calls = True
    core_api.core_engine.model_router.config.setdefault("development", {})["mock_llm_calls"] = True

    _reset_semantic_policy_memory(semantic_db_path)
    _reset_runtime_state(core_api.core_engine)
    return core_api.core_engine


@pytest.fixture
def isolated_case_budget_runtime(isolated_case_runtime: AICore) -> AICore:
    coordinator = isolated_case_runtime.execution_coordinator
    original_policy = copy.deepcopy(coordinator.semantic_policy)
    original_embedding_model = coordinator._embedding_model
    coordinator.semantic_policy = build_budget_semantic_policy()
    coordinator._embedding_model = None
    try:
        yield isolated_case_runtime
    finally:
        coordinator.semantic_policy = original_policy
        coordinator._embedding_model = original_embedding_model


def pytest_configure(config: pytest.Config) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config._nesthub_case_report_timestamp = timestamp
    config._nesthub_case_results: list[dict[str, Any]] = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or "test/case/" not in report.nodeid:
        return
    item.config._nesthub_case_results.append(
        {
            "nodeid": report.nodeid,
            "outcome": report.outcome,
            "duration": report.duration,
            "longrepr": "" if report.passed else str(report.longrepr),
        }
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    results = [item for item in getattr(session.config, "_nesthub_case_results", []) if item["nodeid"]]
    if not results:
        return

    date_dir = REPORTS_ROOT / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    report_path = date_dir / f"{session.config._nesthub_case_report_timestamp}_test_case_report.md"

    passed = sum(1 for item in results if item["outcome"] == "passed")
    failed = sum(1 for item in results if item["outcome"] == "failed")
    skipped = sum(1 for item in results if item["outcome"] == "skipped")

    lines = [
        "# NestHub Test Case Report",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Scope: test/case",
        f"- Exit status: {exitstatus}",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        f"- Skipped: {skipped}",
        "",
        "## Case Results",
        "",
    ]
    for item in results:
        lines.append(f"### {item['nodeid']}")
        lines.append(f"- Outcome: {item['outcome']}")
        lines.append(f"- Duration: {item['duration']:.3f}s")
        if item["longrepr"]:
            lines.append("- Failure:")
            lines.append("```")
            lines.append(item["longrepr"].strip())
            lines.append("```")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")