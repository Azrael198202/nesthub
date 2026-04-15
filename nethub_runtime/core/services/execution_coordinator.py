from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


class ExecutionCoordinator:
    """Executes routed workflow nodes with basic retry and state persistence."""

    def __init__(self, session_store: SessionStore | None = None) -> None:
        self.session_store = session_store or SessionStore()

    def execute(self, plan: list[dict[str, Any]], task: TaskSchema, context: CoreContextSchema) -> dict[str, Any]:
        results: dict[str, Any] = {"steps": [], "task_intent": task.intent}
        step_outputs: dict[str, Any] = {}
        for step in plan:
            retries = step.get("retry", 0)
            attempt = 0
            last_error: str | None = None
            while attempt <= retries:
                try:
                    output = self._run_step(step["name"], task, context, step_outputs)
                    step_outputs[step["name"]] = output
                    results["steps"].append(
                        {"step_id": step["step_id"], "name": step["name"], "status": "completed", "output": output}
                    )
                    break
                except Exception as exc:  # pragma: no cover - defensive fallback
                    last_error = str(exc)
                    attempt += 1
                    if attempt > retries:
                        results["steps"].append(
                            {
                                "step_id": step["step_id"],
                                "name": step["name"],
                                "status": "failed",
                                "error": last_error,
                            }
                        )
        results["final_output"] = step_outputs
        return results

    def _run_step(
        self, step_name: str, task: TaskSchema, context: CoreContextSchema, step_outputs: dict[str, Any]
    ) -> dict[str, Any]:
        if step_name == "extract_records":
            records = self._parse_expense_records(task.input_text)
            return {"records": records, "count": len(records)}
        if step_name == "persist_records":
            records = step_outputs.get("extract_records", {}).get("records", [])
            state = self.session_store.append_records(context.session_id, records)
            return {"saved": len(records), "total_records": len(state.get("records", []))}
        if step_name == "parse_query":
            query = self._parse_query(task.input_text)
            return {"query": query}
        if step_name == "aggregate_query":
            query = step_outputs.get("parse_query", {}).get("query", {})
            state = self.session_store.get(context.session_id)
            aggregation = self._aggregate_records(state.get("records", []), query)
            return {"aggregation": aggregation}
        return {"message": "no-op"}

    def _parse_expense_records(self, text: str) -> list[dict[str, Any]]:
        segments = [segment.strip() for segment in re.split(r"[。；;]|还有|并且", text) if segment.strip()]
        records: list[dict[str, Any]] = []
        for segment in segments:
            amounts = re.findall(r"(\d+)\s*日元", segment)
            if not amounts:
                continue
            amount = int(amounts[-1])
            record = {
                "time": self._extract_time(segment),
                "location": self._extract_location(segment),
                "content": self._extract_content(segment),
                "amount": amount,
                "participants": self._extract_participants(segment),
                "spender": self._extract_spender(segment),
                "category": self._infer_category(segment),
                "raw_text": segment,
                "created_at": datetime.now(UTC).isoformat(),
            }
            records.append(record)
        return records

    def _extract_time(self, text: str) -> str:
        for marker in ("今天", "昨日", "昨天", "上周", "上周末", "这个月", "5月第一周", "五月第一周"):
            if marker in text:
                return marker
        return "unspecified"

    def _extract_location(self, text: str) -> str | None:
        location_markers = ("在", "去", "于")
        for marker in location_markers:
            if marker in text:
                after = text.split(marker, 1)[-1]
                location = re.split(r"[，,。 ]", after.strip())[0]
                if location:
                    return location
        return None

    def _extract_content(self, text: str) -> str:
        cleaned = re.sub(r"\d+\s*日元", "", text)
        cleaned = cleaned.replace("花了", "").replace("买了", "").strip(" ，,。")
        return cleaned or "消费"

    def _extract_participants(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*人", text)
        if match:
            return int(match.group(1))
        if "两个人" in text:
            return 2
        return None

    def _extract_spender(self, text: str) -> str:
        if "家人" in text:
            return "家人"
        if "朋友" in text:
            return "朋友"
        return "我"

    def _infer_category(self, text: str) -> str:
        mapping = {
            "餐饮": ("吃饭", "拉面", "咖啡"),
            "购物": ("买了", "超市", "书"),
            "娱乐": ("电影", "游戏", "娱乐"),
        }
        for category, markers in mapping.items():
            if any(marker in text for marker in markers):
                return category
        return "其他"

    def _parse_query(self, text: str) -> dict[str, Any]:
        query: dict[str, Any] = {"dimensions": [], "filters": {}}
        if "第一周" in text:
            query["filters"]["time"] = "5月第一周"
        elif "这个月" in text:
            query["filters"]["time"] = "这个月"
        elif "上周" in text:
            query["filters"]["time"] = "上周"
        if "餐饮" in text:
            query["filters"]["category"] = "餐饮"
        if "家人" in text:
            query["filters"]["spender"] = "家人"
        elif "我个人" in text or "我 " in f"{text} ":
            query["filters"]["spender"] = "我"
        if "咖啡" in text:
            query["filters"]["keyword"] = "咖啡"
        if "博多" in text:
            query["filters"]["location_keyword"] = "博多"
        if "按" in text and "时间" in text:
            query["dimensions"].append("time")
        if "按" in text and "类别" in text:
            query["dimensions"].append("category")
        return query

    def _aggregate_records(self, records: list[dict[str, Any]], query: dict[str, Any]) -> dict[str, Any]:
        filtered = records
        filters = query.get("filters", {})
        if "time" in filters:
            if filters["time"] == "这个月":
                filtered = [r for r in filtered if r.get("time") in {"这个月", "今天", "昨天"}]
            else:
                filtered = [r for r in filtered if r.get("time") == filters["time"]]
        if "category" in filters:
            filtered = [r for r in filtered if r.get("category") == filters["category"]]
        if "spender" in filters:
            filtered = [r for r in filtered if r.get("spender") == filters["spender"]]
        if "keyword" in filters:
            filtered = [r for r in filtered if filters["keyword"] in r.get("content", "")]
        if "location_keyword" in filters:
            filtered = [r for r in filtered if filters["location_keyword"] in (r.get("location") or "")]
        total_amount = sum(int(r.get("amount", 0)) for r in filtered)
        grouped: dict[str, int] = {}
        for dimension in query.get("dimensions", []):
            dim_group: dict[str, int] = {}
            for record in filtered:
                key = str(record.get(dimension, "unknown"))
                dim_group[key] = dim_group.get(key, 0) + int(record.get("amount", 0))
            grouped[dimension] = dim_group
        return {
            "total_amount": total_amount,
            "count": len(filtered),
            "grouped": grouped,
        }
