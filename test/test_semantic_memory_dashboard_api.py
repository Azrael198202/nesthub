from __future__ import annotations

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def test_semantic_memory_api_exposes_learning_rules(isolated_generated_artifacts) -> None:
    response = client.get("/core/admin/semantic-memory")

    assert response.status_code == 200
    result = response.json()["result"]
    assert "learning_rules" in result
    assert "allowed_policy_keys" in result["learning_rules"]
    assert "blocked_terms" in result["learning_rules"]