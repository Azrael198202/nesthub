from __future__ import annotations

from pathlib import Path

import yaml

from nethub_runtime.blueprint.manifest import BlueprintManifest


def load_blueprint(path: str | Path) -> BlueprintManifest:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return BlueprintManifest.model_validate(data)
