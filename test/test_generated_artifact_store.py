from __future__ import annotations

from pathlib import Path

from nethub_runtime.generated.store import GeneratedArtifactStore


def test_generated_artifact_store_persists_json_and_lists_artifacts() -> None:
    store = GeneratedArtifactStore()
    path = store.persist("blueprint", "blueprint_test_case", {"name": "bp", "steps": ["a", "b"]})

    assert path.exists()
    items = store.list_artifacts()
    assert any(item["artifactId"] == "blueprint_test_case" for item in items["blueprint"])


def test_generated_artifact_store_deletes_artifact() -> None:
    store = GeneratedArtifactStore()
    store.persist("agent", "agent_test_case", {"name": "agent-demo"})

    deleted = store.delete("agent", "agent_test_case")

    assert deleted["deleted"] is True


def test_generated_artifact_store_persists_trace_artifact() -> None:
    store = GeneratedArtifactStore()
    path = store.persist("trace", "trace_test_case", {"status": "completed", "trace_id": "trace_test_case"})

    assert path.exists()
    items = store.list_artifacts()
    assert any(item["artifactId"] == "trace_test_case" for item in items["trace"])