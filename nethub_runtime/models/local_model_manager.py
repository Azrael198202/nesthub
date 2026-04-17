from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import LOCAL_MODEL_REGISTRY_PATH, ensure_core_config_dir


class LocalModelManager:
    """Manage downloadable local models and import Hugging Face GGUF models into Ollama."""

    def __init__(self, registry_path: Path | None = None, storage_root: Path | None = None) -> None:
        ensure_core_config_dir()
        self.registry_path = registry_path or LOCAL_MODEL_REGISTRY_PATH
        self.storage_root = storage_root or (Path(__file__).resolve().parent.parent / "generated" / "local_models")
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def recommend_huggingface_models(self, task_type: str, query: str = "", limit: int = 5) -> list[dict[str, Any]]:
        api = self._get_hf_api()
        search_terms = self._build_search_terms(task_type, query)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        for term in search_terms:
            for model in api.list_models(search=term, limit=max(limit * 3, 10), full=False):
                repo_id = str(getattr(model, "id", "") or "").strip()
                if not repo_id or repo_id in seen:
                    continue
                if any(token in repo_id.lower() for token in ("gguf", "awq", "gptq")):
                    seen.add(repo_id)
                    results.append({
                        "repo_id": repo_id,
                        "search_term": term,
                        "task_type": task_type,
                    })
                if len(results) >= limit:
                    return results
        return results

    def install_huggingface_model(
        self,
        *,
        task_type: str,
        repo_id: str | None = None,
        query: str = "",
        alias: str | None = None,
        filename_pattern: str | None = None,
    ) -> dict[str, Any]:
        api = self._get_hf_api()
        target_repo = repo_id or self._pick_repo_for_task(api=api, task_type=task_type, query=query)
        if not target_repo:
            raise RuntimeError(f"No Hugging Face model candidate found for task_type={task_type} query={query!r}")

        model_info = api.model_info(target_repo)
        gguf_file = self._select_gguf_file(model_info=model_info, filename_pattern=filename_pattern)
        if not gguf_file:
            raise RuntimeError(f"No GGUF file found in repo {target_repo}")

        download_dir = self.storage_root / self._sanitize_repo_id(target_repo)
        download_dir.mkdir(parents=True, exist_ok=True)

        hf_hub_download = self._get_hf_download()
        local_file = Path(
            hf_hub_download(
                repo_id=target_repo,
                filename=gguf_file,
                local_dir=str(download_dir),
                local_dir_use_symlinks=False,
            )
        )

        model_alias = alias or self._default_alias(target_repo, gguf_file)
        modelfile_path = download_dir / "Modelfile"
        modelfile_path.write_text(f"FROM {local_file}\n", encoding="utf-8")

        subprocess.run(["ollama", "create", model_alias, "-f", str(modelfile_path)], check=True, capture_output=True, text=True)
        self._record_registry_entry(
            alias=model_alias,
            repo_id=target_repo,
            task_type=task_type,
            gguf_file=gguf_file,
            local_path=str(local_file),
        )
        return {
            "provider": "ollama",
            "model_name": model_alias,
            "repo_id": target_repo,
            "gguf_file": gguf_file,
            "local_path": str(local_file),
            "imported": True,
        }

    def _build_search_terms(self, task_type: str, query: str) -> list[str]:
        defaults = {
            "code_generation": ["coder instruct gguf", "qwen coder gguf", "deepseek coder gguf"],
            "document_generation": ["instruct gguf", "qwen instruct gguf"],
            "long_context_analysis": ["long context instruct gguf", "qwen2.5 gguf"],
            "semantic_parsing": ["small instruct gguf", "llama instruct gguf"],
            "default": ["instruct gguf", "qwen gguf"],
        }
        seeds = defaults.get(task_type, defaults["default"])
        terms = [query.strip()] if query.strip() else []
        terms.extend(seeds)
        deduped: list[str] = []
        for term in terms:
            if term and term not in deduped:
                deduped.append(term)
        return deduped

    def _pick_repo_for_task(self, *, api: Any, task_type: str, query: str) -> str | None:
        candidates = self.recommend_huggingface_models(task_type=task_type, query=query, limit=10)
        for item in candidates:
            repo_id = str(item.get("repo_id") or "")
            if not repo_id:
                continue
            try:
                info = api.model_info(repo_id)
            except Exception:
                continue
            if self._select_gguf_file(model_info=info, filename_pattern=None):
                return repo_id
        return None

    def _select_gguf_file(self, *, model_info: Any, filename_pattern: str | None) -> str | None:
        siblings = list(getattr(model_info, "siblings", []) or [])
        filenames = [str(getattr(item, "rfilename", "") or "") for item in siblings]
        gguf_files = [name for name in filenames if name.lower().endswith(".gguf")]
        if filename_pattern:
            filtered = [name for name in gguf_files if filename_pattern.lower() in name.lower()]
            if filtered:
                gguf_files = filtered
        preferred_tokens = ("q4_k_m", "q4", "instruct", "chat")
        gguf_files.sort(key=lambda name: (not any(token in name.lower() for token in preferred_tokens), len(name)))
        return gguf_files[0] if gguf_files else None

    def _record_registry_entry(self, *, alias: str, repo_id: str, task_type: str, gguf_file: str, local_path: str) -> None:
        payload = self._load_registry_payload()
        models = payload.setdefault("models", [])
        if alias not in models:
            models.append(alias)
        metadata = payload.setdefault("huggingface_models", {})
        metadata[alias] = {
            "repo_id": repo_id,
            "task_type": task_type,
            "gguf_file": gguf_file,
            "local_path": local_path,
            "provider": "ollama",
        }
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_registry_payload(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"models": [], "huggingface_models": {}}
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"models": [], "huggingface_models": {}}
        payload.setdefault("models", [])
        payload.setdefault("huggingface_models", {})
        return payload

    def _default_alias(self, repo_id: str, gguf_file: str) -> str:
        repo_slug = self._sanitize_repo_id(repo_id)
        file_slug = re.sub(r"[^a-zA-Z0-9]+", "-", Path(gguf_file).stem).strip("-").lower()
        return f"hf-{repo_slug}-{file_slug}"[:80]

    def _sanitize_repo_id(self, repo_id: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "-", repo_id.replace("/", "--")).strip("-").lower()

    def _get_hf_api(self) -> Any:
        try:
            from huggingface_hub import HfApi
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("huggingface_hub is required for local model discovery") from exc
        return HfApi()

    def _get_hf_download(self) -> Any:
        try:
            from huggingface_hub import hf_hub_download
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("huggingface_hub is required for local model download") from exc
        return hf_hub_download