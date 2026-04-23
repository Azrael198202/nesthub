from __future__ import annotations

from typing import Any

from nethub_runtime.core_brain.contracts.validator import ContractValidator


class SchemaValidationService:
    def __init__(self, validator: ContractValidator) -> None:
        self.validator = validator

    def validate_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        return self.validator.validate_intent(intent).model_dump(mode="python")

    def validate_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        return self.validator.validate_workflow(workflow).model_dump(mode="python")
