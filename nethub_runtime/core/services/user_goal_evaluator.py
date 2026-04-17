from __future__ import annotations

import re
from typing import Any

from nethub_runtime.core.schemas.task_schema import TaskSchema


class UserGoalEvaluator:
    def evaluate(self, *, task: TaskSchema, execution_result: dict[str, Any]) -> dict[str, Any]:
        final_output = execution_result.get("final_output") or {}
        flattened_segments: list[str] = []
        for value in final_output.values():
            if isinstance(value, dict):
                flattened_segments.extend(str(item) for item in value.values() if item is not None)
            elif value is not None:
                flattened_segments.append(str(value))
        corpus = " ".join(flattened_segments).lower()
        terms = self._extract_goal_terms(task.input_text)
        matched_terms = [term for term in terms if term in corpus]
        missing_terms = [term for term in terms if term not in corpus]
        satisfied = not terms or len(matched_terms) >= max(1, min(len(terms), 2))
        return {
            "satisfied": satisfied,
            "goal_terms": terms,
            "matched_terms": matched_terms,
            "missing_terms": missing_terms,
        }

    def _extract_goal_terms(self, text: str) -> list[str]:
        normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.lower())
        tokens = [item.strip() for item in normalized.split() if item.strip()]
        stopwords = {"根据", "生成", "并", "以及", "然后", "一个", "一份", "请", "帮我", "把", "的", "了", "在", "前", "后", "我", "用户", "要求"}
        terms = [token for token in tokens if len(token) >= 2 and token not in stopwords]
        deduped: list[str] = []
        for term in terms:
            if term not in deduped:
                deduped.append(term)
        return deduped[:6]
