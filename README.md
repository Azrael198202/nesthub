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

# Install NestHub runtime dependencies
pip install -r requirements.txt

python -m nethub_runtime.main
```

## Public API Quick Start

`api/public_api` uses a smaller dependency set and should not install the full runtime stack.

```bash
python -m venv .venv-public-api
source .venv-public-api/bin/activate   # Windows: .venv-public-api\Scripts\activate
pip install -r api/public_api/requirements.txt

python -m api.public_api.main
```

To connect LINE to NestHub through `public_api`, set these environment variables before starting `api.public_api`:

```bash
export NESTHUB_CORE_HANDLE_URL=http://127.0.0.1:8000/core/handle
export LINE_CHANNEL_ACCESS_TOKEN=...
export LINE_CHANNEL_SECRET=...
```

Then configure the LINE Messaging API webhook URL to:

```bash
https://<your-public-api-host>/api/bridge/im/inbound
```

Flow:

1. LINE sends webhook to `public_api`.
2. `public_api` verifies the LINE signature.
3. `public_api` calls NestHub core through `NESTHUB_CORE_HANDLE_URL`.
4. `public_api` replies to LINE with the NestHub result using `replyToken`, and falls back to push when needed.

## Delayed Document And Image Follow-Up

NestHub now supports split-turn document and image processing in the same session.

Supported sequences:

1. User sends the business request first, then uploads a document or image.
2. User uploads the document or image first, then sends the business request.

Runtime behavior:

1. A request such as `帮我分析一下文件` or `请对这份文档进行翻译` creates a session-scoped pending request instead of executing immediately when no attachment is present.
2. An attachment-only turn such as LINE file upload or TVBox upload enters standby instead of forcing analysis immediately.
3. When both the request and a session attachment are available within the wait window, NestHub continues automatically.

Configuration:

```bash
export NETHUB_DOCUMENT_WAIT_TIMEOUT_SECONDS=300
```

Notes:

1. The effective wait window is clamped to `120` to `300` seconds.
2. LINE standby turns are silent by design, so NestHub does not send a meaningless intermediate reply before the matching document/image or request arrives.
3. Session attachments are persisted under `received/<session_id>/` and reused for follow-up turns.

## Image OCR Chain

Image attachments now use an explicit OCR path instead of ad hoc inline parsing.

OCR order:

1. `PaddleOCR`
2. `pytesseract`
3. Capability acquisition / graceful fallback when no OCR engine is available

This OCR path is shared by:

1. The standalone `ocr_extract` runtime step
2. The document analysis plugin when the session attachment is an image

If no OCR engine is installed, NestHub keeps the main flow intact and returns a controlled fallback instead of crashing.

## Railway Deployment For Public API

If you deploy the public bridge on Railway, do not rely on Railway's default Python dependency detection, because it will pick the root `requirements.txt`.

This repository now includes a root-level `nixpacks.toml` that forces Railway to:

```bash
pip install -r api/public_api/requirements.txt
uvicorn api.public_api.app:app --host 0.0.0.0 --port $PORT
```

Recommended Railway settings:

1. Keep the service root at the repository root if you want to use the checked-in `nixpacks.toml` directly.
2. Ensure the Start Command is not overridden in the Railway dashboard.
3. If you prefer configuring in the Railway UI instead of using `nixpacks.toml`, set:
  - Build Command: `pip install -r api/public_api/requirements.txt`
  - Start Command: `uvicorn api.public_api.app:app --host 0.0.0.0 --port $PORT`

## Framework Architecture (v2.0)

This project now includes a complete AI Core framework based on **LangGraph** and **LiteLLM**:

### 📚 Documentation

**Quick Start**: Read [FRAMEWORK_GUIDE.md](./FRAMEWORK_GUIDE.md) for complete documentation index and learning paths.

**Key Documents**:

1. **LiteLLM Model Routing** - `docs/02_router/litellm_routing_design.md`
   - Unified LLM interface management
   - Multi-model routing strategies (Ollama / OpenAI / Claude / Gemini)
   - Dynamic model selection with fallback chains
   - Configuration hot-reload support

2. **LangGraph Workflow & Agent Framework** - `docs/03_workflow/langgraph_agent_framework.md`
   - Workflow execution with LangGraph
   - Blueprint compilation to executable graphs
   - Agent-based autonomous reasoning (ReAct pattern)
   - State management and execution control

3. **AI Core Integration Guide** - `docs/03_core/integration_guide.md`
   - Complete integration of LiteLLM + LangGraph
   - Startup process documentation (main.py → tvbox/main.py)
   - Execution flow examples (Workflow vs Agent)
   - Configuration and best practices

### 🚀 Startup Entries

```bash
# Standard application startup
python nethub_runtime/app/main.py

# TVBox local runtime startup
python nethub_runtime/tvbox/main.py
```

### 📁 Core Module Structure

```
nethub_runtime/
├── app/main.py                     # Application startup entrypoint
├── models/model_router.py          # LiteLLM-based model routing
├── core/
│   ├── main.py                     # AI Core orchestrator
│   ├── workflows/                  # LangGraph workflow engine
│   ├── agents/                     # LangGraph agent framework
│   └── tools/                      # Tool registry and execution
└── tvbox/main.py                   # TVBox local runtime startup
```

### 🔄 Execution Flow

```
User Input
  ↓
[AI Core Intent Analysis] (LiteLLM routing)
  ↓
[Decision: Workflow or Agent?]
  ├─ Workflow → Blueprint Compilation → LangGraph Execution
  └─ Agent → Agent Spec Generation → LangGraph Agent Reasoning Loop
  ↓
[Result Integration]
  ↓
Output
```

## Suggested Next Step

- Read [FRAMEWORK_GUIDE.md](./FRAMEWORK_GUIDE.md) for complete documentation
- Review startup process in `docs/03_core/integration_guide.md`
- Customize model configuration in `config/model_config.yaml`
- Add domain-specific blueprints to `examples/blueprints/`
- Connect to your TV Box environment for local deployment
