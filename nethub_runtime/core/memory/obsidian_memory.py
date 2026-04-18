"""
Obsidian Memory Integration for NestHub AI.

Obsidian acts as NestHub's local, programmable knowledge system across
five roles:

  📚 RAG 数据源         — vault notes are indexed and searched at query time
  🧠 AI Memory          — past interactions are recalled from persisted notes
  🧾 自动记录系统       — new interactions are written back as .md notes
  📊 轻量数据库         — YAML frontmatter provides structured metadata
  🌐 内容管理系统       — the vault organises domain knowledge as a CMS

Architecture
------------
  ObsidianNote          — parsed representation of one .md file
  ObsidianMemoryStore   — main facade: index vault → search → record

The store is **optional**: if no vault path is configured it becomes a
no-op, so existing behaviour is unchanged.

Configuration
-------------
  Set the environment variable OBSIDIAN_VAULT_PATH to the absolute path
  of your Obsidian vault, or pass vault_path= explicitly to the constructor.

Vault conventions (auto-created by this module)
------------------------------------------------
  <vault>/nesthub-memory/          — auto-recorded interaction notes
    YYYY-MM-DD-HHmmss-<intent>.md  — one note per recorded interaction
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from nethub_runtime.core.memory.vector_store import VectorStore
from nethub_runtime.core.config.settings import ensure_core_config_dir

LOGGER = logging.getLogger("nethub_runtime.core.memory.obsidian")

OBSIDIAN_VAULT_ENV = "OBSIDIAN_VAULT_PATH"
OBSIDIAN_RECORD_TAG = "nesthub-memory"
_VAULT_INDEX_TTL = 300  # seconds before re-indexing


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class ObsidianNote:
    """Parsed representation of a single Obsidian .md file."""

    def __init__(self, path: Path, frontmatter: dict[str, Any], body: str) -> None:
        self.path = path
        self.frontmatter = frontmatter
        self.body = body
        raw_tags = frontmatter.get("tags", [])
        if isinstance(raw_tags, str):
            self.tags: list[str] = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            self.tags = [str(t).strip() for t in raw_tags if t]
        self.intent: str = str(frontmatter.get("intent", "")).strip()
        self.domain: str = str(frontmatter.get("domain", "")).strip()
        self.title: str = str(frontmatter.get("title", path.stem)).strip()

    @property
    def full_text(self) -> str:
        tag_line = " ".join(self.tags)
        return f"{self.title}\n{tag_line}\n{self.body}"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class ObsidianMemoryStore:
    """
    Obsidian vault integration: RAG source, AI memory, auto-recorder,
    lightweight database, and content management system.
    """

    def __init__(
        self,
        vault_path: Path | str | None = None,
        vector_store: VectorStore | None = None,
        auto_record: bool = True,
        writable: bool = True,
    ) -> None:
        ensure_core_config_dir()
        resolved = vault_path or os.environ.get(OBSIDIAN_VAULT_ENV)
        self.vault_path: Path | None = Path(resolved).expanduser() if resolved else None
        self.vector_store = vector_store or VectorStore()
        self.auto_record = auto_record
        self.writable = writable
        self._indexed = False
        self._notes: list[ObsidianNote] = []
        self._index_timestamp: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        return self.vault_path is not None and self.vault_path.is_dir()

    # ------------------------------------------------------------------
    # Frontmatter parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
        """Extract YAML-like frontmatter block between --- delimiters."""
        if not text.startswith("---"):
            return {}, text
        end = text.find("---", 3)
        if end == -1:
            return {}, text
        fm_text = text[3:end].strip()
        body = text[end + 3:].strip()
        frontmatter: dict[str, Any] = {}
        for line in fm_text.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            # Simple list: [a, b, c]
            if value.startswith("[") and value.endswith("]"):
                frontmatter[key] = [
                    v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()
                ]
            else:
                frontmatter[key] = value.strip("\"'")
        return frontmatter, body

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_vault(self, *, force: bool = False) -> int:
        """
        Scan all .md files in the vault and index their content into the
        in-memory vector store.  Returns the number of notes indexed.
        Re-indexes automatically after _VAULT_INDEX_TTL seconds.
        """
        if not self.is_configured:
            return 0
        now = time.monotonic()
        if self._indexed and not force and (now - self._index_timestamp) < _VAULT_INDEX_TTL:
            return len(self._notes)

        self._notes = []
        assert self.vault_path is not None

        for md_file in self.vault_path.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8", errors="ignore")
                fm, body = self._parse_frontmatter(text)
                note = ObsidianNote(md_file, fm, body)
                self._notes.append(note)
                rel_path = str(md_file.relative_to(self.vault_path))
                self.vector_store.add_knowledge(
                    namespace="obsidian",
                    content=note.full_text[:2000],
                    metadata={
                        "source": "obsidian",
                        "file": rel_path,
                        "title": note.title,
                        "intent": note.intent,
                        "domain": note.domain,
                        "tags": note.tags,
                    },
                    item_id=f"obsidian_{abs(hash(rel_path)) % 999983:06d}",
                )
            except Exception:
                continue

        self._indexed = True
        self._index_timestamp = now
        LOGGER.debug("obsidian_memory: indexed %d notes from %s", len(self._notes), self.vault_path)
        return len(self._notes)

    # ------------------------------------------------------------------
    # Search / RAG
    # ------------------------------------------------------------------

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Return the top-k most relevant vault notes for a free-text query."""
        if not self.is_configured:
            return []
        if not self._indexed:
            self.index_vault()
        return self.vector_store.search(query, top_k=top_k, namespace="obsidian")

    def match_intent(self, text: str) -> dict[str, Any] | None:
        """
        Return an intent/domain hint derived from the most relevant vault note,
        or None if no confident match is found.

        The note must have non-empty ``intent`` and ``domain`` frontmatter
        fields for the match to be considered actionable.
        """
        results = self.search(text, top_k=3)
        for result in results:
            meta = result.get("metadata", {})
            intent = meta.get("intent", "")
            domain = meta.get("domain", "")
            if intent and domain:
                return {
                    "intent": intent,
                    "domain": domain,
                    "source": "obsidian_memory",
                    "note_title": meta.get("title", ""),
                    "tags": meta.get("tags", []),
                    "confidence": 0.75,
                }
        return None

    def rag_context(self, query: str, top_k: int = 3) -> str:
        """
        Build a concise RAG context string from the top-k vault notes.
        Suitable for injecting into LLM prompts.
        """
        results = self.search(query, top_k=top_k)
        if not results:
            return ""
        lines: list[str] = []
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            title = meta.get("title") or f"Note {i}"
            content = str(r.get("content", ""))[:400]
            lines.append(f"[{i}] {title}\n{content}")
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Auto-recording (AI Memory / 自动记录系统)
    # ------------------------------------------------------------------

    def record_interaction(
        self,
        text: str,
        *,
        intent: str,
        domain: str,
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Path | None:
        """
        Persist an interaction as a new Obsidian note inside
        ``<vault>/nesthub-memory/``.

        Returns the path of the created note, or None when recording is
        disabled or the vault is not writable.
        """
        if not self.is_configured or not self.auto_record or not self.writable:
            return None
        assert self.vault_path is not None

        ts = datetime.now()
        date_str = ts.strftime("%Y-%m-%d")
        time_str = ts.strftime("%H%M%S")

        nesthub_dir = self.vault_path / "nesthub-memory"
        try:
            nesthub_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None

        note_tags = list(dict.fromkeys([OBSIDIAN_RECORD_TAG, intent, domain] + (tags or [])))
        tags_yaml = ", ".join(f'"{t}"' for t in note_tags if t)

        extra_lines = ""
        if extra:
            for k, v in extra.items():
                extra_lines += f"\n{k}: {json.dumps(v, ensure_ascii=False)}"

        # Sanitise intent name for use in filename
        safe_intent = re.sub(r"[^A-Za-z0-9_-]", "_", intent)[:40]
        note_path = nesthub_dir / f"{date_str}-{time_str}-{safe_intent}.md"

        content = (
            f"---\n"
            f"title: \"{date_str} {intent}\"\n"
            f"date: {date_str}\n"
            f"tags: [{tags_yaml}]\n"
            f"intent: {intent}\n"
            f"domain: {domain}{extra_lines}\n"
            f"---\n\n"
            f"## Request\n\n{text}\n\n"
            f"## Intent Analysis\n\n"
            f"- **Intent**: `{intent}`\n"
            f"- **Domain**: `{domain}`\n"
            f"- **Recorded**: {ts.isoformat()}\n"
        )
        try:
            note_path.write_text(content, encoding="utf-8")
            # Invalidate index cache so next search sees the new note
            self._indexed = False
            LOGGER.debug("obsidian_memory: recorded interaction → %s", note_path)
            return note_path
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Lightweight database helpers (structured frontmatter queries)
    # ------------------------------------------------------------------

    def query_by_tag(self, tag: str) -> list[ObsidianNote]:
        """Return all indexed notes that carry a specific tag."""
        if not self._indexed:
            self.index_vault()
        return [n for n in self._notes if tag in n.tags]

    def query_by_intent(self, intent: str) -> list[ObsidianNote]:
        """Return all indexed notes whose ``intent`` frontmatter matches."""
        if not self._indexed:
            self.index_vault()
        return [n for n in self._notes if n.intent == intent]

    def stats(self) -> dict[str, Any]:
        """Return vault statistics (useful for the semantic-memory dashboard)."""
        if not self._indexed:
            self.index_vault()
        intents: dict[str, int] = {}
        domains: dict[str, int] = {}
        for note in self._notes:
            if note.intent:
                intents[note.intent] = intents.get(note.intent, 0) + 1
            if note.domain:
                domains[note.domain] = domains.get(note.domain, 0) + 1
        return {
            "vault_path": str(self.vault_path) if self.vault_path else None,
            "total_notes": len(self._notes),
            "intent_distribution": intents,
            "domain_distribution": domains,
            "is_configured": self.is_configured,
            "auto_record": self.auto_record,
        }
