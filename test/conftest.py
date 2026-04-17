from __future__ import annotations

import pytest


@pytest.fixture
def isolated_generated_artifacts(tmp_path, monkeypatch) -> None:
    generated_root = tmp_path / "generated_artifacts"
    generated_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(generated_root))