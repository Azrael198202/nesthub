# 🔌 Model Router - Groq & Gemini Free Integration Guide

> 实现 Groq 和 Gemini Free Tier 在 ModelRouter 中的完整支持

---

## 📋 概述

本文档说明如何在 `nethub_runtime/models/model_router.py` 中集成 Groq 和 Google Gemini Free Tier。

**已实现的功能：**
- ✅ `_init_groq()` - Groq 模型初始化
- ✅ `_init_gemini()` - Gemini Free 模型初始化（增强版）
- ✅ 配置热加载支持
- ✅ 延迟监控（特别是 Groq 的超低延迟）
- ✅ 速率限制处理（Gemini Free 的 2 req/min）

---

## 🔍 技术实现细节

### 1. Groq 初始化（`_init_groq()`）

```python
def _init_groq(self, config: dict) -> None:
    """初始化Groq超快推理模型"""
    base_url = config.get('base_url', 'https://api.groq.com')
    try:
        LOGGER.info(f"⚡ Initializing Groq at {base_url}")
        for model in config.get('models', []):
            if model.get('enabled', True):
                model_id = f"groq/{model['name']}"
                self.model_cache[model_id] = {
                    "provider": "groq",
                    "name": model['name'],
                    "base_url": base_url,
                    "latency_ms": model.get('latency_ms', 150),
                    **model
                }
                # Groq 以极低延迟著称
                LOGGER.info(f"  ⚡ Registered: {model_id} (~{model.get('latency_ms', 150)}ms)")
    except Exception as e:
        LOGGER.error(f"Failed to initialize Groq: {e}")
```

**特点：**
- 记录延迟指标（`latency_ms`）用于性能监控
- 使用特殊的日志符号 ⚡ 标识 Groq 模型
- 支持多个 Groq 模型的并行注册

---

### 2. Gemini 增强初始化

Gemini 初始化已更新以支持 Free Tier：

```python
def _init_gemini(self, config: dict) -> None:
    """初始化Gemini模型（包括Free Tier）"""
    try:
        for model in config.get('models', []):
            if model.get('enabled', True):
                model_id = f"google/{model['name']}"
                model_info = {
                    "provider": "google",
                    "name": model['name'],
                    **model
                }
                
                # 特殊处理 Free Tier
                if model.get('is_free_tier', False):
                    model_info['rate_limit_rpm'] = model.get('rate_limit_rpm', 2)
                    LOGGER.info(f"  🆓 Registered Free Tier: {model_id} "
                              f"(context: {model.get('context_window', 0)} tokens, "
                              f"limit: {model.get('rate_limit_rpm')} req/min)")
                else:
                    LOGGER.debug(f"  ✓ Registered: {model_id}")
                
                self.model_cache[model_id] = model_info
    except Exception as e:
        LOGGER.error(f"Failed to initialize Gemini: {e}")
```

**特点：**
- 区分 Free Tier 和付费模型
- 记录速率限制信息
- 在日志中标记 🆓 符号以便识别免费模型

---

## ⚙️ 配置文件结构

### model_config.yaml 提供商配置

```yaml
model_providers:
  # ⚡ Groq 超快推理
  groq:
    type: "groq"
    api_key: "${GROQ_API_KEY}"
    base_url: "https://api.groq.com"
    models:
      - name: "llama-3-70b"
        enabled: true
        context_window: 8192
        latency_ms: 200
      - name: "mixtral-8x7b"
        enabled: true
        context_window: 32000
        latency_ms: 150
      - name: "llama-3.1-405b"
        enabled: false
        context_window: 128000
        latency_ms: 400
    rate_limit_rpm: 30
    timeout: 10
  
  # 🆓 Gemini Free Tier
  gemini_free:
    type: "gemini"
    api_key: "${GEMINI_API_KEY}"
    base_url: "https://generativelanguage.googleapis.com"
    models:
      - name: "gemini-2.0-flash-free"
        enabled: true
        context_window: 1000000
        is_free_tier: true
        rate_limit_rpm: 2
      - name: "gemini-1.5-free"
        enabled: true
        context_window: 1000000
        is_free_tier: true
        rate_limit_rpm: 2
    timeout: 30
```

---

## 🛠️ 路由策略示例

### 快速任务路由（Groq）

```yaml
routing_policies:
  intent_analysis:
    primary: "groq/llama-3-70b"        # ⚡ 超快
    fallback: ["groq/mixtral-8x7b"]
    timeout_sec: 10
    
  fast_extraction:
    primary: "groq/mixtral-8x7b"        # ⚡ MoE + 长上下文
    fallback: ["groq/llama-3-70b"]
    timeout_sec: 15
```

### 长文本路由（Gemini Free）

```yaml
routing_policies:
  document_generation:
    primary: "google/gemini-2.0-flash-free"  # 🆓 最新
    fallback: ["google/gemini-1.5-free"]    # 🆓 稳定
    timeout_sec: 45
    use_streaming: true
    max_tokens: 8000
  
  long_context_analysis:
    primary: "google/gemini-1.5-free"       # 🆓 强推理
    fallback: ["google/gemini-2.0-flash-free"]
    context_needed: 100000                  # 充分利用长上下文
```

---

## 📊 模型选择决策树

```python
async def select_optimal_model(task_type: str, input_length: int) -> str:
    """
    根据任务类型和输入长度自动选择最优模型
    """
    
    # 1. 检查输入长度
    if input_length > 30000:
        # 必须使用长上下文模型
        return "google/gemini-1.5-free"  # 100万 tokens
    
    # 2. 检查是否需要实时响应
    if task_type in ["intent_analysis", "real_time_chat", "fast_extraction"]:
        # 使用 Groq 超快推理
        return model_router.select_model(task_type)  # groq/llama-3-70b
    
    # 3. 长文本密集型任务
    if task_type in ["document_generation", "code_review", "summarization"]:
        # 使用 Gemini Free 长上下文
        return "google/gemini-1.5-free"
    
    # 4. 默认选择：平衡速度和成本
    return "groq/mixtral-8x7b"
```

---

## 🚀 使用示例

### 示例 1：快速意图分析

```python
from nethub_runtime.models.model_router import ModelRouter

router = ModelRouter("config/model_config.yaml")

# 自动选择 Groq 进行快速推理
response = await router.invoke(
    task_type="intent_analysis",
    prompt="用户说：我想订阅高级版本"
)

# 预期延迟：<200ms
# 成本：$0
```

### 示例 2：长文本文档分析

```python
# 自动选择 Gemini Free 处理长文本
with open("research_paper.pdf.txt", "r") as f:
    document = f.read()  # 可能 100K+ tokens

response = await router.invoke(
    task_type="document_generation",
    prompt=f"总结这篇论文：\n{document}"
)

# 支持上下文：100万 tokens
# 成本：$0
```

### 示例 3：混合使用

```python
async def analyze_codebase(repo_path: str):
    """分析整个代码库"""
    
    # Step 1: 用 Gemini Free 读取整个仓库（100万token 上下文）
    repo_contents = read_entire_repo(repo_path)
    
    understanding = await router.invoke(
        task_type="long_context_analysis",
        prompt=f"分析这个项目的架构：\n{repo_contents}"
    )
    
    # Step 2: 用 Groq 快速提取关键信息
    key_points = await router.invoke(
        task_type="fast_extraction",
        prompt=f"从上述分析中提取关键架构点"
    )
    
    return {
        "analysis": understanding,      # 详细分析（Gemini Free）
        "key_points": key_points        # 快速提取（Groq）
    }
```

---

## 🔄 错误处理与回退

### 自动回退链

```python
# 当 Groq 不可用时，自动回退
routing_policies:
  intent_analysis:
    primary: "groq/llama-3-70b"
    fallback: [
        "groq/mixtral-8x7b",           # Groq 备选
        "google/gemini-2.0-flash-free", # Gemini 备选
        "openai/gpt-3.5-turbo"          # 最后备选
    ]
```

### 速率限制处理

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=10, max=32)
)
async def invoke_gemini_with_retry(prompt: str):
    """处理 Gemini Free 的速率限制"""
    try:
        return await router.invoke("document_generation", prompt)
    except RateLimitError as e:
        LOGGER.warning(f"Hit rate limit, retrying: {e}")
        raise
```

---

## 📈 性能监控

### 跟踪延迟

```python
class LatencyMonitor:
    """监控模型延迟"""
    
    def __init__(self):
        self.latencies = {}
    
    def record_latency(self, model: str, latency_ms: float):
        if model not in self.latencies:
            self.latencies[model] = []
        self.latencies[model].append(latency_ms)
    
    def get_average_latency(self, model: str) -> float:
        if model not in self.latencies or not self.latencies[model]:
            return 0
        return sum(self.latencies[model]) / len(self.latencies[model])
    
    def report(self):
        """生成性能报告"""
        print("Average Latencies:")
        for model, latencies in self.latencies.items():
            avg = sum(latencies) / len(latencies)
            print(f"  {model}: {avg:.1f}ms")

# 使用
monitor = LatencyMonitor()
for model in ["groq/llama-3-70b", "google/gemini-1.5-free"]:
    # ... 测试调用 ...
    monitor.record_latency(model, latency_ms)

monitor.report()
```

---

## 🎯 最佳实践总结

| 实践 | 说明 |
|-----|------|
| **使用 Groq 进行实时任务** | 意图分析、快速聊天、流式处理 |
| **使用 Gemini Free 进行长文本** | 文档生成、代码审查、批处理 |
| **配置回退链** | 始终有备选方案 |
| **监控成本和性能** | 定期查看使用统计 |
| **处理速率限制** | 使用重试机制和队列 |
| **启用热加载** | 快速调整模型策略 |

---

## 📞 故障排除

### 问题：Groq API 返回 401 错误
**解决方案：** 检查 `GROQ_API_KEY` 是否正确设置
```bash
echo $GROQ_API_KEY  # 应显示你的 API key
```

### 问题：Gemini Free 速度很慢
**解决方案：** 这是免费服务的正常表现，考虑：
1. 使用 Groq 替代快速任务
2. 离线处理（非实时）
3. 升级到付费 Gemini 版本

### 问题：超过速率限制（Gemini Free）
**解决方案：** 使用重试逻辑或排队机制

---

## 🔗 相关文档

- [LiteLLM 路由设计](./litellm_routing_design.md)
- [Groq API 文档](https://console.groq.com/docs)
- [Google Gemini API](https://ai.google.dev/)
- [快速开始指南](./GROQ_GEMINI_QUICKSTART.md)
