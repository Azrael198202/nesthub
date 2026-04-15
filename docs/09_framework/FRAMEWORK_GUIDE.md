# NestHub 完整框架文档导航

---

## 📚 文档体系

本项目文档从**原理设计**到**完整实现**，分为以下层次：

### 第1层：系统架构总体设计

| 文档 | 位置 | 用途 | 阅读方式 |
|------|------|------|---------|
| **项目上下文** | `docs/01_architecture/project_context.md` | 理解系统总体架构和设计理念 | 📖 详细阅读 |
| **系统架构图** | `docs/01_architecture/architecture.mmd` | 可视化整体架构 | 📊 参考 |

### 第2层：核心模块设计（原始设计文档）

| 文档 | 位置 | 内容 | 用途 |
|------|------|------|------|
| **AI Core 设计文档** | `docs/03_core/ai_core_for_generate.md` | 完整的功能设计与责任定义 | 理论基础 |
| **可编码规范** | `docs/03_core/ai_core_for_generate_complete.md` | 插件化架构设计与最佳实践 | 规范参考 |
| **模型全景清单** | `docs/03_core/core_model.md` | 系统可用的所有模型与能力 | 模型选择 |

### 第3层：框架实现指南（新创建）

下列文档为本次创建的**可直接用于代码生成**的实现指南：

#### ✅ **LiteLLM 模型路由设计**
**文档**: `docs/02_router/litellm_routing_design.md`

**核心内容**:
- 统一LLM接口管理，屏蔽模型差异
- 任务类型到模型的自动映射
- 模型选择、回退策略、配置热更新
- 与AI Core集成点

**代码结构**:
```
nethub_runtime/models/
├── model_router.py         # LiteLLM核心
├── model_config.yaml       # 模型配置
└── prompts.py              # 系统提示词
```

**何时使用**: 
- 需要调用任何LLM进行推理
- 需要支持多种模型（本地/云端）
- 需要自动模型选择与回退

---

#### ✅ **LangGraph Workflow & Agent 框架**
**文档**: `docs/03_workflow/langgraph_agent_framework.md`

**核心内容**:
- 以LangGraph为核心的工作流执行
- 蓝图(Blueprint)自动编译为LangGraph图
- Agent自主推理与持续行动
- 完整的状态管理和执行控制

**代码结构**:
```
nethub_runtime/core/
├── workflows/
│   ├── base_workflow.py    # 基础工作流模板
│   ├── blueprint_compiler.py # 蓝图编译器
│   └── executor.py         # 执行引擎
├── agents/
│   ├── agent_spec.py       # Agent规范
│   ├── agent_builder.py    # Agent构建器
│   └── reasoning_agent.py  # 推理Agent（ReAct）
└── tools/
    ├── registry.py         # 工具注册表
    └── base_tool.py        # 工具基类
```

**何时使用**:
- 需要执行多步骤任务（Workflow）
- 需要自主思考与决策（Agent）
- 需要支持人机协作和中断恢复

---

#### ✅ **AI Core 集成指南**
**文档**: `docs/03_core/integration_guide.md`

**核心内容**:
- 将LiteLLM + LangGraph完整集成
- 启动流程详解（main.py → tvbox/main.py）
- 执行流程示例（Workflow vs Agent）
- 配置文件、最佳实践、监控

**关键启动入口**:
```
nethub_runtime/app/main.py       # 标准启动
└─ 初始化所有组件 ← 参见集成指南

nethub_runtime/tvbox/main.py     # TVBox启动
└─ 复用标准启动 + 本地运行时 ← 参见集成指南
```

---

## 🎯 工作流图：如何使用这些文档

```
新增功能需求
  ↓
[选择合适的文档]
  ├─ 需要调用LLM? ──→ docs/02_router/litellm_routing_design.md
  ├─ 需要多步骤任务? ──→ docs/03_workflow/langgraph_agent_framework.md
  ├─ 需要自主Agent? ──→ docs/03_workflow/langgraph_agent_framework.md
  └─ 需要集成整体? ──→ docs/03_core/integration_guide.md
  ↓
[参照代码结构部分]
  ↓
[实现代码]
  ↓
[参照启动流程]
  ↓
[集成到main.py或tvbox/main.py]
```

---

## 📋 快速参考表

### 按任务类型

| 任务 | 文档 | 代码样本 | 配置文件 |
|------|------|--------|---------|
| 添加新LLM模型 | litellm_routing | ModelRouter类 | model_config.yaml |
| 创建新Workflow | langgraph_framework | BaseWorkflow类 | blueprints/*.yaml |
| 创建新Agent | langgraph_framework | ReasoningAgent类 | agent_spec.py |
| 添加新工具 | langgraph_framework | BaseTool类 | tools/registry.py |
| 修改启动流程 | integration_guide | app/main.py | 无 |
| TVBox本地运行 | integration_guide | tvbox/main.py | 无 |

### 按模块

| 模块 | 主要文档 | 配置文件 | 启动流程 |
|------|--------|--------|---------|
| **LiteLLM Router** | litellm_routing_design.md | model_config.yaml | main.py L40 |
| **LangGraph Workflow** | langgraph_agent_framework.md | blueprints/ | main.py L50 |
| **LangGraph Agent** | langgraph_agent_framework.md | agent_spec.py | main.py L55 |
| **工具系统** | langgraph_agent_framework.md | tools/ | main.py L45 |
| **AI Core** | ai_core_for_generate.md | 无 | main.py L60 |

---

## 🔄 执行流程快速指标

### Workflow 执行流程
```
用户输入
  ↓ AI Core 意图分析 (LiteLLM)
  ↓ 判断：不需要Agent
  ↓ 选择/编译Blueprint
  ↓ LangGraph Workflow 执行
  ├─ 步骤1: LLM推理 (LiteLLM)
  ├─ 步骤2: 工具调用 (Tool Registry)
  ├─ 步骤3: 代码执行
  └─ ... 循环直到完成
  ↓ 结果整合
  ↓ 返回用户
```

### Agent 执行流程
```
用户输入
  ↓ AI Core 意图分析 (LiteLLM)
  ↓ 判断：需要Agent
  ↓ 生成Agent规范 (LiteLLM)
  ↓ LangGraph Agent 初始化
  ↓ 推理循环 (ReAct)
  ├─ 思考 (LiteLLM)
  ├─ 计划 (LiteLLM)
  ├─ 行动 (工具/代码)
  └─ 循环直至final_answer
  ↓ 返回用户
```

---

## 💻 代码模版快速参考

### 1. 调用LLM推理
```python
# 参见: docs/02_router/litellm_routing_design.md

response = await model_router.invoke(
    task_type="intent_analysis",
    prompt="用户输入"
)
```

### 2. 执行Workflow
```python
# 参见: docs/03_workflow/langgraph_agent_framework.md

blueprint = blueprint_compiler.compile("path/to/blueprint.yaml")
result = await workflow_executor.execute_workflow(
    workflow_graph=blueprint,
    initial_input="用户输入",
    context=context
)
```

### 3. 执行Agent
```python
# 参见: docs/03_workflow/langgraph_agent_framework.md

agent_spec = await agent_builder.generate_agent_spec(task, workflow)
agent = await agent_builder.build_agent(agent_spec)
result = await agent.think_and_act("用户输入", context)
```

### 4. 注册新工具
```python
# 参见: docs/03_workflow/langgraph_agent_framework.md

class MyTool(BaseTool):
    async def execute(self, input_data):
        return result

tool_registry.register(MyTool("my_tool", "描述"))
```

---

## 📊 文档地图（树形）

```
docs/
├── 01_architecture/
│   ├── project_context.md          ← 系统总体设计
│   └── architecture.mmd            ← 架构图
│
├── 02_router/
│   └── litellm_routing_design.md   ← ✅ 新创建：LLM路由
│
├── 03_core/
│   ├── ai_core_for_generate.md     ← 原始设计
│   ├── ai_core_for_generate_complete.md ← 原始设计（完整）
│   ├── core_model.md               ← 模型清单
│   └── integration_guide.md        ← ✅ 新创建：集成指南
│
└── 03_workflow/
    └── langgraph_agent_framework.md ← ✅ 新创建：Workflow/Agent框架
```

---

## 🚀 快速开始

### 场景1：理解整体架构
```
1. 读 projects_context.md（获得上下文）
2. 读 integration_guide.md（理解集成）
3. 看 architecture.mmd（可视化）
```

### 场景2：添加新LLM模型
```
1. 读 docs/02_router/litellm_routing_design.md
2. 编辑 config/model_config.yaml
3. 修改 nethub_runtime/models/model_router.py（如需要）
```

### 场景3：实现新功能（Workflow）
```
1. 读 docs/03_workflow/langgraph_agent_framework.md
2. 创建 examples/blueprints/my_feature.yaml
3. 或 创建 nethub_runtime/core/workflows/my_workflow.py
4. 在 app/main.py 中注册
```

### 场景4：启动应用
```
python nethub_runtime/app/main.py        # 标准启动
python nethub_runtime/tvbox/main.py      # TVBox启动
```

---

## ✅ 文档棋盘（检查清单）

| 文档 | 创建时间 | 用途 | 完成度 |
|------|--------|------|--------|
| project_context.md | 原始 | 系统设计 | ✅ |
| ai_core_for_generate.md | 原始 | Core设计 | ✅ |
| ai_core_for_generate_complete.md | 原始 | 完整规范 | ✅ |
| core_model.md | 原始 | 模型清单 | ✅ |
| **litellm_routing_design.md** | 本次创建 | LLM路由 | ✅ |
| **langgraph_agent_framework.md** | 本次创建 | Workflow/Agent | ✅ |
| **integration_guide.md** | 本次创建 | 集成指南 | ✅ |

---

## 📞 联系关键文件

### 启动入口关键文件
- `nethub_runtime/app/main.py` - 标准应用启动 ← 参见integration_guide.md
- `nethub_runtime/tvbox/main.py` - TVBox启动 ← 参见integration_guide.md

### 模型路由关键文件
- `nethub_runtime/models/model_router.py` - 核心 ← 参见litellm_routing_design.md
- `config/model_config.yaml` - 配置 ← 参见litellm_routing_design.md

### 工作流/Agent关键文件
- `nethub_runtime/core/workflows/base_workflow.py` ← 参见langgraph_agent_framework.md
- `nethub_runtime/core/agents/reasoning_agent.py` ← 参见langgraph_agent_framework.md
- `examples/blueprints/*.yaml` ← 参见langgraph_agent_framework.md

---

## 🎓 学习路径建议

### 初学者
1. `project_context.md` - 了解系统
2. `integration_guide.md` - 理解集成
3. 运行 `python nethub_runtime/app/main.py`
4. 查看日志理解启动流程

### 开发者
1. 选择模块（LiteLLM / LangGraph / 工具）
2. 阅读对应文档
3. 查看代码示例
4. 修改配置文件或代码
5. 测试并集成

### 架构师
1. `ai_core_for_generate.md` - 设计理念
2. `ai_core_for_generate_complete.md` - 完整规范
3. `integration_guide.md` - 集成方案
4. 评估扩展性和可维护性

---

## 🔗 关键链接映射

| 概念 | 相关文档 | 代码位置 |
|------|--------|--------|
| 意图分析 | litellm_routing_design.md | core/main.py |
| 任务规划 | langgraph_agent_framework.md | core/workflows/*.py |
| 工作流执行 | langgraph_agent_framework.md | core/workflows/executor.py |
| Agent推理 | langgraph_agent_framework.md | core/agents/reasoning_agent.py |
| 蓝图编译 | langgraph_agent_framework.md | core/workflows/blueprint_compiler.py |
| 模型选择 | litellm_routing_design.md | models/model_router.py |
| 工具调用 | langgraph_agent_framework.md | core/tools/*.py |
| 启动流程 | integration_guide.md | app/main.py + tvbox/main.py |

---

## 📝 版本说明

| 版本 | 日期 | 变化 |
|------|------|------|
| v1.0 | 2024原始 | AI Core设计文档集 |
| v2.0 | 2026/04 | + LiteLLM路由设计 |
| v2.0 | 2026/04 | + LangGraph框架设计 |
| v2.0 | 2026/04 | + 集成指南与启动流程 |

---

## 🎯 总结

**本次创建的三个文档形成完整的可执行架构**：

1. **litellm_routing_design.md** → 解决"用哪个模型"的问题
2. **langgraph_agent_framework.md** → 解决"如何执行"的问题  
3. **integration_guide.md** → 解决"如何集成"的问题

**所有文档均包含**：
- 架构图（Mermaid）
- 完整代码框架
- 配置示例
- 执行流程
- 最佳实践

**直接形成可生成的代码框架**，可用于：
- 代码生成AI直接参考
- 团队开发指南
- 系统扩展基础
- 新功能集成模板

---
