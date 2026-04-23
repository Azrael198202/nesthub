from __future__ import annotations

from typing import Any


class TrainingPipelineService:
    def __init__(self, generated_artifact_store: Any) -> None:
        self.generated_artifact_store = generated_artifact_store

    def build_manifest(self, profile: str = "lora_sft") -> dict[str, Any]:
        return {"profile": profile, "dataset_ready": False, "runs": []}
