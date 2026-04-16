from __future__ import annotations

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def test_semantic_memory_dashboard_is_served() -> None:
    response = client.get("/examples/semantic-memory-dashboard/")

    assert response.status_code == 200
    assert "Semantic Memory Dashboard" in response.text