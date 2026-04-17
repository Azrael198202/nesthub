可用脚本：

- `run_regression.sh`：执行基础 focused runtime 回归。
- `run_isolated_runtime_regression.sh`：先归档 `nethub_runtime/generated/traces` 下已有 trace，再执行隔离型 API/runtime 回归，避免阶段测试互相污染。

VS Code 任务：

- `regression: focused runtime`
- `regression: isolated api runtime`