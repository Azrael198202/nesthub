"""Base agent abstraction for NestHub.

All agent types (PlannerAgent, ExecutorAgent, etc.) inherit from BaseAgent.
It enforces a common lifecycle: initialize → run → teardown, and provides
shared utilities for logging and result structuring.

Design notes
------------
- Agents are stateless between invocations; transient state lives in the
  ``context`` dict that is passed to every ``run()`` call.
- ``run()`` is the only *required* override.  Pre- and post-hooks are optional
  and intended for cross-cutting concerns (metrics, audit logging, etc.).
- ``step()`` exposes a single-step interface for agents that need to be driven
  externally (e.g., by a LangGraph node).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any


class BaseAgent(ABC):
    """Abstract base class for all NestHub agents.

    Subclasses must implement :py:meth:`run`.  Optionally they may override
    :py:meth:`before_run` and :py:meth:`after_run` for setup / teardown work.

    Attributes
    ----------
    agent_id:
        Stable string identifier for this agent instance (set by the subclass
        or generated at construction time).
    name:
        Human-readable display name used in logs and progress reports.
    logger:
        Scoped ``logging.Logger`` instance pre-configured with the agent name.
    """

    # -------------------------------------------------------------------
    # Construction
    # -------------------------------------------------------------------

    def __init__(self, agent_id: str, name: str) -> None:
        """Create a new BaseAgent.

        Parameters
        ----------
        agent_id:
            Unique identifier for this agent instance.
        name:
            Human-readable label shown in logs and UI progress cards.
        """
        self.agent_id = agent_id
        self.name = name
        self.logger = logging.getLogger(f"nethub_runtime.agents.{name}")

    # -------------------------------------------------------------------
    # Lifecycle hooks (optional overrides)
    # -------------------------------------------------------------------

    def before_run(self, context: dict[str, Any]) -> None:
        """Called immediately before :py:meth:`run`.

        Override to perform per-invocation setup (e.g., validate context keys,
        open resources).  The default implementation is a no-op.

        Parameters
        ----------
        context:
            Execution context forwarded unchanged to ``run()``.
        """

    def after_run(self, result: dict[str, Any], context: dict[str, Any]) -> None:
        """Called immediately after :py:meth:`run` returns.

        Override for audit logging, metric emission, or result post-processing.
        Mutations to *result* here will be visible to the caller.  The default
        implementation is a no-op.

        Parameters
        ----------
        result:
            The dict returned by ``run()``.
        context:
            The same context dict passed into ``run()``.
        """

    # -------------------------------------------------------------------
    # Core interface
    # -------------------------------------------------------------------

    @abstractmethod
    def run(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent's primary responsibility.

        This is the single method every concrete agent *must* implement.

        Parameters
        ----------
        task:
            Serialised :class:`~nethub_runtime.core.schemas.task_schema.TaskSchema`
            or an equivalent plain dict describing the work to be done.
        context:
            Runtime context (``session_id``, ``trace_id``, ``metadata``, …)
            as produced by :class:`~nethub_runtime.core.schemas.context_schema.CoreContextSchema`.

        Returns
        -------
        dict[str, Any]
            A result dict that *must* include at least:

            - ``"status"`` – ``"completed"`` | ``"error"`` | ``"partial"``
            - ``"agent_id"`` – echoes back :py:attr:`agent_id`
            - ``"output"`` – the primary payload (type depends on the subclass)
        """

    def step(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
        step_index: int = 0,
    ) -> dict[str, Any]:
        """Execute a single step within a multi-step agent loop.

        The default implementation delegates to :py:meth:`run` and is suitable
        for single-shot agents.  Multi-step agents (e.g., ReAct loops) should
        override this to execute only *one* reasoning/action cycle and expose
        internal state so an external driver (LangGraph node) can decide
        whether to continue.

        Parameters
        ----------
        task:
            Task description forwarded to ``run()``.
        context:
            Execution context forwarded to ``run()``.
        step_index:
            Zero-based index of the current step inside the outer loop.

        Returns
        -------
        dict[str, Any]
            Same shape as ``run()``, with an additional ``"step_index"`` key.
        """
        result = self.run(task, context)
        result["step_index"] = step_index
        return result

    # -------------------------------------------------------------------
    # Convenience wrapper that manages lifecycle hooks and timing
    # -------------------------------------------------------------------

    def invoke(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Run the full agent lifecycle: before_run → run → after_run.

        This is the preferred entry-point for callers that want hook support
        and built-in elapsed-time tracking.

        Parameters
        ----------
        task:
            Task description.
        context:
            Execution context.

        Returns
        -------
        dict[str, Any]
            Result dict from ``run()``, augmented with:

            - ``"agent_id"`` (always present)
            - ``"elapsed_ms"`` (wall-clock time of the ``run()`` call in ms)
        """
        self.before_run(context)
        t0 = time.monotonic()
        try:
            result = self.run(task, context)
        except Exception as exc:
            self.logger.error("Agent %s failed: %s", self.agent_id, exc, exc_info=True)
            result = {
                "status": "error",
                "agent_id": self.agent_id,
                "output": None,
                "error": str(exc),
            }
        elapsed_ms = round((time.monotonic() - t0) * 1000)
        result.setdefault("agent_id", self.agent_id)
        result["elapsed_ms"] = elapsed_ms
        self.after_run(result, context)
        return result

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _ok(self, output: Any, **extra: Any) -> dict[str, Any]:
        """Build a successful result dict.

        Parameters
        ----------
        output:
            The primary result payload.
        **extra:
            Any additional key/value pairs merged into the result dict.

        Returns
        -------
        dict[str, Any]
            ``{"status": "completed", "agent_id": ..., "output": ..., **extra}``
        """
        return {"status": "completed", "agent_id": self.agent_id, "output": output, **extra}

    def _error(self, message: str, **extra: Any) -> dict[str, Any]:
        """Build an error result dict.

        Parameters
        ----------
        message:
            Human-readable description of what went wrong.
        **extra:
            Additional context (e.g., ``exception_type``, ``step_name``).

        Returns
        -------
        dict[str, Any]
            ``{"status": "error", "agent_id": ..., "output": None, "error": message, **extra}``
        """
        return {
            "status": "error",
            "agent_id": self.agent_id,
            "output": None,
            "error": message,
            **extra,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(agent_id={self.agent_id!r}, name={self.name!r})"
