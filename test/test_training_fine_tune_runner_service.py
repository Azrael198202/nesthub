from __future__ import annotations

from nethub_runtime.core.services.training_fine_tune_runner_service import TrainingFineTuneRunnerService
from nethub_runtime.core.services.training_pipeline_service import TrainingPipelineService
from nethub_runtime.generated.store import GeneratedArtifactStore


def test_training_fine_tune_runner_service_creates_dry_run_spec(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(tmp_path / "generated"))
    store = GeneratedArtifactStore()
    store.persist("dataset_sft", "training_sft_demo", [{"input": {"user_text": "a"}, "output": {"answer": "b"}}])
    pipeline = TrainingPipelineService(generated_artifact_store=store)
    service = TrainingFineTuneRunnerService(
        generated_artifact_store=store,
        training_pipeline_service=pipeline,
    )

    run_spec = service.start_run(profile="lora_sft", backend="mock", dry_run=True)

    assert run_spec["status"] == "dry_run"
    assert run_spec["ready"] is True
    assert run_spec["artifact_path"].endswith(".json")
    assert "--mode=dry-run" in " ".join(run_spec["command_preview"])


def test_training_fine_tune_runner_service_inspection_exposes_backend_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(tmp_path / "generated"))
    store = GeneratedArtifactStore()
    pipeline = TrainingPipelineService(generated_artifact_store=store)
    service = TrainingFineTuneRunnerService(
        generated_artifact_store=store,
        training_pipeline_service=pipeline,
    )

    inspection = service.inspect_runner(profile="lora_sft", backend="unsloth")

    assert inspection["backend"]["backend"] == "unsloth"
    assert inspection["backend"]["supports_execution"] is False
    assert inspection["manifest"]["profile"] == "lora_sft"