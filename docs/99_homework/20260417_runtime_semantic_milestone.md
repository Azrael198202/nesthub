# Runtime Semantic Milestone

## Goal

Move NestHub core parsing away from hardcoded language keywords and make runtime memory the first-class source of intent and semantic rule knowledge.

## Completed In This Milestone

- `intent/keyword` knowledge is persisted in `semantic_policy_memory.sqlite3` via `runtime_intent_knowledge`.
- `RuntimeKeywordSignalAnalyzer` reads runtime intent knowledge before fallback heuristics.
- `IntentAnalyzer` writes finalized intent decisions back into runtime memory.
- `ExecutionCoordinator` no longer depends on `intent_policy.json` for:
  - query stopwords
  - time markers
  - group-by markers
- `intent_policy.json` has been reduced to a minimal skeleton centered on numeric parsing.
- `SemanticPolicyStore` now supports runtime overlays for these parser rule families:
  - `actor_extract_patterns`
  - `explicit_date_patterns`
  - `relative_week_rules`
  - `boolean_aliases`
  - `time_marker_rules`
- `ExecutionCoordinator` learning payloads now expose those rule families for runtime evolution.
- `ExecutionCoordinator` now boots from an internal schema-default semantic policy and merges file/runtime overlays on top.
- `semantic_policy.json` has been reduced to a schema-only seed and no longer carries shipped business-language examples.
- Budget-oriented API and E2E tests now inject their own semantic samples instead of depending on repository baseline policy content.

## Current Architectural Boundary

Core code now boots from schema defaults first, with `semantic_policy.json` acting as a writable seed layer rather than the primary source of language knowledge.

That means the architecture is now:

- stable core code
- internal schema defaults
- schema-only semantic seed file
- runtime memory overlay for learned intent and parsing knowledge

## What Is Still Not Finished

- Runtime semantic rule generation is supported by storage and overlay, but not all rule families are actively learned from live traffic yet.
- No eviction, decay, or governance strategy exists yet for long-running runtime semantic knowledge.
- No explicit bootstrap process exists yet to generate an initial semantic baseline for a new language/runtime from scratch.
- The default schema still carries a few generic parser-safe fallbacks; locale-specific semantics are not generated automatically yet.

## Validation Status

- Targeted regression for execution coordinator, semantic policy memory, runtime intent knowledge, budget E2E, and core API passed.
- Focused runtime regression task passed.

## Recommended Next Milestone

1. Add active model-driven learning for parser rule families, not only storage support.
2. Add confidence decay, deduplication, and rollback governance for runtime semantic knowledge.
3. Add runtime bootstrap to generate a first-use semantic baseline per locale.
4. Remove remaining locale or phrase assumptions from generic fallback defaults where safe.