"""
Regression tests for local-first model acquisition priority chain.

Priority order:
  0. Ollama local (free, private) — Phase 0
  1. PyPI packages — Phase 1
  2. HuggingFace models — Phase 2

Tests use subprocess.run / urllib.request patching so no real Ollama or
network calls are made.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from nethub_runtime.core.services.capability_acquisition_service import (
    AcquisitionResult,
    CapabilityAcquisitionService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**kwargs) -> CapabilityAcquisitionService:
    return CapabilityAcquisitionService(**kwargs)


_OLLAMA_TAGS_RESPONSE = json.dumps({
    "models": [
        {"name": "qwen2.5:7b-instruct", "size": 1234},
        {"name": "deepseek-r1:7b", "size": 5678},
    ]
}).encode()

_OLLAMA_GENERATE_RESPONSE = json.dumps({"response": "hello"}).encode()

_OLLAMA_GENERATE_EMPTY = json.dumps({"response": ""}).encode()


def _fake_urlopen_running_and_pulled(req, timeout=2):
    """Simulate Ollama running with models already pulled and verify OK."""
    url = req.full_url if hasattr(req, "full_url") else str(req)
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    if "/api/tags" in url:
        mock_resp.read.return_value = _OLLAMA_TAGS_RESPONSE
    else:
        mock_resp.read.return_value = _OLLAMA_GENERATE_RESPONSE
    return mock_resp


def _fake_urlopen_not_running(req, timeout=2):
    raise OSError("connection refused")


def _fake_urlopen_running_not_pulled(req, timeout=2):
    """Tags endpoint returns empty model list; generate returns OK."""
    url = req.full_url if hasattr(req, "full_url") else str(req)
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    if "/api/tags" in url:
        mock_resp.read.return_value = json.dumps({"models": []}).encode()
    else:
        mock_resp.read.return_value = _OLLAMA_GENERATE_RESPONSE
    return mock_resp


def _fake_urlopen_verify_fails(req, timeout=2):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    if "/api/tags" in url:
        mock_resp.read.return_value = _OLLAMA_TAGS_RESPONSE
    else:
        mock_resp.read.return_value = _OLLAMA_GENERATE_EMPTY
    return mock_resp


def _minimal_strategy_with_ollama() -> dict[str, Any]:
    return {
        "pypi_packages": [],
        "ollama_models": [
            {"model_name": "deepseek-r1:7b", "priority": 1, "label": "DeepSeek-R1"},
            {"model_name": "qwen2.5:7b-instruct", "priority": 2, "label": "Qwen2.5"},
        ],
        "huggingface_candidates": [],
    }


def _minimal_strategy_ollama_only_small() -> dict[str, Any]:
    return {
        "pypi_packages": [],
        "ollama_models": [
            {"model_name": "deepseek-r1:1.5b", "priority": 1},
        ],
        "huggingface_candidates": [],
    }


# ---------------------------------------------------------------------------
# _ollama_is_running
# ---------------------------------------------------------------------------

class TestOllamaIsRunning:
    def test_returns_true_when_reachable(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_and_pulled):
            assert svc._ollama_is_running("http://localhost:11434") is True

    def test_returns_false_when_connection_refused(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            assert svc._ollama_is_running("http://localhost:11434") is False

    def test_returns_false_on_timeout(self):
        svc = _make_service()
        import socket
        with patch("urllib.request.urlopen", side_effect=socket.timeout):
            assert svc._ollama_is_running("http://localhost:11434") is False


# ---------------------------------------------------------------------------
# _ollama_model_pulled
# ---------------------------------------------------------------------------

class TestOllamaModelPulled:
    def test_returns_true_when_model_in_list(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_and_pulled):
            assert svc._ollama_model_pulled("http://localhost:11434", "deepseek-r1:7b") is True

    def test_returns_true_for_untagged_model_name_prefix(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_and_pulled):
            # "deepseek-r1" without tag should match "deepseek-r1:7b"
            assert svc._ollama_model_pulled("http://localhost:11434", "deepseek-r1") is True

    def test_returns_false_when_model_not_in_list(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_and_pulled):
            assert svc._ollama_model_pulled("http://localhost:11434", "llama3:8b") is False

    def test_returns_false_when_ollama_unreachable(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=OSError):
            assert svc._ollama_model_pulled("http://localhost:11434", "deepseek-r1:7b") is False


# ---------------------------------------------------------------------------
# _ollama_verify
# ---------------------------------------------------------------------------

class TestOllamaVerify:
    def test_returns_true_on_nonempty_response(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_and_pulled):
            assert svc._ollama_verify("http://localhost:11434", "deepseek-r1:7b") is True

    def test_returns_false_on_empty_response(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_verify_fails):
            # tags call returns models; generate returns empty response
            # We only want the generate call's effect here — patch both
            assert svc._ollama_verify("http://localhost:11434", "deepseek-r1:7b") is False

    def test_returns_false_on_network_error(self):
        svc = _make_service()
        with patch("urllib.request.urlopen", side_effect=OSError):
            assert svc._ollama_verify("http://localhost:11434", "deepseek-r1:7b") is False


# ---------------------------------------------------------------------------
# _acquire_ollama
# ---------------------------------------------------------------------------

class TestAcquireOllama:
    def test_skips_when_no_ollama_models_in_strategy(self):
        svc = _make_service()
        strategy = {"pypi_packages": [], "ollama_models": [], "huggingface_candidates": []}
        result = svc._acquire_ollama(strategy, "reasoning")
        assert result.success is False
        assert result.detail == "no_ollama_models_in_strategy"

    def test_skips_when_ollama_not_running(self):
        svc = _make_service()
        strategy = _minimal_strategy_with_ollama()
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            result = svc._acquire_ollama(strategy, "reasoning")
        assert result.success is False
        assert result.detail == "ollama_not_running"

    def test_success_when_model_already_pulled_and_verified(self):
        svc = _make_service()
        strategy = _minimal_strategy_with_ollama()
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_and_pulled):
            result = svc._acquire_ollama(strategy, "reasoning")
        assert result.success is True
        assert result.strategy == "ollama"
        assert "deepseek-r1:7b" in (result.model_id or "")

    def test_pulls_model_when_not_yet_downloaded(self):
        svc = _make_service()
        strategy = _minimal_strategy_ollama_only_small()

        pull_proc = MagicMock()
        pull_proc.returncode = 0

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_not_pulled), \
             patch("subprocess.run", return_value=pull_proc) as mock_sub:
            result = svc._acquire_ollama(strategy, "reasoning")

        assert result.success is True
        mock_sub.assert_called_once()
        call_args = mock_sub.call_args[0][0]
        assert call_args[0] == "ollama"
        assert call_args[1] == "pull"
        assert call_args[2] == "deepseek-r1:1.5b"

    def test_falls_through_to_next_candidate_when_pull_fails(self):
        svc = _make_service()
        strategy = _minimal_strategy_with_ollama()

        fail_proc = MagicMock()
        fail_proc.returncode = 1
        fail_proc.stderr = "error: model not found"

        call_count = [0]

        def _urlopen(req, timeout=2):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            if "/api/tags" in url:
                # First health-check: running; subsequent pulled-check: only qwen2.5 present
                call_count[0] += 1
                if call_count[0] == 1:
                    mock_resp.read.return_value = json.dumps({"models": []}).encode()
                else:
                    mock_resp.read.return_value = json.dumps({
                        "models": [{"name": "qwen2.5:7b-instruct"}]
                    }).encode()
            else:
                mock_resp.read.return_value = _OLLAMA_GENERATE_RESPONSE
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen), \
             patch("subprocess.run", return_value=fail_proc):
            result = svc._acquire_ollama(strategy, "reasoning")

        # deepseek-r1:7b pull failed, qwen2.5:7b-instruct already present → success
        assert result.success is True
        assert "qwen2.5:7b-instruct" in (result.model_id or "")

    def test_all_candidates_fail_returns_failure(self):
        svc = _make_service()
        strategy = _minimal_strategy_with_ollama()

        fail_proc = MagicMock()
        fail_proc.returncode = 1
        fail_proc.stderr = "not found"

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_not_pulled), \
             patch("subprocess.run", return_value=fail_proc):
            result = svc._acquire_ollama(strategy, "reasoning")

        assert result.success is False
        assert "failed" in result.detail

    def test_ollama_cli_not_found_skips_gracefully(self):
        svc = _make_service()
        strategy = _minimal_strategy_ollama_only_small()

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_not_pulled), \
             patch("subprocess.run", side_effect=FileNotFoundError("ollama")):
            result = svc._acquire_ollama(strategy, "reasoning")

        assert result.success is False
        assert result.detail == "ollama_cli_not_found"

    def test_sort_by_priority(self):
        """Lower priority number = tried first."""
        svc = _make_service()
        tried: list[str] = []

        original_verify = svc._ollama_verify
        def recording_verify(base_url, model_name):
            tried.append(model_name)
            return True  # succeed on first attempt

        strategy = {
            "ollama_models": [
                {"model_name": "qwen2.5:7b-instruct", "priority": 2},
                {"model_name": "deepseek-r1:7b", "priority": 1},  # lower = first
            ],
            "pypi_packages": [],
            "huggingface_candidates": [],
        }

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_running_and_pulled), \
             patch.object(svc, "_ollama_verify", side_effect=recording_verify):
            result = svc._acquire_ollama(strategy, "reasoning")

        assert result.success is True
        assert tried[0] == "deepseek-r1:7b"


# ---------------------------------------------------------------------------
# Full priority chain via acquire()
# ---------------------------------------------------------------------------

class TestAcquirePriorityChain:
    """Integration-level tests for the full acquire() priority chain."""

    def _stub_strategy(self) -> dict[str, Any]:
        return {
            "ollama_models": [{"model_name": "deepseek-r1:7b", "priority": 1}],
            "pypi_packages": ["pillow"],
            "huggingface_candidates": [],
            "huggingface_pipeline_tag": None,
        }

    def test_ollama_succeeds_no_pypi_or_hf_attempted(self):
        svc = _make_service()
        with patch.object(svc, "_load_strategy", return_value=self._stub_strategy()), \
             patch.object(svc, "_acquire_ollama", return_value=AcquisitionResult(
                 success=True, strategy="ollama", acquired=[], model_id="ollama:deepseek-r1:7b"
             )) as mock_ollama, \
             patch.object(svc, "_acquire_pypi") as mock_pypi, \
             patch.object(svc, "_acquire_huggingface") as mock_hf, \
             patch.object(svc, "_record"):
            result = svc.acquire(task_type="reasoning", gap="no_llm")
        assert result.success is True
        assert result.strategy == "ollama"
        mock_pypi.assert_not_called()
        mock_hf.assert_not_called()

    def test_falls_to_pypi_when_ollama_fails(self):
        svc = _make_service()
        with patch.object(svc, "_load_strategy", return_value=self._stub_strategy()), \
             patch.object(svc, "_acquire_ollama", return_value=AcquisitionResult(
                 success=False, strategy="ollama", acquired=[], detail="ollama_not_running"
             )), \
             patch.object(svc, "_acquire_pypi", return_value=AcquisitionResult(
                 success=True, strategy="pypi", acquired=["pillow"]
             )) as mock_pypi, \
             patch.object(svc, "_acquire_huggingface") as mock_hf, \
             patch.object(svc, "_record"):
            result = svc.acquire(task_type="image_generation", gap="no_image")
        assert result.success is True
        assert result.strategy == "pypi"
        mock_pypi.assert_called_once()
        mock_hf.assert_not_called()

    def test_falls_to_hf_when_ollama_and_pypi_fail(self):
        svc = _make_service()
        with patch.object(svc, "_load_strategy", return_value=self._stub_strategy()), \
             patch.object(svc, "_acquire_ollama", return_value=AcquisitionResult(
                 success=False, strategy="ollama", acquired=[], detail="ollama_not_running"
             )), \
             patch.object(svc, "_acquire_pypi", return_value=AcquisitionResult(
                 success=False, strategy="pypi", acquired=[], detail="auto_install_disabled"
             )), \
             patch.object(svc, "_acquire_huggingface", return_value=AcquisitionResult(
                 success=True, strategy="huggingface", acquired=["diffusers"],
                 model_id="stabilityai/stable-diffusion-xl-base-1.0"
             )) as mock_hf, \
             patch.object(svc, "_record"):
            result = svc.acquire(task_type="image_generation", gap="no_image")
        assert result.success is True
        assert result.strategy == "huggingface"
        mock_hf.assert_called_once()

    def test_memory_replay_skips_all_other_phases(self):
        memory_solution = {
            "model_id": "ollama:deepseek-r1:7b",
            "detail": "worked last time",
            "packages": [],
        }
        mock_store = MagicMock()
        mock_store.lookup_solution.return_value = memory_solution
        mock_store.record_attempt = MagicMock()
        svc = _make_service(learning_store=mock_store)
        with patch.object(svc, "_acquire_ollama") as mock_ollama, \
             patch.object(svc, "_acquire_pypi") as mock_pypi:
            result = svc.acquire(task_type="reasoning", gap="no_llm")
        assert result.strategy == "memory_replay"
        mock_ollama.assert_not_called()
        mock_pypi.assert_not_called()

    def test_no_strategy_returns_failure_immediately(self):
        svc = _make_service()
        with patch.object(svc, "_load_strategy", return_value=None), \
             patch.object(svc, "_acquire_ollama") as mock_ollama:
            result = svc.acquire(task_type="unknown_task", gap="x")
        assert result.success is False
        assert result.strategy == "none"
        mock_ollama.assert_not_called()


# ---------------------------------------------------------------------------
# semantic_policy.json integration — verify the new strategies are readable
# ---------------------------------------------------------------------------

class TestSemanticPolicyStrategies:
    """Verify the updated semantic_policy.json contains the expected fields."""

    def _load_policy(self) -> dict[str, Any]:
        from nethub_runtime.core.config.settings import SEMANTIC_POLICY_PATH
        return json.loads(SEMANTIC_POLICY_PATH.read_text(encoding="utf-8"))

    def test_document_analysis_has_ollama_models(self):
        policy = self._load_policy()
        strategies = policy["capability_acquisition_strategies"]
        assert "document_analysis" in strategies
        ollama_models = strategies["document_analysis"]["ollama_models"]
        model_names = [m["model_name"] for m in ollama_models]
        assert "deepseek-r1:7b" in model_names

    def test_reasoning_strategy_has_deepseek(self):
        policy = self._load_policy()
        strategies = policy["capability_acquisition_strategies"]
        assert "reasoning" in strategies
        model_names = [m["model_name"] for m in strategies["reasoning"]["ollama_models"]]
        assert "deepseek-r1:7b" in model_names

    def test_image_generation_has_sdxl_priority_1(self):
        policy = self._load_policy()
        candidates = policy["capability_acquisition_strategies"]["image_generation"]["huggingface_candidates"]
        priority_1 = next((c for c in candidates if c["priority"] == 1), None)
        assert priority_1 is not None
        assert "stable-diffusion-xl" in priority_1["model_id"]

    def test_web_research_has_playwright(self):
        policy = self._load_policy()
        pkgs = policy["capability_acquisition_strategies"]["web_research"]["pypi_packages"]
        assert "playwright" in pkgs

    def test_ocr_has_paddleocr(self):
        policy = self._load_policy()
        pkgs = policy["capability_acquisition_strategies"]["ocr"]["pypi_packages"]
        assert "paddleocr" in pkgs

    def test_local_model_priority_block_exists(self):
        policy = self._load_policy()
        assert "local_model_priority" in policy
        tiers = policy["local_model_priority"]["tiers"]
        assert tiers[0]["name"] == "local_ollama"
        assert tiers[1]["name"] == "free_remote_api"
        assert tiers[2]["name"] == "paid_remote_api"

    def test_local_model_priority_preferred_models(self):
        policy = self._load_policy()
        preferred = policy["local_model_priority"]["tiers"][0]["preferred_models"]
        assert preferred["reasoning"] == "deepseek-r1:7b"
        assert preferred["code_generation"] == "qwen3-coder:30b"
