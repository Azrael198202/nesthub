"""
Universal execution repair loop — wraps every step execution in nesthub.

When a step produces a degraded or failed result, this loop:

  1. **Diagnoses** why (asks ModelRouter with a brief AI prompt)
  2. **Acquires capability** if the diagnosis suggests a missing package or model
     (delegates to CapabilityAcquisitionService)
  3. **Retries** the step (up to ``max_retries`` from policy)
  4. **Escalates** when retries are exhausted, returning a structured
     ``repair_failed`` output with the full repair history

Steps that return ``needs_api_key`` (or any other escalate-class status) are
passed through immediately — the loop does not attempt to repair them.

This is the domain-agnostic equivalent of ``ImageGenerationRepairLoop``; the
image-specific loop remains in place for the extra entropy / PIL verification
it does, but all other steps now share this same infrastructure.

Configuration is read from::

    semantic_policy.json → runtime_behavior.result_verification
        max_retries: 2
        diagnosis_model_task: "reasoning"
        acquire_capability_on_repair: true
        always_diagnose: false        # set true to diagnose even on degraded results

Usage inside execute_workflow()::

    # __init__:
    self._repair_loop = ExecutionRepairLoop.from_policy(coordinator=self)

    # execute_workflow() inner loop:
    output = self._repair_loop.run(
        step=step, task=task, context=context,
        step_outputs=step_outputs,
        run_step_fn=self._run_step,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.result_verifier import (
    StepResultVerifier,
    StepVerdict,
    VerdictClass,
)

LOGGER = logging.getLogger("nethub_runtime.core.execution_repair_loop")

# Callable signature for the step runner injected by the coordinator
_RunStepFn = Callable[
    [dict[str, Any], TaskSchema, CoreContextSchema, dict[str, Any]],
    dict[str, Any],
]


class ExecutionRepairLoop:
    """Universal step-level self-healing repair loop.

    Wraps any step runner with:
      classify → (diagnose + acquire) × N retries → escalate
    """

    def __init__(
        self,
        coordinator: Any,
        verifier: StepResultVerifier,
        max_retries: int = 2,
        diagnosis_model_task: str = "reasoning",
        acquire_capability_on_repair: bool = True,
        always_diagnose: bool = False,
    ) -> None:
        self._coordinator = coordinator
        self._verifier = verifier
        self._max_retries = max_retries
        self._diagnosis_task = diagnosis_model_task
        self._acquire = acquire_capability_on_repair
        self._always_diagnose = always_diagnose

    @classmethod
    def from_policy(cls, coordinator: Any) -> "ExecutionRepairLoop":
        """Build from ``runtime_behavior.result_verification`` policy block."""
        cfg = _load_policy_section()
        verifier = StepResultVerifier.from_policy(cfg)
        return cls(
            coordinator=coordinator,
            verifier=verifier,
            max_retries=int(cfg.get("max_retries", 2)),
            diagnosis_model_task=str(cfg.get("diagnosis_model_task", "reasoning")),
            acquire_capability_on_repair=bool(cfg.get("acquire_capability_on_repair", True)),
            always_diagnose=bool(cfg.get("always_diagnose", False)),
        )

    # ------------------------------------------------------------------
    # Main entry point (synchronous)
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        step: dict[str, Any],
        task: TaskSchema,
        context: CoreContextSchema,
        step_outputs: dict[str, Any],
        run_step_fn: _RunStepFn,
    ) -> dict[str, Any]:
        """Execute ``step`` via ``run_step_fn``, repairing failures automatically.

        Returns the first output that passes classification, OR a structured
        ``repair_failed`` / ``needs_user_input`` dict when all retries fail.
        """
        step_name = step.get("name", "")
        repair_history: list[dict[str, Any]] = []

        # --- Initial attempt ---
        output = run_step_fn(step, task, context, step_outputs)
        verdict = self._verifier.classify(output, step_name)

        LOGGER.debug(
            "step=%s verdict=%s status=%s",
            step_name, verdict.cls.value, verdict.status,
        )

        if verdict.ok:
            return output

        # --- Escalate immediately if user action required ---
        if verdict.needs_user_input:
            LOGGER.info(
                "step=%s requires user input (status=%s) — escalating",
                step_name, verdict.status,
            )
            return output  # bubble up as-is; caller handles needs_api_key etc.

        # --- Repair loop ---
        for attempt in range(1, self._max_retries + 1):
            log_entry: dict[str, Any] = {
                "attempt": attempt,
                "step": step_name,
                "verdict": verdict.cls.value,
                "reason": verdict.reason,
            }

            # Diagnose
            diagnosis = self._diagnose(
                step_name=step_name,
                verdict=verdict,
                output=output,
                task=task,
                attempt=attempt,
            )
            log_entry["diagnosis"] = diagnosis
            LOGGER.info(
                "repair attempt %d/%d step=%s diagnosis=%s",
                attempt, self._max_retries, step_name, diagnosis[:200],
            )

            # Acquire missing capability
            if self._acquire:
                acquired = self._acquire_capability(step_name, verdict, task, attempt)
                log_entry["acquired"] = acquired
                if acquired:
                    LOGGER.info(
                        "repair attempt %d step=%s acquired=%s",
                        attempt, step_name, acquired,
                    )

            # Retry
            try:
                output = run_step_fn(step, task, context, step_outputs)
            except Exception as exc:
                log_entry["retry_error"] = str(exc)
                repair_history.append(log_entry)
                LOGGER.warning(
                    "repair attempt %d step=%s retry raised: %s",
                    attempt, step_name, exc,
                )
                continue

            verdict = self._verifier.classify(output, step_name)
            log_entry["retry_verdict"] = verdict.cls.value
            repair_history.append(log_entry)

            if verdict.ok:
                LOGGER.info(
                    "step=%s repaired on attempt %d", step_name, attempt
                )
                output["_repair_history"] = repair_history
                return output

            if verdict.needs_user_input:
                LOGGER.info(
                    "step=%s escalated to user input on repair attempt %d",
                    step_name, attempt,
                )
                return output  # bubble up

        # --- All retries exhausted ---
        LOGGER.warning(
            "step=%s could not be repaired after %d attempts",
            step_name, self._max_retries,
        )
        return {
            "status": "repair_failed",
            "step": step_name,
            "last_output": output,
            "repair_history": repair_history,
            "message": (
                f"Step '{step_name}' failed after {self._max_retries} repair "
                "attempts. Check repair_history for details."
            ),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _diagnose(
        self,
        *,
        step_name: str,
        verdict: StepVerdict,
        output: dict[str, Any],
        task: TaskSchema,
        attempt: int,
    ) -> str:
        """Ask ModelRouter for a concise diagnosis of why the step failed."""
        if not self._always_diagnose and verdict.cls == VerdictClass.DEGRADED:
            # Skip expensive AI call for lightweight degraded cases unless configured
            return f"step='{step_name}' degraded (reason={verdict.reason})"

        model_router = getattr(self._coordinator, "model_router", None)
        if model_router is None:
            return f"no_model_router reason={verdict.reason}"

        prompt = (
            f"A step in the NestHub workflow failed:\n"
            f"  step_name: {step_name}\n"
            f"  verdict: {verdict.cls.value} — {verdict.reason}\n"
            f"  task_intent: {task.intent}\n"
            f"  input_text: {task.input_text[:200]}\n"
            f"  output_sample: {json.dumps(output, ensure_ascii=False)[:400]}\n"
            f"  repair_attempt: {attempt}\n\n"
            "In one short sentence, state the most likely technical cause and "
            "the single best repair action."
        )
        try:
            invoke = getattr(model_router, "invoke", None)
            if invoke is None:
                return "model_router.invoke not available"
            import asyncio
            import concurrent.futures

            def _run_in_new_loop() -> str:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(
                        invoke(self._diagnosis_task, prompt,
                               system_prompt="You are a concise NestHub step diagnostic assistant.")
                    )
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(_run_in_new_loop).result(timeout=15)
            return str(result)
        except Exception as exc:
            LOGGER.debug("Diagnosis model call failed: %s", exc)
            return f"diagnosis_unavailable ({exc})"

    def _acquire_capability(
        self,
        step_name: str,
        verdict: StepVerdict,
        task: TaskSchema,
        attempt: int,
    ) -> str | None:
        """Delegate to CapabilityAcquisitionService to resolve a missing capability."""
        svc = getattr(self._coordinator, "capability_acquisition_service", None)
        if svc is None:
            return None
        try:
            result = svc.acquire(
                task_type=task.intent,
                gap=f"{step_name}_{verdict.cls.value}_attempt_{attempt}",
                context={
                    "step_name": step_name,
                    "verdict": verdict.cls.value,
                    "reason": verdict.reason,
                    "repair_attempt": attempt,
                },
            )
            return result.model_id if result.success else None
        except Exception as exc:
            LOGGER.debug("Capability acquisition failed for step %s: %s", step_name, exc)
            return None


# ---------------------------------------------------------------------------
# Policy helpers
# ---------------------------------------------------------------------------

def _load_policy_section() -> dict[str, Any]:
    try:
        policy = json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))
        return (policy.get("runtime_behavior") or {}).get("result_verification") or {}
    except Exception as exc:
        LOGGER.warning("Could not load result_verification policy: %s", exc)
        return {}
