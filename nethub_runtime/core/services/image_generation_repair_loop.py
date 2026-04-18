"""
Image Generation Repair Loop — autonomous retry + paid-API negotiation.

This module orchestrates the full self-healing pipeline when an image
generation attempt produces an invalid result:

  Phase A — Free model retry loop
    1. Ask an AI (via ModelRouter) to diagnose WHY the current backend failed.
    2. Download the next free local model from the candidate list in
       ``semantic_policy.json`` (using CapabilityAcquisitionService).
    3. Re-run generation and verify the result.
    4. Repeat up to ``max_free_retries`` times (config-driven).

  Phase B — Paid model negotiation (when free retries exhausted)
    1. Build a NegotiationRequest listing available paid providers
       (names, endpoint, key_env, docs_url).
    2. Return the request to the caller — the caller is responsible for
       surfacing this to the user and waiting for a key.
    3. When a key arrives (``resume_with_api_key``), register the provider
       in ModelRouter and re-run generation.

Context continuity:
    Every attempt is logged with the same trace_id/session_id so the full
    repair history is traceable across turns.

Usage::

    loop = ImageGenerationRepairLoop.from_policy(coordinator=coordinator)

    # Called after a failed/invalid generation:
    outcome = await loop.run(
        task=task,
        target_path=target_path,
        initial_verdict=verdict,
        trace_id=ctx.trace_id,
        session_id=ctx.session_id,
    )

    if outcome.status == "generated":
        return outcome.result
    elif outcome.status == "needs_api_key":
        # Surface outcome.negotiation_request to the user
        ...
    elif outcome.status == "failed":
        ...

    # Later, when the user provides a key:
    outcome = await loop.resume_with_api_key(
        task=task,
        target_path=target_path,
        provider_name="openai",
        api_key="sk-...",
        trace_id=ctx.trace_id,
        session_id=ctx.session_id,
    )
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.image_result_verifier import (
    ImageGenerationVerifier,
    NegotiationRequest,
    ResultVerdict,
)

LOGGER = logging.getLogger("nethub_runtime.core.image_generation_repair_loop")


# ---------------------------------------------------------------------------
# Outcome dataclass
# ---------------------------------------------------------------------------

@dataclass
class RepairOutcome:
    """Result of a repair loop run."""

    status: str                                   # "generated" | "needs_api_key" | "failed"
    result: dict[str, Any] = field(default_factory=dict)
    negotiation_request: NegotiationRequest | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    trace_id: str = ""
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "status": self.status,
            "result": self.result,
            "attempts": self.attempts,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
        }
        if self.negotiation_request is not None:
            d["negotiation_request"] = self.negotiation_request.to_dict()
        return d


# ---------------------------------------------------------------------------
# Repair loop
# ---------------------------------------------------------------------------

class ImageGenerationRepairLoop:
    """Autonomous repair loop for image generation failures.

    All tunable parameters (max retries, candidate model list, paid providers)
    are read from ``semantic_policy.json`` — no business vocabulary here.
    """

    def __init__(
        self,
        coordinator: Any,
        verifier: "ImageGenerationVerifier",
        max_free_retries: int = 3,
    ) -> None:
        self._coordinator = coordinator
        self._verifier = verifier
        self._max_free_retries = max_free_retries

    @classmethod
    def from_policy(cls, coordinator: Any) -> "ImageGenerationRepairLoop":
        """Build from ``runtime_behavior.image_verification`` policy."""
        cfg = _load_verification_policy()
        verifier = ImageGenerationVerifier.from_policy(cfg)
        max_retries = int(cfg.get("max_free_retries", 3))
        return cls(coordinator=coordinator, verifier=verifier, max_free_retries=max_retries)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        task: TaskSchema,
        target_path: Path,
        initial_verdict: ResultVerdict,
        trace_id: str = "",
        session_id: str = "",
    ) -> RepairOutcome:
        """Run the full repair pipeline.

        Phases:
          A. Free model retry (up to max_free_retries)
          B. Paid model negotiation
        """
        attempts: list[dict[str, Any]] = []

        # --- Phase A: diagnose + retry with free models ---
        for attempt_num in range(1, self._max_free_retries + 1):
            attempt_log: dict[str, Any] = {
                "attempt": attempt_num,
                "phase": "free_model",
                "trace_id": trace_id,
            }

            # 1. Ask AI to diagnose why this failed
            diagnosis_text = await self._ai_diagnose(
                task=task,
                verdict=initial_verdict,
                attempt_num=attempt_num,
                trace_id=trace_id,
            )
            attempt_log["diagnosis"] = diagnosis_text
            LOGGER.info(
                "Repair attempt %d/%d — diagnosis: %s",
                attempt_num, self._max_free_retries, diagnosis_text[:200],
            )

            # 2. Acquire the next free model candidate
            acquired = self._acquire_next_free_model(attempt_num=attempt_num)
            attempt_log["acquired_model"] = acquired
            LOGGER.info("Repair attempt %d — acquired model: %s", attempt_num, acquired)

            # 3. Re-run generation using the newly acquired model
            gen_result = self._generate(task, target_path)
            attempt_log["generation_result"] = gen_result

            if gen_result.get("status") != "generated":
                attempt_log["verdict"] = "generation_failed"
                attempts.append(attempt_log)
                continue

            # 4. Verify the new output
            new_verdict = self._verifier.verify_result(task, target_path)
            attempt_log["verdict"] = "ok" if new_verdict.ok else "invalid"
            attempt_log["diagnosis_detail"] = new_verdict.diagnosis
            attempts.append(attempt_log)

            if new_verdict.ok:
                LOGGER.info(
                    "Image repair succeeded on attempt %d (trace=%s)",
                    attempt_num, trace_id,
                )
                gen_result["repair_attempts"] = attempt_num
                gen_result["repair_history"] = attempts
                return RepairOutcome(
                    status="generated",
                    result=gen_result,
                    attempts=attempts,
                    trace_id=trace_id,
                    session_id=session_id,
                )

            # Update verdict for next iteration
            initial_verdict = new_verdict

        # --- Phase B: escalate to paid models ---
        LOGGER.info(
            "All free retries exhausted (%d). Building paid-model negotiation (trace=%s).",
            self._max_free_retries, trace_id,
        )
        negotiation = self._verifier.build_negotiation_request(
            task, session_id=session_id, trace_id=trace_id
        )
        return RepairOutcome(
            status="needs_api_key",
            result={},
            negotiation_request=negotiation,
            attempts=attempts,
            trace_id=trace_id,
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Resume after user provides an API key
    # ------------------------------------------------------------------

    async def resume_with_api_key(
        self,
        *,
        task: TaskSchema,
        target_path: Path,
        provider_name: str,
        api_key: str,
        trace_id: str = "",
        session_id: str = "",
    ) -> RepairOutcome:
        """Register the user-supplied API key and re-run generation.

        The key is stored only in the process environment (not persisted to
        disk) so it is valid for this session only.  The caller is responsible
        for persisting keys securely if needed.
        """
        provider_cfg = self._find_paid_provider(provider_name)
        if not provider_cfg:
            return RepairOutcome(
                status="failed",
                result={"error": f"Unknown provider: {provider_name}"},
                trace_id=trace_id,
                session_id=session_id,
            )

        # Register the key in the environment for this process
        key_env = str(provider_cfg.get("key_env", f"{provider_name.upper()}_API_KEY"))
        os.environ[key_env] = api_key
        LOGGER.info(
            "API key registered for provider=%s env=%s (trace=%s)",
            provider_name, key_env, trace_id,
        )

        # Notify ModelRouter about the new key so it registers the provider
        self._register_provider_key(provider_name, api_key, provider_cfg)

        # Re-generate
        gen_result = self._generate(task, target_path)
        if gen_result.get("status") != "generated":
            return RepairOutcome(
                status="failed",
                result=gen_result,
                trace_id=trace_id,
                session_id=session_id,
            )

        # Verify
        verdict = self._verifier.verify_result(task, target_path)
        if verdict.ok:
            gen_result["provider"] = provider_name
            gen_result["trace_id"] = trace_id
            return RepairOutcome(
                status="generated",
                result=gen_result,
                trace_id=trace_id,
                session_id=session_id,
            )

        return RepairOutcome(
            status="failed",
            result={
                "diagnosis": verdict.diagnosis,
                "provider": provider_name,
            },
            trace_id=trace_id,
            session_id=session_id,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _ai_diagnose(
        self,
        *,
        task: TaskSchema,
        verdict: ResultVerdict,
        attempt_num: int,
        trace_id: str,
    ) -> str:
        """Ask the model router to diagnose why image generation failed."""
        model_router = getattr(self._coordinator, "model_router", None)
        if model_router is None:
            return f"attempt={attempt_num} diagnosis=no_model_router reason={verdict.diagnosis.get('reason','unknown')}"

        prompt = (
            f"Image generation failed for the prompt: \"{task.input_text}\"\n"
            f"Failure reason: {json.dumps(verdict.diagnosis, ensure_ascii=False)}\n"
            f"This is attempt {attempt_num}.\n"
            "In one short sentence, explain the most likely technical cause and "
            "which type of free local model would fix this."
        )
        try:
            return await model_router.invoke(
                "reasoning",
                prompt,
                system_prompt="You are a concise AI image generation diagnostic assistant.",
            )
        except Exception as exc:
            LOGGER.warning("AI diagnosis failed: %s", exc)
            return f"diagnosis unavailable (error: {exc})"

    def _acquire_next_free_model(self, *, attempt_num: int) -> str | None:
        """Ask CapabilityAcquisitionService to download the next HF candidate."""
        svc = getattr(self._coordinator, "capability_acquisition_service", None)
        if svc is None:
            return None
        try:
            result = svc.acquire(
                task_type="image_generation",
                gap=f"invalid_output_attempt_{attempt_num}",
                context={"repair_attempt": attempt_num},
            )
            return result.model_id if result.success else None
        except Exception as exc:
            LOGGER.warning("Model acquisition failed: %s", exc)
            return None

    def _generate(self, task: TaskSchema, target_path: Path) -> dict[str, Any]:
        """Run image generation via coordinator's ImageGenerationService."""
        from nethub_runtime.core.services.image_generation_service import ImageGenerationService
        svc = ImageGenerationService(self._coordinator)
        try:
            return svc.generate(task, target_path)
        except Exception as exc:
            LOGGER.warning("Image generation error: %s", exc)
            return {"status": "error", "error": str(exc)}

    def _find_paid_provider(self, name: str) -> dict[str, Any] | None:
        cfg = _load_verification_policy()
        for p in cfg.get("paid_providers", []):
            if str(p.get("name", "")).lower() == name.lower():
                return p
        return None

    def _register_provider_key(
        self, provider_name: str, api_key: str, provider_cfg: dict[str, Any]
    ) -> None:
        """Inject the API key into ModelRouter's model cache at runtime."""
        model_router = getattr(self._coordinator, "model_router", None)
        if model_router is None:
            return
        model_id = str(provider_cfg.get("model_id", f"{provider_name}:default"))
        if model_id not in model_router.model_cache:
            model_router.model_cache[model_id] = {
                "provider": provider_name,
                "provider_type": provider_name,
                "name": provider_cfg.get("model_name", ""),
                "base_url": provider_cfg.get("endpoint", ""),
                "api_key": api_key,
                "enabled": True,
                "source": "user_supplied_key",
            }
            LOGGER.info("Registered paid provider in model_cache: %s", model_id)
        else:
            model_router.model_cache[model_id]["api_key"] = api_key
            LOGGER.info("Updated API key for existing provider: %s", model_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_verification_policy() -> dict[str, Any]:
    try:
        policy = json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))
        return (policy.get("runtime_behavior") or {}).get("image_verification") or {}
    except Exception as exc:
        LOGGER.warning("Could not load image_verification policy: %s", exc)
        return {}
