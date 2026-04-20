from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


class TrainingFineTuneRunnerService:
    """Create inspectable, train-ready run specs without executing a real trainer yet."""

    SUPPORTED_BACKENDS = {
        "mock": {
            "label": "Mock Runner",
            "status": "ready",
            "supports_execution": False,
        },
        "unsloth": {
            "label": "Unsloth LoRA",
            "status": "planned",
            "supports_execution": False,
        },
        "llamafactory": {
            "label": "LLaMA-Factory",
            "status": "planned",
            "supports_execution": False,
        },
    }

    def __init__(self, *, generated_artifact_store: Any, training_pipeline_service: Any) -> None:
        self.generated_artifact_store = generated_artifact_store
        self.training_pipeline_service = training_pipeline_service

    def inspect_runner(self, *, profile: str = "lora_sft", backend: str = "mock") -> dict[str, Any]:
        manifest = self.training_pipeline_service.build_training_manifest(profile=profile)
        resolved_backend = backend if backend in self.SUPPORTED_BACKENDS else "mock"
        backend_info = {
            "backend": resolved_backend,
            **self.SUPPORTED_BACKENDS[resolved_backend],
        }
        return {
            "profile": profile,
            "backend": backend_info,
            "manifest": manifest,
            "ready": bool(manifest.get("ready")),
            "command_preview": self._command_preview(manifest=manifest, backend=resolved_backend),
            "next_step": "dry_run_supported",
        }

    def start_run(
        self,
        *,
        profile: str = "lora_sft",
        backend: str = "mock",
        dry_run: bool = True,
        note: str | None = None,
    ) -> dict[str, Any]:
        inspection = self.inspect_runner(profile=profile, backend=backend)
        timestamp = datetime.now(UTC).isoformat()
        run_id = f"training_run_{profile}_{uuid4().hex[:8]}"
        run_payload = {
            "run_id": run_id,
            "created_at": timestamp,
            "profile": profile,
            "backend": inspection["backend"],
            "dry_run": dry_run,
            "status": "dry_run" if dry_run else "planned",
            "ready": inspection["ready"],
            "command_preview": inspection["command_preview"],
            "manifest": inspection["manifest"],
            "note": note or "",
        }
        path = self.generated_artifact_store.persist("dataset_run", run_id, run_payload)
        run_payload["artifact_path"] = str(path)
        run_payload["message"] = (
            "Training run skeleton generated. No trainer was executed."
            if dry_run
            else "Training run planned. Hook a backend executor into this run spec to execute it."
        )
        return run_payload

    def _command_preview(self, *, manifest: dict[str, Any], backend: str) -> list[str]:
        manifest_path = str(manifest.get("artifact_path") or "runtime/generated/datasets/manifests/training_manifest.json")
        profile = str(manifest.get("profile") or "lora_sft")
        if backend == "unsloth":
            return [
                "python -m nethub_runtime.training.run",
                f"--backend={backend}",
                f"--profile={profile}",
                f"--manifest={manifest_path}",
                "--mode=dry-run",
            ]
        if backend == "llamafactory":
            return [
                "llamafactory-cli train",
                f"--manifest={manifest_path}",
                f"--profile={profile}",
                "--dry-run",
            ]
        return [
            "python -m nethub_runtime.training.run",
            f"--backend={backend}",
            f"--profile={profile}",
            f"--manifest={manifest_path}",
            "--mode=dry-run",
        ]