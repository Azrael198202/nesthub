"""
Regression tests — Universal Execution Repair Loop.

Coverage:
  1. StepResultVerifier.classify() — all verdict classes
  2. Fire-and-forget steps with status=dispatched → OK
  3. ExecutionRepairLoop.run() — ok on first attempt (no repair)
  4. ExecutionRepairLoop.run() — degraded → repaired on attempt 2
  5. ExecutionRepairLoop.run() — failed → repaired on attempt 1
  6. ExecutionRepairLoop.run() — exhausted retries → repair_failed output
  7. ExecutionRepairLoop.run() — needs_user_input escalates immediately
  8. ExecutionRepairLoop.run() — run_step raises exception, retried
  9. ExecutionCoordinator.execute_workflow() integration — repair triggered
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from nethub_runtime.core.services.result_verifier import (
    StepResultVerifier,
    StepVerdict,
    VerdictClass,
)
from nethub_runtime.core.services.execution_repair_loop import ExecutionRepairLoop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verifier(**kwargs) -> StepResultVerifier:
    return StepResultVerifier(
        ok_statuses=["generated", "read", "saved", "completed", "ok", "success"],
        failed_statuses=["failed", "error", "invalid_output"],
        escalate_statuses=["needs_api_key"],
        fire_and_forget_steps=["ocr_extract", "stt_transcribe", "tts_synthesize"],
        degraded_message_patterns=["unsupported", "placeholder"],
        **kwargs,
    )


def _loop(max_retries: int = 2, always_diagnose: bool = False) -> ExecutionRepairLoop:
    coordinator = MagicMock()
    coordinator.model_router = None
    coordinator.capability_acquisition_service = None
    return ExecutionRepairLoop(
        coordinator=coordinator,
        verifier=_verifier(),
        max_retries=max_retries,
        always_diagnose=always_diagnose,
    )


def _task(intent: str = "file_generation", text: str = "make a file") -> MagicMock:
    t = MagicMock()
    t.intent = intent
    t.input_text = text
    t.task_id = "t-001"
    t.metadata = {}
    return t


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.session_id = "sess-1"
    ctx.trace_id = "trace-1"
    return ctx


def _step(name: str = "file_generate") -> dict[str, Any]:
    return {"name": name, "step_id": "s-1", "executor_type": "tool"}


# ---------------------------------------------------------------------------
# 1. StepResultVerifier.classify()
# ---------------------------------------------------------------------------

class TestStepResultVerifier:
    def test_empty_output_is_degraded(self) -> None:
        v = _verifier()
        verdict = v.classify({}, "any_step")
        assert verdict.cls == VerdictClass.DEGRADED
        assert verdict.reason == "empty_output"

    def test_none_output_is_degraded(self) -> None:
        v = _verifier()
        verdict = v.classify(None, "any_step")
        assert verdict.cls == VerdictClass.DEGRADED

    def test_ok_status(self) -> None:
        for status in ("generated", "read", "saved", "completed", "ok", "success"):
            verdict = _verifier().classify({"status": status}, "step")
            assert verdict.cls == VerdictClass.OK, f"Expected OK for status={status}"

    def test_failed_status(self) -> None:
        for status in ("failed", "error", "invalid_output"):
            verdict = _verifier().classify({"status": status}, "step")
            assert verdict.cls == VerdictClass.FAILED, f"Expected FAILED for status={status}"

    def test_escalate_status(self) -> None:
        verdict = _verifier().classify({"status": "needs_api_key", "providers": []}, "step")
        assert verdict.cls == VerdictClass.NEEDS_USER_INPUT
        assert verdict.needs_user_input

    def test_dispatched_fire_and_forget_is_ok(self) -> None:
        for step_name in ("ocr_extract", "stt_transcribe", "tts_synthesize"):
            verdict = _verifier().classify({"status": "dispatched"}, step_name)
            assert verdict.cls == VerdictClass.OK, f"Expected OK for fire-and-forget {step_name}"

    def test_dispatched_non_fire_and_forget_is_degraded(self) -> None:
        verdict = _verifier().classify({"status": "dispatched"}, "file_generate")
        assert verdict.cls == VerdictClass.DEGRADED

    def test_message_with_unsupported_is_degraded(self) -> None:
        verdict = _verifier().classify(
            {"message": "unsupported tool step: unknown_step"}, "unknown_step"
        )
        assert verdict.cls == VerdictClass.DEGRADED

    def test_message_with_placeholder_is_degraded(self) -> None:
        verdict = _verifier().classify(
            {"message": "llm step placeholder for generate"}, "llm_step"
        )
        assert verdict.cls == VerdictClass.DEGRADED

    def test_records_key_without_status_is_ok(self) -> None:
        verdict = _verifier().classify({"records": [], "count": 0}, "extract_records")
        assert verdict.cls == VerdictClass.OK

    def test_aggregation_key_without_status_is_ok(self) -> None:
        verdict = _verifier().classify({"aggregation": {"total": 100}}, "aggregate_query")
        assert verdict.cls == VerdictClass.OK

    def test_unknown_output_defaults_to_ok(self) -> None:
        verdict = _verifier().classify({"some_custom_field": True}, "custom_step")
        assert verdict.cls == VerdictClass.OK

    def test_verdict_ok_property(self) -> None:
        v = StepVerdict(cls=VerdictClass.OK)
        assert v.ok
        assert not v.needs_repair
        assert not v.needs_user_input

    def test_verdict_needs_repair_property(self) -> None:
        for cls in (VerdictClass.DEGRADED, VerdictClass.FAILED):
            v = StepVerdict(cls=cls)
            assert v.needs_repair
            assert not v.ok

    def test_from_policy_uses_defaults_when_no_policy(self) -> None:
        with patch(
            "nethub_runtime.core.services.result_verifier._load_policy_section",
            return_value={},
        ):
            verifier = StepResultVerifier.from_policy()
        # Should still classify correctly using defaults
        assert verifier.classify({"status": "generated"}, "step").ok
        assert verifier.classify({"status": "failed"}, "step").cls == VerdictClass.FAILED


# ---------------------------------------------------------------------------
# 2. ExecutionRepairLoop.run() — happy path
# ---------------------------------------------------------------------------

class TestRepairLoopHappyPath:
    def test_ok_output_returned_without_repair(self) -> None:
        loop = _loop()
        output = {"status": "generated", "artifact_path": "/tmp/file.txt"}
        calls = []

        def run_step(step, task, ctx, step_outputs):
            calls.append(1)
            return output

        result = loop.run(
            step=_step(),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["status"] == "generated"
        assert len(calls) == 1  # no retry
        assert "_repair_history" not in result

    def test_records_output_returned_without_repair(self) -> None:
        loop = _loop()

        def run_step(step, task, ctx, step_outputs):
            return {"records": [{"id": 1}], "count": 1}

        result = loop.run(
            step=_step("extract_records"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["records"] == [{"id": 1}]
        assert "_repair_history" not in result


# ---------------------------------------------------------------------------
# 3. ExecutionRepairLoop.run() — degraded → repaired
# ---------------------------------------------------------------------------

class TestRepairLoopDegradedRepair:
    def test_repaired_on_second_attempt(self) -> None:
        loop = _loop(max_retries=2)
        call_count = [0]

        def run_step(step, task, ctx, step_outputs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"message": "unsupported tool step: file_generate"}
            return {"status": "generated", "artifact_path": "/tmp/out.txt"}

        result = loop.run(
            step=_step("file_generate"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["status"] == "generated"
        assert "_repair_history" in result
        assert len(result["_repair_history"]) == 1  # 1 repair attempt before success


# ---------------------------------------------------------------------------
# 4. ExecutionRepairLoop.run() — failed → repaired
# ---------------------------------------------------------------------------

class TestRepairLoopFailedRepair:
    def test_failed_repaired_on_first_retry(self) -> None:
        loop = _loop(max_retries=2)
        call_count = [0]

        def run_step(step, task, ctx, step_outputs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "failed", "message": "backend error"}
            return {"status": "generated", "content": "hello"}

        result = loop.run(
            step=_step("file_generate"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["status"] == "generated"
        assert "_repair_history" in result


# ---------------------------------------------------------------------------
# 5. ExecutionRepairLoop.run() — exhausted retries
# ---------------------------------------------------------------------------

class TestRepairLoopExhausted:
    def test_repair_failed_after_all_retries(self) -> None:
        loop = _loop(max_retries=2)

        def run_step(step, task, ctx, step_outputs):
            return {"status": "failed", "message": "persistent failure"}

        result = loop.run(
            step=_step("file_generate"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["status"] == "repair_failed"
        assert "repair_history" in result
        assert len(result["repair_history"]) == 2  # one log per repair attempt
        assert result["last_output"]["status"] == "failed"

    def test_repair_failed_message_mentions_step_name(self) -> None:
        loop = _loop(max_retries=1)

        def run_step(step, task, ctx, step_outputs):
            return {"status": "error"}

        result = loop.run(
            step=_step("my_custom_step"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert "my_custom_step" in result["message"]


# ---------------------------------------------------------------------------
# 6. ExecutionRepairLoop.run() — needs_user_input escalation
# ---------------------------------------------------------------------------

class TestRepairLoopEscalation:
    def test_needs_api_key_escalates_immediately(self) -> None:
        loop = _loop(max_retries=3)
        call_count = [0]

        def run_step(step, task, ctx, step_outputs):
            call_count[0] += 1
            return {
                "status": "needs_api_key",
                "negotiation_request": {"providers": []},
            }

        result = loop.run(
            step=_step("image_generate"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["status"] == "needs_api_key"
        # Should NOT retry — only 1 call
        assert call_count[0] == 1

    def test_needs_api_key_on_repair_attempt_escalates(self) -> None:
        """If first attempt fails but retry returns needs_api_key, escalate."""
        loop = _loop(max_retries=2)
        call_count = [0]

        def run_step(step, task, ctx, step_outputs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "failed"}
            return {"status": "needs_api_key", "negotiation_request": {}}

        result = loop.run(
            step=_step("image_generate"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["status"] == "needs_api_key"
        assert call_count[0] == 2  # initial + 1 retry


# ---------------------------------------------------------------------------
# 7. ExecutionRepairLoop.run() — exception inside run_step
# ---------------------------------------------------------------------------

class TestRepairLoopException:
    def test_exception_in_run_step_triggers_retry(self) -> None:
        loop = _loop(max_retries=2)
        call_count = [0]

        def run_step(step, task, ctx, step_outputs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "failed"}
            if call_count[0] == 2:
                raise RuntimeError("connection reset")
            return {"status": "generated"}

        result = loop.run(
            step=_step("web_retrieve"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        # Attempt 1: failed → triggers repair
        # Repair attempt 1: exception → logged, continue
        # Repair attempt 2: generated → success
        assert result["status"] == "generated"

    def test_only_exceptions_exhausted_returns_repair_failed(self) -> None:
        loop = _loop(max_retries=2)
        call_count = [0]

        def run_step(step, task, ctx, step_outputs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "failed"}
            raise RuntimeError("always fails")

        result = loop.run(
            step=_step("web_retrieve"),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        assert result["status"] == "repair_failed"


# ---------------------------------------------------------------------------
# 8. ExecutionRepairLoop — capability acquisition called on repair
# ---------------------------------------------------------------------------

class TestRepairLoopCapabilityAcquisition:
    def test_acquisition_service_called_on_repair(self) -> None:
        coordinator = MagicMock()
        coordinator.model_router = None
        acq_result = MagicMock()
        acq_result.success = True
        acq_result.model_id = "stabilityai/model-v2"
        coordinator.capability_acquisition_service.acquire.return_value = acq_result

        loop = ExecutionRepairLoop(
            coordinator=coordinator,
            verifier=_verifier(),
            max_retries=1,
            acquire_capability_on_repair=True,
        )
        call_count = [0]

        def run_step(step, task, ctx, step_outputs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "failed"}
            return {"status": "generated"}

        result = loop.run(
            step=_step(),
            task=_task(),
            context=_ctx(),
            step_outputs={},
            run_step_fn=run_step,
        )
        coordinator.capability_acquisition_service.acquire.assert_called_once()
        assert result["status"] == "generated"


# ---------------------------------------------------------------------------
# 9. Integration with ExecutionCoordinator.execute_workflow()
# ---------------------------------------------------------------------------

class TestExecutionCoordinatorIntegration:
    def _make_coordinator(self):
        from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator
        coordinator = ExecutionCoordinator(
            session_store=MagicMock(),
            model_router=None,
        )
        return coordinator

    def test_execute_workflow_ok_step_passes_through(self) -> None:
        coordinator = self._make_coordinator()
        task = MagicMock()
        task.intent = "text_query"
        task.input_text = "query something"
        task.task_id = "t-1"
        task.metadata = {}
        task.domain = ""
        task.constraints = {}
        task.output_requirements = {}

        ctx = MagicMock()
        ctx.session_id = "sess-1"
        ctx.trace_id = "trace-1"

        plan = [
            {
                "step_id": "s-1",
                "name": "extract_records",
                "executor_type": "tool",
                "inputs": [],
                "outputs": [],
                "selector": {},
                "retry": 0,
            }
        ]

        with patch.object(
            coordinator,
            "_repair_loop",
            wraps=coordinator._repair_loop,
        ) as mock_loop:
            # patch run to return a valid result directly
            mock_loop.run.return_value = {"records": [], "count": 0}
            results = coordinator.execute(plan, task, ctx)

        assert any(s["name"] == "extract_records" for s in results["steps"])
        step_out = next(s for s in results["steps"] if s["name"] == "extract_records")
        assert step_out["status"] == "completed"

    def test_execute_workflow_repair_failed_step_recorded(self) -> None:
        """When repair loop returns repair_failed, the step is still recorded."""
        coordinator = self._make_coordinator()
        task = MagicMock()
        task.intent = "text_query"
        task.input_text = "query"
        task.task_id = "t-2"
        task.metadata = {}
        task.domain = ""
        task.constraints = {}
        task.output_requirements = {}

        ctx = MagicMock()
        ctx.session_id = "sess-2"
        ctx.trace_id = "trace-2"

        plan = [
            {
                "step_id": "s-1",
                "name": "file_generate",
                "executor_type": "tool",
                "inputs": [],
                "outputs": [],
                "selector": {},
                "retry": 0,
            }
        ]

        with patch.object(coordinator._repair_loop, "run") as mock_run:
            mock_run.return_value = {
                "status": "repair_failed",
                "step": "file_generate",
                "repair_history": [],
                "message": "Step 'file_generate' failed after 2 repair attempts.",
            }
            results = coordinator.execute(plan, task, ctx)

        assert any(s["name"] == "file_generate" for s in results["steps"])
        step_out = next(s for s in results["steps"] if s["name"] == "file_generate")
        # repair_failed is a dict returned by the loop — it counts as a completed step
        # (repair logging is inside the loop, not the coordinator)
        assert step_out["status"] == "completed"
        assert step_out["output"]["status"] == "repair_failed"
