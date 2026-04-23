from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TrainingPipelineService:
    """Build train-ready manifests from exported private-brain datasets.

    This service sits between dataset export
    (:class:`~nethub_runtime.core.services.training_dataset_export_service.TrainingDatasetExportService`)
    and the external fine-tuning runner
    (:class:`~nethub_runtime.core.services.training_fine_tune_runner_service.TrainingFineTuneRunnerService`).

    It reads raw artifact descriptors from the
    :class:`~nethub_runtime.core.services.generated_artifact_store.GeneratedArtifactStore`,
    resolves file paths, counts samples, and serialises everything into a
    ``training_manifest_<profile>.json`` artifact that the fine-tune runner
    (or an external ``unsloth``/``llamafactory`` process) can consume directly.

    Implementation status
    ---------------------
    ✅ Manifest building (this service)
    ⚠️  Fine-tuning execution — delegated to an *external* subprocess; the
        runner service only previews the command, it does not run training.
    """

    def __init__(self, *, generated_artifact_store: Any) -> None:
        """Inject the artifact store used to read datasets and persist manifests.

        Parameters
        ----------
        generated_artifact_store:
            Instance of
            :class:`~nethub_runtime.core.services.generated_artifact_store.GeneratedArtifactStore`
            (typed as ``Any`` to avoid circular imports).
        """
        self.generated_artifact_store = generated_artifact_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_training_manifest(self, *, profile: str = "lora_sft") -> dict[str, Any]:
        """Collect all exported datasets and produce a training manifest.

        The manifest is both returned as a dict *and* persisted to the artifact
        store as ``dataset_manifest / training_manifest_<profile>.json``.

        Parameters
        ----------
        profile:
            Training profile identifier.  Currently the only supported value
            is ``"lora_sft"`` (Low-Rank Adaptation + Supervised Fine-Tuning).
            Future profiles: ``"dpo_only"``, ``"full_ft"``.

        Returns
        -------
        dict[str, Any]
            Manifest dict with the following top-level keys:

            - ``profile``             – the requested profile name
            - ``ready``               – ``True`` when at least one SFT dataset exists
            - ``recommended_backend`` – always ``"lora_sft"`` for now
            - ``datasets``            – ``{"sft": [...], "preference": [...]}``,
                                        each entry a descriptor from
                                        :py:meth:`_dataset_descriptor`
            - ``counts``              – ``{"sft": N, "preference": M}``
            - ``training_plan``       – stage list and objectives from
                                        :py:meth:`_training_plan`
            - ``artifact_path``       – absolute path where the manifest was written
        """
        # Retrieve all artifact descriptors grouped by type
        artifacts = self.generated_artifact_store.list_artifacts()

        # SFT (supervised fine-tuning) samples — instruction/response pairs
        sft_items = artifacts.get("dataset_sft", [])

        # Preference samples — chosen / rejected response pairs used for DPO
        preference_items = artifacts.get("dataset_preference", [])

        manifest = {
            "profile": profile,
            # ``ready`` signals to the runner that training can proceed
            "ready": bool(sft_items),
            "recommended_backend": "lora_sft",
            "datasets": {
                "sft": [self._dataset_descriptor(item) for item in sft_items],
                "preference": [self._dataset_descriptor(item) for item in preference_items],
            },
            "counts": {
                "sft": len(sft_items),
                "preference": len(preference_items),
            },
            "training_plan": self._training_plan(
                profile=profile, has_preferences=bool(preference_items)
            ),
        }

        # Persist the manifest so the fine-tune runner can locate it via the store
        manifest_path = self.generated_artifact_store.persist(
            "dataset_manifest",
            f"training_manifest_{profile}",
            manifest,
        )
        manifest["artifact_path"] = str(manifest_path)
        return manifest

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dataset_descriptor(self, item: dict[str, Any]) -> dict[str, Any]:
        """Convert a raw artifact entry into a lean descriptor for the manifest.

        Parameters
        ----------
        item:
            Raw artifact dict from the store — expected keys:
            ``artifactId``, ``path``, ``size``.

        Returns
        -------
        dict[str, Any]
            ``{"artifact_id": ..., "path": ..., "sample_count": ..., "size": ...}``
        """
        path = Path(str(item.get("path") or ""))
        # Count JSON list items on disk so the runner knows dataset sizes upfront
        sample_count = self._sample_count(path)
        return {
            "artifact_id": item.get("artifactId"),
            "path": str(path),
            "sample_count": sample_count,
            "size": item.get("size") or 0,
        }

    def _sample_count(self, path: Path) -> int:
        """Return the number of samples in a JSON-list dataset file.

        Returns ``0`` when the file does not exist or cannot be parsed, so
        the calling code never raises and the manifest remains intact even if
        a dataset file was deleted or corrupted.

        Parameters
        ----------
        path:
            Absolute path to the dataset file (expected JSON array).

        Returns
        -------
        int
            Length of the top-level array, or ``0`` on any error.
        """
        if not path.exists():
            return 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        return len(payload) if isinstance(payload, list) else 0

    def _training_plan(self, *, profile: str, has_preferences: bool) -> dict[str, Any]:
        """Build the training-plan sub-dict embedded in the manifest.

        The plan describes the sequence of stages and the learning objectives
        that the fine-tune runner should configure.

        Parameters
        ----------
        profile:
            Training profile (forwarded from :py:meth:`build_training_manifest`).
        has_preferences:
            ``True`` when preference-pair datasets are available, enabling the
            DPO (Direct Preference Optimisation) objective in stage 2.

        Returns
        -------
        dict[str, Any]
            ``{"profile": ..., "stages": [...], "supervised_objective": ...,
            "preference_objective": ..., "requires": [...]}``
        """
        base: dict[str, Any] = {
            "profile": profile,
            # Standard LoRA-SFT pipeline stages
            "stages": ["prepare", "tokenize", "train", "evaluate"],
            # Primary objective: supervised fine-tuning on instruction/response pairs
            "supervised_objective": "sft",
            # Secondary objective: DPO only when preference data is available
            "preference_objective": "dpo" if has_preferences else "none",
            # Minimum required artifact types for this plan
            "requires": ["dataset_sft"],
        }
        if has_preferences:
            # Preference dataset is required only when DPO is active
            base["requires"].append("dataset_preference")
        return base
