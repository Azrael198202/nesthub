from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_task(intent: str = "image_generation_task"):
    from nethub_runtime.core.schemas.task_schema import TaskSchema

    task = TaskSchema(
        task_id="img-task-1",
        intent=intent,
        input_text="generate image",
        domain="multimodal",
    )
    task.metadata = {"trace_id": "trace-case", "session_id": "session-case"}
    return task


def _make_service():
    from nethub_runtime.core.services.image_generation_service import ImageGenerationService

    coordinator = MagicMock()
    coordinator.capability_acquisition_service = None
    coordinator.model_router = None
    return ImageGenerationService(coordinator)


def test_image_generation_success_case(isolated_case_runtime, tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image
    import random

    target = tmp_path / "generated.png"
    image = Image.new("RGB", (64, 64))
    pixels = image.load()
    for x in range(64):
        for y in range(64):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    image.save(target)

    service = _make_service()
    task = _make_task()
    with patch.object(service, "_try_all_backends", return_value={"status": "generated", "artifact_path": str(target)}):
        result = service.generate(task, target)

    assert result["status"] == "generated"
    assert target.exists()
    assert target.stat().st_size > 0
    assert result.get("result_verification", {}).get("ok") is True


@pytest.mark.parametrize("intent", ["text_generation_task", "data_record"])
def test_image_generation_intent_mismatch_case(isolated_case_runtime, tmp_path: Path, intent: str) -> None:
    service = _make_service()
    result = service.generate(_make_task(intent=intent), tmp_path / "img.png")
    assert result["status"] == "intent_mismatch"
    assert result["intent_verdict"]["expected"] == "image_generation_task"