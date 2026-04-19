# NestHub Workflow 端到端测试用例集

> **适用系统**：`nethub_runtime` (本地 7788) + `api/public_api` (Railway 8080)  
> **执行入口**：`AICore.handle()` / `AICore.handle_stream()`  
> **用例状态**：📝 待转为代码

---

## 目录

| 编号 | 场景名称 | 核心流程 | 重点验证 |
|------|---------|---------|---------|
| TC-01 | 家庭成员智能体创建（多轮对话补全信息） | manage_information_agent | 缺失字段询问 → 补全 → 持久化 |
| TC-02 | 出差行程规划文档生成（Workflow + Artifact） | analyze → generate → persist | Artifact 文件存在 & 内容非空 |
| TC-03 | 结果不达标触发 Repair Loop 再执行 | Workflow + repair | repair_iteration ≥ 1, 最终 OK |
| TC-04 | LINE 图片上传 → OCR 处理 → 结果返回 | ocr_extract via download_url | 文件下载到本地 received/ |
| TC-05 | 费用记录 → 查询 → 分组汇总 | extract_records + aggregate_query | records 数量 & 汇总数值 |
| TC-06 | 查询智能体知识 → 无命中 → 用户补充 → 再查询 | query_information_knowledge | 首次空结果 → 补充后有命中 |
| TC-07 | Agent 路径：创建 ReAct 推理 Agent 并执行 | need_agent=True, agent path | agent_result.success=True |
| TC-08 | 完整 handle_stream 事件序列验证 | handle_stream SSE events | 所有 lifecycle events 按序到达 |

---

## TC-01  家庭成员智能体创建（多轮对话补全信息）

### 场景描述
用户想要为爸爸创建一个联系人智能体，但初始请求信息不完整。NestHub 识别意图后进入
`manage_information_agent` 步骤，每轮返回 `next_action: "ask_user"` 和下一个问题，
直到所有必填字段齐备后完成创建。

### 前置条件
- `AICore` 已初始化，`session_id` 固定为 `"test_family_agent_session"`
- Model router 可正常路由（或使用 fallback rule-based 模式）

### 测试步骤

#### Step 1 — 用户发起初始请求（信息不完整）

**输入**
```
input_text: "帮我建一个爸爸的联系人智能体"
context:
  user_id: "u_test"
  session_id: "test_family_agent_session"
```

**预期 Intent 分析结果**
```json
{
  "intent": "create_information_agent",
  "domain": "agent_management",
  "constraints": { "need_agent": false }
}
```

**预期 Workflow 步骤**
```
[manage_information_agent]
```

**预期响应结构**
```json
{
  "reply": "<包含下一个问题的文本>",
  "execution_result": {
    "steps": [{
      "name": "manage_information_agent",
      "outputs": {
        "dialog_state": { "next_action": "ask_user" },
        "message": "<询问用户的问题>"
      }
    }]
  }
}
```

**断言**
- `result["execution_result"]["steps"][0]["outputs"]["dialog_state"]["next_action"] == "ask_user"`
- `result["reply"]` 包含问句（以"？"结尾或包含疑问词）
- `result["execution_result"]["steps"][0]["outputs"]["agent"]` 中 `entity_label` 不为空

---

#### Step 2 — 用户回答姓名

**输入**（同一 session）
```
input_text: "爸爸，叫张国华"
context:
  session_id: "test_family_agent_session"
```

**预期响应**
- `dialog_state.next_action` 仍为 `"ask_user"`（还有未收集字段）
- `agent.known_fields` 包含 `name: "张国华"`
- `reply` 提问下一个字段（如手机号）

**断言**
- `result["execution_result"]["steps"][0]["outputs"]["agent"]["known_fields"]` 包含 `"name"`
- `result["execution_result"]["steps"][0]["outputs"]["dialog_state"]["next_action"] == "ask_user"`

---

#### Step 3 — 用户补充手机号和生日

**输入**
```
input_text: "手机 138-0000-1234，生日是 1960 年 3 月 15 日"
context:
  session_id: "test_family_agent_session"
```

**预期响应**
- `known_fields` 包含 `phone` 和 `birthday`
- 若所有必填字段已满足：`next_action` 变为 `"finalize_agent"` 或仍为 `"ask_user"`（视 schema 配置）

**断言**
- `result["execution_result"]["steps"][0]["outputs"]["agent"]["known_fields"]` 至少包含 `"name"`, `"phone"`

---

#### Step 4 — 用户主动完成创建

**输入**
```
input_text: "好了，创建完成吧"
context:
  session_id: "test_family_agent_session"
```

**预期响应**
- `dialog_state.next_action == "finalize_agent"` 或步骤输出包含 `"completion_ready": true`
- `agent.agent_id` 不为空
- `reply` 含有"已创建"/"完成"之类的确认语

**断言**
```python
outputs = result["execution_result"]["steps"][0]["outputs"]
assert outputs.get("dialog_state", {}).get("next_action") in ("finalize_agent", "complete")
assert outputs.get("agent", {}).get("agent_id")
```

---

#### Step 5 — 验证智能体已持久化

**操作**：通过 `session_store` 直接查询 session，或再次 `handle` 查询知识

**输入**
```
input_text: "爸爸的手机号是多少"
context:
  session_id: "test_family_agent_session"
```

**预期 Intent**
```json
{ "intent": "query_agent_knowledge", "domain": "knowledge_ops" }
```

**预期步骤**：`[query_information_knowledge]`

**断言**
- `result["reply"]` 包含 `"138"` 或 `"13800001234"`
- `result["execution_result"]["steps"][0]["outputs"]["answer"]` 不为空

---

### 失败情形 & 处理预期

| 情形 | 预期行为 |
|------|---------|
| 用户回答无关内容（"今天天气好"） | `next_action` 仍为 `ask_user`，重新提问 |
| 用户中途放弃（空输入） | 会话状态保留，下次进入同 session 继续 |
| model_router 不可用 | fallback rule-based 模式接管，流程不中断 |

---

## TC-02  出差行程规划文档生成

### 场景描述
用户请求 NestHub 根据出差信息生成一份大阪行程简报 Word/Markdown 文件。
NestHub 识别为 `prepare_trip_brief` 意图，规划多步 Workflow，最终产出文件 Artifact。

### 前置条件
- 无需预置智能体
- `NETHUB_GENERATED_ROOT` 指向可写目录（或使用 `tmp_path` fixture）

### 测试步骤

#### Step 1 — 用户发起请求

**输入**
```
input_text: "帮我整理下周一到周五大阪出差的行程简报，包含日程安排和注意事项"
context:
  user_id: "u_biz"
  metadata:
    trip_destination: "大阪"
    trip_dates: "2026-04-27 ~ 2026-05-01"
```

**预期 Intent**
```json
{
  "intent": "prepare_trip_brief",
  "domain": "general",
  "output_requirements": ["analysis", "artifact", "summary"]
}
```

**预期 Workflow 步骤（含顺序）**
```
1. analyze_workflow_context   (executor: llm)
2. generate_workflow_artifact (executor: tool)
3. persist_workflow_output    (executor: tool)
```

**断言**
```python
step_names = [s["name"] for s in result["workflow"]["steps"]]
assert "analyze_workflow_context" in step_names
assert "generate_workflow_artifact" in step_names
assert "persist_workflow_output" in step_names
# 顺序验证
assert step_names.index("analyze_workflow_context") < step_names.index("generate_workflow_artifact")
assert step_names.index("generate_workflow_artifact") < step_names.index("persist_workflow_output")
```

---

#### Step 2 — 执行结果验证

**对 `result["execution_result"]` 的断言**
```python
er = result["execution_result"]
# 每步都有 inputs/outputs
for step in er["steps"]:
    assert step["inputs"]
    assert step["outputs"]

# generate_workflow_artifact 产出了文件
gen_step = next(s for s in er["steps"] if s["name"] == "generate_workflow_artifact")
assert gen_step["outputs"]["status"] in ("ok", "success", "received")
artifact_path = gen_step["outputs"].get("artifact_path")
assert artifact_path

# 文件真实存在
from pathlib import Path
assert Path(artifact_path).exists()
assert Path(artifact_path).stat().st_size > 0
```

---

#### Step 3 — Artifact 索引验证

```python
artifacts = result.get("artifacts", [])
artifact_types = {a["artifact_type"] for a in artifacts}
assert "document" in artifact_types or "trace" in artifact_types

# artifact_index 包含 document 类型
artifact_index = result.get("artifact_index", {})
assert any(artifact_index.values())
```

---

#### Step 4 — Reply 摘要验证

```python
reply = result["reply"]
assert len(reply) > 20
# 包含出发地/目的地或日期关键词
assert any(kw in reply for kw in ["大阪", "行程", "出差", "下周"])
```

---

## TC-03  结果不达标触发 Repair Loop 再执行

### 场景描述
首次执行时，蓝图解析返回空（模拟缺少匹配蓝图），触发 `capability_gap_detected`。
`RuntimeRepairService` 识别缺口后构建修复 Workflow，第二轮执行成功完成。

### 测试方法
使用 `monkeypatch` 替换 `blueprint_resolver.resolve` 首次返回空列表，第二次返回真实蓝图。

### 测试步骤

#### Step 1 — 构造触发缺口的条件

```python
call_count = 0
original_resolve = core.blueprint_resolver.resolve

def patched_resolve(task, workflow):
    nonlocal call_count
    call_count += 1
    if call_count == 1:
        return []  # 第一次：无蓝图 → 触发缺口
    return original_resolve(task, workflow)  # 第二次：正常

core.blueprint_resolver.resolve = patched_resolve
```

#### Step 2 — 执行

**输入**
```
input_text: "记录今天午餐花了 80 元"
context:
  user_id: "u_repair_test"
```

#### Step 3 — 验证 autonomous_implementation_trace

```python
trace = result["execution_result"]["autonomous_implementation_trace"]
assert trace["capability_gap_detected"] is True
assert trace["autonomous_implementation_supported"] is True
assert trace["generated_patch_registered"] is True
assert trace["generated_artifact_type"] == "blueprint"
assert trace["trigger_reason"] == "no_reusable_blueprint_resolved"
```

#### Step 4 — 验证最终执行仍然成功

```python
# 尽管蓝图缺口被检测到，执行应该仍然完成（fallback 执行路径）
assert result["execution_result"]["steps"]
assert result["execution_result"]["execution_type"] == "workflow"
# 最终 reply 非空
assert result["reply"]
```

#### Step 5 — handle_stream 的 repair 事件验证（扩展）

使用 `handle_stream` 时，验证以下事件按序出现：
```
intent_analyzed
→ workflow_planned
→ execution_started  (或类似)
→ repair_triggered   (repair loop 触发)
→ repair_completed
→ lifecycle_end
```

```python
events = []
async for chunk in core.handle_stream(input_text="记录修复测试花费 30 元", context={}):
    events.append(chunk["event"])

event_set = set(events)
assert "intent_analyzed" in event_set
assert "workflow_planned" in event_set
assert "lifecycle_end" in event_set or "lifecycle_error" in event_set
```

---

## TC-04  LINE 图片上传 → OCR 处理 → 本地文件下载

### 场景描述
模拟 LINE bridge 消息，附件中包含图片 URL（Railway → 本地的跨主机场景）。
NestHub 接收消息后识别为 `ocr_task`，`handle_ocr_extract_step` 通过 `download_url`
下载文件到本地 `received/` 目录。

### 前置条件
- 需要一个可访问的图片 URL（测试时使用本地 HTTP mock server 或真实 Railway URL）
- 或使用 `responses` / `httpretty` 拦截 HTTP 请求，返回 fixture 图片字节

### 测试步骤

#### Step 1 — 构造 bridge 消息

```python
import httpretty  # or responses

# 注册 mock HTTP 响应
httpretty.register_uri(
    httpretty.GET,
    "https://mock-railway.app/api/received/20260419/test_image.jpg",
    body=open("test/fixtures/sample_image.jpg", "rb").read(),
    content_type="image/jpeg",
)

bridge_message = {
    "bridge_message_id": "bm_ocr_test_001",
    "text": "识别图片内容: test_image.jpg",
    "external_user_id": "U_test",
    "external_chat_id": "C_test",
    "external_message_id": "610001",
    "attachments": [{
        "file_name": "test_image.jpg",
        "content_type": "image/jpeg",
        "input_type": "image",
        "stored_path": "",  # 跨主机场景：stored_path 不可访问
        "download_url": "https://mock-railway.app/api/received/20260419/test_image.jpg",
        "source_message_type": "image",
        "external_message_id": "610001",
    }]
}
```

#### Step 2 — 通过 core_engine 处理

```python
result = asyncio.run(core.handle(
    input_text=bridge_message["text"],
    context={
        "user_id": bridge_message["external_user_id"],
        "metadata": {
            "source": "line_bridge",
            "attachments": bridge_message["attachments"],
        }
    },
    fmt="dict",
    use_langraph=True,
))
```

#### Step 3 — 验证 Intent 路由正确

```python
# 图片消息应路由到 ocr_task（不是 data_record）
assert result["workflow"]["steps"][0]["name"] == "ocr_extract"
# 或通过 task 验证
# assert result["execution_result"]["task_intent"] == "ocr_task"
```

#### Step 4 — 验证文件已下载到本地

```python
import os
from pathlib import Path

ocr_step = next(s for s in result["execution_result"]["steps"] if s["name"] == "ocr_extract")
outputs = ocr_step["outputs"]

# 状态为 received（文件下载成功，OCR 尚未实现）
assert outputs["status"] in ("received", "ok")
assert outputs.get("file_name") == "test_image.jpg"

# 本地 received/ 目录下存在该文件
if outputs.get("artifact_path"):
    local_path = Path(outputs["artifact_path"])
    assert local_path.exists()
    assert local_path.stat().st_size > 0
```

#### Step 5 — 验证没有触发 repair loop

```python
trace = result["execution_result"].get("autonomous_implementation_trace", {})
# "received" 状态不应触发修复
assert result["execution_result"].get("repair_iteration", 0) == 0
```

---

## TC-05  费用记录 → 按类别查询 → 分组汇总

### 场景描述
用户连续输入三条费用，随后查询本周交通费用总额。
测试跨多次 `handle` 调用的 session 状态保持，以及 `aggregate_query` 步骤的正确计算。

### 前置条件
- 使用 `isolated_generated_artifacts` fixture（隔离 session store）
- `budget_semantic_runtime` fixture（关闭 embedding，使用 rule-based 模式）

### 测试步骤

#### Step 1-3 — 顺序写入三条记录

```python
session_id = "test_budget_session_tc05"
ctx_base = {"user_id": "u_budget", "session_id": session_id}

records_to_insert = [
    "今天打车去机场花了 120 元",
    "买了感冒药 45 元",
    "地铁月票充值 100 元",
]

for text in records_to_insert:
    r = asyncio.run(core.handle(text, context=ctx_base, fmt="dict", use_langraph=True))
    assert r["execution_result"]["steps"][0]["outputs"]["saved"] >= 1
```

#### Step 2 — 断言 3 条记录已持久化

```python
r = asyncio.run(core.handle("我总共记录了几条", context=ctx_base, fmt="dict", use_langraph=True))
# 期望 reply 中包含数字 3 或 records 字段 >= 3
```

#### Step 3 — 查询交通类费用

```python
r = asyncio.run(core.handle(
    "本周交通费用一共多少",
    context=ctx_base,
    fmt="dict",
    use_langraph=True,
))

agg_step = next(
    (s for s in r["execution_result"]["steps"] if s["name"] == "aggregate_query"),
    None
)
assert agg_step is not None

agg_out = agg_step["outputs"]["aggregation"]
# 打车 120 + 地铁 100 = 220
assert agg_out.get("total") == 220 or "220" in r["reply"]
```

#### Step 4 — 按类别分组查询

```python
r = asyncio.run(core.handle(
    "按类别汇总所有费用",
    context=ctx_base,
    fmt="dict",
    use_langraph=True,
))

reply = r["reply"]
# 至少包含两个类别
assert "交通" in reply or "transportation" in reply
assert "医疗" in reply or "healthcare" in reply
```

---

## TC-06  查询智能体知识 → 无命中 → 用户补充 → 再查询

### 场景描述
智能体刚创建（知识尚未完善），第一次查询返回空结果，系统提示用户补充。
用户补充关键信息后，第二次查询命中并返回答案。

### 前置条件
- TC-01 中创建的家庭成员智能体（或手动注入一个仅含姓名、无电话的智能体）

### 测试步骤

#### Step 1 — 查询不存在的字段

**输入**
```
input_text: "爸爸的邮箱是什么"
context:
  session_id: "test_family_agent_session"
```

**预期**
- `steps[0].outputs.knowledge_hits == []` 或 `answer` 为空
- `reply` 包含"暂时没有"/"未找到"/"请补充"等提示

```python
kn_step = next(s for s in r["execution_result"]["steps"] if s["name"] == "query_information_knowledge")
assert not kn_step["outputs"].get("knowledge_hits")  # 空命中
# reply 提示用户补充
assert any(kw in r["reply"] for kw in ["没有", "未找到", "补充", "不知道"])
```

#### Step 2 — 用户补充邮箱

**输入**
```
input_text: "爸爸的邮箱是 dad@example.com"
context:
  session_id: "test_family_agent_session"
```

**预期 Intent**：`refine_information_agent` 或 `capture_agent_knowledge`

**断言**
```python
assert r["execution_result"]["steps"][0]["outputs"]["dialog_state"]["stage"] in (
    "ai_workflow", "complete"
)
```

#### Step 3 — 再次查询

**输入**
```
input_text: "爸爸的邮箱是什么"
context:
  session_id: "test_family_agent_session"
```

**预期**
- 本次命中，`reply` 包含 `"dad@example.com"`

```python
assert "dad@example.com" in r["reply"] or "dad@example.com" in str(
    r["execution_result"]["steps"][0]["outputs"].get("answer", "")
)
```

---

## TC-07  Agent 路径：创建 ReAct 推理 Agent 并完成任务

### 场景描述
当 `task.constraints.need_agent == True` 时，`AICore` 走 Agent 路径，
生成 `AgentSpec`，构建 `ReasoningAgent`，执行 `think_and_act` 推理循环，
最终返回 `agent_result.success == True`，并产出 agent 配置文件 Artifact。

### 测试步骤

#### Step 1 — 执行（使用 mock agent 避免模型调用）

参考 `test_core_engine_agent_runtime.py` 中的 mock 模式：

```python
class DummyAgent:
    async def think_and_act(self, input_text: str, context: dict):
        return {
            "final_answer": f"任务完成: {input_text}",
            "success": True,
            "iterations": 2,
            "reasoning_steps": [
                {"step": 1, "thought": "分析用户请求"},
                {"step": 2, "thought": "执行并汇总结果"},
            ]
        }

# Patch
core.agent_builder.generate_agent_spec = _fake_generate_agent_spec
core.agent_builder.build_agent = _fake_build_agent
```

#### Step 2 — 执行 handle

```python
result = asyncio.run(core.handle(
    input_text="请使用智能体帮我生成一份周报草稿",
    context={"user_id": "u_agent_test"},
    fmt="dict",
    use_langraph=True,
))
```

#### Step 3 — 验证 Agent 执行结果

```python
er = result["execution_result"]
assert er["execution_type"] == "agent"
assert er["agent_result"]["success"] is True
assert er["agent_result"]["iterations"] >= 1
assert er["agent_result"]["final_answer"]
```

#### Step 4 — 验证 Agent Artifact 已持久化

```python
generated_path = result["agent"].get("generated_artifact_path")
assert generated_path
from pathlib import Path
assert Path(generated_path).exists()

# Artifact 索引中存在 agent 类型
artifacts = result.get("artifacts", [])
assert any(a["artifact_type"] in ("agent", "trace") for a in artifacts)
```

#### Step 5 — 再次执行相同任务（蓝图复用验证）

```python
result2 = asyncio.run(core.handle(
    input_text="再帮我生成一份日报",
    context={"user_id": "u_agent_test"},
    fmt="dict",
    use_langraph=True,
))
# 第二次执行：autonomous_implementation_triggered 为 False（已有蓝图）
trace = result2["execution_result"]["autonomous_implementation_trace"]
assert trace["autonomous_implementation_triggered"] is False
```

---

## TC-08  handle_stream 完整事件序列验证

### 场景描述
通过 `handle_stream` 验证所有 SSE lifecycle 事件按正确顺序到达，
没有跳过关键节点，也没有出现未预期的 `error` 事件。

### 测试步骤

```python
import asyncio

async def collect_stream_events(input_text: str, context: dict) -> list[dict]:
    events = []
    async for chunk in core.handle_stream(input_text=input_text, context=context):
        events.append(chunk)
    return events

events = asyncio.run(collect_stream_events(
    "记录今天下午喝咖啡花了 35 元",
    context={"user_id": "u_stream_test"}
))
```

#### 验证事件类型集合

```python
event_types = [e["event"] for e in events]
event_set = set(event_types)

# 必须出现的事件
required_events = {"lifecycle_start", "intent_analyzed", "workflow_planned", "lifecycle_end"}
assert required_events.issubset(event_set), f"Missing: {required_events - event_set}"

# 不能出现 lifecycle_error（无错误场景）
assert "lifecycle_error" not in event_set
```

#### 验证事件顺序

```python
def idx(event_name: str) -> int:
    for i, e in enumerate(events):
        if e["event"] == event_name:
            return i
    return -1

assert idx("lifecycle_start") < idx("intent_analyzed")
assert idx("intent_analyzed") < idx("workflow_planned")
assert idx("workflow_planned") < idx("lifecycle_end")
```

#### 验证事件内容

```python
intent_event = next(e for e in events if e["event"] == "intent_analyzed")
assert intent_event["intent"]
assert intent_event["trace_id"]

workflow_event = next(e for e in events if e["event"] == "workflow_planned")
assert workflow_event["step_count"] >= 1
assert workflow_event["steps"]
```

---

## 综合场景：用户提问 → 信息缺失 → 补充 → 生成文件

> 本场景串联 TC-01（智能体创建） + TC-02（文档生成） + TC-06（知识查询），
> 模拟一个完整的"从无到有"全生命周期。

### 流程概述

```
用户: "帮我整理爸爸这次去大阪的行程，发给他"
  ↓
NestHub: 识别为 prepare_trip_brief，但缺少"爸爸联系方式"
  ↓
NestHub 回问: "请问您是指哪位家庭成员？能告诉我联系方式吗？"
  ↓
用户: "爸爸，手机 138-0000-1234"
  ↓
NestHub: 
  1. create_information_agent → 持久化爸爸信息
  2. prepare_trip_brief → 生成行程文件
  3. reply 包含行程摘要 + 下载链接
```

### 断言检查点

```python
# Turn 1: 系统发现信息缺失，提问
assert any(kw in turn1_reply for kw in ["联系方式", "哪位", "请问"])

# Turn 2: 补充后系统完成两件事
# a) 智能体创建成功
agent_out = turn2_result["execution_result"]["steps"][0]["outputs"]
assert agent_out.get("agent", {}).get("agent_id")

# b) 行程文件生成
from pathlib import Path
artifact_path = next(
    (a.get("path") for a in turn2_result.get("artifacts", []) if a.get("artifact_type") == "document"),
    None
)
assert artifact_path and Path(artifact_path).exists()

# c) Reply 包含关键信息
assert "大阪" in turn2_result["reply"]
assert "张国华" in turn2_result["reply"] or "爸爸" in turn2_result["reply"]
```

---

## 附录：测试数据 Fixtures

### `test/fixtures/sample_image.jpg`
- 用于 TC-04 的 OCR 测试
- 建议使用 `pillow` 动态生成：
```python
# conftest.py 或 fixture 文件
from PIL import Image, ImageDraw
import io

def make_test_image(text: str = "测试图片 ABC 123") -> bytes:
    img = Image.new("RGB", (400, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 80), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()
```

### 常用 Mock 配置

```python
# 无 Model Router（纯 rule-based 模式）
from unittest.mock import AsyncMock
core.intent_analyzer.analyze = AsyncMock(return_value=mock_task)

# Mock blueprint_resolver 触发缺口
core.blueprint_resolver.resolve = lambda task, wf: []

# Mock Agent
core.agent_builder.build_agent = AsyncMock(return_value=DummyAgent())
```

---

## 转为代码的优先级建议

| 优先级 | 用例 | 理由 |
|--------|------|------|
| P0 | TC-05（费用记录+查询） | 核心业务流，已有类似测试基础 |
| P0 | TC-04（LINE图片下载） | 最近修复的主要 bug，需要回归保护 |
| P1 | TC-01（智能体创建多轮） | 对话状态管理最复杂，价值最高 |
| P1 | TC-08（stream 事件序列） | 低成本，覆盖 handle_stream 整条链路 |
| P2 | TC-03（Repair Loop） | 已有 test_execution_repair_loop.py 基础 |
| P2 | TC-07（Agent 路径） | 已有 test_core_engine_agent_runtime.py 基础 |
| P3 | TC-02（文档生成） | 依赖文件生成步骤实现完整度 |
| P3 | TC-06（知识查询+补充） | 依赖 TC-01 先完成 |
