from __future__ import annotations

from pathlib import Path

from nethub_runtime.core.memory.semantic_policy_store import SemanticPolicyStore
from nethub_runtime.core.memory.vector_store import VectorStore, SQLiteVectorPersistence
from nethub_runtime.core.services.memory_promotion_service import MemoryPromotionService
from nethub_runtime.generated.store import GeneratedArtifactStore


def _write_policy(path: Path) -> None:
    path.write_text(
        """
{
  "tokenizer": {"preferred": "regex", "fallback": "regex", "min_token_length": 2},
  "semantic_matching": {"method": "embedding_or_token", "embedding_model": "", "similarity_threshold": 0.62, "fallback_to_external_threshold": 0.35},
  "normalization": {"text_replace": {}, "synonyms": {}},
  "intent_detection": {"group_query_markers": []},
  "aggregation_query": {"generic_action_terms": []},
  "information_collection": {"completion_phrases": ["完成添加"], "default_completion_phrase": "完成添加", "field_capture_markers": [], "field_aliases": {}, "field_query_keywords": {}, "list_query_markers": [], "record_name_suffixes": [], "record_name_split_separators": []},
  "semantic_label_threshold": 0.32,
  "semantic_label_margin": 0.08,
  "entity_aliases": {"actor": {}},
  "ignored_query_tokens": [],
  "label_taxonomy": {},
  "record_type_rules": {"generic": {"default": true, "default_label": "other"}},
  "query_metric_rules": {},
  "segment_split_patterns": ["[。；;\\n]"],
  "location_markers": [],
  "location_keyword_patterns": [],
  "participant_pattern": "(\\d+)",
  "participant_aliases": {},
  "content_cleanup_patterns": [],
  "content_strip_chars": " ,.",
  "group_by_aliases": {},
  "actor_extract_patterns": [],
  "explicit_date_patterns": [],
  "relative_week_rules": [],
  "boolean_aliases": {"truthy": ["yes"], "falsy": ["no"]},
  "model_semantic_parser": {"enabled": false, "prefer_model_for_query_parsing": false, "prefer_model_for_record_extraction": false, "strict_schema_validation": true},
  "time_marker_rules": {},
  "policy_memory": {"enabled": true, "backend": "sqlite", "read_only_main_policy": true, "auto_candidate_zone": true, "auto_activate": {"enabled": true, "min_hits": 2, "min_confidence": 0.75}, "learning": {"enabled": false, "extractor": "model", "max_updates_per_text": 8, "default_confidence": 0.82}, "self_heal": {"enabled": true, "max_failures": 2, "rollback_batch_size": 2}},
  "external_semantic_router": {"enabled": false},
  "multimodal_intent_rules": []
}
        """.strip(),
        encoding="utf-8",
    )


def test_memory_promotion_service_promotes_document_analysis(tmp_path: Path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    vector_db_path = tmp_path / "vector_store.sqlite3"
    _write_policy(policy_path)

    service = MemoryPromotionService(
        semantic_policy_store=SemanticPolicyStore(policy_path=policy_path, db_path=db_path),
        vector_store=VectorStore(persistence=SQLiteVectorPersistence(vector_db_path)),
        generated_artifact_store=GeneratedArtifactStore(),
    )

    summary = service.promote_execution_result(
        task={"intent": "file_upload_task", "domain": "multimodal_ops", "input_text": "请总结这份文档"},
        context={"trace_id": "trace_memory_promote_case", "session_id": "session_memory_promote_case"},
        execution_result={
            "final_output": {
                "analyze_document": {
                    "status": "completed",
                    "summary": "这份文档说明了项目进度和下周行动项。",
                    "source_documents": ["brief.txt"],
                    "requested_action": "summarize",
                }
            }
        },
    )

    assert summary["promoted"] is True
    assert summary["promotion_count"] == 1
    assert summary["items"][0]["kind"] == "document_analysis"
    assert summary["items"][0]["status"] == "promoted"
    assert summary["items"][0]["inspection"]["namespace"] == "document_analysis"
    assert summary.get("artifact_path")


def test_memory_promotion_service_deduplicates_same_document_summary(tmp_path: Path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    vector_db_path = tmp_path / "vector_store.sqlite3"
    _write_policy(policy_path)

    service = MemoryPromotionService(
        semantic_policy_store=SemanticPolicyStore(policy_path=policy_path, db_path=db_path),
        vector_store=VectorStore(persistence=SQLiteVectorPersistence(vector_db_path)),
        generated_artifact_store=GeneratedArtifactStore(),
    )

    first = service.promote_execution_result(
        task={"intent": "file_upload_task", "domain": "multimodal_ops", "input_text": "总结文档"},
        context={"trace_id": "trace_memory_promote_first", "session_id": "session_memory_promote_case"},
        execution_result={
            "final_output": {
                "analyze_document": {
                    "status": "completed",
                    "summary": "这份文档说明了项目进度和下周行动项。",
                    "source_documents": ["brief.txt"],
                    "requested_action": "summarize",
                }
            }
        },
    )
    second = service.promote_execution_result(
        task={"intent": "file_upload_task", "domain": "multimodal_ops", "input_text": "再总结一次文档"},
        context={"trace_id": "trace_memory_promote_second", "session_id": "session_memory_promote_case"},
        execution_result={
            "final_output": {
                "analyze_document": {
                    "status": "completed",
                    "summary": "这份文档说明了项目进度和下周行动项。",
                    "source_documents": ["brief.txt"],
                    "requested_action": "summarize",
                }
            }
        },
    )

    assert first["items"][0]["status"] == "promoted"
    assert second["items"][0]["status"] == "deduplicated"
    assert second["items"][0]["vector_item_id"] == first["items"][0]["vector_item_id"]
    assert second["items"][0]["inspection"]["similar_items"]


def test_memory_promotion_service_structures_information_agent_facts(tmp_path: Path) -> None:
    policy_path = tmp_path / "semantic_policy.json"
    db_path = tmp_path / "semantic_policy_memory.sqlite3"
    vector_db_path = tmp_path / "vector_store.sqlite3"
    _write_policy(policy_path)

    service = MemoryPromotionService(
        semantic_policy_store=SemanticPolicyStore(policy_path=policy_path, db_path=db_path),
        vector_store=VectorStore(persistence=SQLiteVectorPersistence(vector_db_path)),
        generated_artifact_store=GeneratedArtifactStore(),
    )

    summary = service.promote_execution_result(
        task={"intent": "capture_agent_knowledge", "domain": "general", "input_text": "将供应商甲信息添加到供应商资料智能体中"},
        context={"trace_id": "trace_information_agent_promote", "session_id": "session_information_agent_promote"},
        execution_result={
            "final_output": {
                "manage_information_agent": {
                    "message": "已完成添加，并已记录该供应商信息。",
                    "dialog_state": {"stage": "knowledge_added"},
                    "agent": {
                        "agent_id": "supplier_agent",
                        "role": "供应商资料信息智能体",
                        "knowledge_entity_label": "供应商",
                        "schema_fields": ["item_name", "contact", "details"],
                        "activation_keywords": ["添加供应商到供应商资料智能体中", "查询供应商资料智能体"],
                        "profile": "entity_directory",
                    },
                    "workflow_state": {
                        "profile": "entity_directory",
                        "entity_label": "供应商",
                        "query_aliases": {"联系方式": "contact"},
                    },
                    "knowledge": {
                        "item_name": "供应商甲",
                        "contact": "vendor@example.com",
                        "details": "ABC株式会社，负责样品交付",
                    },
                }
            }
        },
    )

    assert summary["promoted"] is True
    assert summary["promotion_count"] == 1
    item = summary["items"][0]
    assert item["kind"] == "information_agent"
    assert item["status"] == "promoted"
    assert any(fact["type"] == "information_agent_definition" for fact in item["facts"])
    assert any(fact["type"] == "information_agent_record" for fact in item["facts"])
    assert any(exp["type"] == "information_agent_runtime_experience" for exp in item["experiences"])
    assert any(exp["type"] == "information_agent_capture_pattern" for exp in item["experiences"])


def test_core_engine_document_result_contains_memory_promotion() -> None:
    import asyncio

    from nethub_runtime.core.services.core_engine import AICore

    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    temp_path = Path("/tmp/memory_promotion_brief.txt")
    temp_path.write_text("项目状态稳定，下一步是完成联调和测试。", encoding="utf-8")

    result = asyncio.run(
        core.handle(
            input_text="请对这份文档进行总结，然后发给我",
            context={
                "session_id": "memory-promotion-core-session",
                "metadata": {
                    "attachments": [
                        {
                            "file_name": "memory_promotion_brief.txt",
                            "content_type": "text/plain",
                            "input_type": "document",
                            "stored_path": str(temp_path),
                        }
                    ]
                },
            },
            fmt="dict",
            use_langraph=False,
        )
    )

    promotion = result["execution_result"].get("memory_promotion") or {}
    assert promotion.get("promoted") is True
    assert promotion.get("promotion_count", 0) >= 1
    dataset_export = result["execution_result"].get("training_dataset_export") or {}
    assert dataset_export.get("exported") is True
    assert dataset_export.get("sft_count", 0) >= 1


def test_core_engine_private_brain_summary_includes_dataset_counts() -> None:
    from nethub_runtime.core.services.core_engine import AICore

    core = AICore(model_config_path="nethub_runtime/config/model_config.yaml")
    summary = core.inspect_private_brain_summary()

    assert "layers" in summary
    assert "training_assets" in summary["layers"]
    assert "sft_samples" in summary["layers"]["training_assets"]