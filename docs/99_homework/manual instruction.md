## 2026-04-17 回归、测试、优化说明

### 1. 本次目标

本次主要完成了三类工作：

1. 让家庭成员智能体相关回归测试可以稳定执行。
2. 让测试过程中产生的 generated 数据不再污染正式目录。
3. 补齐可手动执行的回归脚本和 VS Code 任务入口，方便后续阶段测试重复使用。

---

### 2. 当前可手动执行的回归入口

### 2.4 测试结果存放位置

测试结果、回归报告、单测过程记录，统一放在：

- `test/reports/`

这次家庭成员智能体测试报告的正式位置是：

- `test/reports/20260417_family_member_agent_test_report.md`

`docs/99_homework/` 只保留操作说明、回归策略和手动执行方法，不再存放测试结果正文。

#### 2.1 基础 focused runtime 回归

命令：

```bash
./scripts/run_regression.sh
```

用途：

- 执行基础 runtime 回归。
- 主要用于验证核心运行链路是否正常。


#### 2.2 隔离型 API/runtime 回归

命令：

```bash
./scripts/run_isolated_runtime_regression.sh
```

用途：

- 先归档已有 trace。
- 再执行带隔离策略的 API/runtime 回归。
- 适合阶段性测试前后使用，避免测试数据互相污染。


#### 2.3 VS Code 任务入口

在 VS Code 中可直接运行以下任务：

- `regression: focused runtime`
- `regression: isolated api runtime`

对应配置文件：

- `.vscode/tasks.json`

---

### 3. 当前隔离策略

#### 3.1 generated 根目录支持环境变量覆盖

系统已经支持通过环境变量覆盖 generated 根目录：

```bash
NETHUB_GENERATED_ROOT=/some/temp/path
```

对应实现位置：

- `nethub_runtime/config/settings.py`
- `nethub_runtime/generated/store.py`


#### 3.2 pytest 共享隔离 fixture

已经新增共享 fixture：

- `test/conftest.py`

fixture 名称：

- `isolated_generated_artifacts`

作用：

- 给测试注入独立的临时 generated 目录。
- 让 runtime trace、generated artifact 等写到临时目录，而不是正式目录。


#### 3.3 已接入隔离的测试

目前已接入共享隔离策略的测试包括：

- `test/test_family_member_agent_runtime.py`
- `test/test_core_api.py`
- `test/test_budget_scene_e2e_regression.py`
- `test/overall/test_family_agent_workflow_dataset.py`
- `test/test_semantic_memory_dashboard_api.py`
- `test/test_semantic_memory_dashboard_static.py`

这些测试在执行过程中产生的数据，不会继续写到正式 generated 目录。

---

### 4. trace 归档策略

隔离型脚本会在执行前自动处理：

目录：

- `nethub_runtime/generated/traces`

归档目标：

- `logs/generated_artifacts_archive/<timestamp>/`

这样做的作用：

1. 测试前把旧 trace 挪走。
2. 保留历史运行痕迹，方便排查。
3. 避免后续阶段测试混入旧产物。

---

### 5. 本轮已完成的核心优化

#### 5.1 信息智能体 domain logic 解耦

原本留在 `execution_coordinator.py` 里的信息智能体知识采集/查询逻辑，已经拆到独立 service：

- `nethub_runtime/core/services/information_agent_service.py`

效果：

- coordinator 更聚焦于调度。
- 信息智能体逻辑更容易扩展和维护。


#### 5.2 execution handler plugin 协议增强

execution handler registry 现在支持 manifest 化插件协议，且已加入结构化 requirement：

- `nethub_runtime/core/services/execution_handler_registry.py`

效果：

- 插件可以声明自己提供哪些 executor 和 step。
- 插件可以声明运行时 requirement。
- registry 可以记录 requirement 是否满足。


#### 5.3 family-member 回归测试稳定化

家庭成员智能体链路已经验证通过，且测试期间不会污染正式 generated 目录。

关键测试：

- `test/test_family_member_agent_runtime.py`

---

### 6. 推荐手动执行顺序

#### 6.1 日常快速检查

先执行：

```bash
./scripts/run_regression.sh
```


#### 6.2 阶段测试前检查

执行：

```bash
./scripts/run_isolated_runtime_regression.sh
```

适用场景：

- 准备做阶段联调。
- 准备做更大范围测试。
- 需要避免历史测试数据影响当前测试。


#### 6.3 单独验证家庭成员智能体

执行：

```bash
python3 -m pytest test/test_family_member_agent_runtime.py -q
```

如果当前环境使用虚拟环境，也可以替换为：

```bash
.venv/bin/python -m pytest test/test_family_member_agent_runtime.py -q
```

---

### 7. 后续建议

后续如果继续优化，建议优先做这两项：

1. 把剩余会写 generated 产物的测试继续接入共享隔离 fixture。
2. 再补一个更完整的 stage regression 脚本，把 focused runtime 和 isolated api runtime 串起来，形成统一阶段回归入口。
