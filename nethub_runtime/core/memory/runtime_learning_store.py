"""
Runtime Learning Store.

NestHub's continuous self-improvement memory layer.

Every execution attempt — success or failure — is recorded here.  Future
attempts on the same task type can query this store first to skip the
acquisition discovery loop and replay a known-good solution directly.

Records are stored as structured intent-knowledge entries in the existing
``SemanticPolicyStore`` (SQLite-backed) so no new infrastructure is needed.

Learning record schema::

    {
        "task_type": "image_generation",
        "gap": "no_image_model",
        "strategy": "huggingface",
        "outcome": "success",            # success | failed | partial
        "detail": "model xyz downloaded",
        "model_id": "nota-ai/bk-sdm-tiny",
        "acquired": ["diffusers", "torch"],
        "attempt_count": 3,              # how many times we tried this
        "timestamp": "2026-04-17T...",
    }
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

LOGGER = logging.getLogger("nethub_runtime.core.runtime_learning_store")


class RuntimeLearningStore:
    """
    Records every capability acquisition attempt and its outcome.

    Uses ``SemanticPolicyStore`` as the durable backend so learned solutions
    survive process restarts and are queryable by the rest of the runtime.
    """

    _KEY_PREFIX = "learning:"

    def __init__(self, semantic_policy_store: Any) -> None:
        self.store = semantic_policy_store

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_attempt(
        self,
        *,
        task_type: str,
        gap: str,
        strategy: str,
        outcome: str,
        detail: str = "",
        model_id: str | None = None,
        acquired: list[str] | None = None,
    ) -> None:
        """Persist one acquisition attempt record."""
        key = f"{self._KEY_PREFIX}{task_type}:{gap}"
        payload: dict[str, Any] = {
            "task_type": task_type,
            "gap": gap,
            "strategy": strategy,
            "outcome": outcome,
            "detail": detail,
            "model_id": model_id,
            "acquired": acquired or [],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        confidence = 0.95 if outcome == "success" else 0.3
        try:
            self.store.record_intent_knowledge(
                key,
                payload,
                source="runtime_learning_store",
                confidence=confidence,
                evidence=detail,
            )
            LOGGER.info(
                "learning_store: recorded %s/%s outcome=%s strategy=%s",
                task_type, gap, outcome, strategy,
            )
        except Exception as exc:
            LOGGER.warning("learning_store: record_attempt failed: %s", exc)

    def record_execution_outcome(
        self,
        *,
        task_type: str,
        intent: str,
        input_summary: str,
        outcome: str,
        repair_iterations: int,
        unmet_requirements: list[str],
        solution_summary: str,
    ) -> None:
        """
        Record the final outcome of a full execution cycle including repairs.

        Called by the core engine after each handle() completes.
        Builds a richer record used for detecting patterns in what kinds of
        requests keep failing and which repair strategies work.
        """
        key = f"{self._KEY_PREFIX}execution:{task_type}:{intent}"
        payload: dict[str, Any] = {
            "task_type": task_type,
            "intent": intent,
            "input_summary": input_summary[:200],
            "outcome": outcome,
            "repair_iterations": repair_iterations,
            "unmet_requirements": unmet_requirements,
            "solution_summary": solution_summary,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        confidence = 0.9 if outcome == "success" else 0.4
        try:
            self.store.record_intent_knowledge(
                key,
                payload,
                source="runtime_learning_store",
                confidence=confidence,
                evidence=solution_summary,
            )
        except Exception as exc:
            LOGGER.warning("learning_store: record_execution_outcome failed: %s", exc)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def lookup_solution(
        self,
        *,
        task_type: str,
        gap: str,
        min_confidence: float = 0.8,
    ) -> dict[str, Any] | None:
        """
        Look up a previously successful acquisition for task_type + gap.

        Returns the stored payload if a high-confidence success record exists,
        so the caller can replay it without rediscovery.
        """
        key = f"{self._KEY_PREFIX}{task_type}:{gap}"
        try:
            runtime_policy = self.store.load_runtime_policy()
            # The policy store merges all active candidates — check for our key
            candidates = self.store.inspect_memory(policy_key=key)
            records = candidates.get("records") or []
            # Filter to successful records above confidence threshold
            successes = [
                r for r in records
                if r.get("confidence", 0) >= min_confidence
                and (r.get("payload") or {}).get("outcome") == "success"
            ]
            if not successes:
                return None
            # Return the most recent successful record
            best = max(successes, key=lambda r: r.get("timestamp") or "")
            payload: dict[str, Any] = best.get("payload") or {}
            LOGGER.info(
                "learning_store: found known solution for %s/%s: %s",
                task_type, gap, payload.get("detail"),
            )
            return payload
        except Exception as exc:
            LOGGER.debug("learning_store: lookup_solution error: %s", exc)
            return None

    def get_learning_summary(self) -> dict[str, Any]:
        """Return aggregate statistics about what the runtime has learned."""
        try:
            all_records = self.store.inspect_memory()
            records = all_records.get("records") or []
            learning_records = [
                r for r in records
                if str(r.get("policy_key") or "").startswith(self._KEY_PREFIX)
            ]
            successes = [r for r in learning_records if (r.get("payload") or {}).get("outcome") == "success"]
            failures = [r for r in learning_records if (r.get("payload") or {}).get("outcome") == "failed"]
            task_types: set[str] = {
                str((r.get("payload") or {}).get("task_type") or "")
                for r in learning_records
                if (r.get("payload") or {}).get("task_type")
            }
            return {
                "total_records": len(learning_records),
                "successes": len(successes),
                "failures": len(failures),
                "known_task_types": sorted(task_types),
            }
        except Exception as exc:
            return {"error": str(exc)}
