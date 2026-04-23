from __future__ import annotations

from typing import Any


class TrainingFineTuneRunnerService:
    def __init__(
        self,
        *,
        generated_artifact_store: Any,
        training_pipeline_service: Any,
        semantic_policy_store: Any | None = None,
    ) -> None:
        self.generated_artifact_store = generated_artifact_store
        self.training_pipeline_service = training_pipeline_service
        self.semantic_policy_store = semantic_policy_store

    def inspect_runner(self, profile: str = "lora_sft", backend: str = "mock") -> dict[str, Any]:
        return {"profile": profile, "backend": backend, "ready": True, "last_run": None}

    def start_run(
        self,
        *,
        profile: str = "lora_sft",
        backend: str = "mock",
        dry_run: bool = True,
        note: str = "",
    ) -> dict[str, Any]:
        return {
            "profile": profile,
            "backend": backend,
            "dry_run": dry_run,
            "note": note,
            "status": "queued" if not dry_run else "dry_run_ok",
        }


__all__ = ["TrainingFineTuneRunnerService"]
