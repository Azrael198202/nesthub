# NestHub 端到端集成操作测试计划

> 版本：v1.0 | 日期：2026-04-19  
> 目标：验证从自然语言输入到结构化结果的完整流水线，覆盖智能体创建、知识采集、查询、预算记录、图片生成五大场景。

---

## 0. 前置条件

| 项目 | 要求 |
|------|------|
| Python 版本 | 3.11+ |
| 运行模式 | `mock_llm_calls = true`（不依赖外部 API） |
| Session 隔离 | 每个测试用例使用独立 `session_id`，避免跨用例状态污染 |
| 环境变量 | `NETHUB_GENERATED_ROOT` 指向临时目录（`pytest tmp_path`） |

---

## 1. 场景：信息智能体完整生命周期

### 1.1 创建供应商信息智能体

**操作序列**

| 步骤 | 用户输入 | 预期意图 | 预期响应关键字 |
|------|----------|----------|----------------|
| 1 | `帮我创建供应商资料智能体` | `create_information_agent` | `dialog_state.stage` = `ai_workflow` |
| 2 | `主要记录供应商名称、联系人、邮箱和供货品类。` | `refine_information_agent` | `dialog_state.stage` = `ai_workflow` |
| 3 | `没有了，完成创建。` | `finalize_information_agent` | `configured_agent.status` = `active` |

**断言**
- Step 1: `result["task"]["intent"] == "create_information_agent"`
- Step 3: `result["execution_result"]["final_output"]["manage_information_agent"]["configured_agent"]["status"] == "active"`
- Step 3: `configured_agent["activation_keywords"]` 非空列表

---

### 1.2 向智能体添加知识

**操作序列**（接续 1.1，同一 session）

| 步骤 | 用户输入 | 预期意图 | 预期响应关键字 |
|------|----------|----------|----------------|
| 4 | `供应商名称：科技甲株式会社` | `capture_agent_knowledge` | `dialog_state.stage` ∈ {`collecting_knowledge`, `knowledge_added`} |
| 5 | `联系人：田中太郎` | `capture_agent_knowledge` | 继续字段采集 |
| 6 | `邮箱：tanaka@tech.co.jp` | `capture_agent_knowledge` | 继续字段采集 |
| 7 | `供货品类：半导体元件，完成添加` | `capture_agent_knowledge` | `dialog_state.stage` = `knowledge_added` |

**断言**
- Step 7: `dialog_state["stage"] == "knowledge_added"`
- Step 7: `configured_agent["knowledge_records"]` 包含 ≥ 1 条记录

---

### 1.3 查询智能体知识

**操作序列**（接续 1.2，同一 session）

| 步骤 | 用户输入 | 预期意图 | 预期响应关键字 |
|------|----------|----------|----------------|
| 8 | `科技甲的邮箱是什么？` | `query_agent_knowledge` | `answer` 包含 `tanaka@tech.co.jp` |
| 9 | `有哪些供应商？` | `query_agent_knowledge` | `knowledge_hits` 非空 |

**断言**
- Step 8: `result["execution_result"]["final_output"]["query_agent_knowledge"]["answer"]` 包含目标字符串
- Step 9: `len(result["execution_result"]["final_output"]["query_agent_knowledge"]["knowledge_hits"]) >= 1`

---

## 2. 场景：预算记录与查询

### 2.1 多条消费记录提取

**操作序列**（独立 session）

| 步骤 | 用户输入 | 预期意图 | 预期结果 |
|------|----------|----------|----------|
| 1 | `吃饭花了3000日元，两人，在博多一兰。今天买咖啡500日元，还有书1200日元。` | `data_record` | 提取 ≥ 3 条记录 |
| 2 | `这个月一共花了多少？` | `data_query` | `aggregation.total` > 0 |
| 3 | `按类别统计一下` | `data_query` | `aggregation.groups` 非空 |

**断言**
- Step 1: `result["task"]["intent"] in ("data_record", "record_expense")`
- Step 1: 所有提取记录均含 `amount` 和 `content` 字段
- Step 2: `result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]["total"] >= 4700`
- Step 3: `result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]["groups"]` 非空

---

### 2.2 单条记录追加与幂等性

| 步骤 | 用户输入 | 预期意图 | 预期结果 |
|------|----------|----------|----------|
| 1 | `今天打车花了800日元` | `data_record` | 提取 1 条记录 |
| 2 | `今天打车花了800日元` | `data_record` | 仍提取 1 条（不应重复合并） |

**断言**
- 两次 Step 1 后 `total_records` 应等于 2（系统不做自动去重）

---

## 3. 场景：图片生成

### 3.1 正常生成（Pillow 占位符）

| 步骤 | 用户输入 | 预期意图 | 预期结果 |
|------|----------|----------|----------|
| 1 | 直接调用 `ImageGenerationService.generate(task, path)` | `image_generation_task` | `status = "generated"` |

**断言**
- `result["status"] == "generated"`
- 目标路径文件存在且 > 0 字节
- `result.get("result_verification", {}).get("ok") == True`

---

### 3.2 意图不匹配时提前返回

| 步骤 | task.intent | 预期结果 |
|------|-------------|----------|
| 1 | `text_generation_task` | `status = "intent_mismatch"` |
| 2 | `data_record` | `status = "intent_mismatch"` |

**断言**
- `result["status"] == "intent_mismatch"`
- `result["intent_verdict"]["expected"] == "image_generation_task"`

---

## 4. 场景：Session Memory 工具链

### 4.1 文件系统工具

| 操作 | 入参 | 预期结果 |
|------|------|----------|
| `write` | `path=<tmp>/test.txt`, `content="hello"` | `success=True` |
| `read` | `path=<tmp>/test.txt` | `content="hello"` |
| `list` | `path=<tmp>/` | `entries` 含 `test.txt` |
| `exists` | `path=<tmp>/test.txt` | `exists=True`, `is_file=True` |
| `delete` | `path=<tmp>/test.txt` | `success=True`；文件不再存在 |
| `teleport`（未知操作） | `path=<tmp>/` | `success=False`；`error` 含 `"unknown"` |

---

### 4.2 Shell 执行工具

| 操作 | 命令 | 预期结果 |
|------|------|----------|
| 允许命令 | `echo hello` | `success=True`；`stdout` 含 `"hello"` |
| 拒绝危险命令 | `rm -rf /` | `success=False`；`error` 含 `"not in the allowed list"` |
| 空命令 | `""` | `success=False` |

---

### 4.3 代码执行工具

| 操作 | 代码 | 预期结果 |
|------|------|----------|
| 简单表达式 | `x = 1 + 1` | `success=True`；`locals["x"] == 2` |
| 打印捕获 | `print('hi')` | `stdout` 含 `"hi"` |
| 语法错误 | `def broken(:` | `success=False`；`error` 非空 |
| 空代码 | `"   "` | `success=False` |

---

## 5. 场景：工作流执行与修复循环

### 5.1 执行协调器正常流程

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 提交 `data_record` 意图任务 | 工作流计划含 `extract_records` 步骤 |
| 2 | 工作流执行完成 | `execution_result.status = "completed"` |

---

### 5.2 自我修复循环（语法错误场景）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 注入故意损坏的 Python 代码片段 | 运行时检测到 `SyntaxError` |
| 2 | 修复循环启动 | `repair_attempts >= 1` |
| 3 | 修复后重新执行 | 最终 `status = "repaired"` 或 `"completed"` |

---

## 6. 验收标准汇总

| 场景 | 通过条件 |
|------|----------|
| 智能体创建 | `configured_agent.status == "active"` |
| 知识采集 | `knowledge_records` ≥ 1 条 |
| 知识查询 | 返回匹配的 answer 或 knowledge_hits |
| 预算记录 | 提取记录数 ≥ 输入段落数；含 `amount`、`content` |
| 预算查询 | `aggregation.total` 数值合理 |
| 图片生成 | `status = "generated"`，文件存在 |
| 意图不匹配 | `status = "intent_mismatch"` 提前返回 |
| 工具链 | 所有工具用例 `success` 符合预期 |

---

## 7. 测试用例转换计划

本 MD 验证通过后，将按以下规则生成对应的 pytest 文件：

| MD 章节 | 目标测试文件 |
|---------|-------------|
| §1 智能体生命周期 | `test/test_e2e_information_agent_lifecycle.py` |
| §2 预算记录与查询 | `test/test_e2e_budget_workflow.py` |
| §3 图片生成 | 扩展 `test/test_image_generation_verification.py` |
| §4 工具链 | 已覆盖 `test/test_session_memory_tasks.py` |
| §5 工作流修复 | 已覆盖 `test/test_execution_repair_loop.py` |
