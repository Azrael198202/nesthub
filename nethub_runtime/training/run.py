from __future__ import annotations

import argparse
import json
from typing import Any

from nethub_runtime.config.runtime_paths import SEMANTIC_POLICY_PATH
from nethub_runtime.core_brain.services.training_fine_tune_runner_service import TrainingFineTuneRunnerService
from nethub_runtime.core_brain.services.training_pipeline_service import TrainingPipelineService
from nethub_runtime.generated.store import GeneratedArtifactStore
from nethub_runtime.memory.semantic_policy_store import SemanticPolicyStore


def build_runner_service() -> TrainingFineTuneRunnerService:
    store = GeneratedArtifactStore()
    semantic_policy_store = SemanticPolicyStore(policy_path=SEMANTIC_POLICY_PATH)
    pipeline = TrainingPipelineService(generated_artifact_store=store)
    return TrainingFineTuneRunnerService(
        generated_artifact_store=store,
        training_pipeline_service=pipeline,
        semantic_policy_store=semantic_policy_store,
    )


def run_cli(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="NestHub training runner CLI")
    parser.add_argument("--profile", default="lora_sft")
    parser.add_argument("--backend", default="mock")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    runner = build_runner_service()
    if args.inspect or (not args.dry_run and not args.execute):
      result = runner.inspect_runner(profile=args.profile, backend=args.backend)
    else:
      result = runner.start_run(
          profile=args.profile,
          backend=args.backend,
          dry_run=not args.execute,
          note=args.note or (f"manifest={args.manifest}" if args.manifest else ""),
      )
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
