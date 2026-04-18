from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from nethub_runtime.core.memory.session_store import SessionStore
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.utils.id_generator import generate_id


class ContextManager:
    """Manages unified context, history, session, and trace metadata.

    Session architecture
    --------------------
    * **Main session** — persistent per-user context (preferences, history).
      Identified by ``raw_context["session_id"]``.
    * **Task session** — isolated per-task context, prevents cross-task
      contamination.  Activated when ``raw_context["task_topic"]`` is
      present.  The task session ID is ``task:{main_session_id}:{topic}``.

    The ``CoreContextSchema`` returned always reflects the *active* session
    (task session when one is created; main session otherwise).  The main
    session ID is carried in ``context.metadata["main_session_id"]`` so
    downstream services can read it without parsing IDs.
    """

    def __init__(self, session_store: SessionStore | None = None) -> None:
        self.session_store = session_store or SessionStore()

    def load(self, raw_context: dict[str, Any] | None) -> CoreContextSchema:
        raw_context = raw_context or {}
        main_session_id = raw_context.get("session_id") or "default"
        trace_id = raw_context.get("trace_id") or generate_id("trace")
        task_topic: str | None = raw_context.get("task_topic") or None

        if task_topic:
            # Create / retrieve a task-scoped session for this topic
            active_session_id = self.session_store.create_task_session(
                main_session_id, task_topic
            )
        else:
            active_session_id = main_session_id

        state = self.session_store.get(active_session_id)
        metadata = dict(raw_context.get("metadata") or {})
        metadata["main_session_id"] = main_session_id
        if task_topic:
            metadata["task_topic"] = task_topic
            metadata["task_session_id"] = active_session_id

        return CoreContextSchema(
            session_id=active_session_id,
            trace_id=trace_id,
            timezone=raw_context.get("timezone", "Asia/Tokyo"),
            locale=raw_context.get("locale", "ja-JP"),
            session_state=state,
            metadata=metadata,
        )

    def enrich(self, context: CoreContextSchema) -> CoreContextSchema:
        now = datetime.now(UTC).isoformat()
        context.metadata.setdefault("enriched_at", now)
        record_count = len(context.session_state.get("records", []))
        context.metadata["record_count"] = record_count
        # Write the enriched metadata back to the session store
        self.session_store.patch(
            context.session_id,
            {"_last_enriched_at": now, "_record_count": record_count},
        )
        return context
