from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class TrainingFineTuneRunnerService:
    """Create inspectable, train-ready run specs without executing a real trainer yet."""

    FALLBACK_BACKENDS = {
        "mock": {
            "label": "Mock Runner",
            "supports_execution": False,
            "command_template": [
                "python",
                "-m",
                "nethub_runtime.training.run",
                "--backend={backend}",
                "--profile={profile}",
                "--manifest={manifest_path}",
                "--dry-run",
            ],
        },
        "unsloth": {
            "label": "Unsloth LoRA",
            "supports_execution": True,
            "command_template": [
                "python",
                "-m",
                "nethub_runtime.training.run",
                "--backend={backend}",
                "--profile={profile}",
                "--manifest={manifest_path}",
                "--execute",
            ],
        },
        "llamafactory": {
            "label": "LLaMA-Factory",
            "supports_execution": True,
            "command_template": [
                "llamafactory-cli",
                "train",
                "--manifest={manifest_path}",
                "--profile={profile}",
            ],
        },
    }

    def __init__(self, *, generated_artifact_store: Any, training_pipeline_service: Any, semantic_policy_store: Any | None = None) -> None:
        self.generated_artifact_store = generated_artifact_store
        self.training_pipeline_service = training_pipeline_service
        self.semantic_policy_store = semantic_policy_store

    def inspect_runner(self, *, profile: str = "lora_sft", backend: str = "mock") -> dict[str, Any]:
        manifest = self.training_pipeline_service.build_training_manifest(profile=profile)
        runtime_config = self._runtime_training_config()
        resolved_backend, backend_info = self._resolve_backend(backend=backend, profile=profile, manifest=manifest, runtime_config=runtime_config)
        return {
            "profile": profile,
            "backend": backend_info,
            "manifest": manifest,
            "ready": bool(manifest.get("ready")),
            "command_preview": self._command_preview(manifest=manifest, backend=resolved_backend, backend_info=backend_info),
            "runtime_config": runtime_config,
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
        execution_result = self._execute_if_requested(
            dry_run=dry_run,
            inspection=inspection,
        )
        run_payload = {
            "run_id": run_id,
            "created_at": timestamp,
            "profile": profile,
            "backend": inspection["backend"],
            "dry_run": dry_run,
            "status": execution_result.get("status") if execution_result else ("dry_run" if dry_run else "planned"),
            "ready": inspection["ready"],
            "command_preview": inspection["command_preview"],
            "manifest": inspection["manifest"],
            "runtime_config": inspection.get("runtime_config") or {},
            "note": note or "",
        }
        if execution_result:
            run_payload["execution"] = execution_result
        path = self.generated_artifact_store.persist("dataset_run", run_id, run_payload)
        run_payload["artifact_path"] = str(path)
        run_payload["message"] = self._message_for_run(dry_run=dry_run, execution_result=execution_result)
        return run_payload

    def _command_preview(self, *, manifest: dict[str, Any], backend: str, backend_info: dict[str, Any]) -> list[str]:
        manifest_path = str(manifest.get("artifact_path") or "runtime/generated/datasets/manifests/training_manifest.json")
        profile = str(manifest.get("profile") or "lora_sft")
        template = list(backend_info.get("command_template") or [])
        if not template:
            template = list(self.FALLBACK_BACKENDS.get("mock", {}).get("command_template") or [])
        values = {
            "backend": backend,
            "profile": profile,
            "manifest_path": manifest_path,
        }
        return [str(item).format(**values) for item in template]

    def _resolve_backend(
        self,
        *,
        backend: str,
        profile: str,
        manifest: dict[str, Any],
        runtime_config: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        configured = runtime_config.get("backends") or {}
        requested_backend = str(backend or runtime_config.get("default_backend") or "mock")
        resolved_backend = requested_backend if requested_backend in configured else "mock"
        backend_info = dict(configured.get(resolved_backend) or self.FALLBACK_BACKENDS["mock"])
        backend_info["backend"] = resolved_backend
        backend_info["status"] = "ready" if manifest.get("ready") else "waiting_for_datasets"
        backend_info["profile"] = profile
        return resolved_backend, backend_info

    def _runtime_training_config(self) -> dict[str, Any]:
        runtime_policy = {}
        if self.semantic_policy_store is not None:
            runtime_policy = ((self.semantic_policy_store.load_runtime_policy() or {}).get("runtime_behavior") or {}).get("training") or {}
        backends = dict(self.FALLBACK_BACKENDS)
        for key, value in (runtime_policy.get("backends") or {}).items():
            merged = dict(backends.get(key) or {})
            merged.update(value or {})
            backends[key] = merged

        env_default_backend = os.getenv("NETHUB_TRAINING_BACKEND", "").strip()
        env_allow_execution = os.getenv("NETHUB_TRAINING_ALLOW_EXECUTION", "").strip().lower()
        for backend_name in list(backends.keys()):
            env_command = os.getenv(f"NETHUB_TRAINING_{backend_name.upper()}_COMMAND", "").strip()
            if env_command:
                backends[backend_name]["command_template"] = env_command.split()
        return {
            "default_profile": str(os.getenv("NETHUB_TRAINING_PROFILE", runtime_policy.get("default_profile") or "lora_sft")),
            "default_backend": env_default_backend or str(runtime_policy.get("default_backend") or "mock"),
            "allow_execution": env_allow_execution in {"1", "true", "yes", "on"} if env_allow_execution else bool(runtime_policy.get("allow_execution", False)),
            "workspace_root": str(Path(os.getenv("NETHUB_TRAINING_WORKSPACE_ROOT", runtime_policy.get("workspace_root") or ".")).expanduser()),
            "backends": backends,
        }

    def _execute_if_requested(self, *, dry_run: bool, inspection: dict[str, Any]) -> dict[str, Any] | None:
        if dry_run:
            return None
        backend = inspection.get("backend") or {}
        runtime_config = inspection.get("runtime_config") or {}
        if not runtime_config.get("allow_execution"):
            return {
                "status": "blocked",
                "reason": "execution_disabled",
            }
        if not backend.get("supports_execution"):
            return {
                "status": "blocked",
                "reason": "backend_not_executable",
            }
        command_preview = list(inspection.get("command_preview") or [])
        if not command_preview:
            return {
                "status": "blocked",
                "reason": "missing_command_preview",
            }
        proc = subprocess.run(
            command_preview,
            cwd=str(runtime_config.get("workspace_root") or "."),
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "status": "completed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }

    def _message_for_run(self, *, dry_run: bool, execution_result: dict[str, Any] | None) -> str:
        if dry_run:
            return "Training run skeleton generated. No trainer was executed."
        if not execution_result:
            return "Training run planned. Hook a backend executor into this run spec to execute it."
        if execution_result.get("status") == "completed":
            return "Training command executed successfully."
        if execution_result.get("status") == "failed":
            return "Training command executed but failed. Inspect stderr in the run artifact."
        return "Training execution was requested but blocked by backend or policy settings."