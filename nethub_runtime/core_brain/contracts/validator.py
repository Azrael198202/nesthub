from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from nethub_runtime.core_brain.contracts.models import (
    BlueprintContract,
    IntentContract,
    ToolContract,
    TraceContract,
    WorkflowContract,
)


class ContractValidationError(ValueError):
    def __init__(self, contract_name: str, details: str) -> None:
        super().__init__(f"{contract_name} validation failed: {details}")
        self.contract_name = contract_name
        self.details = details


class ContractValidator:
    """Centralized schema/DTO validation for core_brain runtime contracts."""

    def validate_intent(self, payload: dict[str, Any]) -> IntentContract:
        return self._validate("intent", IntentContract, payload)

    def validate_workflow(self, payload: dict[str, Any]) -> WorkflowContract:
        return self._validate("workflow", WorkflowContract, payload)

    def validate_blueprint(self, payload: dict[str, Any]) -> BlueprintContract:
        return self._validate("blueprint", BlueprintContract, payload)

    def validate_tool(self, payload: dict[str, Any]) -> ToolContract:
        return self._validate("tool", ToolContract, payload)

    def validate_trace(self, payload: dict[str, Any]) -> TraceContract:
        return self._validate("trace", TraceContract, payload)

    def _validate(self, contract_name: str, model: type[Any], payload: dict[str, Any]) -> Any:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise ContractValidationError(contract_name, exc.json()) from exc
