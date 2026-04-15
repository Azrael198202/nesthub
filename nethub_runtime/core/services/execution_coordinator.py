from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nethub_runtime.core.config.settings import INTENT_POLICY_PATH
from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema


class ExecutionCoordinator:
    """Executes workflow nodes with retry, state persistence, and generic data ops."""

    def __init__(self, session_store: SessionStore | None = None, intent_policy_path: Path | None = None) -> None:
        self.session_store = session_store or SessionStore()
        self.intent_policy_path = intent_policy_path or INTENT_POLICY_PATH
        self.intent_policy = self._load_intent_policy()

    def _load_intent_policy(self) -> dict[str, Any]:
        if self.intent_policy_path.exists():
            return json.loads(self.intent_policy_path.read_text(encoding="utf-8"))
        return {"time_markers": [], "stopwords": [], "group_by_markers": [], "numeric_value_patterns": []}

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
                        {
                            "step_id": step["step_id"],
                            "name": step["name"],
                            "status": "completed",
                            "capability": step.get("capability", {}),
                            "runtime_capabilities": step.get("runtime_capabilities", {}),
                            "output": output,
                        }
                    )
                    break
                except Exception as exc:  # pragma: no cover
                    last_error = str(exc)
                    attempt += 1
                    if attempt > retries:
                        results["steps"].append(
                            {"step_id": step["step_id"], "name": step["name"], "status": "failed", "error": last_error}
                        )
        results["final_output"] = step_outputs
        return results

    def _run_step(
        self, step_name: str, task: TaskSchema, context: CoreContextSchema, step_outputs: dict[str, Any]
    ) -> dict[str, Any]:
        if step_name == "extract_records":
            records = self._extract_records(task.input_text)
            return {"records": records, "count": len(records)}
        if step_name == "persist_records":
            records = step_outputs.get("extract_records", {}).get("records", [])
            state = self.session_store.append_records(context.session_id, records)
            return {"saved": len(records), "total_records": len(state.get("records", []))}
        if step_name == "parse_query":
            state = self.session_store.get(context.session_id)
            return {"query": self._parse_query(task.input_text, state.get("records", []))}
        if step_name == "aggregate_query":
            query = step_outputs.get("parse_query", {}).get("query", {})
            state = self.session_store.get(context.session_id)
            return {"aggregation": self._aggregate_records(state.get("records", []), query)}
        if step_name == "ocr_extract":
            return {"artifact_type": "text", "status": "dispatched", "task": "ocr", "message": "OCR dispatch prepared."}
        if step_name == "stt_transcribe":
            return {"artifact_type": "text", "status": "dispatched", "task": "stt", "message": "STT dispatch prepared."}
        if step_name == "tts_synthesize":
            return {"artifact_type": "audio", "status": "dispatched", "task": "tts", "message": "TTS dispatch prepared."}
        if step_name == "image_generate":
            return {"artifact_type": "image", "status": "dispatched", "task": "image_generation"}
        if step_name == "video_generate":
            return {"artifact_type": "video", "status": "dispatched", "task": "video_generation"}
        if step_name == "file_generate":
            return {"artifact_type": "file", "status": "dispatched", "task": "file_generation"}
        if step_name == "web_retrieve":
            return {"artifact_type": "web_content", "status": "dispatched", "task": "web_research"}
        if step_name == "web_summarize":
            return {"artifact_type": "summary", "status": "dispatched", "task": "web_summary"}
        return {"message": "no-op"}

    def _extract_records(self, text: str) -> list[dict[str, Any]]:
        segments = [segment.strip() for segment in re.split(r"[。；;\n]|还有|并且|and", text) if segment.strip()]
        records: list[dict[str, Any]] = []
        for segment in segments:
            amount = self._extract_amount(segment)
            if amount is None:
                continue
            records.append(
                {
                    "time": self._extract_time(segment),
                    "location": self._extract_location(segment),
                    "content": self._extract_content(segment),
                    "amount": amount,
                    "participants": self._extract_participants(segment),
                    "actor": self._extract_actor(segment),
                    "label": self._infer_label(segment),
                    "raw_text": segment,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
        return records

    def _extract_amount(self, text: str) -> int | None:
        for pattern in self.intent_policy.get("numeric_value_patterns", []):
            matched = re.search(pattern, text, flags=re.IGNORECASE)
            if matched:
                value = matched.group(1)
                if value:
                    return int(float(value))
        fallback = re.search(r"(\d+(?:\.\d+)?)", text)
        if fallback:
            return int(float(fallback.group(1)))
        return None

    def _extract_time(self, text: str) -> str:
        for marker in self.intent_policy.get("time_markers", []):
            if marker in text:
                return marker
        return "unspecified"

    def _extract_location(self, text: str) -> str | None:
        for marker in ("在", "去", "于", "at", "in"):
            if marker in text:
                candidate = text.split(marker, 1)[-1].strip()
                return re.split(r"[，,。 ]", candidate)[0] or None
        return None

    def _extract_content(self, text: str) -> str:
        cleaned = re.sub(r"\d+(?:\.\d+)?\s*(日元|円|yen|usd|rmb|元|块|美元|￥|\$)?", "", text, flags=re.IGNORECASE)
        cleaned = cleaned.strip(" ，,.。")
        return cleaned or "entry"

    def _extract_participants(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*人", text)
        if match:
            return int(match.group(1))
        if "两个人" in text:
            return 2
        return None

    def _extract_actor(self, text: str) -> str:
        if "家人" in text:
            return "家人"
        if "朋友" in text:
            return "朋友"
        return "self"

    def _infer_label(self, text: str) -> str:
        lowered = text.lower()
        label_rules: dict[str, list[str]] = self.intent_policy.get("label_rules", {})
        for label, markers in label_rules.items():
            if any(marker.lower() in lowered for marker in markers):
                return label
        return "other"

    def _parse_query(self, text: str, existing_records: list[dict[str, Any]]) -> dict[str, Any]:
        stopwords = set(self.intent_policy.get("stopwords", []))
        normalized = text
        for stopword in stopwords:
            normalized = normalized.replace(stopword, " ")
        tokens = [tok for tok in re.split(r"[\s，,。；;！？!?]+", normalized) if tok]
        terms = [tok for tok in tokens if tok not in stopwords and len(tok) > 1]
        record_matched_terms = self._find_terms_from_records(text, existing_records)
        dynamic_terms = record_matched_terms or self._extract_dynamic_terms(terms, existing_records)
        group_by = self._extract_group_by(text)
        return {
            "metric": "sum",
            "terms": dynamic_terms,
            "group_by": group_by,
            "time_marker": self._extract_time(text),
        }

    def _find_terms_from_records(self, query_text: str, existing_records: list[dict[str, Any]]) -> list[str]:
        terms: list[str] = []
        for item in existing_records:
            for field in ("content", "location", "label", "actor"):
                value = str(item.get(field, "")).strip()
                if len(value) >= 2 and value in query_text and value not in terms:
                    terms.append(value)
        return terms

    def _extract_dynamic_terms(self, terms: list[str], existing_records: list[dict[str, Any]]) -> list[str]:
        if not existing_records:
            return terms
        corpus = " ".join(
            f"{item.get('content','')} {item.get('location','')} {item.get('label','')} {item.get('actor','')}"
            for item in existing_records
        )
        return [term for term in terms if term in corpus]

    def _extract_group_by(self, text: str) -> list[str]:
        results: list[str] = []
        marker_map = {
            "按时间": "time",
            "按类别": "label",
            "按地点": "location",
            "按人员": "actor",
        }
        for marker in self.intent_policy.get("group_by_markers", []):
            if marker in text and marker in marker_map:
                results.append(marker_map[marker])
        return results

    def _aggregate_records(self, records: list[dict[str, Any]], query: dict[str, Any]) -> dict[str, Any]:
        filtered = list(records)
        time_marker = query.get("time_marker")
        if time_marker and time_marker != "unspecified":
            filtered = [item for item in filtered if item.get("time") == time_marker or time_marker in str(item.get("time"))]
        terms = query.get("terms", [])
        if terms:
            filtered = [item for item in filtered if all(term in json.dumps(item, ensure_ascii=False) for term in terms)]
        total_amount = sum(int(item.get("amount", 0)) for item in filtered)
        grouped: dict[str, dict[str, int]] = {}
        for dim in query.get("group_by", []):
            grouped[dim] = {}
            for item in filtered:
                key = str(item.get(dim, "unknown"))
                grouped[dim][key] = grouped[dim].get(key, 0) + int(item.get("amount", 0))
        return {"total_amount": total_amount, "count": len(filtered), "grouped": grouped}
