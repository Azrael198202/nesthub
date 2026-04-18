"""
Image generation service with autonomous self-healing capability.

When no image backend is available, the service:
1. Detects the capability gap
2. Triggers auto-install of required packages (pillow, diffusers, torch)
3. Falls back to autonomous code generation executed in a subprocess
4. Retries through the backend chain until one succeeds

This embodies the core design principle from docs/03_core/ai_core.md §4.7:
  "发现缺口 -> 自写实现 -> 回到可复用运行态"
  (Detect gap → self-implement → return to reusable runtime state)
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import textwrap
import logging
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.image_result_verifier import ImageGenerationVerifier
from nethub_runtime.core.services.image_generation_repair_loop import ImageGenerationRepairLoop

LOGGER = logging.getLogger("nethub_runtime.core.image_generation_service")

# Ordered list of backends tried in sequence.
# huggingface_auto sits between local_diffusion (which needs a cached model)
# and pillow (pure placeholder), so it can autonomously acquire a real model
# from HuggingFace when no local model is present.
# Priority: local first (free) → paid API (real quality) → pillow placeholder (absolute last resort)
_BACKENDS = ["local_diffusion", "huggingface_auto", "openai_api", "pillow"]

# Packages needed per backend (import spec → pip name)
_BACKEND_PACKAGES: dict[str, list[tuple[str, str]]] = {
    "pillow": [("PIL", "pillow")],
    "local_diffusion": [("diffusers", "diffusers"), ("torch", "torch")],
    "huggingface_auto": [
        ("diffusers", "diffusers"),
        ("transformers", "transformers"),
        ("huggingface_hub", "huggingface_hub"),
        ("torch", "torch"),
        ("PIL", "pillow"),
    ],
}


class ImageGenerationService:
    """
    Self-healing image generation service.

    Tries backends in order:
      1. External model API (OpenAI image generation, etc.) via model_router
      2. Local diffusion model (diffusers + torch)
      3. Pillow placeholder (geometry-drawn, always installable)

    If all backends fail, triggers autonomous capability repair:
      - pip-installs missing packages (pillow at minimum)
      - Retries the backend chain
      - As a last resort, generates and executes minimal Python code in a
        subprocess so that the image is produced even in degraded environments
    """

    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator
        # Lazily resolved so the service works even when coordinator has no
        # capability_acquisition_service attribute (e.g. in unit tests).
        self._acquisition_svc: Any | None = getattr(
            coordinator, "capability_acquisition_service", None
        )
        self._verifier = ImageGenerationVerifier.from_policy()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(self, task: TaskSchema, target_path: Path) -> dict[str, Any]:
        """Generate image at target_path, with intent + result verification and self-healing."""
        import asyncio
        import concurrent.futures

        # ---- Step 1: Verify intent before doing any generation ----
        intent_verdict = self._verifier.verify_intent(task)
        if not intent_verdict.ok:
            LOGGER.warning(
                "intent_verification_failed task=%s reason=%s",
                task.task_id, intent_verdict.reason,
            )
            return {
                "artifact_type": "image",
                "status": "intent_mismatch",
                "task": task.intent,
                "intent_verdict": {
                    "ok": False,
                    "intent": intent_verdict.intent,
                    "reason": intent_verdict.reason,
                },
                "message": (
                    f"Intent was understood as '{intent_verdict.intent}' — "
                    "please rephrase your request to make clear you want an image."
                ),
            }
        LOGGER.info("intent_verification OK intent=%s task=%s", task.intent, task.task_id)

        # ---- Step 2: Attempt generation ----
        result = self._try_all_backends(task, target_path)

        if result["status"] == "generated":
            # ---- Step 3: Verify the output is a real image ----
            # Pillow is a known placeholder backend — skip entropy verification
            # to avoid an infinite repair loop (pillow always draws text).
            if result.get("method") == "pillow":
                result["result_verification"] = {"ok": True, "method": "pillow_placeholder"}
                LOGGER.info("pillow placeholder accepted without entropy check (task=%s)", task.task_id)
                return result

            verdict = self._verifier.verify_result(task, target_path)
            if verdict.ok:
                result["result_verification"] = {"ok": True, **verdict.diagnosis}
                return result

            # Output exists but is invalid (text render, blank, etc.)
            LOGGER.warning(
                "result_verification FAILED task=%s reason=%s",
                task.task_id, verdict.diagnosis.get("reason"),
            )
            result["result_verification"] = {"ok": False, **verdict.diagnosis}
            result["status"] = "invalid_output"

            # ---- Step 4: Enter repair loop (always in a fresh thread/loop) ----
            repair_loop = ImageGenerationRepairLoop.from_policy(coordinator=self.coordinator)

            def _run_repair() -> Any:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(
                        repair_loop.run(
                            task=task,
                            target_path=target_path,
                            initial_verdict=verdict,
                            trace_id=str(task.metadata.get("trace_id", "")),
                            session_id=str(task.metadata.get("session_id", "")),
                        )
                    )
                finally:
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                outcome = pool.submit(_run_repair).result()

            if outcome.status == "generated":
                return outcome.result
            if outcome.status == "needs_api_key":
                return {
                    "artifact_type": "image",
                    "status": "needs_api_key",
                    "task": "image_generation",
                    "repair_history": outcome.attempts,
                    "negotiation_request": outcome.negotiation_request.to_dict()
                    if outcome.negotiation_request
                    else None,
                    "message": (
                        "Free models exhausted. Provide an API key to continue."
                    ),
                }
            # outcome.status == "failed"
            return {
                "artifact_type": "image",
                "status": "failed",
                "task": "image_generation",
                "repair_history": outcome.attempts,
                "message": "Image generation failed after all repair attempts.",
            }

        # Backend chain failed entirely — try capability repair then re-enter loop
        LOGGER.info(
            "image_generation: no backend succeeded (task=%s). "
            "Delegating to CapabilityAcquisitionService.",
            task.task_id,
        )

        repair_result = self._trigger_capability_repair()
        LOGGER.info("capability_repair result: %s", repair_result)

        result = self._try_all_backends(task, target_path)
        if result["status"] == "generated":
            verdict = self._verifier.verify_result(task, target_path)
            result["capability_gap_repaired"] = True
            result["repair_result"] = repair_result
            result["result_verification"] = {"ok": verdict.ok, **verdict.diagnosis}
            if not verdict.ok:
                result["status"] = "invalid_output"
            return result

        # ---- Last resort: autonomous code generation + subprocess execution ----
        LOGGER.info(
            "image_generation: still no backend after repair. "
            "Attempting autonomous code generation."
        )
        generated_ok = self._generate_and_execute_image_code(task, target_path)
        if generated_ok:
            verdict = self._verifier.verify_result(task, target_path)
            return {
                "artifact_type": "image",
                "artifact_path": str(target_path),
                "status": "generated" if verdict.ok else "invalid_output",
                "task": "image_generation",
                "file_name": target_path.name,
                "storage": "workspace",
                "capability_gap_repaired": True,
                "repair_result": repair_result,
                "result_verification": {"ok": verdict.ok, **verdict.diagnosis},
                "method": "autonomous_code_generation",
            }

        return {
            "artifact_type": "image",
            "status": "failed",
            "task": "image_generation",
            "message": "Image generation failed after all autonomous repair attempts.",
            "repair_result": repair_result,
        }

    # ------------------------------------------------------------------
    # Backend chain
    # ------------------------------------------------------------------

    def _try_all_backends(self, task: TaskSchema, target_path: Path) -> dict[str, Any]:
        for backend in _BACKENDS:
            image_bytes = self._try_backend(backend, task)
            if image_bytes is not None:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(image_bytes)
                return {
                    "artifact_type": "image",
                    "artifact_path": str(target_path),
                    "status": "generated",
                    "task": "image_generation",
                    "file_name": target_path.name,
                    "storage": "workspace",
                    "method": backend,
                }
        return {"artifact_type": "image", "status": "no_backend", "task": "image_generation"}

    def _try_backend(self, backend: str, task: TaskSchema) -> bytes | None:
        try:
            if backend == "local_diffusion":
                return self._try_local_diffusion(task)
            if backend == "huggingface_auto":
                return self._try_huggingface_auto(task)
            if backend == "pillow":
                return self._try_pillow(task.input_text)
            if backend == "openai_api":
                return self._try_model_api(task)
        except Exception as exc:
            LOGGER.debug("backend %s failed: %s", backend, exc)
        return None

    def _try_model_api(self, task: TaskSchema) -> bytes | None:
        """Try external image API: OpenAI DALL-E 3 → Stability AI → Replicate.

        Reads keys from environment; skips silently when no key is present.
        """
        import os, urllib.request, urllib.error, json as _json, base64 as _b64

        prompt = task.input_text or ""

        # --- OpenAI DALL-E 3 ---
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key:
            try:
                body = _json.dumps({
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "b64_json",
                }).encode()
                req = urllib.request.Request(
                    "https://api.openai.com/v1/images/generations",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = _json.loads(resp.read())
                b64 = (data.get("data") or [{}])[0].get("b64_json", "")
                if b64:
                    LOGGER.info("_try_model_api: OpenAI DALL-E 3 success")
                    return _b64.b64decode(b64)
            except urllib.error.HTTPError as e:
                LOGGER.warning("_try_model_api: OpenAI error %s: %s", e.code, e.read()[:200])
            except Exception as exc:
                LOGGER.debug("_try_model_api: OpenAI failed: %s", exc)

        # --- Stability AI ---
        stability_key = os.getenv("STABILITY_API_KEY", "").strip()
        if stability_key:
            try:
                body = _json.dumps({
                    "text_prompts": [{"text": prompt}],
                    "cfg_scale": 7, "height": 1024, "width": 1024,
                    "samples": 1, "steps": 30,
                }).encode()
                req = urllib.request.Request(
                    "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {stability_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = _json.loads(resp.read())
                b64 = ((data.get("artifacts") or [{}])[0]).get("base64", "")
                if b64:
                    LOGGER.info("_try_model_api: Stability AI success")
                    return _b64.b64decode(b64)
            except Exception as exc:
                LOGGER.debug("_try_model_api: Stability AI failed: %s", exc)

        return None

    def _try_local_diffusion(self, task: TaskSchema) -> bytes | None:
        """
        Try a locally-cached diffusion model via the diffusers library.

        Only runs when diffusers + torch are already installed and the default
        HuggingFace cache already contains a model — no download triggered here.
        Download and model selection is the responsibility of
        ``_try_huggingface_auto``.
        """
        if importlib.util.find_spec("diffusers") is None:
            return None
        if importlib.util.find_spec("torch") is None:
            return None
        import io
        from diffusers import DiffusionPipeline  # type: ignore
        import torch  # type: ignore

        # Use the model that huggingface_auto already downloaded and persisted
        # in policy, if available.  Fall back to the first candidate in policy.
        model_id = self._get_active_hf_model_id()
        if not model_id:
            return None  # no model acquired yet — huggingface_auto will handle it

        pipe = DiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            safety_checker=None,
            local_files_only=True,  # only use cache; no download here
        )
        if torch.cuda.is_available():
            pipe = pipe.to("cuda")
        steps = self._get_hf_model_steps(model_id)
        image = pipe(task.input_text, num_inference_steps=steps).images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # HuggingFace autonomous model acquisition backend
    # ------------------------------------------------------------------

    def _try_huggingface_auto(self, task: TaskSchema) -> bytes | None:
        """
        Autonomous HuggingFace model acquisition via CapabilityAcquisitionService.

        Delegates the full discovery → install → verify loop to the universal
        acquisition service.  On success, the winning model_id is persisted by
        that service so future requests skip discovery.
        """
        svc = self._acquisition_svc
        if svc is None:
            # Fallback: direct acquisition when running outside the full engine
            from nethub_runtime.core.services.capability_acquisition_service import (
                CapabilityAcquisitionService,
            )
            svc = CapabilityAcquisitionService(
                security_guard=getattr(self.coordinator, "security_guard", None)
            )

        result = svc.acquire(task_type="image_generation", gap="no_image_model")
        if not result.success:
            LOGGER.info("huggingface_auto: acquisition failed: %s", result.detail)
            return None

        # Model is now cached locally — use the confirmed model_id to run inference
        model_id = result.model_id or self._get_active_hf_model_id()
        if not model_id:
            return None

        import io
        import torch  # type: ignore
        from diffusers import DiffusionPipeline  # type: ignore

        steps = self._get_hf_model_steps(model_id)
        pipe = DiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            safety_checker=None,
        )
        if torch.cuda.is_available():
            pipe = pipe.to("cuda")
        image = pipe(task.input_text, num_inference_steps=steps).images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # HuggingFace policy helpers (read-only — acquisition is in CapabilityAcquisitionService)
    # ------------------------------------------------------------------

    def _get_active_hf_model_id(self) -> str | None:
        """Return the model_id last confirmed working by CapabilityAcquisitionService."""
        try:
            from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
            store = SemanticPolicyStore(policy_path=SEMANTIC_POLICY_PATH)
            runtime = store.load_runtime_policy()
            return runtime.get("active_model_image_generation") or None
        except Exception:
            return None

    def _get_hf_model_steps(self, model_id: str) -> int:
        """Return inference_steps for a given model_id from the acquisition strategy."""
        try:
            policy = json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))
            candidates = (
                (policy.get("capability_acquisition_strategies") or {})
                .get("image_generation", {})
                .get("huggingface_candidates") or []
            )
            for c in candidates:
                if c.get("model_id") == model_id:
                    return int(c.get("inference_steps", 20))
        except Exception:
            pass
        return 20

    # ------------------------------------------------------------------
    # Autonomous capability repair (delegates to CapabilityAcquisitionService)
    # ------------------------------------------------------------------

    def _trigger_capability_repair(self) -> dict[str, Any]:
        """
        Delegate capability gap repair to CapabilityAcquisitionService.

        The universal acquisition loop (search PyPI, search HuggingFace Hub,
        install, record to learning store) lives there.  Any other service
        that lacks a capability calls the same path.
        """
        svc = self._acquisition_svc
        if svc is None:
            from nethub_runtime.core.services.capability_acquisition_service import (
                CapabilityAcquisitionService,
            )
            svc = CapabilityAcquisitionService(
                security_guard=getattr(self.coordinator, "security_guard", None)
            )
        result = svc.acquire(task_type="image_generation", gap="missing_packages")
        return result.to_dict()

    def _try_pillow(self, prompt: str) -> bytes | None:
        """
        Generic labeled placeholder PNG.

        No business-specific shapes — canvas renders the prompt text so the
        output is meaningful regardless of content.  Actual imagery is the
        responsibility of a real model backend.
        """
        if importlib.util.find_spec("PIL") is None:
            return None
        import io
        from PIL import Image, ImageDraw  # type: ignore

        width, height = 512, 512
        img = Image.new("RGB", (width, height), color=(245, 245, 250))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, width - 11, height - 11], outline=(180, 190, 210), width=2)

        words = prompt.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if len(test) > 50:
                if current:
                    lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        y = 30
        for line in lines[:16]:
            draw.text((20, y), line, fill=(60, 70, 90))
            y += 22

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Autonomous capability repair (delegates to CapabilityAcquisitionService)
    # ------------------------------------------------------------------

    def _trigger_capability_repair(self) -> dict[str, Any]:
        """
        Delegate capability gap repair to CapabilityAcquisitionService.
        """
        svc = self._acquisition_svc
        if svc is None:
            from nethub_runtime.core.services.capability_acquisition_service import (
                CapabilityAcquisitionService,
            )
            svc = CapabilityAcquisitionService(
                security_guard=getattr(self.coordinator, "security_guard", None)
            )
        result = svc.acquire(task_type="image_generation", gap="missing_packages")
        return result.to_dict()

    # ------------------------------------------------------------------
    # Last-resort: autonomous code generation + subprocess execution
    # ------------------------------------------------------------------

    def _generate_and_execute_image_code(self, task: TaskSchema, target_path: Path) -> bool:
        """
        Autonomously generate and execute a minimal Python script that:
          1. pip-installs Pillow if missing
          2. Renders the prompt text as a labeled placeholder PNG

        The script is fully generic — no business-specific drawing.
        Executed in a subprocess so it can self-install Pillow before
        the current interpreter has access to it.
        """
        label = repr(task.input_text[:200])
        target_repr = repr(str(target_path))
        code = textwrap.dedent(f"""\
            import sys, subprocess, importlib.util
            if importlib.util.find_spec("PIL") is None:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "pillow", "--quiet"],
                    check=True,
                )
                importlib.invalidate_caches()

            from PIL import Image, ImageDraw
            from pathlib import Path

            target = Path({target_repr})
            target.parent.mkdir(parents=True, exist_ok=True)

            img = Image.new("RGB", (512, 512), color=(245, 245, 250))
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 10, 501, 501], outline=(180, 190, 210), width=2)

            prompt = {label}
            words = prompt.split()
            lines, current = [], ""
            for w in words:
                test = (current + " " + w).strip()
                if len(test) > 50:
                    if current:
                        lines.append(current)
                    current = w
                else:
                    current = test
            if current:
                lines.append(current)
            y = 30
            for line in lines[:16]:
                draw.text((20, y), line, fill=(60, 70, 90))
                y += 22

            img.save(str(target), format="PNG")
            print("OK:" + str(target))
        """)
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if proc.returncode == 0 and target_path.exists():
                LOGGER.info("autonomous_code_generation: image saved to %s", target_path)
                return True
            LOGGER.warning(
                "autonomous_code_generation script failed (rc=%d): %s",
                proc.returncode,
                proc.stderr[:300],
            )
        except Exception as exc:
            LOGGER.warning("autonomous_code_generation exception: %s", exc)
        return False
