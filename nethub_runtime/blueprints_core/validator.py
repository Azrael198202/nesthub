from __future__ import annotations

from nethub_runtime.core_brain.contracts.blueprint import BlueprintContract


class BlueprintValidator:
    def validate(self, payload: dict) -> dict:
        return BlueprintContract.model_validate(payload).model_dump(mode="python")
