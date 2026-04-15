from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.utils.id_generator import generate_id


class ContextManager:
    """Manages unified context, history, session, and trace metadata."""

    def __init__(self, session_store: SessionStore | None = None) -> None:
        self.session_store = session_store or SessionStore()

    def load(self, raw_context: dict[str, Any] | None) -> CoreContextSchema:
        raw_context = raw_context or {}
        session_id = raw_context.get("session_id") or "default"
        trace_id = raw_context.get("trace_id") or generate_id("trace")
        state = self.session_store.get(session_id)
        metadata = raw_context.get("metadata") or {}
        return CoreContextSchema(
            session_id=session_id,
            trace_id=trace_id,
            timezone=raw_context.get("timezone", "Asia/Tokyo"),
            locale=raw_context.get("locale", "ja-JP"),
            session_state=state,
            metadata=metadata,
        )

    def enrich(self, context: CoreContextSchema) -> CoreContextSchema:
        context.metadata.setdefault("enriched_at", datetime.now(UTC).isoformat())
        context.metadata.setdefault("record_count", len(context.session_state.get("records", [])))
        return context
