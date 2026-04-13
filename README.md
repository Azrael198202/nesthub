# HomeHub / NestHub Runtime Skeleton

This is a cross-platform Python skeleton for:

- Capability Resolver
- Environment Manager
- Bootstrap on first start
- Automatic install of missing models / tools / packages
- Blueprint manifest loading and execution planning

## Target Platforms

- Current development environment: macOS
- Target runtime environments:
  - Linux (TV Box / edge device)
  - Windows
  - macOS

## Main Goals

1. Detect the current operating system and runtime profile
2. Load bootstrap requirements at first startup
3. Install packages, tools, and models as needed
4. Resolve blueprint requirements dynamically
5. Retry execution once dependencies are available

## Directory Structure

```text
src/nethub_runtime/
  app/                startup entrypoint and bootstrap flow
  blueprint/          blueprint manifest / loader / executor
  capability/         capability resolver, install planning, registries
  config/             settings and config loading
  core/               common models and enums
  environment/        environment manager and installers
  models/             model provider abstraction and ollama provider
  platform/           OS detection and runtime profile
  runtime/            command execution and security policy
  tools/              local shell/python tool wrappers
examples/blueprints/  sample blueprint manifests
```

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m nethub_runtime.main
```

## Suggested Next Step

- connect this skeleton to your AI Core planner/router
- map blueprint generation output to `BlueprintManifest`
- add real package managers for Linux/Windows/macOS
- add your TV Box command whitelist and sandbox policy
