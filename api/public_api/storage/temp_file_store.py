from __future__ import annotations

import mimetypes
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any


@dataclass
class TempFileRecord:
    file_id: str
    file_name: str
    stored_path: Path
    created_at: datetime
    expires_at: datetime
    content_type: str
    metadata: dict[str, Any]


class TempFileStore:
    def __init__(self, base_dir: str | Path | None = None, ttl_seconds: int = 3600):
        root = Path(base_dir or os.getenv("NESTHUB_PUBLIC_API_TEMP_DIR") or Path.cwd() / ".public_api_temp")
        self.base_dir = root
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, TempFileRecord] = {}
        self._lock = Lock()

    def save_bytes(
        self,
        *,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TempFileRecord:
        self.cleanup_expired()
        safe_name = Path(file_name or "download.bin").name or "download.bin"
        suffix = Path(safe_name).suffix
        file_id = uuid.uuid4().hex
        stored_path = self.base_dir / f"{file_id}{suffix}"
        stored_path.write_bytes(content)
        guessed_type = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        now = datetime.now(UTC)
        record = TempFileRecord(
            file_id=file_id,
            file_name=safe_name,
            stored_path=stored_path,
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            content_type=guessed_type,
            metadata=metadata or {},
        )
        with self._lock:
            self._records[file_id] = record
        return record

    def get(self, file_id: str) -> TempFileRecord | None:
        self.cleanup_expired()
        with self._lock:
            record = self._records.get(file_id)
            if not record:
                return None
            if record.expires_at <= datetime.now(UTC):
                self._delete_record(record)
                return None
            return record

    def cleanup_expired(self) -> int:
        expired_ids: list[str] = []
        now = datetime.now(UTC)
        with self._lock:
            for file_id, record in self._records.items():
                if record.expires_at <= now or not record.stored_path.exists():
                    expired_ids.append(file_id)
            for file_id in expired_ids:
                record = self._records.pop(file_id, None)
                if record is not None and record.stored_path.exists():
                    try:
                        record.stored_path.unlink()
                    except OSError:
                        pass
        return len(expired_ids)

    def _delete_record(self, record: TempFileRecord) -> None:
        self._records.pop(record.file_id, None)
        if record.stored_path.exists():
            try:
                record.stored_path.unlink()
            except OSError:
                pass