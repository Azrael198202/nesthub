from __future__ import annotations

from fastapi.testclient import TestClient

from nethub_runtime.config.settings import ensure_generated_dirs
from nethub_runtime.tvbox.main import _create_app


def test_generated_workspace_dirs_are_created_under_package() -> None:
    paths = ensure_generated_dirs()

    assert paths["root"].name == "generated"
    assert paths["root"].parent.name == "nethub_runtime"
    assert paths["features"].exists()
    assert paths["agents"].exists()
    assert paths["blueprints"].exists()
    assert paths["traces"].exists()


def test_tvbox_generated_feature_is_written_to_generated_features_dir() -> None:
    client = TestClient(_create_app())

    response = client.post("/api/custom-agents/generate-feature")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "/nethub_runtime/generated/features/" in payload["featurePath"]