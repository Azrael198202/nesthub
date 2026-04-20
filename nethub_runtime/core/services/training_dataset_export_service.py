from __future__ import annotations

from typing import Any


class TrainingDatasetExportService:
    """Export high-value runtime results into reusable training datasets."""

    def __init__(self, *, generated_artifact_store: Any) -> None:
        self.generated_artifact_store = generated_artifact_store

    def export_execution_result(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any],
        execution_result: dict[str, Any],
    ) -> dict[str, Any]:
        final_output = execution_result.get("final_output") or {}
        trace_id = str(context.get("trace_id") or execution_result.get("trace_id") or "").strip()
        session_id = str(context.get("session_id") or "").strip()
        if not trace_id:
            return {"exported": False, "sft_count": 0, "preference_count": 0, "artifacts": [], "skipped": ["missing_trace_id"]}

        sft_samples = self._build_sft_samples(task=task, context=context, execution_result=execution_result, final_output=final_output)
        preference_samples = self._build_preference_samples(task=task, context=context, execution_result=execution_result, final_output=final_output)

        artifacts: list[dict[str, Any]] = []
        if sft_samples:
            sft_path = self.generated_artifact_store.persist(
                "dataset_sft",
                f"training_sft_{trace_id}",
                sft_samples,
            )
            artifacts.append({"category": "dataset_sft", "path": str(sft_path), "count": len(sft_samples)})
        if preference_samples:
            pref_path = self.generated_artifact_store.persist(
                "dataset_preference",
                f"training_preference_{trace_id}",
                preference_samples,
            )
            artifacts.append({"category": "dataset_preference", "path": str(pref_path), "count": len(preference_samples)})

        return {
            "exported": bool(artifacts),
            "trace_id": trace_id,
            "session_id": session_id,
            "sft_count": len(sft_samples),
            "preference_count": len(preference_samples),
            "artifacts": artifacts,
            "skipped": [] if artifacts else ["no_high_value_samples"],
        }

    def _build_sft_samples(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any],
        execution_result: dict[str, Any],
        final_output: dict[str, Any],
    ) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        base_input = {
            "user_text": str(task.get("input_text") or "").strip(),
            "context": {
                "session_id": context.get("session_id"),
                "trace_id": context.get("trace_id"),
                "metadata": context.get("metadata") or {},
            },
            "retrieved_knowledge": execution_result.get("memory_promotion", {}).get("items") or [],
        }
        quality = {
            "outcome": self._outcome_label(execution_result),
            "repair_iterations": int(execution_result.get("repair_iteration") or len(execution_result.get("repair_history") or [])),
            "user_goal_satisfied": bool((execution_result.get("goal_evaluation") or {}).get("satisfied", False)),
        }

        analyze_document = final_output.get("analyze_document") or {}
        if str(analyze_document.get("status") or "") == "completed":
            answer = str(analyze_document.get("translation") or analyze_document.get("summary") or analyze_document.get("message") or "").strip()
            if answer:
                samples.append(
                    {
                        "sample_type": "document_analysis",
                        "input": base_input,
                        "output": {
                            "answer": answer,
                            "final_output": {"analyze_document": analyze_document},
                        },
                        "quality": quality,
                    }
                )

        manage_information_agent = final_output.get("manage_information_agent") or {}
        dialog_state = manage_information_agent.get("dialog_state") if isinstance(manage_information_agent.get("dialog_state"), dict) else {}
        if dialog_state.get("stage") == "knowledge_added":
            answer = str(manage_information_agent.get("message") or "").strip()
            if answer:
                samples.append(
                    {
                        "sample_type": "information_agent_capture",
                        "input": base_input,
                        "output": {
                            "answer": answer,
                            "final_output": {"manage_information_agent": manage_information_agent},
                        },
                        "quality": quality,
                    }
                )
        return samples

    def _build_preference_samples(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any],
        execution_result: dict[str, Any],
        final_output: dict[str, Any],
    ) -> list[dict[str, Any]]:
        repair_history = execution_result.get("repair_history") or []
        if not repair_history:
            return []
        chosen = self._extract_answer(final_output)
        if not chosen:
            return []
        rejected = str((execution_result.get("outcome_evaluation") or {}).get("unmet_requirements") or "").strip()
        if not rejected:
            rejected = "initial execution path failed to satisfy all requirements"
        return [
            {
                "sample_type": "repair_preference",
                "input": {
                    "user_text": str(task.get("input_text") or "").strip(),
                    "context": {
                        "session_id": context.get("session_id"),
                        "trace_id": context.get("trace_id"),
                    },
                },
                "chosen": chosen,
                "rejected": rejected,
                "quality": {
                    "outcome": self._outcome_label(execution_result),
                    "repair_iterations": len(repair_history),
                    "user_goal_satisfied": bool((execution_result.get("goal_evaluation") or {}).get("satisfied", False)),
                    "repair_preferences": execution_result.get("repair_preferences") or {},
                },
                "repair_preferences": execution_result.get("repair_preferences") or {},
            }
        ]

    def _extract_answer(self, final_output: dict[str, Any]) -> str:
        for value in final_output.values():
            if not isinstance(value, dict):
                continue
            for field in ("answer", "message", "summary", "translation", "content"):
                content = str(value.get(field) or "").strip()
                if content:
                    return content
        return ""

    def _outcome_label(self, execution_result: dict[str, Any]) -> str:
        goal = execution_result.get("goal_evaluation") or {}
        outcome = execution_result.get("outcome_evaluation") or {}
        if goal.get("satisfied") is True:
            return "success"
        if outcome.get("should_repair"):
            return "partial"
        return str(outcome.get("status") or "success")
