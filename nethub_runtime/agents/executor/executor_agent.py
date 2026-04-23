"""ExecutorAgent — drives the ExecutionCoordinator through a workflow plan.

Responsibility
--------------
ExecutorAgent is the bridge between a *plan* (a ``WorkflowSchema`` serialised
to a dict) and actual step execution.  It:

1. Accepts a ``WorkflowSchema`` dict (typically produced by
   :class:`~nethub_runtime.agents.planner.planner_agent.PlannerAgent`).
2. Delegates execution to
   :class:`~nethub_runtime.core.services.execution_coordinator.ExecutionCoordinator`,
   which runs each step in DAG order, applies pre/post hooks, and updates the
   live progress store.
3. Returns the final aggregated result so the caller (or
   :class:`~nethub_runtime.core.services.core_engine.AICore`) can pass it to
   :class:`~nethub_runtime.core.services.result_integrator.ResultIntegrator`.

Usage example::

    coordinator = ExecutionCoordinator(...)
    executor = ExecutorAgent.create(coordinator)

    plan_result  = planner_agent.invoke(task_dict, ctx_dict)
    exec_result  = executor.invoke(plan_result["output"], ctx_dict)
    final_output = exec_result["output"]   # merged step outputs

Non-blocking execution
----------------------
When called from an ``async`` context (e.g., FastAPI route) the caller should
wrap :py:meth:`run` in ``asyncio.to_thread()`` to avoid blocking the event
loop — exactly as :class:`~nethub_runtime.core.services.core_engine.AICore`
does when handling ``/api/voice/chat`` and ``/api/custom-agents/intake``.
"""

from __future__ import annotations

import logging
from typing import Any

from nethub_runtime.agents.base.base_agent import BaseAgent
from nethub_runtime.core.schemas.context_schema import CoreContextSchema
from nethub_runtime.core.schemas.task_schema import TaskSchema
from nethub_runtime.core.schemas.workflow_schema import WorkflowSchema
from nethub_runtime.core.services.execution_coordinator import ExecutionCoordinator
from nethub_runtime.core.utils.id_generator import generate_id

LOGGER = logging.getLogger("nethub_runtime.agents.executor")


class ExecutorAgent(BaseAgent):
    """Agent that executes a workflow plan step by step.

    Attributes
    ----------
    coordinator:
        The :class:`ExecutionCoordinator` that handles per-step dispatch,
        capability routing, hook firing, and live progress tracking.
    """

    def __init__(self, agent_id: str, coordinator: ExecutionCoordinator) -> None:
        """Create an ExecutorAgent backed by *coordinator*.

        Prefer :py:meth:`create` for convenience construction.

        Parameters
        ----------
        agent_id:
            Unique identifier for this instance.
        coordinator:
            Fully initialised
            :class:`~nethub_runtime.core.services.execution_coordinator.ExecutionCoordinator`.
        """
        super().__init__(agent_id=agent_id, name="executor_agent")
        self.coordinator = coordinator

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        coordinator: ExecutionCoordinator,
        agent_id: str | None = None,
    ) -> "ExecutorAgent":
        """Construct an ExecutorAgent wrapping an existing coordinator.

        Parameters
        ----------
        coordinator:
            Pre-built :class:`ExecutionCoordinator`.
        agent_id:
            Optional stable ID.  A random ID is generated when omitted.

        Returns
        -------
        ExecutorAgent
            Ready-to-use executor agent.
        """
        return cls(
            agent_id=agent_id or generate_id("executor"),
            coordinator=coordinator,
        )

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Execute a workflow plan.

        The method expects *task* to carry a ``"workflow_schema"`` key whose
        value is a :class:`WorkflowSchema` serialised to a dict (as produced
        by :py:meth:`~nethub_runtime.agents.planner.planner_agent.PlannerAgent.run`).
        If that key is absent the entire *task* dict is attempted as the schema
        directly.

        Parameters
        ----------
        task:
            Dict containing at minimum:

            - ``"workflow_schema"`` – serialised ``WorkflowSchema``
            - ``"task_id"``          – forwarded to the coordinator (optional)
            - ``"input_text"``       – original user text (optional)
        context:
            Serialised :class:`CoreContextSchema` or plain dict with at least
            ``session_id`` and ``trace_id``.

        Returns
        -------
        dict[str, Any]
            On success::

                {
                    "status": "completed",
                    "agent_id": "<executor_agent_id>",
                    "output": {               # merged step outputs
                        "final_output": {...},
                        "steps": [...],
                        ...
                    },
                    "step_count": <int>,
                }

            On failure::

                {
                    "status": "error",
                    "agent_id": "...",
                    "output": None,
                    "error": "<message>",
                }
        """
        # --- 1. Extract and validate the workflow schema ---------------------
        raw_schema = task.get("workflow_schema") or task
        try:
            workflow_schema = (
                WorkflowSchema(**raw_schema)
                if not isinstance(raw_schema, WorkflowSchema)
                else raw_schema
            )
        except Exception as exc:
            return self._error(f"Invalid workflow schema: {exc}")

        # --- 2. Coerce the task into a TaskSchema for the coordinator --------
        try:
            task_schema = TaskSchema(
                task_id=str(task.get("task_id") or generate_id("task")),
                intent=str(task.get("intent") or "general"),
                input_text=str(task.get("input_text") or ""),
                domain=str(task.get("domain") or "general"),
                constraints=task.get("constraints") or {},
                output_requirements=task.get("output_requirements") or [],
                metadata=task.get("metadata") or {},
            )
        except Exception as exc:
            return self._error(f"Invalid task for executor: {exc}")

        # --- 3. Coerce context -----------------------------------------------
        try:
            ctx_schema = (
                CoreContextSchema(**context)
                if not isinstance(context, CoreContextSchema)
                else context
            )
        except Exception as exc:
            return self._error(f"Invalid context for executor: {exc}")

        # --- 4. Build an execution plan from the workflow schema -------------
        #
        # ExecutionCoordinator.execute() expects a plain list-of-step dicts
        # (the "execution plan") rather than the WorkflowSchema directly.
        # CapabilityRouter.route_workflow() is the canonical translator, but we
        # keep the agent layer thin and simply serialise the workflow steps.
        try:
            execution_plan = [step.model_dump() for step in workflow_schema.steps]
        except Exception as exc:
            return self._error(f"Failed to serialise workflow steps: {exc}")

        step_count = len(execution_plan)
        LOGGER.info(
            "ExecutorAgent %s: executing %d step(s) for session %s",
            self.agent_id,
            step_count,
            ctx_schema.session_id,
        )

        # --- 5. Delegate to ExecutionCoordinator -----------------------------
        try:
            exec_result: dict[str, Any] = self.coordinator.execute(
                execution_plan, task_schema, ctx_schema
            )
        except Exception as exc:
            LOGGER.error(
                "ExecutorAgent %s: coordinator raised %s", self.agent_id, exc, exc_info=True
            )
            return self._error(f"Execution failed: {exc}", step_count=step_count)

        # --- 6. Surface execution errors as agent errors ---------------------
        coord_status = str(exec_result.get("status") or "")
        if coord_status == "error":
            error_msg = str(exec_result.get("error") or "ExecutionCoordinator reported an error")
            LOGGER.warning(
                "ExecutorAgent %s: execution completed with error — %s",
                self.agent_id,
                error_msg,
            )
            return self._error(error_msg, step_count=step_count, raw_result=exec_result)

        LOGGER.info(
            "ExecutorAgent %s: execution completed — status=%s, steps=%d",
            self.agent_id,
            coord_status or "completed",
            step_count,
        )
        return self._ok(exec_result, step_count=step_count)

    # ------------------------------------------------------------------
    # Step-level interface (for LangGraph node integration)
    # ------------------------------------------------------------------

    def step(
        self,
        task: dict[str, Any],
        context: dict[str, Any],
        step_index: int = 0,
    ) -> dict[str, Any]:
        """Execute a *single* step from the workflow plan.

        Unlike :py:meth:`run` (which drives the whole plan), ``step()``
        executes only the step at position *step_index*.  This allows an
        external LangGraph node to advance the execution one step at a time,
        inspect intermediate results, and decide whether to continue, retry,
        or abort.

        Parameters
        ----------
        task:
            Same shape as in :py:meth:`run`, plus an optional
            ``"step_outputs"`` key carrying results from prior steps.
        context:
            Execution context dict.
        step_index:
            Zero-based index of the step to execute.

        Returns
        -------
        dict[str, Any]
            Result dict with ``"step_index"`` echoed back and
            ``"output"`` containing the single-step result dict.
        """
        raw_schema = task.get("workflow_schema") or task
        try:
            workflow_schema = (
                WorkflowSchema(**raw_schema)
                if not isinstance(raw_schema, WorkflowSchema)
                else raw_schema
            )
        except Exception as exc:
            result = self._error(f"Invalid workflow schema for step {step_index}: {exc}")
            result["step_index"] = step_index
            return result

        steps = workflow_schema.steps
        if step_index >= len(steps):
            result = self._error(
                f"step_index {step_index} out of range (plan has {len(steps)} step(s))"
            )
            result["step_index"] = step_index
            return result

        target_step = steps[step_index].model_dump()

        # Build minimal TaskSchema / CoreContextSchema
        try:
            task_schema = TaskSchema(
                task_id=str(task.get("task_id") or generate_id("task")),
                intent=str(task.get("intent") or "general"),
                input_text=str(task.get("input_text") or ""),
            )
            ctx_schema = (
                CoreContextSchema(**context)
                if not isinstance(context, CoreContextSchema)
                else context
            )
        except Exception as exc:
            result = self._error(f"Invalid task/context for step: {exc}")
            result["step_index"] = step_index
            return result

        prior_outputs: dict[str, Any] = task.get("step_outputs") or {}

        try:
            # ExecutionCoordinator exposes _execute_step for targeted dispatch
            step_result = self.coordinator._execute_step(  # noqa: SLF001
                step=target_step,
                task=task_schema,
                context=ctx_schema,
                step_outputs=prior_outputs,
            )
        except Exception as exc:
            LOGGER.error("ExecutorAgent step %d failed: %s", step_index, exc, exc_info=True)
            result = self._error(f"Step {step_index} execution failed: {exc}")
            result["step_index"] = step_index
            return result

        result = self._ok(step_result, step_index=step_index, step_name=target_step.get("name"))
        result["step_index"] = step_index
        return result
