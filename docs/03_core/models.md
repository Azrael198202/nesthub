# Core 数据模型说明（完整结构）

本模块定义 AI Core 的核心数据结构，所有服务、API、存储均依赖于这些模型。

---

## 1. TaskSpec

描述一次用户请求的主任务。

```python
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class TaskSpec(BaseModel):
    task_id: str
    intent: str
    user_input: str
    domain: Optional[str]
    constraints: Dict[str, Any]
    required_outputs: List[str]
```

---

## 2. WorkflowSpec & WorkflowStep

描述任务被拆解后的执行流程。

```python
class WorkflowStep(BaseModel):
    step_id: str
    name: str
    depends_on: List[str] = []
    description: Optional[str] = None
    assigned_model: Optional[str] = None
    assigned_tool: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

class WorkflowSpec(BaseModel):
    workflow_id: str
    task_id: str
    mode: Optional[str]
    steps: List[WorkflowStep]
```

---

## 3. BlueprintSpec

描述可复用的执行逻辑蓝图。

```python
class BlueprintSpec(BaseModel):
    blueprint_id: str
    name: str
    purpose: Optional[str]
    inputs: List[str]
    outputs: List[str]
    required_models: Optional[List[str]] = None
    required_tools: Optional[List[str]] = None
    runtime: Optional[str] = None
```

---

## 4. AgentSpec

描述具备角色、目标、能力与策略的智能体。

```python
class AgentSpec(BaseModel):
    agent_id: str
    name: str
    role: str
    goals: List[str]
    model_policy: Optional[Dict[str, str]] = None  # 任务类型到模型名的映射
    tool_policy: Optional[List[str]] = None        # 可用工具列表
    blueprints: Optional[List[str]] = None         # 绑定的蓝图ID
    memory_policy: Optional[Dict[str, Any]] = None # 记忆/上下文策略
```

---

## 5. 设计原则

- 所有模型基于 Pydantic，便于校验和序列化。
- 字段命名与文档、接口保持一致，便于前后端协作。
- 可根据实际需求扩展字段（如 runtime、memory_policy、parameters 等）。
- 策略相关字段（model_policy、tool_policy）支持灵活扩展。

---

## 6. 示例 JSON

### AgentSpec 示例

```json
{
  "agent_id": "agent_001",
  "name": "proposal_writer_jp",
  "role": "Japanese proposal writer",
  "goals": ["write formal proposals", "summarize client requirements"],
  "model_policy": {
    "planning": "strong_reasoning_model",
    "writing": "document_specialized_model",
    "fact_check": "web_summary_model"
  },
  "tool_policy": ["file_reader", "web_research", "doc_export"],
  "blueprints": ["proposal_writer_blueprint"],
  "memory_policy": {"long_term": true, "session_scope": "project"}
}
```

---

如需扩展，可在本文件补充详细字段说明、接口约定等。
