from __future__ import annotations


class WeaviateRetriever:
    """Phase-0 fallback retriever.

    First阶段先保留接口，后续可替换成真实 Weaviate client。
    """

    def retrieve(self, query: str) -> list[dict[str, str]]:
        if not query.strip():
            return []
        return []
