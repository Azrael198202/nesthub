"""
Hook Registry — pre/post step interception points.

Inspired by claude-agent-sdk-python's hook mechanism:
  hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[fn])]}

Usage::

    from nethub_runtime.core.hooks import get_hook_registry, HookContext

    registry = get_hook_registry()

    # Run on every step before execution
    registry.register("pre_step", my_guard_fn)

    # Run only before "image_generate" steps
    registry.register("pre_step", image_guard_fn, matcher="image_generate")

    # Run after every step (receives output)
    registry.register("post_step", my_logger_fn)

Hook function signature::

    def my_fn(ctx: HookContext) -> dict | None:
        # returning {"deny": True, "reason": "..."} from pre_step blocks the step
        # returning None passes through silently
        ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

LOGGER = logging.getLogger("nethub_runtime.core.hooks")

# A hook callable receives HookContext and may return a dict or None.
# For pre_step: returning {"deny": True, "reason": "..."} blocks the step.
HookFn = Callable[["HookContext"], dict[str, Any] | None]


@dataclass
class HookContext:
    """Contextual data passed to every hook function."""

    event: str                           # "pre_step" | "post_step"
    step_name: str
    step: dict[str, Any]
    task_intent: str
    session_id: str
    output: dict[str, Any] | None = None  # populated for post_step only
    metadata: dict[str, Any] = field(default_factory=dict)


class HookRegistry:
    """
    Registry for pre/post step hooks.

    Hooks are matched by event name and an optional step-name matcher.
    Multiple hooks can be registered for the same event — they are run
    in registration order.  The first hook that returns a non-None value
    short-circuits the remaining hooks for that event.
    """

    def __init__(self) -> None:
        # event -> list of (matcher, fn)
        self._hooks: dict[str, list[tuple[str | None, HookFn]]] = {}

    def register(
        self,
        event: str,
        fn: HookFn,
        *,
        matcher: str | None = None,
    ) -> None:
        """Register a hook function.

        Args:
            event:   "pre_step" or "post_step"
            fn:      Hook callable — (HookContext) -> dict | None
            matcher: Optional step name filter.  When set, the hook only
                     fires when ``ctx.step_name == matcher``.
        """
        self._hooks.setdefault(event, []).append((matcher, fn))
        LOGGER.debug(
            "Hook registered: event=%s matcher=%s fn=%s",
            event,
            matcher or "*",
            getattr(fn, "__name__", repr(fn)),
        )

    def run(self, event: str, ctx: HookContext) -> dict[str, Any] | None:
        """Run all matching hooks for *event* with *ctx*.

        Returns the first non-None result; returns None when all hooks
        pass through.
        """
        for matcher, fn in self._hooks.get(event, []):
            if matcher is not None and ctx.step_name != matcher:
                continue
            try:
                result = fn(ctx)
                if result is not None:
                    return result
            except Exception as exc:  # pragma: no cover
                LOGGER.warning(
                    "Hook %s raised an error: %s",
                    getattr(fn, "__name__", repr(fn)),
                    exc,
                )
        return None

    def list_hooks(self) -> dict[str, list[dict[str, Any]]]:
        """Return a summary of all registered hooks (useful for diagnostics)."""
        return {
            event: [
                {"matcher": m or "*", "fn": getattr(fn, "__name__", repr(fn))}
                for m, fn in entries
            ]
            for event, entries in self._hooks.items()
        }


# Module-level singleton shared across the process.
_global_hook_registry = HookRegistry()


def get_hook_registry() -> HookRegistry:
    """Return the global HookRegistry singleton."""
    return _global_hook_registry
