from __future__ import annotations

from datetime import UTC, datetime
import shutil
import urllib.request
from pathlib import Path
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

    def _received_dir(self, session_id: str) -> Path:
        base = Path(__file__).resolve().parents[3] / "received" / session_id
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _is_document_attachment(self, attachment: dict[str, Any]) -> bool:
        input_type = str(attachment.get("input_type") or "").lower()
        content_type = str(attachment.get("content_type") or "").lower()
        file_name = str(attachment.get("file_name") or "").lower()
        document_suffixes = (
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".md",
        )
        if input_type == "document":
            return True
        if content_type.startswith("text/"):
            return True
        return file_name.endswith(document_suffixes)

    def _is_image_attachment(self, attachment: dict[str, Any]) -> bool:
        input_type = str(attachment.get("input_type") or "").lower()
        content_type = str(attachment.get("content_type") or "").lower()
        file_name = str(attachment.get("file_name") or "").lower()
        image_suffixes = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
        if input_type == "image":
            return True
        if content_type.startswith("image/"):
            return True
        return file_name.endswith(image_suffixes)

    def _is_analysis_attachment(self, attachment: dict[str, Any]) -> bool:
        return self._is_document_attachment(attachment) or self._is_image_attachment(attachment)

    def _copy_or_download_attachment(self, session_id: str, attachment: dict[str, Any]) -> str:
        file_name = str(attachment.get("file_name") or "document.bin").strip() or "document.bin"
        source_path = str(attachment.get("received_path") or attachment.get("stored_path") or "").strip()
        target_dir = self._received_dir(session_id)
        target_path = target_dir / Path(file_name).name
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            counter = 1
            while True:
                candidate = target_dir / f"{stem}_{counter}{suffix}"
                if not candidate.exists():
                    target_path = candidate
                    break
                counter += 1

        if source_path and Path(source_path).exists():
            shutil.copy2(source_path, target_path)
            return str(target_path)

        download_url = str(attachment.get("download_url") or "").strip()
        if download_url:
            with urllib.request.urlopen(download_url, timeout=30) as response:  # nosec B310
                target_path.write_bytes(response.read())
            return str(target_path)

        return ""

    def _ingest_document_attachments(self, session_id: str, metadata: dict[str, Any], state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        attachments = list(metadata.get("attachments") or [])
        if not attachments:
            return metadata, state

        existing_documents = list(state.get("documents") or [])
        existing_analysis_attachments = list(state.get("analysis_attachments") or [])
        existing_keys = {
            (
                str(item.get("external_message_id") or ""),
                str(item.get("file_name") or ""),
                str(item.get("stored_path") or item.get("download_url") or ""),
            )
            for item in [*existing_documents, *existing_analysis_attachments]
            if isinstance(item, dict)
        }
        updated_attachments: list[dict[str, Any]] = []
        new_documents: list[dict[str, Any]] = []
        new_analysis_attachments: list[dict[str, Any]] = []

        for attachment in attachments:
            normalized = dict(attachment)
            if not self._is_analysis_attachment(normalized):
                updated_attachments.append(normalized)
                continue

            received_path = str(normalized.get("received_path") or "").strip()
            if not received_path:
                try:
                    received_path = self._copy_or_download_attachment(session_id, normalized)
                except Exception:
                    received_path = ""
            if received_path:
                normalized["received_path"] = received_path

            record = {
                "file_name": str(normalized.get("file_name") or Path(received_path).name or "document"),
                "content_type": str(normalized.get("content_type") or "application/octet-stream"),
                "input_type": str(normalized.get("input_type") or "document"),
                "stored_path": str(normalized.get("stored_path") or ""),
                "received_path": received_path,
                "download_url": str(normalized.get("download_url") or ""),
                "source_message_type": str(normalized.get("source_message_type") or "file"),
                "external_message_id": str(normalized.get("external_message_id") or ""),
                "imported_at": datetime.now(UTC).isoformat(),
            }
            document_key = (record["external_message_id"], record["file_name"], record["stored_path"] or record["download_url"])
            if document_key not in existing_keys:
                existing_keys.add(document_key)
                new_analysis_attachments.append(record)
                if self._is_document_attachment(normalized):
                    new_documents.append(record)
            updated_attachments.append(normalized)

        if new_documents or new_analysis_attachments:
            state = self.session_store.patch(
                session_id,
                {
                    "documents": [*existing_documents, *new_documents],
                    "analysis_attachments": [*existing_analysis_attachments, *new_analysis_attachments],
                    "last_document_at": datetime.now(UTC).isoformat(),
                },
            )
        metadata["attachments"] = updated_attachments
        metadata["document_attachments"] = [item for item in updated_attachments if self._is_document_attachment(item)]
        metadata["image_attachments"] = [item for item in updated_attachments if self._is_image_attachment(item)]
        metadata["analysis_attachments"] = [item for item in updated_attachments if self._is_analysis_attachment(item)]
        return metadata, state

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
        metadata, state = self._ingest_document_attachments(active_session_id, metadata, state)

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
