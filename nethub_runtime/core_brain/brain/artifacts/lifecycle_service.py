from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from nethub_runtime.core_brain.contracts.artifact import ArtifactManifestContract


class ArtifactLifecycleService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "generated"
        self.paths = {
            "draft": self.root / "drafts",
            "registered": self.root / "registered",
            "active": self.root / "active",
            "failed": self.root / "failed",
            "archive": self.root / "archive",
        }
        for path in self.paths.values():
            path.mkdir(parents=True, exist_ok=True)

    def create_draft(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return self._write("draft", manifest)

    def register(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return self._write("registered", {**manifest, "status": "registered"})

    def activate(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return self._write("active", {**manifest, "status": "active"})

    def fail(self, manifest: dict[str, Any], error_reason: str) -> dict[str, Any]:
        return self._write("failed", {**manifest, "status": "failed", "error_reason": error_reason})

    def _write(self, stage: str, manifest: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        payload = {
            "created_at": now,
            "updated_at": now,
            "checksum": "",
            **manifest,
            "registered_at": str(manifest.get("registered_at") or now),
        }
        contract = ArtifactManifestContract.model_validate(payload)
        serializable = contract.model_dump(mode="python")
        serializable["checksum"] = sha256(json.dumps(serializable, sort_keys=True).encode("utf-8")).hexdigest()
        path = self.paths[stage] / f"{serializable['id']}.manifest.json"
        path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        return serializable
