# nethub_runtime 模块说明与复用落位（2026-04-23）

本文档基于当前代码（`core-brain` 已切换后）梳理 `nethub_runtime` 的模块职责。
目标：
- 解释每个模块做什么
- 标记是否仍在主链路
- 给出可复用能力的沉淀位置

## 1. 运行主链路

当前主链路：

`nethub_runtime.main` -> `nethub_runtime.app.main` -> `create_core_engine()` -> `core_brain.engine.CoreBrainEngine`

并行启动：
- TVBox UI：`nethub_runtime.tvbox.main`
- IM 轮询 demo：`nethub_runtime.integrations.im.line_demo`

## 2. 顶层模块说明（按目录）

| 模块 | 主要职责 | 当前状态 | 复用建议 |
|---|---|---|---|
| `nethub_runtime/app` | 应用装配与启动上下文组装 | 主链路在用 | 可复用为统一 Bootstrap 层 |
| `nethub_runtime/core_brain` | 新核心：意图/路由/上下文/记忆/响应主流程 | 主链路在用 | 作为后续 Brain 能力唯一扩展点 |
| `nethub_runtime/core` | 兼容层（旧 API、通用模型/枚举、少量兼容服务） | 兼容在用 | 逐步下沉“通用定义”，减少业务逻辑 |
| `nethub_runtime/tvbox` | 本地 UI + 对话 API + 文件与桥接交互 | 主链路在用 | UI 侧能力可继续复用 |
| `nethub_runtime/config` | 运行路径、目录、密钥、模型路由配置 | 主链路在用 | 作为全局配置入口 |
| `nethub_runtime/capability` | 能力盘点、缺失依赖分析、安装计划生成 | 在用（bootstrap / blueprint） | 可复用于 agent/tool 预检 |
| `nethub_runtime/environment` | 依赖安装器（pip/tool/ollama）与计划执行 | 在用 | 可复用于自动修复与部署前检查 |
| `nethub_runtime/platform` | OS/运行环境探测 | 在用 | 适合复用于安装策略与调度 |
| `nethub_runtime/blueprint` | Blueprint 清单加载、依赖解析、执行占位 | 在用（基础层） | 适合后续接入真实执行器 |
| `nethub_runtime/models` | LiteLLM 路由、Provider 适配、本地模型导入管理 | 在用（部分） | 可作为独立模型网关层 |
| `nethub_runtime/runtime` | 命令执行与策略控制 | 在用 | 可复用于工具执行沙箱 |
| `nethub_runtime/tools` | Tool 抽象及 Shell/Python 工具实现 | 在用（基础层） | 可复用于 workflow step 执行 |
| `nethub_runtime/generated` | 统一产物持久化（trace/feature/dataset 等） | 在用 | 推荐保持单一 Artifact Store |
| `nethub_runtime/training` | 训练 runner CLI（当前为兼容简化实现） | 在用（CLI） | 可复用于训练作业触发入口 |
| `nethub_runtime/integrations` | 外部集成（LINE demo、外部日志拉取） | 在用（桥接辅助） | 可复用于多渠道接入模板 |
| `nethub_runtime/agents` | agent 目录骨架（当前为空） | 占位 | 后续要么补实装，要么移除 |

## 3. 关键子模块（需要重点理解）

## 3.1 core_brain（核心）

- `core_brain/engine.py`
  - 统一引擎入口：`handle()` / `handle_stream()`
  - 对外兼容旧返回结构（`task`、`execution_result`、`workflow_plan`）
- `brain/chat/brain_facade.py`
  - 编排主流程：构建上下文 -> 意图分析 -> 路由 -> 生成回答 -> 记忆写回
- `brain/context/context_builder.py`
  - 五层上下文组装（system/session/task/long_term/execution）
- `brain/llm/*`
  - `model_registry.py` / `prompt_registry.py` / `litellm_client.py`
  - 当前默认支持“安全回退到 mock”，避免开发环境卡死
- `brain/memory/*`
  - session/task/long-term/execution 的 repo + service 分层
- `brain/routing/*`
  - 路由策略和升级策略（按 `confidence` 与 `allow_external`）
- `configs/*`
  - 配置中心：app/models/prompts/routing/schemas

## 3.2 core（兼容层）

- `core/services/core_engine_provider.py`
  - 统一引擎工厂，已固定返回 `CoreBrainEngine`
- `core/routers/core_api.py`
  - 暴露 API：`/handle`、`/handle/stream`、`/core-brain/chat`、`/core/chat`
- `core/main.py`
  - API app 装配，兼容 `/api` 与 `/core` 前缀
- `core/models.py` + `core/enums.py`
  - 通用数据结构与枚举（可跨模块复用）

## 3.3 tvbox（UI 与调试控制台）

- `tvbox/main.py`
  - FastAPI UI 入口
  - 对话入口调用 `core_engine.handle(...)`
  - bridge 场景消息处理、产物回传、调试面板 API
- `tvbox/components/i18n.py`
  - 多语言资源加载与 fallback 逻辑

## 3.4 models（模型网关能力）

- `models/model_router.py`
  - 统一模型路由、多 provider 管理、fallback、冷却机制
- `models/local_model_manager.py`
  - HuggingFace GGUF 模型推荐与导入 Ollama
- `models/openai_provider.py` / `models/ollama_provider.py`
  - provider 级封装（可作为低层适配）

## 3.5 capability + environment + blueprint（执行准备层）

- `capability/registry.py`
  - 本地依赖快照与注册
- `capability/resolver.py`
  - 基于 blueprint 和 runtime profile 计算缺失依赖
- `environment/manager.py`
  - 按安装器执行依赖补齐
- `blueprint/executor.py`
  - 串联“缺失检测 -> 安装 -> 执行占位”

## 4. 可复用组件与落位建议

以下组件建议作为“可复用基础设施”，优先沉淀而不是散落复制：

1. 运行配置与目录管理
- 组件：`nethub_runtime/config/settings.py`
- 建议落位：保留在 `nethub_runtime/config`（全局唯一）

2. 通用数据模型与状态枚举
- 组件：`nethub_runtime/core/models.py`、`nethub_runtime/core/enums.py`
- 建议落位：短期保留 `core`；中期可迁到 `nethub_runtime/common`（减少“core”语义歧义）

3. 命令执行与策略控制
- 组件：`runtime/command_runner.py`、`runtime/policies.py`
- 建议落位：保留 `runtime`，供 tools/environment 共同复用

4. 产物存储
- 组件：`generated/store.py`
- 建议落位：保持唯一实现，禁止各模块重复写文件管理逻辑

5. 能力检测与安装链路
- 组件：`capability/*` + `environment/*`
- 建议落位：保留现位置，供 blueprint/workflow/agent 统一预检

6. 模型路由层
- 组件：`models/model_router.py` + `models/local_model_manager.py`
- 建议落位：保留 `models`，作为 Brain 之外的独立模型网关

7. core_brain 的上下文/路由/记忆分层
- 组件：`core_brain/brain/context|routing|memory`
- 建议落位：仅在 `core_brain` 内扩展，不再回写到 legacy `core`

## 5. 当前建议的“继续清理”顺序

1. `agents/` 当前 3 个文件为空：
- 若近期不用，建议删除整个目录；
- 若准备启用，至少补最小基类与接口定义。

2. `core/config` 中历史配置很多：
- 建议分两类：`still_used` / `legacy`；
- 逐步迁入 `core_brain/configs`。

3. `core/services` 中兼容桩模块：
- 当前为了不打断 import 已保留少量简化实现；
- 后续可在确认无引用后继续收缩。

## 6. 一句话结论

`nethub_runtime` 现阶段应以 `core_brain` 为唯一智能主链路，`core` 仅保留兼容壳；
可复用能力应集中沉淀在 `config/runtime/generated/capability/environment/models` 这几层，避免再次出现 `core/core+` 的分叉与重复。
