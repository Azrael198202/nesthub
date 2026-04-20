from __future__ import annotations

from nethub_runtime.core.services.training_dataset_export_service import TrainingDatasetExportService
from nethub_runtime.generated.store import GeneratedArtifactStore


def test_training_dataset_export_service_exports_document_sft_sample(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(tmp_path / "generated"))
    service = TrainingDatasetExportService(generated_artifact_store=GeneratedArtifactStore())

    summary = service.export_execution_result(
        task={"intent": "file_upload_task", "domain": "multimodal_ops", "input_text": "请总结文档"},
        context={"trace_id": "trace_dataset_document", "session_id": "dataset-session"},
        execution_result={
            "final_output": {
                "analyze_document": {
                    "status": "completed",
                    "summary": "这份文档总结了项目排期和负责人分工。",
                    "requested_action": "summarize",
                    "source_documents": ["brief.txt"],
                }
            },
            "goal_evaluation": {"satisfied": True},
            "repair_history": [],
        },
    )

    assert summary["exported"] is True
    assert summary["sft_count"] == 1
    assert summary["preference_count"] == 0
    assert any(item["category"] == "dataset_sft" for item in summary["artifacts"])


def test_training_dataset_export_service_exports_preference_sample_after_repair(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NETHUB_GENERATED_ROOT", str(tmp_path / "generated"))
    service = TrainingDatasetExportService(generated_artifact_store=GeneratedArtifactStore())

    summary = service.export_execution_result(
        task={"intent": "capture_agent_knowledge", "domain": "agent_management", "input_text": "把供应商甲信息记录下来"},
        context={"trace_id": "trace_dataset_preference", "session_id": "dataset-session"},
        execution_result={
            "final_output": {
                "manage_information_agent": {
                    "message": "已完成添加，并已记录该供应商信息。",
                    "dialog_state": {"stage": "knowledge_added"},
                    "knowledge": {"item_name": "供应商甲", "contact": "vendor@example.com"},
                }
            },
            "goal_evaluation": {"satisfied": True},
            "outcome_evaluation": {"unmet_requirements": ["initial_capture_failed"]},
            "repair_history": [{"iteration": 1, "workflow_id": "repair_flow"}],
            "repair_preferences": {"analysis_before_retry": True, "guided_repair": True},
        },
    )

    assert summary["exported"] is True
    assert summary["sft_count"] == 1
    assert summary["preference_count"] == 1
    assert any(item["category"] == "dataset_preference" for item in summary["artifacts"])

    preference_path = next(item["path"] for item in summary["artifacts"] if item["category"] == "dataset_preference")
    import json
    from pathlib import Path
    payload = json.loads(Path(preference_path).read_text(encoding="utf-8"))
    assert payload[0]["repair_preferences"]["analysis_before_retry"] is True
