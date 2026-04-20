from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nethub_runtime.core.main import app


client = TestClient(app)


def test_runtime_memory_api_returns_promoted_document_hits(isolated_generated_artifacts) -> None:
    temp_path = Path("/tmp/runtime_memory_api_doc.txt")
    temp_path.write_text("项目状态稳定，下一步是完成联调和测试。", encoding="utf-8")

    handle_response = client.post(
        "/core/handle",
        json={
            "input_text": "请对这份文档进行总结",
            "context": {
                "session_id": "runtime-memory-api-document",
                "metadata": {
                    "attachments": [
                        {
                            "file_name": "runtime_memory_api_doc.txt",
                            "content_type": "text/plain",
                            "input_type": "document",
                            "stored_path": str(temp_path),
                        }
                    ]
                },
            },
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert handle_response.status_code == 200

    inspect_response = client.get(
        "/core/admin/runtime-memory",
        params={"query": "联调 测试", "namespace": "document_analysis", "top_k": 5},
    )
    assert inspect_response.status_code == 200
    result = inspect_response.json()["result"]
    assert result["promotion_artifacts"]
    assert result["vector_hits"]
    assert any(hit["namespace"] == "document_analysis" for hit in result["vector_hits"])


def test_runtime_memory_api_returns_information_agent_fact_hits(isolated_generated_artifacts) -> None:
    promote_response = client.post(
        "/core/handle",
        json={
            "input_text": "帮我创建供应商资料智能体",
            "context": {"session_id": "runtime-memory-api-agent", "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    assert promote_response.status_code == 200

    client.post(
        "/core/handle",
        json={
            "input_text": "主要记录供应商资料的信息。",
            "context": {"session_id": "runtime-memory-api-agent", "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    client.post(
        "/core/handle",
        json={
            "input_text": "完成创建供应商资料信息智能体",
            "context": {"session_id": "runtime-memory-api-agent", "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    client.post(
        "/core/handle",
        json={
            "input_text": "将供应商甲信息添加到供应商资料智能体中",
            "context": {"session_id": "runtime-memory-api-agent", "locale": "ja-JP", "timezone": "Asia/Tokyo"},
            "output_format": "dict",
            "use_langraph": False,
        },
    )
    for text in ["供应商甲", "供应商", "负责样品交付", "1234567890 / vendor@example.com", "ABC株式会社，完成添加"]:
        client.post(
            "/core/handle",
            json={
                "input_text": text,
                "context": {"session_id": "runtime-memory-api-agent", "locale": "ja-JP", "timezone": "Asia/Tokyo"},
                "output_format": "dict",
                "use_langraph": False,
            },
        )

    inspect_response = client.get(
        "/core/admin/runtime-memory",
        params={"query": "供应商甲 vendor@example.com", "namespace": "information_agent_fact", "top_k": 5},
    )
    assert inspect_response.status_code == 200
    result = inspect_response.json()["result"]
    assert result["vector_hits"]
    assert any(hit["namespace"] == "information_agent_fact" for hit in result["vector_hits"])