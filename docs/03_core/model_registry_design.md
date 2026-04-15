# AI Core 模型库与模型选择设计方案

本设计文档描述如何在 NestHub AI Core 中实现灵活的模型库（Model Registry），支持本地、云端、Hugging Face 等多种模型的注册、管理与动态选择。

---

## 1. 设计目标
- 支持多种类型模型（本地/云端/Hugging Face）统一注册与管理
- 支持chat、语义分析、知识库检索等多种能力
- 可按需动态选择、切换和路由推理请求
- 便于扩展和维护

## 2. 模型库结构

```python
# core/model_registry.py
class ModelRegistry:
    def register(self, name: str, model: BaseModelAdapter): ...
    def get(self, name: str) -> BaseModelAdapter: ...
    def list_models(self) -> list[str]: ...
    def select(self, task_type: str, **kwargs) -> BaseModelAdapter: ...

# BaseModelAdapter 统一推理接口
class BaseModelAdapter:
    def chat(self, messages: list[dict], **kwargs): ...
    def embed(self, text: str, **kwargs): ...
    def analyze(self, text: str, **kwargs): ...
```

- 本地模型适配器：如 Ollama/Llama.cpp/本地微调模型
- 云端模型适配器：如 OpenAI/Qwen/讯飞等
- Hugging Face模型适配器：自动下载/加载

## 3. 配置与注册

- 支持通过配置文件（如 config/settings.py）注册模型
- 支持运行时动态注册/卸载模型
- 支持模型能力标签（如 chat/embedding/semantic）

## 4. 动态选择与路由

- 根据请求类型、优先级、可用性等动态选择模型
- 支持 API 指定模型或自动选择
- 统一入口：如 `model_registry.select(task_type="chat")`

## 5. 知识库与向量数据库集成

- 支持本地知识库检索（如 FAISS、Milvus、Chroma）
- 支持模型与向量数据库协同工作
- 典型流程：embed -> 检索 -> chat/分析

## 6. 扩展性

- 新增模型只需实现 BaseModelAdapter 并注册
- 支持多模型并行/级联/回退

---

## 7. 示例

```python
from core.model_registry import ModelRegistry
from core.adapters.model_adapter import LocalChatModel, OpenAIModel, HFModel

model_registry = ModelRegistry()
model_registry.register("local-llama", LocalChatModel(...))
model_registry.register("openai-gpt", OpenAIModel(...))
model_registry.register("hf-qwen", HFModel(...))

# 动态选择
model = model_registry.select(task_type="chat")
resp = model.chat([{"role": "user", "content": "你好"}])
```

---

本设计为后续代码实现提供结构和接口参考。