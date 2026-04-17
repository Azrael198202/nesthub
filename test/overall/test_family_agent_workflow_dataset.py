from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


DATASET_PATH = Path(__file__).with_name("family_agent_workflow_cases.yaml")
client = TestClient(app)


def _load_dataset() -> dict[str, Any]:
    return yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))


DATASET = _load_dataset()
ACTIVE_SCENARIOS = [item for item in DATASET["scenarios"] if item["status"] == "active"]
PENDING_SCENARIOS = [item for item in DATASET["scenarios"] if item["status"] == "pending"]


def _path_parts(path: str) -> list[str]:
    return [part for part in path.split(".") if part]


def _get_path(data: Any, path: str) -> Any:
    current = data
    for raw_part in _path_parts(path):
        part = raw_part
        while "[" in part:
            name, remainder = part.split("[", 1)
            if name:
                current = current[name]
            index_text, part = remainder.split("]", 1)
            current = current[int(index_text)]
        if part:
            current = current[part]
    return current


def _object_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if key.endswith("_contains"):
            actual_key = key.removesuffix("_contains")
            if value not in str(actual.get(actual_key, "")):
                return False
            continue
        if actual.get(key) != value:
            return False
    return True


def _run_step(step: dict[str, Any], session_id: str, defaults: dict[str, Any], transport: dict[str, Any]) -> dict[str, Any]:
    request = step["request"]
    payload = {
        "input_text": request["input_text"],
        "context": {**defaults.get("context", {}), **request.get("context", {}), "session_id": session_id},
        "output_format": request.get("output_format", transport.get("output_format", "dict")),
        "use_langraph": request.get("use_langraph", transport.get("use_langraph", False)),
    }
    response = client.post(transport["endpoint"], json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _assertions_for(step_name: str, response_data: dict[str, Any], assertions: list[dict[str, Any]]) -> None:
    for assertion in assertions:
        assertion_type = assertion["type"]
        path = assertion.get("path")
        value = _get_path(response_data, path) if path else None

        if assertion_type == "path_equals":
            assert value == assertion["expected"], f"{step_name} {path} expected {assertion['expected']!r}, got {value!r}"
            continue
        if assertion_type == "path_in":
            assert value in assertion["expected_any"], f"{step_name} {path} expected one of {assertion['expected_any']!r}, got {value!r}"
            continue
        if assertion_type == "list_length":
            assert len(value) == assertion["expected"], f"{step_name} {path} expected length {assertion['expected']}, got {len(value)}"
            continue
        if assertion_type == "list_contains_objects":
            assert isinstance(value, list), f"{step_name} {path} is not a list"
            for expected_object in assertion["expected_objects"]:
                assert any(_object_matches(item, expected_object) for item in value), (
                    f"{step_name} {path} missing object subset {expected_object!r}; actual={value!r}"
                )
            continue
        raise AssertionError(f"Unsupported assertion type: {assertion_type}")


@pytest.mark.parametrize("scenario", ACTIVE_SCENARIOS, ids=[item["id"] for item in ACTIVE_SCENARIOS])
def test_family_agent_workflow_active_scenarios(scenario: dict[str, Any], isolated_generated_artifacts) -> None:
    session_id = f"overall-{scenario['session_key']}-{uuid.uuid4().hex}"
    for step in scenario.get("steps", []):
        response_data = _run_step(step, session_id, DATASET.get("defaults", {}), DATASET["metadata"]["transport"])
        _assertions_for(step["name"], response_data, step.get("assertions", []))


def test_family_agent_workflow_dataset_has_pending_coverage_notes() -> None:
    assert PENDING_SCENARIOS, "Pending scenarios should remain documented until the platform gains full coverage."
    for scenario in PENDING_SCENARIOS:
        assert scenario.get("reason"), f"{scenario['id']} must document why it is still pending"


def test_family_agent_workflow_dataset_metadata_is_consistent() -> None:
    assert DATASET["metadata"]["suite_id"] == "family_agent_workflow_overall"
    assert DATASET["metadata"]["transport"]["endpoint"] == "/core/handle"
    assert {scenario["status"] for scenario in DATASET["scenarios"]} <= {"active", "pending"}