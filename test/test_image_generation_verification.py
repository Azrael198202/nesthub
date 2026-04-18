"""
Regression tests — Image Generation Verification & Self-Healing Repair Loop.

Tests exercise the full intent→generate→verify→repair→paid-API pipeline
without touching real networks or downloading real models.

Coverage:
  1. IntentVerdict — ok and mismatch cases
  2. ResultVerdict — file missing, file too small, text-rendered (low entropy),
     valid image, PIL-unavailable fallback
  3. NegotiationRequest.to_dict() structure
  4. ImageGenerationRepairLoop.run() — successful repair on 2nd attempt
  5. ImageGenerationRepairLoop.resume_with_api_key() — success + unknown provider
  6. ImageGenerationService.generate() — intent mismatch, valid first-shot,
     invalid then repaired, needs_api_key bubble-up
"""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# --------------------------------------------------------------------------
# Helpers / stubs
# --------------------------------------------------------------------------

def _make_task(
    intent: str = "image_generation_task",
    input_text: str = "generate an image with cats and dogs",
    task_id: str = "t-001",
) -> Any:
    task = MagicMock()
    task.intent = intent
    task.input_text = input_text
    task.task_id = task_id
    task.metadata = {"trace_id": "trace-abc", "session_id": "sess-xyz"}
    return task


def _make_verifier(
    image_intent_name: str = "image_generation_task",
    paid_providers: list | None = None,
) -> "ImageGenerationVerifier":
    from nethub_runtime.core.services.image_result_verifier import ImageGenerationVerifier
    return ImageGenerationVerifier(
        image_intent_name=image_intent_name,
        paid_providers=paid_providers or [
            {
                "name": "openai",
                "display_name": "OpenAI DALL-E 3",
                "model_name": "dall-e-3",
                "model_id": "openai:dall-e-3",
                "endpoint": "https://api.openai.com/v1/images/generations",
                "key_env": "OPENAI_API_KEY",
                "key_format": "sk-...",
            }
        ],
    )


# --------------------------------------------------------------------------
# 1. Intent verification
# --------------------------------------------------------------------------

class TestIntentVerdict:
    def test_intent_matches(self) -> None:
        from nethub_runtime.core.services.image_result_verifier import IntentVerdict
        verifier = _make_verifier()
        task = _make_task(intent="image_generation_task")
        verdict = verifier.verify_intent(task)
        assert isinstance(verdict, IntentVerdict)
        assert verdict.ok is True
        assert verdict.intent == "image_generation_task"

    def test_intent_mismatch_returns_false(self) -> None:
        verifier = _make_verifier()
        task = _make_task(intent="text_generation_task")
        verdict = verifier.verify_intent(task)
        assert verdict.ok is False
        assert "text_generation_task" in verdict.reason
        assert "image_generation_task" in verdict.reason

    def test_unknown_intent_mismatch(self) -> None:
        verifier = _make_verifier()
        task = _make_task(intent="unknown_intent")
        verdict = verifier.verify_intent(task)
        assert verdict.ok is False


# --------------------------------------------------------------------------
# 2. Result verification
# --------------------------------------------------------------------------

class TestResultVerdict:
    def test_file_missing(self, tmp_path: Path) -> None:
        verifier = _make_verifier()
        task = _make_task()
        missing = tmp_path / "does_not_exist.png"
        verdict = verifier.verify_result(task, missing)
        assert verdict.ok is False
        assert verdict.diagnosis["reason"] == "file_missing"
        assert "retry_generation" in verdict.recommendations

    def test_file_too_small(self, tmp_path: Path) -> None:
        verifier = _make_verifier()
        task = _make_task()
        tiny_file = tmp_path / "tiny.png"
        tiny_file.write_bytes(b"X" * 500)  # below 1024-byte minimum
        verdict = verifier.verify_result(task, tiny_file)
        assert verdict.ok is False
        assert verdict.diagnosis["reason"] == "file_too_small"

    def test_valid_image_without_pil(self, tmp_path: Path) -> None:
        """When PIL is not importable, falls back to size-heuristic (ok=True for big file)."""
        verifier = _make_verifier()
        task = _make_task()
        big_file = tmp_path / "big.png"
        big_file.write_bytes(b"0" * 50_000)  # 50 KB → size heuristic OK

        with patch("importlib.util.find_spec", return_value=None):
            verdict = verifier.verify_result(task, big_file)

        assert verdict.ok is True
        assert verdict.diagnosis["method"] == "size_heuristic"

    def test_text_rendered_as_image(self, tmp_path: Path) -> None:
        """A uniform-colour image (entropy ≈ 0) triggers text_rendered_as_image."""
        pytest.importorskip("PIL")
        from PIL import Image

        # 256×256 pure-white image.  PNG compresses uniform pixels very well
        # so the file is often < 1024 B.  Patch the module threshold so the
        # size gate doesn't fire and only the entropy check runs.
        img = Image.new("RGB", (256, 256), color=(255, 255, 255))
        img_file = tmp_path / "white.png"
        img.save(img_file)

        verifier = _make_verifier()
        task = _make_task()

        import nethub_runtime.core.services.image_result_verifier as _mod
        with patch.object(_mod, "_MIN_IMAGE_BYTES", 100):
            verdict = verifier.verify_result(task, img_file)

        assert verdict.ok is False
        assert verdict.diagnosis["reason"] == "text_rendered_as_image"
        assert "try_paid_api" in verdict.recommendations

    def test_real_rgb_image_passes(self, tmp_path: Path) -> None:
        """A reasonably varied colour image should pass entropy check."""
        pytest.importorskip("PIL")
        from PIL import Image  # type: ignore
        import random

        img = Image.new("RGB", (64, 64))
        pixels = img.load()
        for x in range(64):
            for y in range(64):
                pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))  # noqa

        img_file = tmp_path / "random.png"
        img.save(img_file)

        verifier = _make_verifier()
        task = _make_task()
        verdict = verifier.verify_result(task, img_file)
        assert verdict.ok is True
        assert verdict.diagnosis["method"] == "pil_entropy"


# --------------------------------------------------------------------------
# 3. NegotiationRequest structure
# --------------------------------------------------------------------------

class TestNegotiationRequest:
    def test_to_dict_structure(self) -> None:
        from nethub_runtime.core.services.image_result_verifier import NegotiationRequest
        providers = [{"name": "openai", "key_env": "OPENAI_API_KEY"}]
        req = NegotiationRequest(
            providers=providers,
            context_summary="cats and dogs image",
            session_id="s-1",
            trace_id="t-1",
        )
        d = req.to_dict()
        assert d["type"] == "api_key_required"
        assert d["providers"] == providers
        assert d["session_id"] == "s-1"
        assert d["trace_id"] == "t-1"
        assert "message" in d

    def test_build_negotiation_from_verifier(self) -> None:
        verifier = _make_verifier()
        task = _make_task()
        req = verifier.build_negotiation_request(task, session_id="s-2", trace_id="t-2")
        assert req.session_id == "s-2"
        assert req.trace_id == "t-2"
        assert len(req.providers) >= 1
        assert "cats and dogs" in req.context_summary


# --------------------------------------------------------------------------
# 4. Repair loop — success on 2nd attempt
# --------------------------------------------------------------------------

class TestRepairLoop:
    def _make_loop(self, verifier=None):
        from nethub_runtime.core.services.image_generation_repair_loop import ImageGenerationRepairLoop
        coordinator = MagicMock()
        coordinator.capability_acquisition_service = MagicMock()
        coordinator.model_router = None
        loop = ImageGenerationRepairLoop(
            coordinator=coordinator,
            verifier=verifier or _make_verifier(),
            max_free_retries=3,
        )
        return loop, coordinator

    def test_success_on_second_attempt(self, tmp_path: Path) -> None:
        """On attempt 1 verify fails; on attempt 2 verify passes."""
        pytest.importorskip("PIL")
        from PIL import Image
        import random

        target = tmp_path / "out.png"
        call_count = [0]

        def fake_generate(task, path):
            call_count[0] += 1
            img = Image.new("RGB", (64, 64))
            pixels = img.load()
            # Second call → vary colours so entropy passes
            if call_count[0] >= 2:
                for x in range(64):
                    for y in range(64):
                        pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))  # noqa
            img.save(path)
            return {"status": "generated", "artifact_path": str(path)}

        from nethub_runtime.core.services.image_result_verifier import ResultVerdict

        loop, coordinator = self._make_loop()

        with patch.object(loop, "_generate", side_effect=fake_generate):
            with patch.object(loop, "_ai_diagnose", new_callable=AsyncMock) as mock_diag:
                mock_diag.return_value = "model produced plain text"
                with patch.object(loop, "_acquire_next_free_model", return_value="stabilityai/model-v2"):
                    # Create a low-entropy initial verdict to enter the loop
                    bad_verdict = ResultVerdict(
                        ok=False,
                        diagnosis={"reason": "text_rendered_as_image", "entropy": 0.01},
                        recommendations=["switch_to_diffusion_model"],
                    )
                    outcome = asyncio.run(
                        loop.run(
                            task=_make_task(),
                            target_path=target,
                            initial_verdict=bad_verdict,
                            trace_id="trace-1",
                            session_id="sess-1",
                        )
                    )
        assert outcome.status == "generated", f"Got: {outcome.status} {outcome.attempts}"
        assert outcome.trace_id == "trace-1"
        assert outcome.session_id == "sess-1"

    def test_exhausted_retries_return_needs_api_key(self, tmp_path: Path) -> None:
        """All retries fail → outcome.status == 'needs_api_key'."""
        from nethub_runtime.core.services.image_result_verifier import ResultVerdict

        target = tmp_path / "out.png"
        target.write_bytes(b"X" * 500)  # always too small

        loop, _ = self._make_loop()
        bad_verdict = ResultVerdict(
            ok=False,
            diagnosis={"reason": "file_too_small"},
            recommendations=["retry_with_different_backend"],
        )

        with patch.object(loop, "_generate", return_value={"status": "generated"}):
            with patch.object(loop, "_ai_diagnose", new_callable=AsyncMock, return_value="disk full"):
                with patch.object(loop, "_acquire_next_free_model", return_value=None):
                    outcome = asyncio.run(
                        loop.run(
                            task=_make_task(),
                            target_path=target,
                            initial_verdict=bad_verdict,
                        )
                    )

        assert outcome.status == "needs_api_key"
        assert outcome.negotiation_request is not None
        assert len(outcome.negotiation_request.providers) >= 1

    def test_resume_with_unknown_provider_fails(self, tmp_path: Path) -> None:
        from nethub_runtime.core.services.image_generation_repair_loop import ImageGenerationRepairLoop
        coordinator = MagicMock()
        # Load from policy — providers come from semantic_policy.json
        loop = ImageGenerationRepairLoop.from_policy(coordinator=coordinator)
        outcome = asyncio.run(
            loop.resume_with_api_key(
                task=_make_task(),
                target_path=tmp_path / "out.png",
                provider_name="nonexistent_provider_xyz",
                api_key="abc123",
            )
        )
        assert outcome.status == "failed"
        assert "Unknown provider" in outcome.result.get("error", "")

    def test_resume_with_valid_key_registers_env(self, tmp_path: Path) -> None:
        """Providing a key for a known provider registers the env variable."""
        pytest.importorskip("PIL")
        from PIL import Image
        import random

        target = tmp_path / "paid.png"

        img = Image.new("RGB", (64, 64))
        pixels = img.load()
        for x in range(64):
            for y in range(64):
                pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))  # noqa
        img.save(target)

        from nethub_runtime.core.services.image_generation_repair_loop import ImageGenerationRepairLoop
        coordinator = MagicMock()
        loop = ImageGenerationRepairLoop.from_policy(coordinator=coordinator)

        with patch.object(loop, "_generate", return_value={"status": "generated"}):
            outcome = asyncio.run(
                loop.resume_with_api_key(
                    task=_make_task(),
                    target_path=target,
                    provider_name="openai",
                    api_key="sk-testkey",
                    trace_id="trace-paid",
                )
            )

        # The env variable should now be set
        assert os.environ.get("OPENAI_API_KEY") == "sk-testkey"
        assert outcome.status == "generated"
        assert outcome.trace_id == "trace-paid"

        # Cleanup env
        del os.environ["OPENAI_API_KEY"]


# --------------------------------------------------------------------------
# 5. ImageGenerationService.generate() integration
# --------------------------------------------------------------------------

class TestImageGenerationServiceGenerate:
    def _make_service(self):
        from nethub_runtime.core.services.image_generation_service import ImageGenerationService
        coordinator = MagicMock()
        coordinator.capability_acquisition_service = None
        coordinator.model_router = None
        svc = ImageGenerationService(coordinator)
        return svc

    def test_intent_mismatch_returns_early(self, tmp_path: Path) -> None:
        svc = self._make_service()
        task = _make_task(intent="text_generation_task")
        result = svc.generate(task, tmp_path / "img.png")
        assert result["status"] == "intent_mismatch"
        assert "intent_verdict" in result

    def test_valid_generation_with_pil_passes(self, tmp_path: Path) -> None:
        """Backend succeeds + result is valid → status=generated."""
        pytest.importorskip("PIL")
        from PIL import Image
        import random

        target = tmp_path / "out.png"
        img = Image.new("RGB", (64, 64))
        pixels = img.load()
        for x in range(64):
            for y in range(64):
                pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))  # noqa
        img.save(target)

        svc = self._make_service()
        task = _make_task()

        with patch.object(svc, "_try_all_backends", return_value={"status": "generated", "artifact_path": str(target)}):
            result = svc.generate(task, target)

        assert result["status"] == "generated"
        assert result.get("result_verification", {}).get("ok") is True

    def test_invalid_output_triggers_repair_loop(self, tmp_path: Path) -> None:
        """Backend reports generated but file is tiny → enters repair loop."""
        target = tmp_path / "out.png"
        target.write_bytes(b"X" * 200)  # too small

        svc = self._make_service()
        task = _make_task()

        with patch.object(
            svc, "_try_all_backends", return_value={"status": "generated", "artifact_path": str(target)}
        ):
            with patch(
                "nethub_runtime.core.services.image_generation_service.ImageGenerationRepairLoop.from_policy"
            ) as mock_loop_cls:
                mock_loop = MagicMock()
                from nethub_runtime.core.services.image_generation_repair_loop import RepairOutcome
                mock_loop.run = AsyncMock(
                    return_value=RepairOutcome(
                        status="needs_api_key",
                        negotiation_request=_make_verifier().build_negotiation_request(task),
                    )
                )
                mock_loop_cls.return_value = mock_loop
                result = svc.generate(task, target)

        assert result["status"] == "needs_api_key"
        assert "negotiation_request" in result
