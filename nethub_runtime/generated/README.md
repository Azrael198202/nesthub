# Runtime Generated Artifacts

这个目录专门用于系统在运行时自动生成的产物，避免污染 `core`、手写 blueprint 和其他稳定代码目录。

建议约定：

- `code/`：自动补齐功能时生成的代码补丁或运行时 feature 文件
- `blueprints/`：自动生成的 blueprint 定义
- `agents/`：运行时生成并持久化的 agent 规格或状态快照
- `features/`：TVBox / Studio 等界面触发生成的功能文件
- `traces/`：自主实现、能力缺口检测、生成过程等运行时 trace

这里的内容默认视为“系统生成物”，不应与手工维护的核心源码混放。