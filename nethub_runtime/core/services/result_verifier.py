"""
Generic step result verifier — classifies any step output dict and decides
whether nesthub should accept it, retry it, or escalate to the user.

This is the domain-agnostic core of the universal self-healing pipeline.
Image generation was the first use-case; this module makes the same pattern
available to every executor type (tool, llm, code, agent, knowledge_retrieval).

Classification rules are driven entirely by ``semantic_policy.json``
under ``runtime_behavior.result_verification`` — no status strings or step
names are hardcoded in business logic.

Verdict classes::

    OK             — result is usable as-is
    DEGRADED       — result is a placeholder / dispatch-only; may improve with retry
    FAILED         — result explicitly signals failure; retry with diagnosis
    NEEDS_USER_INPUT — escalate immediately; cannot auto-repair

Usage::

    verifier = StepResultVerifier.from_policy()
    verdict  = verifier.classify(output, step_name="file_generate")

    if verdict.cls == VerdictClass.FAILED:
        # → trigger repair loop
    elif verdict.cls == VerdictClass.NEEDS_USER_INPUT:
        # → surface verdict.details to the caller
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH

LOGGER = logging.getLogger("nethub_runtime.core.result_verifier")

# ---------------------------------------------------------------------------
# Verdict enum
# ---------------------------------------------------------------------------

class VerdictClass(str, Enum):
    OK              = "ok"
    DEGRADED        = "degraded"          # placeholder / dispatch-only
    FAILED          = "failed"            # explicit failure; retry
    NEEDS_USER_INPUT = "needs_user_input" # escalate — user action required


# ---------------------------------------------------------------------------
# Verdict dataclass
# ---------------------------------------------------------------------------

@dataclass
class StepVerdict:
    cls: VerdictClass
    status: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.cls == VerdictClass.OK

    @property
    def needs_repair(self) -> bool:
        return self.cls in (VerdictClass.DEGRADED, VerdictClass.FAILED)

    @property
    def needs_user_input(self) -> bool:
        return self.cls == VerdictClass.NEEDS_USER_INPUT


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class StepResultVerifier:
    """Classifies any step output dict using policy-driven rules.

    All status string lists, step names, and message patterns live in
    ``semantic_policy.json``; none are hardcoded here.
    """

    def __init__(
        self,
        ok_statuses: list[str] | None = None,
        failed_statuses: list[str] | None = None,
        escalate_statuses: list[str] | None = None,
        fire_and_forget_steps: list[str] | None = None,
        degraded_message_patterns: list[str] | None = None,
    ) -> None:
        self._ok = set(ok_statuses or _DEFAULTS["ok_statuses"])
        self._failed = set(failed_statuses or _DEFAULTS["failed_statuses"])
        self._escalate = set(escalate_statuses or _DEFAULTS["escalate_statuses"])
        self._fire_and_forget = set(fire_and_forget_steps or _DEFAULTS["fire_and_forget_steps"])
        self._degraded_patterns = list(
            degraded_message_patterns or _DEFAULTS["degraded_message_patterns"]
        )

    @classmethod
    def from_policy(cls, policy: dict[str, Any] | None = None) -> "StepResultVerifier":
        """Build from ``runtime_behavior.result_verification`` policy block."""
        cfg = policy or _load_policy_section()
        return cls(
            ok_statuses=cfg.get("ok_statuses"),
            failed_statuses=cfg.get("failed_statuses"),
            escalate_statuses=cfg.get("escalate_statuses"),
            fire_and_forget_steps=cfg.get("fire_and_forget_steps"),
            degraded_message_patterns=cfg.get("degraded_message_patterns"),
        )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def classify(self, output: dict[str, Any] | None, step_name: str = "") -> StepVerdict:
        """Classify a step output dict.

        Checks (in priority order):
          1. None or empty dict → DEGRADED
          2. status field maps to an explicit class
          3. "message" contains a degraded pattern → DEGRADED
          4. Presence of domain-specific ok keys (records, aggregation, query…)
          5. fire-and-forget step with status=dispatched → OK
          6. Default → OK (unknown outputs assumed ok)
        """
        if not output:
            return StepVerdict(
                cls=VerdictClass.DEGRADED,
                reason="empty_output",
                details={"step_name": step_name},
            )

        status = str(output.get("status", "")).lower()

        # --- Explicit escalate (user must act) ---
        if status in self._escalate:
            return StepVerdict(
                cls=VerdictClass.NEEDS_USER_INPUT,
                status=status,
                reason=f"step requires user action (status={status})",
                details=output,
            )

        # --- Explicit failure ---
        if status in self._failed:
            return StepVerdict(
                cls=VerdictClass.FAILED,
                status=status,
                reason=f"step reported failure (status={status})",
                details=output,
            )

        # --- Explicit ok ---
        if status in self._ok:
            return StepVerdict(cls=VerdictClass.OK, status=status)

        # --- Dispatched: ok only for fire-and-forget steps ---
        if status == "dispatched":
            if step_name in self._fire_and_forget:
                return StepVerdict(
                    cls=VerdictClass.OK,
                    status="dispatched",
                    reason="fire_and_forget",
                )
            return StepVerdict(
                cls=VerdictClass.DEGRADED,
                status="dispatched",
                reason=(
                    f"step '{step_name}' returned 'dispatched' but is not a "
                    "fire-and-forget step — the result may be incomplete"
                ),
            )

        # --- Message contains a degraded signal ---
        message = str(output.get("message", "")).lower()
        for pattern in self._degraded_patterns:
            if pattern.lower() in message:
                return StepVerdict(
                    cls=VerdictClass.DEGRADED,
                    status=status,
                    reason=f"degraded message pattern matched: '{pattern}'",
                    details={"message_snippet": output.get("message", "")[:200]},
                )

        # --- Domain-specific ok indicators (no status field set) ---
        ok_keys = {"records", "aggregation", "query", "content", "artifact_path", "knowledge"}
        if ok_keys & output.keys():
            return StepVerdict(cls=VerdictClass.OK, status=status or "implicit_ok")

        # --- Default: assume ok for unknown structures ---
        return StepVerdict(cls=VerdictClass.OK, status=status or "unknown")


# ---------------------------------------------------------------------------
# Default policy values
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "ok_statuses": [
        "generated", "read", "saved", "completed", "ok", "success",
        "summarized", "retrieved", "transcribed", "repaired", "received",
    ],
    "failed_statuses": [
        "failed", "error", "invalid_output", "intent_mismatch",
        "not_found",
    ],
    "escalate_statuses": [
        "needs_api_key",
    ],
    "fire_and_forget_steps": [
        "ocr_extract",
        "stt_transcribe",
        "tts_synthesize",
        "video_generate",
    ],
    "degraded_message_patterns": [
        "unsupported",
        "placeholder",
        "not implemented",
        "stub",
    ],
}


def _load_policy_section() -> dict[str, Any]:
    try:
        policy = json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))
        return (policy.get("runtime_behavior") or {}).get("result_verification") or {}
    except Exception as exc:
        LOGGER.warning("Could not load result_verification policy: %s", exc)
        return {}
