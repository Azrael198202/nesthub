from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from nethub_runtime.config.settings import ensure_generated_dirs


class GeneratedArtifactStore:
    CATEGORY_TO_DIR = {
        "blueprint": "blueprints",
        "agent": "agents",
        "feature": "features",
        "trace": "traces",
        "code": "code",
        "dataset_sft": "datasets_sft",
        "dataset_preference": "datasets_preferences",
        "dataset_manifest": "datasets_manifests",
        "dataset_run": "datasets_runs",
    }

    def __init__(self) -> None:
        self.paths = ensure_generated_dirs()

    def _paths(self) -> dict[str, Path]:
        self.paths = ensure_generated_dirs()
        return self.paths

    def persist(self, category: str, artifact_id: str, payload: Any, *, extension: str = ".json") -> Path:
        directory = self._paths()[self.CATEGORY_TO_DIR[category]]
        path = directory / f"{artifact_id}{extension}"
        if extension in {".py", ".md", ".txt", ".yaml", ".yml"} and isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
            return path
        serializable = self._serialize(payload)
        path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def list_artifacts(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        paths = self._paths()
        for category, key in self.CATEGORY_TO_DIR.items():
            directory = paths[key]
            items: list[dict[str, Any]] = []
            for path in sorted(directory.iterdir() if directory.exists() else [], key=lambda item: item.name):
                if not path.is_file():
                    continue
                items.append(
                    {
                        "artifactId": path.stem,
                        "category": category,
                        "path": str(path),
                        "name": path.name,
                        "size": path.stat().st_size,
                        "contentPreview": self._preview(path),
                    }
                )
            result[category] = items
        return result

    def delete(self, category: str, artifact_id: str) -> dict[str, Any]:
        directory = self._paths()[self.CATEGORY_TO_DIR[category]]
        candidates = list(directory.glob(f"{artifact_id}.*"))
        for path in candidates:
            if path.is_file():
                path.unlink()
                return {"ok": True, "deleted": True, "path": str(path)}
        return {"ok": True, "deleted": False, "path": str(directory / artifact_id)}

    def _serialize(self, payload: Any) -> Any:
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return payload
        return {"value": payload}

    def _preview(self, path: Path) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return ""
        return text[:240]