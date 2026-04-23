# core-brain 设计与落地规范（供 Codex / 开发团队直接执行）

版本：v0.1  
状态：架构冻结版（第一阶段）  
目标：重建 `core-brain`，替代当前 `core / core+` 中不稳定、难扩展、难路由、难记忆、难配置的问题，以“**配置优先、知识驱动、螺旋式开发、可替换模型与可替换工作流**”为第一原则。

---

## 0. 本文档的定位

这不是“随便聊思路”的文档，而是给 **Codex / 开发者 / NestHub 团队**看的实施规范。

要求：

1. **先搭骨架，再补能力，不允许一开始写死复杂逻辑。**
2. **能配置的，不硬编码。**
3. **能注册的，不散落在业务代码。**
4. **能走知识库和模板的，不直接把 prompt 写死在 handler 里。**
5. **能抽象成接口的，不直接绑定单一模型、单一向量库、单一工作流引擎。**
6. `core-brain` 的职责是：**理解 → 路由 → 拆解 → 执行编排 → 写回记忆**，而不是把所有业务逻辑揉成一个大模型调用器。

---

## 1. 核心目标（必须实现）

### 1.1 第一阶段必须落地的能力

1. 提供与 `core / core+` 同级的 **TVBox 对话测试接口**。
2. 建立新的 `core-brain` 基础骨架。
3. 支持：
   - 本地模型对话
   - 本地模型 + LoRA
   - 外部模型 API 对话
   - 模型注册与运行时装载
   - 意图分析
   - Workflow 拆解
   - 五层上下文管理
   - 知识库检索
   - 基础 session / task memory
4. 全部采用 **配置驱动**。
5. 对 Codex 明确规定：**先补通主链路，不追求一步到位的复杂自治 Agent。**

### 1.2 第二阶段逐步增强的能力

1. Blueprint 自动生成 / 修正
2. 工具 schema 自动对齐
3. Workflow 自学习
4. 失败重试与策略降级
5. 多模型投票 / 结果校验
6. 长期记忆提炼
7. 多智能体协作

---

## 2. 技术栈（强制规定）

以下是 **core-brain 第一阶段强制技术选型**。除非架构评审通过，否则不得随意替换。

### 2.1 编程语言与工程组织

- **Python 3.11+**：主实现语言
- **FastAPI**：对外 API（含 TVBox 测试入口）
- **Pydantic v2**：配置、schema、DTO、运行时校验
- **LangGraph**：工作流状态机 / 执行图
- **LiteLLM**：统一模型路由层
- **Ollama**：本地模型运行与 Modelfile / LoRA 适配
- **Weaviate**：意图、模板、长期记忆、Blueprint 检索库
- **PostgreSQL + pgvector（可选回退）**：结构化状态、审计、可选向量能力
- **Elasticsearch**：日志、执行轨迹、检索增强、观测
- **Redis（建议）**：短期状态缓存、任务锁、临时执行态

### 2.2 智能体 / 编排 / 辅助框架的角色定位

以下框架**允许接入，但不能反客为主**：

- **LangGraph**：唯一主编排引擎
- **LiteLLM**：唯一统一模型网关
- **AutoGen**：只作为实验性多智能体协作模块，不进入主链路
- **CrewAI**：只作为任务编排参考，不作为第一阶段主框架
- **MetaGPT**：只参考其 SOP 思路，不直接作为运行时核心
- **Dify**：只作为低代码工作流参考或外部管理工具，不作为 core-brain 内核
- **RAG**：作为能力模式，而不是单独框架
- **MCP**：作为工具协议接入层，放在 tool gateway，不与 session 逻辑耦合

### 2.3 绝对禁止

1. 禁止把 prompt、schema、模型名、provider key 直接写死在 controller 中。
2. 禁止把 session memory 和长期记忆混在一起。
3. 禁止把 task 拆解结果只存在对话历史中而不落状态。
4. 禁止直接在业务代码里 if/else 切换几十个模型。
5. 禁止先做“万能 agent”，后补配置。

---

## 3. 模型策略（强制规定）

## 3.1 模型分层

`core-brain` 中的模型必须分成以下层级：

### A. 本地基础模型层

用于：

- 对话
- 意图识别
- workflow 拆解
- JSON 输出
- schema 填充
- 工具调用草案生成

第一阶段建议作为默认注册项：

- `Qwen3-4B-Instruct-2507`
- `Qwen3.5-35B-A3B`
- `DeepSeek` 系列（按你本地可用版本落地）

### B. 本地 LoRA 适配层

用于：

- 意图分析增强
- workflow 拆解增强
- 企业私域术语适配
- 输出格式稳定性增强

LoRA 不单独作为模型使用，而是：

- 绑定到基础模型
- 作为 adapter 注册
- 通过模型配置路由

### C. 外部模型层

统一通过 LiteLLM 接入：

- OpenAI
- Groq
- Gemini
- Anthropic
- OpenAI-compatible 其他网关（可扩展）

> 说明：Claude Code 是一个编码工具形态/终端形态产品，不应在 `core-brain` 中被当成“标准模型 provider 名”硬写。真正接入时，应区分：
>
> - **Anthropic API provider**：用于模型调用
> - **Claude Code 风格能力**：作为“代码代理参考模式”来借鉴

---

## 3.2 模型职责分工（第一阶段硬性约定）

### 默认职责分配表

| 任务类型 | 首选模型 | 备选模型 | 说明 |
| ------- | --- | --- | -- |
| 普通聊天 | Qwen3-4B-Instruct-2507 | 外部轻量模型 | 优先低成本、低延迟 |
| 意图识别 | Qwen3-4B + Intent LoRA | Qwen3.5-35B-A3B | 必须输出 JSON |
| workflow 拆解 | Qwen3.5-35B-A3B + Workflow LoRA | DeepSeek | 重点看结构和稳定性 |
| blueprint 草案 | Qwen3.5-35B-A3B | OpenAI / Anthropic | 复杂结构时升级 |
| 代码生成建议 | 外部代码强模型 | Qwen3.5-35B-A3B | 结果需二次校验 |
| schema 校验解释 | Qwen3-4B | Gemini / OpenAI | 快速、低成本 |
| 长文本总结 | 外部长上下文模型 | Qwen3.5-35B-A3B | 长输入时升级 |

---

## 4. 配置优先原则（强制）

所有能力都必须从“注册中心 + 配置文件”读取，而不是写死。

### 4.1 配置目录建议

```text
core_brain/
  app/
  brain/
    api/
    chat/
    context/
    memory/
    routing/
    workflows/
    tools/
    kb/
    execution/
    observability/
  configs/
    app/
      app.yaml
      env.dev.yaml
      env.prod.yaml
    models/
      registry.yaml
      local/
        qwen3_4b_instruct_2507.yaml
        qwen3_4b_intent_lora.yaml
        qwen3_5_35b_a3b.yaml
        qwen3_5_35b_workflow_lora.yaml
        deepseek_workflow.yaml
      external/
        openai_gpt.yaml
        groq_default.yaml
        gemini_default.yaml
        anthropic_default.yaml
    prompts/
      registry.yaml
      intent/
        intent_v1.yaml
      workflow/
        workflow_decomposer_v1.yaml
      blueprint/
        blueprint_builder_v1.yaml
      summary/
        session_summarizer_v1.yaml
    schemas/
      intent.schema.json
      workflow.schema.json
      blueprint.schema.json
      task_state.schema.json
      session_state.schema.json
    routing/
      routing_policy.yaml
      escalation_policy.yaml
    kb/
      weaviate_collections.yaml
      embedding_models.yaml
      retrieval_policy.yaml
    tvbox/
      tvbox_api.yaml
    tools/
      tool_registry.yaml
      mcp_registry.yaml
    lora/
      registry.yaml
      adapters/
        intent_lora.yaml
        workflow_lora.yaml
```

---

## 4.2 模型注册文件规范

每个模型一个文件，统一在 `models/registry.yaml` 中索引。

### 示例：`configs/models/local/qwen3_4b_instruct_2507.yaml`

```yaml
id: qwen3-4b-instruct-2507
name: Qwen3-4B-Instruct-2507
provider: ollama
transport: litellm
model: ollama_chat/qwen3-4b-instruct-2507
category: local_base
capabilities:
  - chat
  - intent
  - json_output
  - summary
strengths:
  - low_latency
  - low_cost
  - stable_short_json
weaknesses:
  - weak_complex_planning
  - weak_long_context
recommended_for:
  - simple_chat
  - intent_classification
  - schema_filling
context_window: 32768
default_params:
  temperature: 0.2
  top_p: 0.9
  max_tokens: 1200
routing_tags:
  - local
  - cheap
  - intent
availability:
  enabled: true
  healthcheck: /api/brain/models/health/qwen3-4b-instruct-2507
fallback_order:
  - qwen3.5-35b-a3b
  - openai-primary
```

### 示例：`configs/models/local/qwen3_4b_intent_lora.yaml`

```yaml
id: qwen3-4b-intent-lora
name: Qwen3-4B Intent LoRA
provider: ollama
transport: litellm
model: ollama_chat/qwen3-4b-intent-lora
base_model: qwen3-4b-instruct-2507
category: local_lora
capabilities:
  - intent
  - json_output
  - classification
lora_adapter: intent-lora-v1
recommended_for:
  - intent_classification
  - workflow_entry_routing
strict_json: true
context_window: 16384
default_params:
  temperature: 0.1
  top_p: 0.8
  max_tokens: 800
routing_tags:
  - local
  - lora
  - intent
availability:
  enabled: true
fallback_order:
  - qwen3-4b-instruct-2507
  - qwen3.5-35b-a3b
```

### 示例：`configs/models/external/openai_gpt.yaml`

```yaml
id: openai-primary
name: OpenAI Primary
provider: openai
transport: litellm
model: gpt-5
category: external
capabilities:
  - chat
  - code
  - reasoning
  - summary
  - json_output
recommended_for:
  - complex_planning
  - difficult_code_generation
  - blueprint_refinement
requires_api_key_env: OPENAI_API_KEY
routing_tags:
  - external
  - strong_reasoning
availability:
  enabled: true
fallback_order:
  - anthropic-primary
  - gemini-primary
```

---

## 4.3 LoRA 注册规范

### 示例：`configs/lora/registry.yaml`

```yaml
adapters:
  - id: intent-lora-v1
    task: intent_classification
    base_model: qwen3-4b-instruct-2507
    adapter_path: ./artifacts/lora/intent-lora-v1
    serving_mode: ollama_modelfile
    status: active

  - id: workflow-lora-v1
    task: workflow_decomposition
    base_model: qwen3.5-35b-a3b
    adapter_path: ./artifacts/lora/workflow-lora-v1
    serving_mode: ollama_modelfile
    status: active
```

### 示例：Ollama Modelfile（供 LoRA 装配）

```text
FROM qwen3:4b
ADAPTER ./artifacts/lora/intent-lora-v1
PARAMETER temperature 0.1
PARAMETER top_p 0.8
SYSTEM You are an intent classifier. Output JSON only.
```

---

## 5. Prompt 与 Schema 强约束

`core-brain` 不允许“口头说输出 JSON”。必须：

1. Prompt 模板独立存放
2. JSON Schema 独立存放
3. 每轮调用绑定：
   - prompt id
   - schema id
   - model route
   - validation policy

### 5.1 意图识别 Prompt 模板示例

文件：`configs/prompts/intent/intent_v1.yaml`

```yaml
id: intent_v1
name: Intent Classification Prompt V1
version: 1
system: |
  You are the intent analysis engine of NestHub core-brain.
  You must classify the user request into structured JSON.
  Do not answer as a chat assistant.
  Do not produce markdown.
  Output JSON only.
user_template: |
  Analyze the following user input and output strict JSON.

  User Input:
  {{ user_input }}

  Main Session Summary:
  {{ main_session_summary }}

  Task Session Summary:
  {{ task_session_summary }}

  Retrieved Intent Knowledge:
  {{ retrieved_intent_knowledge }}
schema_id: intent.schema.json
output_mode: json_only
```

### 5.2 意图 JSON Schema 示例

文件：`configs/schemas/intent.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "IntentClassification",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "intent_id",
    "intent_name",
    "confidence",
    "task_type",
    "needs_workflow",
    "needs_tool",
    "needs_memory_lookup",
    "output_mode"
  ],
  "properties": {
    "intent_id": { "type": "string" },
    "intent_name": { "type": "string" },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "task_type": {
      "type": "string",
      "enum": [
        "chat",
        "intent_analysis",
        "workflow_design",
        "blueprint_generation",
        "tool_execution",
        "memory_lookup",
        "code_generation",
        "document_generation"
      ]
    },
    "needs_workflow": { "type": "boolean" },
    "needs_tool": { "type": "boolean" },
    "needs_memory_lookup": { "type": "boolean" },
    "output_mode": {
      "type": "string",
      "enum": ["answer", "json", "plan", "workflow", "blueprint"]
    },
    "candidate_blueprints": {
      "type": "array",
      "items": { "type": "string" }
    },
    "missing_information": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

---

## 6. 五层上下文架构（强制）

这是 `core-brain` 的主心骨，不允许改成“全量聊天记录拼 prompt”。

## 6.1 上下文层定义

### Layer 1：系统上下文（System Context）

固定层。

包含：

- AI OS 角色定义
- 当前支持能力
- 输出格式要求
- 安全规则
- 工具调用规则
- workflow / blueprint 规则
- schema 约束

特点：

- 基本不变
- 不属于聊天历史
- 由配置注入

### Layer 2：主会话上下文（Main Session Context）

当前用户主题状态摘要。

只存：

- 当前目标
- 当前阶段
- 已确认信息
- 未确认问题
- 当前草稿结果
- 当前下一步建议

禁止：

- 原样塞入全部历史消息

### Layer 3：Task Session Context

主会话下按任务拆分。

示例：

- `task_001`：收集家庭成员字段
- `task_002`：生成 workflow
- `task_003`：生成 blueprint
- `task_004`：生成提醒规则

每个 task 仅保留：

- 任务目标
- 输入材料
- 当前状态
- 中间产物
- 失败原因
- 下一步动作

### Layer 4：长期记忆 / 知识库上下文（Long-term Memory / KB Context）

不是聊天记录，而是提炼后的长期知识。

示例：

- 用户常用语言
- 用户输出偏好
- 用户正在做 AI OS / workflow / agent 系统
- 既有 schema
- 既有 blueprint 模板
- 既有 intent 模板

只在需要时检索，不全量注入。

### Layer 5：临时执行上下文（Ephemeral Execution Context）

本次执行临时态。

内容：

- 上一步工具结果
- 当前 step 结果 JSON
- 执行轨迹
- 重试次数
- 步骤状态

只服务本次执行，可落 Elasticsearch / Redis / execution trace store。

---

## 6.2 上下文生成顺序（强制）

```text
用户输入
  ↓
消息预处理
  ↓
上下文分类
  ├─ 系统上下文
  ├─ 主会话上下文
  ├─ task 上下文
  ├─ 长期记忆检索
  └─ 临时执行上下文
  ↓
生成本轮 prompt context
  ↓
LLM / workflow engine
  ↓
结果写回
  ├─ 更新 session state
  ├─ 更新 task state
  └─ 必要时写入长期记忆
```

---

## 7. 记忆与知识库设计（强制）

## 7.1 存储职责分离

### PostgreSQL

保存结构化、强一致内容：

- session_state
- task_state
- workflow_run
- blueprint_run
- execution_audit
- user_profile_structured

### Weaviate

保存可检索语义知识：

- intent patterns
- workflow templates
- blueprint templates
- long-term memory summaries
- reusable prompt cases
- schema explanation docs

### Elasticsearch

保存：

- 调用日志
- 工具轨迹
- 中间结果
- 调试检索
- prompt / response 审计索引

### Redis

保存：

- 短时缓存
- task lock
- request dedupe
- 执行上下文热数据

---

## 7.2 Weaviate Collection 建议

文件：`configs/kb/weaviate_collections.yaml`

```yaml
collections:
  - name: IntentPattern
    description: Intent classification knowledge units
    properties:
      - name: intent_id
        type: text
      - name: intent_name
        type: text
      - name: examples
        type: text[]
      - name: slots
        type: text[]
      - name: output_schema_id
        type: text
      - name: priority
        type: number

  - name: WorkflowTemplate
    description: Reusable workflow decomposition templates
    properties:
      - name: workflow_id
        type: text
      - name: workflow_name
        type: text
      - name: domain
        type: text
      - name: steps_json
        type: text
      - name: trigger_conditions
        type: text[]
      - name: required_slots
        type: text[]

  - name: BlueprintTemplate
    description: Reusable blueprint definitions
    properties:
      - name: blueprint_id
        type: text
      - name: blueprint_name
        type: text
      - name: blueprint_json
        type: text
      - name: tags
        type: text[]

  - name: LongTermMemory
    description: Summarized durable user or system memory
    properties:
      - name: memory_id
        type: text
      - name: memory_type
        type: text
      - name: scope
        type: text
      - name: content
        type: text
      - name: source_ref
        type: text
      - name: confidence
        type: number
```

---

## 7.3 Embedding 模型原则

意图知识库与 workflow 模板库的 embedding 模型必须单独配置，不与生成模型耦合。

### `configs/kb/embedding_models.yaml`

```yaml
embedding_models:
  default:
    provider: ollama
    model: bge-m3
    dimensions: 1024
    use_for:
      - intent_kb
      - workflow_templates
      - blueprint_templates

  fallback:
    provider: external
    model: text-embedding-3-large
    use_for:
      - difficult_retrieval
      - long_term_memory
```

---

## 8. 路由策略（强制）

`core-brain` 的路由分三层：

1. **规则层**：硬规则判断
2. **本地模型层**：优先本地完成
3. **升级层**：必要时调用外部模型

### 8.1 总路由

```text
用户请求
   ↓
[规则层（强制判断）]
   ↓
[本地模型（Qwen / DeepSeek / LoRA）]
   ↓
是否成功？
   ↓ yes → 返回
   ↓ no
[升级判断（是否允许外部调用）]
   ↓
[外部模型（OpenAI / Groq / Gemini / Anthropic）]
   ↓
[结果校验]
   ↓
返回用户 + 写入知识库
```

### 8.2 升级条件（必须配置）

- JSON 校验失败超过阈值
- 本地模型意图置信度低于阈值
- workflow 拆解结构不完整
- 需要大上下文摘要
- 需要高质量代码生成
- 需要高质量 blueprint 重构

### 示例：`configs/routing/escalation_policy.yaml`

```yaml
escalation:
  max_local_retries: 2
  conditions:
    - name: low_intent_confidence
      when: intent.confidence < 0.72
      action: escalate_to_external

    - name: invalid_json_output
      when: validation.json_failed_count >= 2
      action: switch_model

    - name: workflow_missing_required_steps
      when: workflow.missing_required_steps == true
      action: escalate_to_external

  default_external_route:
    code_generation: openai-primary
    complex_planning: anthropic-primary
    long_context_summary: gemini-primary
```

---

## 9. TVBox 接口要求（第一阶段必须可跑）

目标：让 `core-brain` 与 `core / core+` 一样，能在 TVBox 中直接做对话测试。

## 9.1 原则

1. **先兼容旧调用方式，再内部替换实现。**
2. TVBox 只认一个清晰的 brain chat API。
3. 外部接口稳定，内部可逐步替换。

## 9.2 推荐 API

### POST `/api/core-brain/chat`

请求：

```json
{
  "session_id": "main_001",
  "task_id": "task_001",
  "user_id": "demo_user",
  "message": "帮我创建家庭成员信息的智能体",
  "mode": "chat",
  "context_policy": "default",
  "allow_external": true,
  "stream": false,
  "client": {
    "name": "tvbox",
    "version": "0.1.0"
  }
}
```

响应：

```json
{
  "request_id": "req_123",
  "session_id": "main_001",
  "task_id": "task_001",
  "intent": {
    "intent_name": "agent_creation",
    "confidence": 0.93
  },
  "route": {
    "provider": "ollama",
    "model": "qwen3-4b-intent-lora",
    "escalated": false
  },
  "result": {
    "type": "answer",
    "content": "已识别为创建家庭成员信息智能体需求，建议先收集字段定义。"
  },
  "state_updates": {
    "main_session_updated": true,
    "task_session_updated": true,
    "long_term_memory_written": false
  }
}
```

## 9.3 兼容性建议

如果旧版 TVBox 调用的是 `/api/core/chat`，则添加 **compat adapter**：

```text
TVBox
  -> old endpoint adapter
  -> core-brain facade
  -> new router
```

即：

- 保留旧入参格式
- 在 adapter 层转换为新 DTO
- 不要把旧协议污染到内部模块

---

## 10. 模块骨架（第一阶段必须生成）

```text
core_brain/
  app/
    main.py
    bootstrap.py

  brain/
    api/
      routers/
        health.py
        chat.py
        models.py
        memory.py
      dto/
        chat_request.py
        chat_response.py

    chat/
      brain_facade.py
      chat_service.py
      response_builder.py

    routing/
      router_service.py
      route_selector.py
      escalation_service.py
      policy_loader.py

    context/
      context_builder.py
      system_context.py
      main_session_context.py
      task_session_context.py
      long_term_context.py
      execution_context.py
      summarizers/
        session_summarizer.py
        task_summarizer.py

    memory/
      repositories/
        session_repo.py
        task_repo.py
        long_term_repo.py
        execution_repo.py
      services/
        session_memory_service.py
        task_memory_service.py
        long_term_memory_service.py

    kb/
      retrieval/
        weaviate_retriever.py
        embedding_service.py
      writers/
        kb_writer.py

    llm/
      litellm_client.py
      model_registry.py
      prompt_registry.py
      schema_registry.py
      validators/
        json_validator.py
        schema_validator.py

    workflows/
      graph/
        chat_graph.py
        intent_graph.py
        workflow_graph.py
      nodes/
        preprocess_node.py
        intent_node.py
        retrieval_node.py
        planner_node.py
        answer_node.py
        writeback_node.py

    tools/
      tool_gateway.py
      mcp_gateway.py
      registry.py

    observability/
      logger.py
      trace_service.py
      elastic_writer.py

  tests/
    unit/
    integration/
    contract/

  configs/
  scripts/
  artifacts/
```

---

## 11. 第一阶段最小代码骨架（示例，不允许直接写死扩展逻辑）

## 11.1 `app/main.py`

```python
from fastapi import FastAPI
from brain.api.routers.chat import router as chat_router
from brain.api.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="core-brain")
    app.include_router(health_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    return app


app = create_app()
```

## 11.2 `brain/api/dto/chat_request.py`

```python
from pydantic import BaseModel, Field
from typing import Optional


class ClientInfo(BaseModel):
    name: str = "unknown"
    version: str = "0.0.0"


class ChatRequest(BaseModel):
    session_id: str
    task_id: Optional[str] = None
    user_id: str
    message: str = Field(min_length=1)
    mode: str = "chat"
    context_policy: str = "default"
    allow_external: bool = True
    stream: bool = False
    client: ClientInfo = ClientInfo()
```

## 11.3 `brain/api/routers/chat.py`

```python
from fastapi import APIRouter, Depends
from brain.api.dto.chat_request import ChatRequest
from brain.chat.brain_facade import BrainFacade

router = APIRouter()


def get_brain_facade() -> BrainFacade:
    return BrainFacade.from_default_config()


@router.post("/core-brain/chat")
def core_brain_chat(req: ChatRequest, facade: BrainFacade = Depends(get_brain_facade)):
    return facade.handle_chat(req)
```

## 11.4 `brain/chat/brain_facade.py`

```python
from brain.routing.router_service import RouterService
from brain.context.context_builder import ContextBuilder
from brain.llm.model_registry import ModelRegistry
from brain.llm.prompt_registry import PromptRegistry
from brain.memory.services.session_memory_service import SessionMemoryService
from brain.memory.services.task_memory_service import TaskMemoryService


class BrainFacade:
    def __init__(
        self,
        router_service: RouterService,
        context_builder: ContextBuilder,
        model_registry: ModelRegistry,
        prompt_registry: PromptRegistry,
        session_memory: SessionMemoryService,
        task_memory: TaskMemoryService,
    ):
        self.router_service = router_service
        self.context_builder = context_builder
        self.model_registry = model_registry
        self.prompt_registry = prompt_registry
        self.session_memory = session_memory
        self.task_memory = task_memory

    @classmethod
    def from_default_config(cls):
        return cls(
            router_service=RouterService.from_config(),
            context_builder=ContextBuilder.from_config(),
            model_registry=ModelRegistry.from_config(),
            prompt_registry=PromptRegistry.from_config(),
            session_memory=SessionMemoryService.from_config(),
            task_memory=TaskMemoryService.from_config(),
        )

    def handle_chat(self, req):
        context_bundle = self.context_builder.build(req)
        route = self.router_service.select_route(req=req, context_bundle=context_bundle)
        result = self.router_service.execute(req=req, route=route, context_bundle=context_bundle)
        self.session_memory.write_back(req, result)
        self.task_memory.write_back(req, result)
        return result
```

> 注意：这里只给“骨架代码示例”。真正实现时，**必须把具体 provider、prompt id、schema id、路由规则都读取配置**。

---

## 12. LangGraph 主流程（第一阶段）

第一阶段建议只做 1 条主链路：

```text
preprocess
  -> load_context
  -> intent_analysis
  -> retrieve_knowledge
  -> decide_route
  -> generate_result
  -> validate_result
  -> writeback_state
  -> respond
```

### 节点职责

- `preprocess`：清洗消息、识别 client、标准化输入
- `load_context`：聚合五层上下文
- `intent_analysis`：识别 intent / task type / 是否需要 workflow
- `retrieve_knowledge`：查 Weaviate / session summary / blueprint 模板
- `decide_route`：选择本地 / 外部模型
- `generate_result`：调用模型
- `validate_result`：JSON / schema / business rule 校验
- `writeback_state`：写 session / task / execution / memory
- `respond`：输出 TVBox 所需格式

---

## 13. 意图知识结构（必须有）

第一阶段不要求模型自己“悟出来所有 intent”，而是先建立可维护的 intent 知识结构。

### 13.1 Intent 知识单元应包含

- `intent_id`
- `intent_name`
- `domain`
- `description`
- `typical_examples`
- `required_slots`
- `optional_slots`
- `suggested_prompt_id`
- `suggested_schema_id`
- `suggested_workflow_template`
- `default_output_mode`

### 示例

```json
{
  "intent_id": "agent.create.family_profile",
  "intent_name": "创建家庭成员信息智能体",
  "domain": "household_agent",
  "description": "为家庭成员信息采集和后续消费/日程/提醒场景创建智能体",
  "typical_examples": [
    "帮我创建家庭成员信息的智能体",
    "为家里人建立一个资料智能体",
    "创建家庭成员数据采集 agent"
  ],
  "required_slots": [
    "family_scope",
    "member_fields",
    "data_storage_policy"
  ],
  "optional_slots": [
    "notification_policy",
    "language_policy"
  ],
  "suggested_prompt_id": "intent_v1",
  "suggested_schema_id": "intent.schema.json",
  "suggested_workflow_template": "workflow.family_agent_bootstrap.v1",
  "default_output_mode": "plan"
}
```

---

## 14. Workflow 模板结构（必须配置化）

### 示例：`workflow.family_agent_bootstrap.v1`

```yaml
id: workflow.family_agent_bootstrap.v1
name: Family Agent Bootstrap
version: 1
trigger_intents:
  - agent.create.family_profile
steps:
  - id: collect_scope
    type: ask_user_or_extract
    goal: collect family scope
    required_slots:
      - family_scope

  - id: collect_member_fields
    type: ask_user_or_extract
    goal: collect required member fields
    required_slots:
      - member_fields

  - id: generate_member_schema
    type: llm_structured_output
    prompt_id: blueprint_builder_v1
    schema_id: blueprint.schema.json

  - id: generate_task_plan
    type: llm_structured_output
    prompt_id: workflow_decomposer_v1
    schema_id: workflow.schema.json

  - id: save_blueprint_candidate
    type: persist
    target: weaviate.BlueprintTemplate

  - id: return_plan
    type: answer
```

---

## 15. LoRA 微调逻辑（必须纳入，但分阶段实现）

## 15.1 第一阶段只要求具备“装配与切换”能力

第一阶段不要求在 `core-brain` 内部完成训练平台，但必须支持：

1. 识别某个模型是否带 LoRA adapter
2. 根据路由策略调用带 LoRA 的模型
3. 用配置文件管理 LoRA adapter
4. 能在推理阶段切换不同任务 adapter

## 15.2 第二阶段再做训练链路

建议训练链路单独工程化：

```text
training/
  datasets/
    intent/
    workflow/
  recipes/
    qwen_intent_lora.yaml
    qwen_workflow_lora.yaml
  scripts/
    train_intent_lora.py
    train_workflow_lora.py
```

### 训练数据格式建议

#### 意图分类数据

```json
{
  "instruction": "Classify the user request into structured intent JSON.",
  "input": "帮我创建家庭成员信息的智能体",
  "output": {
    "intent_id": "agent.create.family_profile",
    "intent_name": "创建家庭成员信息智能体",
    "confidence": 0.98,
    "task_type": "workflow_design",
    "needs_workflow": true,
    "needs_tool": false,
    "needs_memory_lookup": true,
    "output_mode": "plan"
  }
}
```

#### Workflow 拆解数据

```json
{
  "instruction": "Decompose the request into a workflow JSON.",
  "input": "创建家庭成员信息智能体，并通过对话收集成员字段，最后生成 blueprint",
  "output": {
    "workflow_name": "family_agent_bootstrap",
    "steps": [
      {"id": "collect_scope", "type": "ask"},
      {"id": "collect_member_fields", "type": "ask"},
      {"id": "generate_schema", "type": "llm"},
      {"id": "generate_blueprint", "type": "llm"}
    ]
  }
}
```

---

## 16. 参考项目如何借鉴（不是照搬）

## 16.1 Claude Code

借鉴点：

- 工程感强
- 对代码任务的分步处理
- 工具使用有边界
- CLI / 代理执行流程清晰

不照搬点：

- 不把 `core-brain` 做成纯 CLI 编码代理
- 不把 Anthropic 专属流程写死成系统核心

## 16.2 TuriXAI / TuriX-CUA

借鉴点：

- 任务执行与动作链路清晰
- 可把“计划 → 执行 → 校验”思想迁移到 workflow

不照搬点：

- `core-brain` 第一阶段不做桌面 computer use 主链路

## 16.3 OpenClaw

借鉴点：

- 多通道接入思路
- Agent 框架分层
- 对渠道与模型的解耦意识

不照搬点：

- 不把“多渠道 bot 框架”直接等价成 `core-brain`

---

## 17. 螺旋式开发路线（强制按阶段推进）

## Phase 0：骨架打通

必须完成：

- FastAPI 可启动
- `/api/core-brain/chat` 可调用
- TVBox 可对接
- LiteLLM 可调用 1 个本地模型
- session / task state 基本可写

## Phase 1：本地对话 + 意图识别

必须完成：

- 本地模型路由
- Prompt / Schema 注册
- intent JSON 输出
- session summary
- task summary

## Phase 2：workflow 拆解 + 知识库

必须完成：

- Weaviate 建表
- Intent KB 检索
- Workflow 模板检索
- workflow 拆解输出

## Phase 3：LoRA + 升级路由

必须完成：

- Intent LoRA 接入
- Workflow LoRA 接入
- 外部模型升级策略
- 结果校验与重试

## Phase 4：Blueprint / Tool / Memory 增强

必须完成：

- blueprint 生成
- tool registry
- MCP gateway
- 长期记忆提炼

---

## 18. 对 Codex 的执行要求（必须遵守）

1. **先建目录和配置，再写实现。**
2. 每一个新增模块必须先定义：
   - 输入 DTO
   - 输出 DTO
   - 配置来源
   - 依赖接口
3. 不允许先写一堆 if/else 再回头抽象。
4. 不允许把模型名、prompt、schema 写死在 service 中。
5. 每实现一个能力，必须补：
   - 单元测试
   - 配置样例
   - README / 使用说明
6. 优先保证：
   - 可运行
   - 可替换
   - 可观测
   - 可回退
7. 所有“智能”逻辑必须可追踪：
   - 用了哪个模型
   - 哪个 prompt
   - 哪个 schema
   - 哪个知识检索
   - 为什么升级到外部模型

---

## 19. 第一阶段交付清单（必须完成）

### 代码层

- [ ] `core_brain` 新目录初始化
- [ ] FastAPI 基础启动
- [ ] TVBox chat 接口
- [ ] LiteLLM 客户端封装
- [ ] 模型注册中心
- [ ] Prompt 注册中心
- [ ] Schema 注册中心
- [ ] ContextBuilder 骨架
- [ ] SessionMemory / TaskMemory 骨架
- [ ] LangGraph 主链路骨架
- [ ] Elasticsearch trace writer 骨架

### 配置层

- [ ] app 配置
- [ ] 模型配置
- [ ] routing policy
- [ ] escalation policy
- [ ] prompt 配置
- [ ] schema 配置
- [ ] tvbox 配置
- [ ] weaviate collection 配置
- [ ] embedding model 配置
- [ ] lora registry 配置

### 文档层

- [ ] README
- [ ] `.env.example`
- [ ] `configs/README.md`
- [ ] `docs/core_brain_architecture.md`
- [ ] `docs/core_brain_api.md`

---

## 20. 最终结论（严格执行）

`core-brain` 的第一原则不是“做一个最聪明的大模型壳子”，而是：

> **做一个可配置、可路由、可记忆、可审计、可逐步增强的 AI 内核。**

具体落地方针：

1. **FastAPI + LiteLLM + LangGraph** 作为第一阶段主干。
2. **Ollama + 本地模型 + LoRA** 作为本地能力底座。
3. **Weaviate + PostgreSQL + Elasticsearch + Redis** 作为数据与记忆基础设施。
4. **Prompt / Schema / Workflow / Blueprint / Model 全部配置化。**
5. **上下文严格分五层。**
6. **先保证 TVBox 能对话，再逐步增强 intent、workflow、blueprint、memory。**
7. **先做可运行骨架，再做强智能。**

---

## 21. 给 NestHub 团队的一句话

不是“让模型替你想一切”，而是：

> **先把系统思维、模块边界、配置结构、知识结构、上下文结构设计清楚，再让模型在这个框架里稳定发挥。**

这才是 `core-brain` 应该教给 NestHub 的思维方式。
