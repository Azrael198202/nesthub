"""
Bootstrap Loader — injects workspace identity files into agent context.

Inspired by OpenClaw's bootstrap file system:
  AGENTS.md  — operating instructions + memory
  SOUL.md    — persona, tone, boundaries
  TOOLS.md   — user-maintained tool notes
  IDENTITY.md — agent name / vibe
  USER.md    — user profile

On the first turn of every new session, the loader reads these files from
``workspace_path``, trims each to ``max_tokens_per_file`` rough characters,
and assembles a single system-context string that callers prepend to their
system prompt.

Usage::

    loader = BootstrapLoader.from_policy()
    context = loader.load()          # returns assembled string or ""
    # then prepend context to your system prompt before the first LLM call
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("nethub_runtime.core.bootstrap")

_DEFAULT_FILES = ["AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md", "USER.md"]
_DEFAULT_WORKSPACE = "~/.nesthub/workspace"
_DEFAULT_MAX_CHARS = 8000   # ~2000 tokens × 4 chars/token


class BootstrapLoader:
    """Loads workspace bootstrap files and assembles a system-context string.

    Args:
        workspace_path:   Directory that contains the bootstrap files.
        files:            Ordered list of filenames to attempt loading.
        max_chars_each:   Maximum character length per file (hard trim with marker).
        skip_missing:     When True, silently skip absent files; when False,
                          inject a ``[MISSING: filename]`` placeholder.
    """

    def __init__(
        self,
        workspace_path: str | Path = _DEFAULT_WORKSPACE,
        files: list[str] | None = None,
        max_chars_each: int = _DEFAULT_MAX_CHARS,
        skip_missing: bool = True,
    ) -> None:
        self.workspace_path = Path(os.path.expanduser(str(workspace_path)))
        self.files = files or list(_DEFAULT_FILES)
        self.max_chars_each = max_chars_each
        self.skip_missing = skip_missing

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_policy(cls, policy: dict[str, Any] | None = None) -> "BootstrapLoader":
        """Build a ``BootstrapLoader`` from a ``runtime_behavior.bootstrap``
        policy dict (as stored in ``semantic_policy.json``).

        Falls back to defaults when *policy* is None or partially specified.
        """
        cfg = policy or {}
        workspace = cfg.get("workspace_path", _DEFAULT_WORKSPACE)
        # Allow {workspace} template in paths elsewhere, but here the
        # workspace_path IS the root, so expand ~ and env vars only.
        workspace = os.path.expandvars(str(workspace))
        files = cfg.get("files") or list(_DEFAULT_FILES)
        max_tokens = int(cfg.get("max_tokens_per_file", 2000))
        max_chars = max_tokens * 4   # rough 1 token ≈ 4 chars
        skip_missing = bool(cfg.get("skip_missing", True))
        return cls(
            workspace_path=workspace,
            files=files,
            max_chars_each=max_chars,
            skip_missing=skip_missing,
        )

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def load(self) -> str:
        """Read and assemble all bootstrap files into a single context block.

        Returns an empty string when the workspace does not exist or is empty.
        """
        if not self.workspace_path.is_dir():
            LOGGER.debug("Bootstrap workspace not found: %s", self.workspace_path)
            return ""

        sections: list[str] = []
        for filename in self.files:
            file_path = self.workspace_path / filename
            content = self._read_file(file_path, filename)
            if content is not None:
                sections.append(f"## {filename}\n{content}")

        if not sections:
            return ""

        assembled = "\n\n".join(sections)
        LOGGER.info(
            "Bootstrap loaded: %d file(s) from %s (%d chars)",
            len(sections),
            self.workspace_path,
            len(assembled),
        )
        return assembled

    def load_as_messages(self) -> list[dict[str, str]]:
        """Return bootstrap content as a system-role chat message list.

        Useful when the caller builds an OpenAI-style messages array.
        Returns [] when nothing was loaded.
        """
        content = self.load()
        if not content:
            return []
        return [{"role": "system", "content": f"[Bootstrap Context]\n{content}"}]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _read_file(self, path: Path, filename: str) -> str | None:
        """Read *path*, trimming to ``max_chars_each``.

        Returns the (possibly trimmed) string, or None when the file is
        absent/blank and ``skip_missing`` is True.
        """
        if not path.exists():
            if self.skip_missing:
                return None
            return f"[MISSING: {filename}]"

        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            LOGGER.warning("Failed to read bootstrap file %s: %s", path, exc)
            return None

        if not text:
            return None   # blank file — skip regardless of skip_missing

        if len(text) > self.max_chars_each:
            text = text[: self.max_chars_each] + f"\n\n[... {filename} trimmed at {self.max_chars_each} chars]"

        return text
