from __future__ import annotations

from unittest.mock import MagicMock

from nethub_runtime.core.memory.runtime_learning_store import RuntimeLearningStore


def test_runtime_learning_store_lookup_execution_guidance_returns_latest_success() -> None:
    store = MagicMock()
    store.inspect_memory.return_value = {
        "records": [
            {
                "timestamp": "2026-04-20T10:00:00+00:00",
                "confidence": 0.9,
                "payload": {
                    "task_type": "file_upload_task",
                    "intent": "file_upload_task",
                    "outcome": "success",
                    "repair_iterations": 1,
                    "solution_summary": "retry with analyze step",
                },
            },
            {
                "timestamp": "2026-04-20T11:00:00+00:00",
                "confidence": 0.95,
                "payload": {
                    "task_type": "file_upload_task",
                    "intent": "file_upload_task",
                    "outcome": "success",
                    "repair_iterations": 0,
                    "solution_summary": "reuse verified document analysis path",
                    "repair_preferences": {"analysis_before_retry": True},
                },
            },
        ]
    }
    learning = RuntimeLearningStore(store)

    guidance = learning.lookup_execution_guidance(task_type="file_upload_task", intent="file_upload_task")

    assert guidance is not None
    assert guidance["solution_summary"] == "reuse verified document analysis path"
    assert guidance["repair_iterations"] == 0
    assert guidance["repair_preferences"]["analysis_before_retry"] is True
