# core-brain-implementation.md (Execution-Ready, Codex-Friendly)

## 0. Goal

Build core-brain that can:

- Run via TVBox chat interface
- Use local LLM first, fallback to external APIs
- Perform intent analysis + workflow decomposition
- Manage 5-layer context system
- Support RAG (Weaviate)
- Generate code / configs / workflows automatically
- Auto-register and run generated artifacts

---

## 1. Tech Stack (STRICT)

backend: FastAPI  
llm_router: LiteLLM  
workflow_engine: LangGraph  
vector_db: Weaviate  
relational_db: PostgreSQL + pgvector  
cache: Redis  
search: Elasticsearch  
local_llm: Ollama  
external_llm: OpenAI / Groq / Gemini / Anthropic  

---

## 2. Key Principle

NEVER hardcode logic. EVERYTHING must be config-driven.

---

## 3. Directory Structure

core-brain/
├── app/
│   ├── main.py
│   ├── tvbox_api.py
│   ├── router.py
│   ├── engine/
│   │   ├── intent_engine.py
│   │   ├── workflow_engine.py
│   │   ├── codegen_engine.py
├── configs/
├── generated/
└── scripts/

---

## 4. TVBox API

```python
from fastapi import APIRouter
from pydantic import BaseModel
from app.engine.intent_engine import run_pipeline

router = APIRouter()

class ChatRequest(BaseModel):
    text: str
    session_id: str = "default"

@router.post("/chat")
async def chat(req: ChatRequest):
    # Entry point for TVBox interaction
    result = await run_pipeline(req.text, req.session_id)
    return {"reply": result}
```

---

## 5. LLM Router (Local + Fallback)

```python
from litellm import completion

async def call_llm(model_config, messages):
    # Try local model first
    try:
        return completion(model=model_config["model"], messages=messages)

    except Exception:
        # fallback to external model
        fallback = model_config.get("fallback")
        return completion(model=fallback, messages=messages)
```

---

## 6. Intent Engine

```python
async def analyze_intent(text, model_config):
    messages = [
        {"role": "system", "content": "Extract intent in JSON."},
        {"role": "user", "content": text}
    ]
    return await call_llm(model_config, messages)
```

---

## 7. Workflow Engine (Fallback)

```python
async def generate_workflow(intent):
    try:
        workflow = call_local_model(intent)
        validate(workflow)
        return workflow
    except:
        return call_external_model(intent)
```

---

## 8. CodeGen Engine

```python
class CodeGenEngine:

    async def generate_all(self, intent):
        workflow = await self.generate_workflow(intent)
        blueprint = await self.generate_blueprint(workflow)
        code = await self.generate_code(blueprint)
        self.save_all(workflow, blueprint, code)
```

---

## 9. Model Config (Fallback Enabled)

configs/models/intent.yaml

name: intent-model  
provider: ollama  
model: qwen3:4b  
fallback: gpt-4o  

---

## 10. Context Layers

1. System Context  
2. Session Context  
3. Task Context  
4. Long-term Memory (RAG)  
5. Execution Context  

---

## 11. RAG

```python
def retrieve_memory(query):
    return weaviate.search(query)
```

---

## 12. Auto Generation Flow

User Input → Intent → RAG → Workflow → CodeGen → Register → Run

---

## 13. LoRA Support

```python
def apply_lora(model_config):
    if model_config.get("lora"):
        load_adapter(model_config["lora"])
```

---

## 14. FINAL TARGET

User: Build accounting system

→ AI generates:
- workflow
- DB schema
- API
- runnable system
