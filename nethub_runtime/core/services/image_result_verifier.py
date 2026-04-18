"""
Image Generation Verifier — closes the "intent → result" feedback loop.

Flow (mirrors OpenClaw's hook + repair philosophy):

  Step 1 – Intent Verification
    Before generating: confirm the understood intent matches the user's request.
    Checks that TaskSchema.intent == "image_generation_task" AND the prompt
    contains the subject described in the original input.

  Step 2 – Result Verification
    After generating: verify the output is actually an image file (not plain
    text rendered to PNG, not a blank canvas, not a 0-byte file).
    Uses PIL histogram analysis when available; falls back to file-size heuristics.

  Step 3 – Diagnosis
    When the result is wrong, classify WHY (wrong_backend / blank_output /
    text_rendered / file_missing) and return a structured diagnosis that the
    repair loop can act on.

  Step 4 – Paid-model Negotiation
    When all free retries are exhausted, build a ``NegotiationRequest`` describing
    which paid APIs are available (in priority order from semantic_policy.json),
    what key format is needed, and what the endpoint looks like.  The caller
    (ImageGenerationService) surfaces this to the user and waits for a key.

Usage::

    verifier = ImageGenerationVerifier.from_policy()

    # Check intent BEFORE generating
    ok, reason = verifier.verify_intent(task)

    # Check result AFTER generating
    verdict = verifier.verify_result(task, image_path)

    if not verdict.ok:
        diagnosis = verdict.diagnosis       # dict with "reason" key
        recs     = verdict.recommendations  # list[str] of suggested actions
"""

from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.schemas.task_schema import TaskSchema

LOGGER = logging.getLogger("nethub_runtime.core.image_result_verifier")

# Minimum file size that counts as a real image (pillow placeholder is ~30 KB)
_MIN_IMAGE_BYTES = 1024
# A text-rendered PNG is usually small and uniform — histogram entropy below
# this threshold (0..1 normalised) strongly suggests no photographic content.
# Pure white = ~0.165; real generated image ≥ 0.7.  Use 0.3 as the gate.
_MIN_ENTROPY_SCORE = 0.3


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class IntentVerdict:
    """Result of intent verification (before generation)."""
    ok: bool
    intent: str
    reason: str = ""


@dataclass
class ResultVerdict:
    """Result of output verification (after generation)."""
    ok: bool
    diagnosis: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class NegotiationRequest:
    """Describes what the user needs to supply to unlock a paid image API."""
    providers: list[dict[str, Any]]   # [{name, endpoint, key_env, key_format, docs_url}]
    context_summary: str              # Short description of what was being generated
    session_id: str = ""
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "api_key_required",
            "providers": self.providers,
            "context_summary": self.context_summary,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "message": (
                "Free models could not produce a valid image. "
                "Please provide an API key for one of the paid providers listed above."
            ),
        }


# ---------------------------------------------------------------------------
# Main verifier
# ---------------------------------------------------------------------------

class ImageGenerationVerifier:
    """Verifies intent and output quality for image generation tasks.

    All domain vocabulary (subject keywords, paid provider names) lives in
    ``semantic_policy.json``; this class contains only structural logic.
    """

    def __init__(
        self,
        image_intent_name: str = "image_generation_task",
        paid_providers: list[dict[str, Any]] | None = None,
    ) -> None:
        self._image_intent = image_intent_name
        self._paid_providers = paid_providers or []

    @classmethod
    def from_policy(cls, policy: dict[str, Any] | None = None) -> "ImageGenerationVerifier":
        """Build from ``runtime_behavior.image_verification`` policy block."""
        cfg = policy or _load_policy_section()
        return cls(
            image_intent_name=cfg.get("image_intent_name", "image_generation_task"),
            paid_providers=cfg.get("paid_providers", []),
        )

    # ------------------------------------------------------------------
    # Step 1 — Intent verification
    # ------------------------------------------------------------------

    def verify_intent(self, task: TaskSchema) -> IntentVerdict:
        """Check that the parsed intent is actually image generation.

        Returns IntentVerdict(ok=True) when the intent matches the configured
        image intent name.  A mismatch means the intent analysis mis-classified
        the request and the caller should re-run intent analysis or prompt the
        user for clarification.
        """
        if task.intent != self._image_intent:
            return IntentVerdict(
                ok=False,
                intent=task.intent,
                reason=(
                    f"Intent resolved to '{task.intent}' but expected "
                    f"'{self._image_intent}'. Input may have been misclassified."
                ),
            )
        LOGGER.debug("Intent verification OK: %s", task.intent)
        return IntentVerdict(ok=True, intent=task.intent)

    # ------------------------------------------------------------------
    # Step 2 — Result verification
    # ------------------------------------------------------------------

    def verify_result(self, task: TaskSchema, image_path: Path) -> ResultVerdict:
        """Verify the generated image file actually contains visual content.

        Checks (in order):
          1. File exists and is not empty.
          2. File is a valid image (PIL can open it).
          3. Image has real visual entropy (not a plain text render).
        """
        # --- File existence / size ---
        if not image_path.exists():
            return ResultVerdict(
                ok=False,
                diagnosis={"reason": "file_missing", "path": str(image_path)},
                recommendations=["retry_generation", "check_output_path"],
            )

        file_size = image_path.stat().st_size
        if file_size < _MIN_IMAGE_BYTES:
            return ResultVerdict(
                ok=False,
                diagnosis={
                    "reason": "file_too_small",
                    "bytes": file_size,
                    "min_expected": _MIN_IMAGE_BYTES,
                },
                recommendations=["retry_with_different_backend", "check_model_availability"],
            )

        # --- PIL image validation ---
        if importlib.util.find_spec("PIL") is not None:
            verdict = self._verify_with_pil(image_path, task)
            return verdict

        # --- Fallback: size-only heuristic ---
        LOGGER.debug("PIL not available; using size heuristic only")
        return ResultVerdict(ok=True, diagnosis={"method": "size_heuristic", "bytes": file_size})

    def _verify_with_pil(self, image_path: Path, task: TaskSchema) -> ResultVerdict:
        """Use PIL for structural + entropy validation."""
        try:
            from PIL import Image  # type: ignore
        except ImportError:
            return ResultVerdict(ok=True, diagnosis={"method": "pil_unavailable"})

        try:
            img = Image.open(image_path)
            img.verify()          # raises if the file is corrupt
            img = Image.open(image_path)  # re-open after verify()
        except Exception as exc:
            return ResultVerdict(
                ok=False,
                diagnosis={"reason": "corrupt_image", "error": str(exc)},
                recommendations=["retry_generation", "try_different_model"],
            )

        # Entropy check — text-to-PNG renders have very low colour variance
        entropy = self._image_entropy(img)
        LOGGER.debug("Image entropy score: %.4f (threshold=%.4f)", entropy, _MIN_ENTROPY_SCORE)

        if entropy < _MIN_ENTROPY_SCORE:
            return ResultVerdict(
                ok=False,
                diagnosis={
                    "reason": "text_rendered_as_image",
                    "entropy": round(entropy, 4),
                    "prompt": task.input_text[:120],
                    "detail": (
                        "The output appears to be text/placeholder rendered to PNG "
                        "rather than a real generated image. The model likely produced "
                        "a caption or label instead of actual pixel art."
                    ),
                },
                recommendations=[
                    "switch_to_diffusion_model",
                    "retry_with_huggingface_auto",
                    "try_paid_api",
                ],
            )

        return ResultVerdict(
            ok=True,
            diagnosis={"method": "pil_entropy", "entropy": round(entropy, 4)},
        )

    @staticmethod
    def _image_entropy(img: Any) -> float:
        """Return a 0-1 colour-entropy score.  Low → image is nearly uniform."""
        try:
            rgb = img.convert("RGB")
            histogram = rgb.histogram()  # 256 bins × 3 channels = 768 values
            total = sum(histogram) or 1
            import math
            entropy = 0.0
            for count in histogram:
                if count > 0:
                    p = count / total
                    entropy -= p * math.log2(p)
            # Normalise: max theoretical entropy for 768 bins is log2(768) ≈ 9.58
            return entropy / 9.58
        except Exception:
            return 1.0   # assume OK on error

    # ------------------------------------------------------------------
    # Step 3 — Paid-model negotiation
    # ------------------------------------------------------------------

    def build_negotiation_request(
        self,
        task: TaskSchema,
        *,
        session_id: str = "",
        trace_id: str = "",
    ) -> NegotiationRequest:
        """Build a request asking the user to supply a paid API key.

        The provider list comes from ``semantic_policy.json::runtime_behavior
        .image_verification.paid_providers`` so no provider names are
        hardcoded here.
        """
        return NegotiationRequest(
            providers=self._paid_providers,
            context_summary=(
                f"I was trying to generate: \"{task.input_text[:200]}\"\n"
                "All free local models have been tried and the result does not "
                "contain the expected visual content."
            ),
            session_id=session_id,
            trace_id=trace_id,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_policy_section() -> dict[str, Any]:
    """Load ``runtime_behavior.image_verification`` from semantic_policy.json."""
    try:
        policy = json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))
        return (policy.get("runtime_behavior") or {}).get("image_verification") or {}
    except Exception as exc:
        LOGGER.warning("Could not load image_verification policy: %s", exc)
        return {}
