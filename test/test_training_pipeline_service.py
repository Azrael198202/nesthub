from __future__ import annotations

from nethub_runtime.core.services.training_pipeline_service import TrainingPipelineService
from nethub_runtime.generated.store import GeneratedArtifactStore


def test_training_pipeline_service_builds_manifest_from_exported_datasets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(tmp_path / "generated"))
    store = GeneratedArtifactStore()
    store.persist("dataset_sft", "training_sft_demo", [{"input": {"user_text": "a"}, "output": {"answer": "b"}}])
    store.persist("dataset_preference", "training_preference_demo", [{"chosen": "good", "rejected": "bad"}])
    service = TrainingPipelineService(generated_artifact_store=store)

    manifest = service.build_training_manifest(profile="lora_sft")

    assert manifest["ready"] is True
    assert manifest["counts"]["sft"] == 1
    assert manifest["counts"]["preference"] == 1
    assert manifest["training_plan"]["preference_objective"] == "dpo"
    assert manifest["artifact_path"].endswith("training_manifest_lora_sft.json")
