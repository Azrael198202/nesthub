"""PlannerAgent — converts a raw task into an executable workflow plan.

Responsibility
--------------
PlannerAgent sits between intent recognition and execution.  Given a
:class:`~nethub_runtime.core.schemas.task_schema.TaskSchema` (or equivalent
dict), it:

1. Calls :class:`~nethub_runtime.core.services.task_decomposer.TaskDecomposer`
   to split the task into ordered sub-tasks.
2. Passes the sub-tasks through the
   :class:`~nethub_runtime.core.services.workflow_planner.WorkflowPlanner`
   plugin chain, which selects the highest-priority matching plugin to generate
   a :class:`~nethub_runtime.core.schemas.workflow_schema.WorkflowSchema`.
3. Returns the resulting plan dict so that
   :class:`~nethub_runtime.agents.executor.executor_agent.ExecutorAgent` (or
   :class:`~nethub_runtime.core.services.execution_coordinator.ExecutionCoordinator`
   directly) can execute it.

Usage example::

    planner = PlannerAgent.create()
    result = planner.invoke(task.model_dump(), context.model_dump())
    workflow_schema = result["output"]   # WorkflowSchema serialised to dict

Integration with AICore
-----------------------
:class:`~nethub_runtime.core.services.core_engine.AICore` does *not* use
PlannerAgent directly — it wires the individual services.  PlannerAgent is
exposed as a standalone facade so external code and tests can drive the
planning phase in isolation.
"""

from __future__ import annotations

import logging
from typing import Any

from nethub_runtime.agents.base.base_agent import BaseAgent
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.services.task_decomposer import TaskDecomposer
from nethub_runtime.core.services.workflow_planner import WorkflowPlanner
from nethub_runtime.core.utils.id_generator import generate_id

LOGGER = logging.getLogger("nethub_runtime.agents.planner")


class PlannerAgent(BaseAgent):
    """Agent responsible for decomposing a task and selecting a workflow plan.

    Attributes
    ----------
    task_decomposer:
        Splits a :class:`TaskSchema` into a list of
        :class:`~nethub_runtime.core.schemas.task_schema.SubTask` objects.
    workflow_planner:
        Runs the priority-sorted plugin chain to produce a
        :class:`~nethub_runtime.core.schemas.workflow_schema.WorkflowSchema`.
    """

    def __init__(
        self,
        agent_id: str,
        task_decomposer: TaskDecomposer,
        workflow_planner: WorkflowPlanner,
    ) -> None:
        """Create a PlannerAgent with pre-built collaborators.

        Prefer :py:meth:`create` for convenience construction.

        Parameters
        ----------
        agent_id:
            Unique identifier for this instance.
        task_decomposer:
            Pre-initialised :class:`TaskDecomposer`.
        workflow_planner:
            Pre-initialised :class:`WorkflowPlanner` (holds the plugin chain).
        """
        super().__init__(agent_id=agent_id, name="planner_agent")
        self.task_decomposer = task_decomposer
        self.workflow_planner = workflow_planner

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, agent_id: str | None = None) -> "PlannerAgent":
        """Construct a PlannerAgent with default collaborators.

        Parameters
        ----------
        agent_id:
            Optional stable ID.  A random ID is generated when omitted.

        Returns
        -------
        PlannerAgent
            Ready-to-use agent with a fresh TaskDecomposer and WorkflowPlanner.
        """
        return cls(
            agent_id=agent_id or generate_id("planner"),
            task_decomposer=TaskDecomposer(),
            workflow_planner=WorkflowPlanner(),
        )

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Decompose *task* and generate a workflow plan.

        Parameters
        ----------
        task:
            Serialised :class:`TaskSchema` or plain dict with at least the
            keys ``task_id``, ``intent``, and ``input_text``.
        context:
            Serialised :class:`CoreContextSchema` or plain dict with at least
            ``session_id`` and ``trace_id``.

        Returns
        -------
        dict[str, Any]
            On success::

                {
                    "status": "completed",
                    "agent_id": "<planner_agent_id>",
                    "output": {               # WorkflowSchema serialised to dict
                        "workflow_id": "...",
                        "steps": [...],
                        ...
                    },
                    "subtask_count": <int>,
                }

            On failure::

                {
                    "status": "error",
                    "agent_id": "...",
                    "output": None,
                    "error": "<message>",
                }
        """
        # --- 1. Validate / coerce inputs -----------------------------------
        try:
            task_schema = TaskSchema(**task) if not isinstance(task, TaskSchema) else task
            ctx_schema = (
                CoreContextSchema(**context)
                if not isinstance(context, CoreContextSchema)
                else context
            )
        except Exception as exc:
            return self._error(f"Invalid task or context: {exc}")

        # --- 2. Decompose task into sub-tasks --------------------------------
        try:
            sub_tasks = self.task_decomposer.decompose(task_schema)
        except Exception as exc:
            LOGGER.warning("TaskDecomposer failed for task %s: %s", task_schema.task_id, exc)
            return self._error(f"Task decomposition failed: {exc}", task_id=task_schema.task_id)

        LOGGER.debug(
            "PlannerAgent %s: task %s decomposed into %d sub-task(s)",
            self.agent_id,
            task_schema.task_id,
            len(sub_tasks),
        )

        # --- 3. Select and run the best-matching workflow planner plugin ------
        try:
            workflow_schema = self.workflow_planner.plan(task_schema, ctx_schema)
        except Exception as exc:
            LOGGER.warning(
                "WorkflowPlanner failed for task %s: %s", task_schema.task_id, exc
            )
            return self._error(
                f"Workflow planning failed: {exc}",
                task_id=task_schema.task_id,
                subtask_count=len(sub_tasks),
            )

        LOGGER.info(
            "PlannerAgent %s: plan ready — %d workflow step(s) for task %s",
            self.agent_id,
            len(workflow_schema.steps),
            task_schema.task_id,
        )

        return self._ok(
            workflow_schema.model_dump(),
            subtask_count=len(sub_tasks),
            step_count=len(workflow_schema.steps),
            task_id=task_schema.task_id,
        )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def plan_only(
        self, task: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return the raw WorkflowSchema dict or ``None`` on failure.

        Thin wrapper around :py:meth:`invoke` for callers that only care about
        the plan and want to handle errors themselves.

        Parameters
        ----------
        task:
            Task dict.
        context:
            Context dict.

        Returns
        -------
        dict[str, Any] | None
            The ``"output"`` value from the result dict, or ``None`` if the
            agent reported an error.
        """
        result = self.invoke(task, context)
        if result.get("status") == "completed":
            return result.get("output")
        LOGGER.warning(
            "PlannerAgent.plan_only failed: %s", result.get("error", "unknown error")
        )
        return None
