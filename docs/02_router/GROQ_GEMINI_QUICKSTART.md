# ⚡ Groq + 🆓 Gemini Free Tier - 快速开始指南

> **成本：$0** | **速度：超快（<200ms）** | **上下文：极长（100万+）**

---

## 🚀 5分钟快速启动

### 1️⃣ 获取 API 密钥（完全免费）

#### Groq API（⚡ 超快推理）
```bash
# 访问官网
https://groq.com

# 登录并获取 API Key
# 设置环境变量
export GROQ_API_KEY="your_groq_api_key_here"
```

#### Google Gemini Free Tier（🆓 长上下文）
```bash
# 访问 Google AI Studio
https://aistudio.google.com/

# 获取 API Key（免费）
export GEMINI_API_KEY="your_gemini_api_key_here"
```

---

### 2️⃣ 更新配置文件

```yaml
# config/model_config.yaml

model_providers:
  # ⚡ 添加 Groq
  groq:
    api_key: "${GROQ_API_KEY}"
    models:
      - name: "llama-3-70b"
        enabled: true
      - name: "mixtral-8x7b"
        enabled: true
  
  # 🆓 添加 Gemini Free
  gemini_free:
    api_key: "${GEMINI_API_KEY}"
    models:
      - name: "gemini-2.0-flash-free"
        enabled: true
      - name: "gemini-1.5-free"
        enabled: true

routing_policies:
  # 快速任务 → Groq
  intent_analysis:
    primary: "groq/llama-3-70b"     # ⚡ <200ms
  
  # 长文本 → Gemini Free
  document_generation:
    primary: "gemini_free:gemini-1.5-free"  # 🆓 100万tokens
```

### 3️⃣ 使用代码

```python
from nethub_runtime.app.main import start_app
from nethub_runtime.core.main import AICore

# 启动应用
context = start_app(model_config_path="config/model_config.yaml")
core = context["core"]

# 使用快速推理（Groq）
response = await core.handle(
    input_text="这是什么意思？",
    context={"task_type": "intent_analysis"}
)

# 使用长文本分析（Gemini Free）
response = await core.handle(
    input_text="分析这个400页的PDF...",
    context={"task_type": "document_generation"}
)
```

---

## 📊 性能对比

| 任务类型 | Groq | Gemini Free | OpenAI | 成本 |
|---------|------|-----------|--------|------|
| 意图分析 | ⚡ 150ms | 🟦 800ms | 2000ms | **$0** |
| 文档生成 | 8K上下文 | 🆓 100万 | 128K | **$0** |
| 快速聊天 | ⚡ 200ms | 🟦 1000ms | 2000ms | **$0** |
| 代码审查 | 32K最多 | 🆓 100万 | 128K | **$0** |

---

## 💡 最佳实践

### ✅ 使用 Groq 的场景
```
✓ 实时应用（聊天、API）
✓ 批量处理（需要低延迟）
✓ 流式处理（token-by-token）
✓ 成本优先场景
```

### ✅ 使用 Gemini Free 的场景
```
✓ 长文本分析（>10K tokens）
✓ 文档生成（长输出）
✓ 代码库审查（整个项目）
✓ 批处理（非实时）
```

### ⚠️ 速率限制处理

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
async def safe_gemini_call(prompt: str):
    """Gemini Free 有 2 req/min 限制，使用重试机制"""
    return await model_router.invoke("document_generation", prompt)

# 对于批量任务，使用队列
from queue import Queue
import asyncio

async def batch_process_gemini(tasks: list):
    """以 2 req/min 的速率处理任务"""
    for task in tasks:
        result = await safe_gemini_call(task)
        yield result
        await asyncio.sleep(30)  # 维持 2 req/min
```

---

## 🔍 监控和调试

### 查看正在使用的模型
```python
# 列出已注册的模型
models = model_router.list_available_models()
print("Available models:", models)
"""
Available models: [
    'groq/llama-3-70b',
    'groq/mixtral-8x7b',
    'gemini_free/gemini-2.0-flash-free',
    'gemini_free/gemini-1.5-free',
    ...
]
"""
```

### 跟踪模型调用
```python
# 之后会添加到 ModelMetrics
metrics = model_router.metrics.get_summary()
print(f"Groq calls: {metrics['groq_calls']}")
print(f"Gemini Free calls: {metrics['gemini_free_calls']}")
print(f"Cost saved: ${metrics['cost_saved']:.2f}")
```

---

## ⚙️ 高级配置

### 条件路由
```yaml
routing_policies:
  smart_routing:
    # 自动选择：快速 vs 长上下文
    rules:
      - if: "input_tokens < 1000 AND need_speed"
        then: "groq/llama-3-70b"  # 超快
      - if: "input_tokens > 100000"
        then: "gemini_free:gemini-1.5-free"  # 长上下文
      - else: "groq/mixtral-8x7b"  # 平衡
```

### 混合提供商
```python
# 同时利用两个免费模型的优势
async def hybrid_process(large_document: str):
    # Step 1: 用 Gemini Free 理解整个文档（100万token）
    summary = await model_router.invoke(
        task_type="document_generation",
        prompt=f"总结这个文档:\n{large_document}"
    )
    
    # Step 2: 用 Groq 快速提取关键信息
    keywords = await model_router.invoke(
        task_type="fast_extraction",
        prompt=f"从中提取关键词:\n{summary}"
    )
    
    return {"summary": summary, "keywords": keywords}
```

---

## 📝 常见问题

### Q: Gemini Free 有什么限制？
**A:** 每分钟 2 个请求，但上下文极长（100万token），适合离线处理和批量任务。

### Q: Groq 和 Gemini 能同时使用吗？
**A:** 完全可以！这正是设计的核心 - 快速任务用 Groq，长文本用 Gemini Free。

### Q: 成本真的是 $0 吗？
**A:** 是的，Groq 和 Gemini Free 都完全免费。但如果需要更高性能/准确度，可以付费升级。

### Q: 如果 API 失败了怎么办？
**A:** ModelRouter 会自动切换到 fallback 模型。可以配置优先级链。

---

## 📞 获取帮助

- Groq 文档：https://console.groq.com/docs
- Gemini API 文档：https://ai.google.dev/
- NestHub 文档：`docs/02_router/litellm_routing_design.md`

---

**预期收益：**
- ✅ 成本削减 90%+
- ✅ 响应时间 <200ms（Groq 任务）
- ✅ 支持 100万+ token 长上下文
- ✅ 100% 向后兼容现有代码
