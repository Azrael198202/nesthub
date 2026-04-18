"""
Tool Registry - Manages available tools and capabilities.
Reference: docs/03_workflow/langgraph_agent_framework.md
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import logging
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Any, Optional, Callable
from abc import ABC, abstractmethod

LOGGER = logging.getLogger("nethub_runtime.core.tools")

# ---------------------------------------------------------------------------
# Skill decorator & directory-based loading
#
# Inspired by OpenClaw's tiered skill loading:
#   workspace > project > personal > managed > bundled
#
# Skills can be registered programmatically via @skill or discovered from
# SKILL.md files in configured directories.  Directory-loaded skills have
# lower priority than code-registered skills.
#
# Usage::
#
#     @skill("web_search", "Search the web", supported_intents=["web_research_task"])
#     async def web_search(args: dict) -> dict:
#         ...
#
#     # Load from directories (e.g. at startup):
#     load_skills_from_dirs([
#         {"path": "~/.nesthub/workspace/skills", "source": "workspace", "priority": 1},
#         {"path": "~/.agents/skills", "source": "personal", "priority": 3},
#     ])
# ---------------------------------------------------------------------------

# source priority constants (lower number = higher precedence)
SKILL_SOURCE_WORKSPACE = 1
SKILL_SOURCE_PROJECT   = 2
SKILL_SOURCE_PERSONAL  = 3
SKILL_SOURCE_MANAGED   = 4
SKILL_SOURCE_BUNDLED   = 5
SKILL_SOURCE_CODE      = 0   # @skill decorator — always wins

_skill_registry: dict[str, dict[str, Any]] = {}


def skill(
    name: str,
    description: str,
    *,
    supported_intents: list[str] | None = None,
    input_schema: dict[str, Any] | None = None,
) -> Callable:
    """Decorator that registers a plain async function as a named skill.

    Args:
        name:              Unique skill identifier (matches step names for routing).
        description:       Human-readable description of what the skill does.
        supported_intents: List of task intent strings this skill handles.
                           CapabilityRouter uses this to annotate routed steps.
        input_schema:      Optional dict describing expected input keys.
    """
    def decorator(fn: Callable) -> Callable:
        _skill_registry[name] = {
            "name": name,
            "description": description,
            "supported_intents": supported_intents or [],
            "input_schema": input_schema or {},
            "fn": fn,
            "source": "code",
            "priority": SKILL_SOURCE_CODE,
        }
        LOGGER.debug("Skill registered via @skill: %s", name)
        return fn
    return decorator


def register_skill(entry: dict[str, Any]) -> None:
    """Register a skill dict (e.g. loaded from a SKILL.md file).

    Only registers if:
    - The name is new, OR
    - The incoming entry has lower ``priority`` number (higher precedence).
    """
    name = entry.get("name", "").strip()
    if not name:
        return
    existing = _skill_registry.get(name)
    incoming_priority = int(entry.get("priority", SKILL_SOURCE_BUNDLED))
    if existing is None or incoming_priority < int(existing.get("priority", SKILL_SOURCE_BUNDLED)):
        _skill_registry[name] = {**entry, "priority": incoming_priority}
        LOGGER.debug(
            "Skill registered: %s (source=%s priority=%d)",
            name, entry.get("source", "?"), incoming_priority,
        )


def load_skills_from_dirs(
    dirs: list[dict[str, Any]],
    *,
    workspace_path: str | Path | None = None,
) -> int:
    """Scan skill directories (highest precedence first) and register any
    ``SKILL.md`` files found as discoverable skills.

    Each directory entry is a dict with keys:
        path     — filesystem path (supports ~ and {workspace} placeholder)
        source   — human label (workspace / project / personal / managed / bundled)
        priority — lower = higher precedence (see SKILL_SOURCE_* constants)

    Args:
        dirs:            List of dir descriptors from ``runtime_behavior.skill_dirs``.
        workspace_path:  Value to substitute for ``{workspace}`` in paths.

    Returns:
        Number of new skills registered.
    """
    workspace_str = str(workspace_path or os.path.expanduser("~/.nesthub/workspace"))
    # Sort highest precedence first so register_skill's priority guard works.
    sorted_dirs = sorted(dirs, key=lambda d: int(d.get("priority", SKILL_SOURCE_BUNDLED)))
    registered = 0
    for dir_entry in sorted_dirs:
        raw_path = str(dir_entry.get("path", "")).replace("{workspace}", workspace_str)
        resolved = Path(os.path.expandvars(os.path.expanduser(raw_path)))
        source = str(dir_entry.get("source", "unknown"))
        priority = int(dir_entry.get("priority", SKILL_SOURCE_BUNDLED))
        if not resolved.is_dir():
            LOGGER.debug("Skill dir not found, skipping: %s", resolved)
            continue
        for skill_file in sorted(resolved.glob("*.md")):
            entry = _parse_skill_md(skill_file, source=source, priority=priority)
            if entry:
                prev_count = len(_skill_registry)
                register_skill(entry)
                if len(_skill_registry) > prev_count:
                    registered += 1
    if registered:
        LOGGER.info("Skills loaded from dirs: %d new skill(s) registered", registered)
    return registered


def _parse_skill_md(path: Path, *, source: str, priority: int) -> dict[str, Any] | None:
    """Extract skill metadata from a SKILL.md file.

    Expected minimal format (YAML front-matter or first heading)::

        # skill_name
        Description: one-line description
        Intents: intent_a, intent_b

    Returns None when the file cannot be meaningfully parsed.
    """
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not text:
        return None

    name = path.stem.lower().replace(" ", "_").replace("-", "_")
    description = ""
    supported_intents: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not description:
            # Use first H1 as skill name if it looks like an identifier
            candidate = stripped[2:].strip().lower().replace(" ", "_")
            if candidate:
                name = candidate
        elif stripped.lower().startswith("description:"):
            description = stripped.split(":", 1)[-1].strip()
        elif stripped.lower().startswith("intents:"):
            raw = stripped.split(":", 1)[-1].strip()
            supported_intents = [i.strip() for i in raw.split(",") if i.strip()]

    return {
        "name": name,
        "description": description or f"Skill loaded from {path.name}",
        "supported_intents": supported_intents,
        "input_schema": {},
        "fn": None,
        "source": source,
        "priority": priority,
        "skill_file": str(path),
    }


def list_skills() -> list[dict[str, Any]]:
    """Return all registered skills sorted by priority (highest first).

    Callable ``fn`` is excluded for serialisability.
    """
    skills = [{k: v for k, v in s.items() if k != "fn"} for s in _skill_registry.values()]
    return sorted(skills, key=lambda s: int(s.get("priority", SKILL_SOURCE_BUNDLED)))


def get_skill(name: str) -> dict[str, Any] | None:
    """Look up a registered skill by name. Returns None if not found."""
    return _skill_registry.get(name)


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self, name: str, description: str):
        """
        初始化工具
        
        Args:
            name: 工具名称
            description: 工具描述
        """
        self.name = name
        self.description = description
    
    @abstractmethod
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """
        执行工具
        
        Args:
            input_data: 输入数据
        
        Returns:
            执行结果
        """
        pass
    
    def get_schema(self) -> dict[str, Any]:
        """获取工具schema（用于Agent调用）"""
        return {
            "name": self.name,
            "description": self.description,
            "type": "tool",
        }


class ToolRegistry:
    """
    工具注册表
    
    管理所有可用的工具和能力，支持：
    - 注册/注销工具
    - 按名称查询工具
    - 列出所有工具
    """
    
    def __init__(self):
        """初始化工具注册表"""
        self.tools: dict[str, BaseTool] = {}
        LOGGER.info("✓ Tool Registry initialized")
    
    def register(self, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self.tools[tool.name] = tool
        LOGGER.debug(f"  Tool registered: {tool.name}")
    
    def unregister(self, name: str) -> None:
        """
        注销工具
        
        Args:
            name: 工具名称
        """
        if name in self.tools:
            del self.tools[name]
            LOGGER.debug(f"  Tool unregistered: {name}")
        else:
            LOGGER.warning(f"Tool not found: {name}")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
        
        Returns:
            工具实例，如果未找到则返回 None
        """
        return self.tools.get(name)
    
    def list_all(self) -> list[str]:
        """
        列出所有工具名称
        
        Returns:
            工具名称列表
        """
        return list(self.tools.keys())
    
    def list_with_schemas(self) -> list[dict[str, Any]]:
        """
        列出所有工具的 schema
        
        Returns:
            工具 schema 列表
        """
        return [tool.get_schema() for tool in self.tools.values()]
    
    async def execute(self, tool_name: str, input_data: dict[str, Any]) -> Any:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            input_data: 输入数据
        
        Returns:
            执行结果
        """
        tool = self.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        try:
            result = await tool.execute(input_data)
            return result
        except Exception as e:
            LOGGER.error(f"Tool execution failed: {tool_name}, error: {e}")
            raise


# ========== 内置工具示例 ==========

class WebSearchTool(BaseTool):
    """Web搜索工具"""
    
    def __init__(self):
        super().__init__("web_search", "Search the web for information")
    
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """Execute a web search using the DuckDuckGo Instant Answer API (no key needed)."""
        query = input_data.get("query", "")
        max_results = int(input_data.get("max_results", 5))
        LOGGER.debug("Executing web search: %s", query)
        if not query:
            return {"success": False, "error": "query is required"}
        try:
            # DuckDuckGo Instant Answer JSON API — free, no key
            params = urllib.parse.urlencode({"q": query, "format": "json", "no_redirect": 1})
            url = f"https://api.duckduckgo.com/?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "nesthub-runtime/1.0"})
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, timeout=10).read().decode(),
            )
            import json as _json
            data = _json.loads(raw)
            results: list[dict[str, Any]] = []
            # Abstract (best single answer)
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", query),
                    "snippet": data["Abstract"],
                    "url": data.get("AbstractURL", ""),
                    "source": "abstract",
                })
            # Related topics
            for topic in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("Text", "")[:80],
                        "snippet": topic.get("Text", ""),
                        "url": topic.get("FirstURL", ""),
                        "source": "related",
                    })
            return {"success": True, "query": query, "results": results[:max_results]}
        except Exception as exc:
            LOGGER.warning("web_search failed: %s", exc)
            return {"success": False, "error": str(exc), "results": []}


class FileSystemTool(BaseTool):
    """文件系统工具"""
    
    def __init__(self):
        super().__init__("filesystem", "Access file system operations")
    
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """Execute filesystem operations: read / write / list / exists / delete.

        Accepted operations and required fields:
          - read:   path
          - write:  path, content
          - list:   path  (directory listing)
          - exists: path
          - delete: path  (files only; no recursive delete for safety)
        """
        operation = str(input_data.get("operation", "")).lower()
        raw_path = input_data.get("path", "")
        LOGGER.debug("Executing filesystem operation=%s path=%s", operation, raw_path)

        if not raw_path:
            return {"success": False, "error": "path is required"}

        path = Path(os.path.expandvars(os.path.expanduser(str(raw_path))))

        try:
            if operation == "read":
                if not path.is_file():
                    return {"success": False, "error": f"not a file: {path}"}
                content = path.read_text(encoding="utf-8", errors="replace")
                return {"success": True, "path": str(path), "content": content, "size": len(content)}

            elif operation == "write":
                content = str(input_data.get("content", ""))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                return {"success": True, "path": str(path), "bytes_written": len(content.encode())}

            elif operation == "list":
                if not path.is_dir():
                    return {"success": False, "error": f"not a directory: {path}"}
                entries = [
                    {"name": e.name, "type": "dir" if e.is_dir() else "file",
                     "size": e.stat().st_size if e.is_file() else None}
                    for e in sorted(path.iterdir())
                ]
                return {"success": True, "path": str(path), "entries": entries}

            elif operation == "exists":
                return {"success": True, "path": str(path), "exists": path.exists(),
                        "is_file": path.is_file(), "is_dir": path.is_dir()}

            elif operation == "delete":
                if not path.exists():
                    return {"success": False, "error": f"not found: {path}"}
                if path.is_dir():
                    return {"success": False, "error": "delete of directories is not supported"}
                path.unlink()
                return {"success": True, "path": str(path), "deleted": True}

            else:
                return {"success": False, "error": f"unknown operation: {operation}"}

        except PermissionError as exc:
            return {"success": False, "error": f"permission denied: {exc}"}
        except Exception as exc:
            LOGGER.warning("filesystem tool error: %s", exc)
            return {"success": False, "error": str(exc)}


class ShellExecutionTool(BaseTool):
    """Shell执行工具"""
    
    def __init__(self):
        super().__init__("shell", "Execute shell commands")
    
    # Commands that are explicitly allowed for execution (security allowlist)
    _ALLOWED_COMMANDS: frozenset[str] = frozenset({
        "ls", "cat", "echo", "pwd", "date", "whoami", "uname",
        "python", "python3", "pip", "pip3", "git", "curl", "wget",
        "find", "grep", "wc", "head", "tail", "sort", "uniq",
    })

    async def execute(self, input_data: dict[str, Any]) -> Any:
        """Execute a shell command from a security allowlist.

        Accepted fields:
          command  — the shell command string
          timeout  — seconds before killing (default 30)
          cwd      — working directory (default None = caller's cwd)
        """
        command = str(input_data.get("command", "")).strip()
        timeout = int(input_data.get("timeout", 30))
        cwd = input_data.get("cwd") or None
        LOGGER.debug("Executing shell command: %s", command[:120])

        if not command:
            return {"success": False, "error": "command is required"}

        # Security: only allow commands whose first token is in the allowlist
        first_token = command.split()[0].split("/")[-1]  # strip path prefix
        if first_token not in self._ALLOWED_COMMANDS:
            LOGGER.warning("shell tool: rejected non-allowlisted command '%s'", first_token)
            return {"success": False, "error": f"command '{first_token}' is not in the allowed list"}

        try:
            loop = asyncio.get_event_loop()
            proc = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    command, shell=True, capture_output=True, text=True,
                    timeout=timeout, cwd=cwd,
                ),
            )
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"command timed out after {timeout}s"}
        except Exception as exc:
            LOGGER.warning("shell tool error: %s", exc)
            return {"success": False, "error": str(exc)}


class CodeExecutionTool(BaseTool):
    """代码执行工具"""
    
    def __init__(self):
        super().__init__("code_execution", "Execute Python code")
    
    async def execute(self, input_data: dict[str, Any]) -> Any:
        """Execute Python code in an isolated namespace with captured stdout/stderr.

        Accepted fields:
          code     — Python source string to execute
          timeout  — seconds before aborting (default 10)

        The executed code may define variables; their values are returned under
        ``locals`` if they are JSON-serialisable.  ``print()`` output is
        captured under ``stdout``.
        """
        code = str(input_data.get("code", ""))
        timeout = int(input_data.get("timeout", 10))
        LOGGER.debug("Executing code (%d chars)", len(code))

        if not code.strip():
            return {"success": False, "error": "code is required"}

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        namespace: dict[str, Any] = {"__builtins__": __builtins__}

        try:
            loop = asyncio.get_event_loop()

            def _run() -> None:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    exec(compile(code, "<nesthub_tool>", "exec"), namespace)  # noqa: S102

            await asyncio.wait_for(loop.run_in_executor(None, _run), timeout=timeout)

            # Collect serialisable locals (exclude builtins and private)
            safe_locals: dict[str, Any] = {}
            for k, v in namespace.items():
                if k.startswith("_"):
                    continue
                try:
                    import json as _json
                    _json.dumps(v)
                    safe_locals[k] = v
                except (TypeError, ValueError):
                    safe_locals[k] = repr(v)

            return {
                "success": True,
                "stdout": stdout_buf.getvalue(),
                "stderr": stderr_buf.getvalue(),
                "locals": safe_locals,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": f"code execution timed out after {timeout}s"}
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "stdout": stdout_buf.getvalue(),
                "stderr": stderr_buf.getvalue(),
            }
