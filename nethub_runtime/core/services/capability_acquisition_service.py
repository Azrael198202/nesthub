"""
Universal Capability Acquisition Service.

NestHub's self-awareness principle:
  "遇到自己无法完成的任务 → 检测缺口 → 去网络找到能用的工具/模型 → 安装 → 重试 → 记忆结果"
  (Encounter unresolvable task → detect gap → find suitable tool/model online → install → retry → remember)

Any service that discovers it lacks a capability delegates here instead of
hard-coding the acquisition logic itself.  All acquisition strategies
(HuggingFace task tags, PyPI search terms, model priorities) live in
``semantic_policy.json`` — this file contains only the structural acquisition
loop, never business vocabulary.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import subprocess
import sys
import urllib.request
import urllib.parse
from typing import Any

from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH

LOGGER = logging.getLogger("nethub_runtime.core.capability_acquisition_service")

# PyPI JSON API — no auth required, safe for read-only discovery
_PYPI_API = "https://pypi.org/pypi/{package}/json"
# HuggingFace Hub API — no auth required for public model listing
_HF_API_MODELS = "https://huggingface.co/api/models"


class AcquisitionResult:
    """Returned by every acquire call so callers handle it uniformly."""

    def __init__(
        self,
        *,
        success: bool,
        strategy: str,
        acquired: list[str],
        model_id: str | None = None,
        detail: str = "",
    ) -> None:
        self.success = success
        self.strategy = strategy
        self.acquired = acquired
        self.model_id = model_id
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "strategy": self.strategy,
            "acquired": self.acquired,
            "model_id": self.model_id,
            "detail": self.detail,
        }


class CapabilityAcquisitionService:
    """
    Universal, data-driven capability acquisition for all NestHub services.

    Usage — any service that hits a capability wall calls::

        acq = CapabilityAcquisitionService(security_guard=self.coordinator.security_guard)
        result = acq.acquire(task_type="image_generation", gap="no_image_model")
        if result.success:
            # retry with newly installed capability

    All domain knowledge (which packages / models to acquire for which task)
    is read from ``semantic_policy.json::capability_acquisition_strategies``.
    The code here is structural only.
    """

    def __init__(
        self,
        *,
        security_guard: Any | None = None,
        learning_store: Any | None = None,
    ) -> None:
        self.security_guard = security_guard
        self.learning_store = learning_store  # RuntimeLearningStore — injected at startup

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(
        self,
        *,
        task_type: str,
        gap: str,
        context: dict[str, Any] | None = None,
    ) -> AcquisitionResult:
        """
        Main entry point.

        Attempts acquisition in order:
          1. Check learning store for a known solution (fastest path)
          2. Install PyPI packages listed in the strategy
          3. Search and download a HuggingFace model for the task
        """
        context = context or {}

        # --- 1. Check memory for a known-good solution ---
        if self.learning_store is not None:
            known = self.learning_store.lookup_solution(task_type=task_type, gap=gap)
            if known:
                LOGGER.info(
                    "capability_acquisition: known solution found for %s/%s: %s",
                    task_type, gap, known,
                )
                result = self._apply_known_solution(known)
                if self.learning_store:
                    self.learning_store.record_attempt(
                        task_type=task_type,
                        gap=gap,
                        strategy="memory_replay",
                        outcome="success" if result.success else "failed",
                        detail=result.detail,
                        model_id=result.model_id,
                    )
                return result

        strategy = self._load_strategy(task_type)
        if not strategy:
            LOGGER.info(
                "capability_acquisition: no acquisition strategy for task_type=%s", task_type
            )
            result = AcquisitionResult(
                success=False,
                strategy="none",
                acquired=[],
                detail=f"No acquisition strategy configured for {task_type}",
            )
            self._record(task_type, gap, result)
            return result

        # --- Phase 0: Local Ollama (free, private, highest priority) ---
        ollama_result = self._acquire_ollama(strategy, task_type)
        if ollama_result.success:
            self._record(task_type, gap, ollama_result)
            return ollama_result

        # --- 2. Install PyPI packages ---
        pypi_result = self._acquire_pypi(strategy)
        if pypi_result.success:
            self._record(task_type, gap, pypi_result)
            return pypi_result

        # --- 3. Search + download HuggingFace model ---
        hf_result = self._acquire_huggingface(strategy, task_type)
        self._record(task_type, gap, hf_result)
        return hf_result

    def search_huggingface_models(
        self, *, pipeline_tag: str, limit: int = 5, sort: str = "downloads"
    ) -> list[dict[str, Any]]:
        """
        Query HuggingFace Hub API for public models matching a pipeline tag.
        Returns a list of {modelId, downloads, pipeline_tag} dicts.
        """
        params = urllib.parse.urlencode({
            "filter": pipeline_tag,
            "sort": sort,
            "limit": str(limit),
            "full": "false",
        })
        url = f"{_HF_API_MODELS}?{params}"
        try:
            LOGGER.info("capability_acquisition: querying HuggingFace Hub: %s", url)
            req = urllib.request.Request(url, headers={"User-Agent": "nesthub-runtime/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if isinstance(data, list):
                    return data
        except Exception as exc:
            LOGGER.warning("capability_acquisition: HF Hub query failed: %s", exc)
        return []

    def verify_package_on_pypi(self, package: str) -> bool:
        """Return True if ``package`` exists on PyPI (HEAD request to JSON API)."""
        url = _PYPI_API.format(package=urllib.parse.quote(package))
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "nesthub-runtime/1.0"})
            with urllib.request.urlopen(req, timeout=8):
                return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal acquisition steps
    # ------------------------------------------------------------------

    def _acquire_ollama(self, strategy: dict[str, Any], task_type: str) -> AcquisitionResult:
        """
        Phase 0 — Try to satisfy the capability using a locally-running Ollama instance.

        Logic:
          1. Health-check Ollama at http://localhost:11434/api/tags  (fast, 2 s timeout)
          2. Read ``ollama_models`` list from the strategy (sorted by priority)
          3. For each candidate: if not yet pulled, run ``ollama pull <name>``
          4. Verify the model with a minimal generation prompt
          5. Return AcquisitionResult(success=True, strategy="ollama") on first working model

        The Ollama step is skipped gracefully (returns success=False) when:
          - ``ollama_models`` is empty / absent in the strategy
          - Ollama is not running (health-check fails)
          - All pull/verify attempts fail
        """
        candidates: list[dict[str, Any]] = strategy.get("ollama_models") or []
        if not candidates:
            return AcquisitionResult(
                success=False, strategy="ollama", acquired=[],
                detail="no_ollama_models_in_strategy",
            )

        # 1. Health-check
        ollama_base = "http://localhost:11434"
        if not self._ollama_is_running(ollama_base):
            LOGGER.info(
                "capability_acquisition: Ollama not reachable at %s — skipping local phase",
                ollama_base,
            )
            return AcquisitionResult(
                success=False, strategy="ollama", acquired=[],
                detail="ollama_not_running",
            )

        # 2. Sort by priority
        sorted_candidates = sorted(candidates, key=lambda c: int(c.get("priority", 99)))

        # 3+4. Pull + verify
        for candidate in sorted_candidates:
            model_name: str = str(candidate.get("model_name") or "")
            if not model_name:
                continue
            label: str = str(candidate.get("label", model_name))
            LOGGER.info("capability_acquisition: checking Ollama model %s (%s)", model_name, label)

            # Check if already pulled
            if not self._ollama_model_pulled(ollama_base, model_name):
                LOGGER.info("capability_acquisition: pulling Ollama model %s …", model_name)
                try:
                    proc = subprocess.run(
                        ["ollama", "pull", model_name],
                        capture_output=True, text=True, timeout=600,
                    )
                    if proc.returncode != 0:
                        LOGGER.info(
                            "capability_acquisition: ollama pull %s failed: %s",
                            model_name, proc.stderr[:200],
                        )
                        continue
                except FileNotFoundError:
                    LOGGER.info(
                        "capability_acquisition: ollama CLI not found — skipping Ollama phase"
                    )
                    return AcquisitionResult(
                        success=False, strategy="ollama", acquired=[],
                        detail="ollama_cli_not_found",
                    )
                except subprocess.TimeoutExpired:
                    LOGGER.info(
                        "capability_acquisition: ollama pull %s timed out", model_name
                    )
                    continue
                except Exception as exc:
                    LOGGER.info("capability_acquisition: ollama pull error: %s", exc)
                    continue

            # Verify with a minimal prompt
            if self._ollama_verify(ollama_base, model_name):
                LOGGER.info(
                    "capability_acquisition: Ollama model %s is functional", model_name
                )
                return AcquisitionResult(
                    success=True,
                    strategy="ollama",
                    acquired=[],
                    model_id=f"ollama:{model_name}",
                    detail=f"local Ollama model {model_name} verified OK",
                )
            else:
                LOGGER.info(
                    "capability_acquisition: Ollama model %s failed verification — trying next",
                    model_name,
                )

        return AcquisitionResult(
            success=False, strategy="ollama", acquired=[],
            detail=f"all {len(sorted_candidates)} Ollama candidates failed",
        )

    def _ollama_is_running(self, base_url: str) -> bool:
        """Return True if Ollama API is reachable."""
        try:
            req = urllib.request.Request(
                f"{base_url}/api/tags", headers={"User-Agent": "nesthub-runtime/1.0"}
            )
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            return False

    def _ollama_model_pulled(self, base_url: str, model_name: str) -> bool:
        """Return True if the model is already available locally via Ollama."""
        try:
            req = urllib.request.Request(
                f"{base_url}/api/tags", headers={"User-Agent": "nesthub-runtime/1.0"}
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
            models = data.get("models") or []
            return any(
                m.get("name", "").split(":")[0] == model_name.split(":")[0]
                and (model_name == m.get("name", "") or ":" not in model_name)
                for m in models
            )
        except Exception:
            return False

    def _ollama_verify(self, base_url: str, model_name: str) -> bool:
        """Send a minimal generation request and confirm a non-empty response."""
        try:
            payload = json.dumps({
                "model": model_name,
                "prompt": "hi",
                "stream": False,
                "options": {"num_predict": 5},
            }).encode()
            req = urllib.request.Request(
                f"{base_url}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "nesthub-runtime/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            return bool(data.get("response"))
        except Exception:
            return False

    def _load_strategy(self, task_type: str) -> dict[str, Any] | None:
        """Load the acquisition strategy for a task_type from semantic_policy.json."""
        try:
            policy = json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))
            strategies: dict[str, Any] = policy.get("capability_acquisition_strategies") or {}
            return strategies.get(task_type) or None
        except Exception as exc:
            LOGGER.warning("capability_acquisition: could not load strategy: %s", exc)
            return None

    def _acquire_pypi(self, strategy: dict[str, Any]) -> AcquisitionResult:
        """Install packages listed in strategy[pypi_packages]."""
        packages: list[str] = strategy.get("pypi_packages") or []
        if not packages:
            return AcquisitionResult(
                success=False, strategy="pypi", acquired=[], detail="no_pypi_packages_in_strategy"
            )

        missing = [p for p in packages if importlib.util.find_spec(p.split("[")[0].replace("-", "_")) is None]
        if not missing:
            return AcquisitionResult(
                success=True, strategy="pypi", acquired=[], detail="already_installed"
            )

        if self.security_guard is not None and not self.security_guard.allow_runtime_auto_install():
            return AcquisitionResult(
                success=False, strategy="pypi", acquired=[], detail="auto_install_disabled"
            )

        LOGGER.info("capability_acquisition: pip-installing %s", missing)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode == 0:
                importlib.invalidate_caches()
                LOGGER.info("capability_acquisition: installed %s", missing)
                return AcquisitionResult(
                    success=True, strategy="pypi", acquired=missing,
                    detail=f"installed via pip: {missing}",
                )
            return AcquisitionResult(
                success=False, strategy="pypi", acquired=[],
                detail=f"pip failed: {proc.stderr[:300]}",
            )
        except subprocess.TimeoutExpired:
            return AcquisitionResult(
                success=False, strategy="pypi", acquired=[], detail="pip_timeout"
            )
        except Exception as exc:
            return AcquisitionResult(
                success=False, strategy="pypi", acquired=[], detail=str(exc)
            )

    def _acquire_huggingface(
        self, strategy: dict[str, Any], task_type: str
    ) -> AcquisitionResult:
        """
        Search HuggingFace Hub for a model matching the strategy's pipeline_tag,
        then download it via the diffusers / huggingface_hub library.
        """
        pipeline_tag: str = strategy.get("huggingface_pipeline_tag") or ""
        model_filter: dict[str, Any] = strategy.get("huggingface_model_filter") or {}
        explicit_candidates: list[dict[str, Any]] = strategy.get("huggingface_candidates") or []

        if not pipeline_tag and not explicit_candidates:
            return AcquisitionResult(
                success=False, strategy="huggingface", acquired=[],
                detail="no_huggingface_config_in_strategy",
            )

        # Prefer explicit candidates in policy (already vetted + ordered by priority)
        if explicit_candidates:
            candidates = sorted(explicit_candidates, key=lambda c: int(c.get("priority", 99)))
        else:
            # Dynamically discover from Hub
            limit = int(model_filter.get("limit", 5))
            sort = str(model_filter.get("sort", "downloads"))
            raw = self.search_huggingface_models(
                pipeline_tag=pipeline_tag, limit=limit, sort=sort
            )
            candidates = [{"model_id": m.get("modelId", ""), "inference_steps": 20} for m in raw if m.get("modelId")]

        if not candidates:
            return AcquisitionResult(
                success=False, strategy="huggingface", acquired=[],
                detail=f"no models found on HuggingFace for pipeline_tag={pipeline_tag}",
            )

        # Ensure diffusers + huggingface_hub are installed before attempting download
        hf_deps = ["diffusers", "transformers", "accelerate", "huggingface_hub", "torch", "pillow"]
        hf_missing = [p for p in hf_deps if importlib.util.find_spec(p) is None]
        if hf_missing:
            if self.security_guard is not None and not self.security_guard.allow_runtime_auto_install():
                return AcquisitionResult(
                    success=False, strategy="huggingface", acquired=[],
                    detail="auto_install_disabled — cannot install HF dependencies",
                )
            LOGGER.info("capability_acquisition: installing HF deps %s", hf_missing)
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet"] + hf_missing,
                    capture_output=True, text=True, timeout=300,
                )
                if proc.returncode != 0:
                    return AcquisitionResult(
                        success=False, strategy="huggingface", acquired=[],
                        detail=f"HF deps install failed: {proc.stderr[:300]}",
                    )
                importlib.invalidate_caches()
            except Exception as exc:
                return AcquisitionResult(
                    success=False, strategy="huggingface", acquired=[], detail=str(exc)
                )

        import torch  # type: ignore
        from diffusers import DiffusionPipeline  # type: ignore

        for candidate in candidates:
            model_id: str = str(candidate.get("model_id") or "")
            if not model_id:
                continue
            steps: int = int(candidate.get("inference_steps", 20))
            LOGGER.info("capability_acquisition: probing HuggingFace model %s", model_id)
            try:
                pipe = DiffusionPipeline.from_pretrained(
                    model_id,
                    torch_dtype=(
                        torch.float16 if torch.cuda.is_available() else torch.float32
                    ),
                    safety_checker=None,
                )
                if torch.cuda.is_available():
                    pipe = pipe.to("cuda")
                # Minimal probe: generate a 64×64 image to confirm the model works
                _ = pipe("test", num_inference_steps=min(steps, 1), height=64, width=64).images[0]
                LOGGER.info(
                    "capability_acquisition: model %s is functional — recording as active",
                    model_id,
                )
                self._persist_active_model(task_type, model_id, steps)
                return AcquisitionResult(
                    success=True,
                    strategy="huggingface",
                    acquired=["diffusers", "torch"],
                    model_id=model_id,
                    detail=f"model {model_id} downloaded and verified",
                )
            except Exception as exc:
                LOGGER.info(
                    "capability_acquisition: model %s probe failed (%s) — trying next",
                    model_id, exc,
                )

        return AcquisitionResult(
            success=False, strategy="huggingface", acquired=[],
            detail=f"all {len(candidates)} HuggingFace candidates failed",
        )

    def _apply_known_solution(self, known: dict[str, Any]) -> AcquisitionResult:
        """Re-apply a solution that was previously recorded as successful."""
        packages = known.get("packages") or []
        model_id = known.get("model_id")

        if packages:
            missing = [p for p in packages if importlib.util.find_spec(p) is None]
            if missing:
                try:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--quiet"] + missing,
                        capture_output=True, text=True, timeout=300, check=True,
                    )
                    importlib.invalidate_caches()
                except Exception:
                    pass

        return AcquisitionResult(
            success=True,
            strategy="memory_replay",
            acquired=packages,
            model_id=model_id,
            detail=f"replayed known solution: {known.get('detail', '')}",
        )

    def _persist_active_model(self, task_type: str, model_id: str, steps: int) -> None:
        """Write the confirmed-working model into the runtime policy for fast replay."""
        try:
            from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
            store = SemanticPolicyStore(policy_path=SEMANTIC_POLICY_PATH)
            store.record_intent_knowledge(
                f"capability_acquisition:{task_type}",
                {
                    f"active_model_{task_type}": model_id,
                    "inference_steps": steps,
                    "source": "capability_acquisition_service",
                },
                source="capability_acquisition_service",
                confidence=1.0,
                evidence=model_id,
            )
        except Exception as exc:
            LOGGER.warning("_persist_active_model failed: %s", exc)

    def _record(self, task_type: str, gap: str, result: AcquisitionResult) -> None:
        if self.learning_store is not None:
            try:
                self.learning_store.record_attempt(
                    task_type=task_type,
                    gap=gap,
                    strategy=result.strategy,
                    outcome="success" if result.success else "failed",
                    detail=result.detail,
                    model_id=result.model_id,
                    acquired=result.acquired,
                )
            except Exception:
                pass
