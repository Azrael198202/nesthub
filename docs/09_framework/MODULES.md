# Module Definition

## 1. platform
Responsible for runtime detection.

- `platform.detector`: detect OS, shell capability, Python, Ollama, CPU architecture
- `platform.os_profile`: normalized runtime profile for Linux / Windows / macOS

## 2. core
Shared domain objects.

- `core.enums`: OS type, tool type, install target, execution status
- `core.models`: capability request/result, bootstrap manifest, command result

## 3. config
Configuration and paths.

- `config.settings`: app directories, bootstrap files, registry file locations

## 4. capability
Resolve what is required before execution.

- `capability.registry`: current installed models/tools/packages
- `capability.install_plan`: describe missing dependencies and plan
- `capability.resolver`: compare blueprint requirements with registry/profile

## 5. environment
Install and register missing dependencies.

- `environment.manager`: orchestrate installers
- `environment.installers.base`: installer interface
- `environment.installers.pip_installer`: install Python packages
- `environment.installers.ollama_installer`: pull local models
- `environment.installers.tool_installer`: install or register tools
- `environment.installers.shell_installer`: shell-based bootstrap helper

## 6. blueprint
Runtime execution unit.

- `blueprint.manifest`: manifest schema
- `blueprint.loader`: load YAML blueprint
- `blueprint.executor`: resolve → install → execute

## 7. runtime
Controlled command execution.

- `runtime.command_runner`: run commands with timeout/logging
- `runtime.policies`: shell whitelist and safety policy

## 8. tools
Executable local tools.

- `tools.base`: tool interface
- `tools.shell_tool`: controlled shell execution
- `tools.python_tool`: local Python execution

## 9. models
Model provider abstraction.

- `models.provider`: abstract provider interface
- `models.ollama_provider`: local model operations for Ollama

## 10. app
Startup and bootstrap.

- `app.bootstrap`: first-start bootstrap workflow
- `main.py`: demo entrypoint
