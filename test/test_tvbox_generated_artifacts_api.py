from __future__ import annotations

from fastapi.testclient import TestClient

from nethub_runtime.generated.store import GeneratedArtifactStore
from nethub_runtime.tvbox.main import _create_app


def test_tvbox_generated_artifacts_api_lists_generated_files() -> None:
    store = GeneratedArtifactStore()
    store.persist("blueprint", "tvbox_blueprint_case", {"name": "tvbox-blueprint"})
    client = TestClient(_create_app())

    response = client.get("/api/generated-artifacts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert any(item["artifactId"] == "tvbox_blueprint_case" for item in payload["items"]["blueprint"])


def test_tvbox_generated_artifacts_api_deletes_generated_files() -> None:
    store = GeneratedArtifactStore()
    store.persist("agent", "tvbox_agent_case", {"name": "tvbox-agent"})
    client = TestClient(_create_app())

    response = client.post("/api/generated-artifacts/delete", json={"category": "agent", "artifactId": "tvbox_agent_case"})

    assert response.status_code == 200
    assert response.json()["deleted"] is True