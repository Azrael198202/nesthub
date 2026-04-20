from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TrainingPipelineService:
    """Build train-ready manifests from exported private-brain datasets."""

    def __init__(self, *, generated_artifact_store: Any) -> None:
        self.generated_artifact_store = generated_artifact_store

    def build_training_manifest(self, *, profile: str = "lora_sft") -> dict[str, Any]:
        artifacts = self.generated_artifact_store.list_artifacts()
        sft_items = artifacts.get("dataset_sft", [])
        preference_items = artifacts.get("dataset_preference", [])

        manifest = {
            "profile": profile,
            "ready": bool(sft_items),
            "recommended_backend": "lora_sft",
            "datasets": {
                "sft": [self._dataset_descriptor(item) for item in sft_items],
                "preference": [self._dataset_descriptor(item) for item in preference_items],
            },
            "counts": {
                "sft": len(sft_items),
                "preference": len(preference_items),
            },
            "training_plan": self._training_plan(profile=profile, has_preferences=bool(preference_items)),
        }
        manifest_path = self.generated_artifact_store.persist(
            "dataset_manifest",
            f"training_manifest_{profile}",
            manifest,
        )
        manifest["artifact_path"] = str(manifest_path)
        return manifest

    def _dataset_descriptor(self, item: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(item.get("path") or ""))
        sample_count = self._sample_count(path)
        return {
            "artifact_id": item.get("artifactId"),
            "path": str(path),
            "sample_count": sample_count,
            "size": item.get("size") or 0,
        }

    def _sample_count(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        return len(payload) if isinstance(payload, list) else 0

    def _training_plan(self, *, profile: str, has_preferences: bool) -> dict[str, Any]:
        base = {
            "profile": profile,
            "stages": ["prepare", "tokenize", "train", "evaluate"],
            "supervised_objective": "sft",
            "preference_objective": "dpo" if has_preferences else "none",
            "requires": ["dataset_sft"],
        }
        if has_preferences:
            base["requires"].append("dataset_preference")
        return base
