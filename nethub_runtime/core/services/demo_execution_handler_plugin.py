from __future__ import annotations

from nethub_runtime.core.services.execution_handler_registry import (
    ExecutionHandlerPluginExecutorSpec,
    ExecutionHandlerPluginManifest,
    ExecutionHandlerPluginRequirement,
    ExecutionHandlerPluginStepSpec,
)


class DemoExecutionHandlerPlugin:
    def build_manifest(self, coordinator) -> ExecutionHandlerPluginManifest:
        return ExecutionHandlerPluginManifest(
            name="demo_execution_handler_plugin",
            version="1.0",
            requirements=[
                ExecutionHandlerPluginRequirement(
                    requirement_type="dispatcher",
                    name="llm",
                    description="Requires the coordinator LLM dispatcher.",
                ),
                ExecutionHandlerPluginRequirement(
                    requirement_type="service",
                    name="information_agent_service",
                    description="Verifies domain services can be surfaced as runtime requirements.",
                    required=False,
                ),
            ],
            executors=[
                ExecutionHandlerPluginExecutorSpec(
                    executor_type="demo_executor",
                    handler=coordinator._dispatch_llm_step,
                    description="Route demo executor steps through the LLM dispatcher.",
                )
            ],
            steps=[
                ExecutionHandlerPluginStepSpec(
                    executor_type="demo_executor",
                    step_name="demo_step",
                    handler=lambda step, task, context, step_outputs: {
                        "message": "demo plugin handler executed",
                        "input_text": task.input_text,
                        "session_id": context.session_id,
                    },
                    description="Simple demo step used by registry plugin tests.",
                )
            ],
        )


def demo_execution_handler_plugin() -> DemoExecutionHandlerPlugin:
    return DemoExecutionHandlerPlugin()