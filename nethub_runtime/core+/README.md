# core+

`core+` 是基于 `docs/09_framework/VersionUp.md` 的非侵入式 Core 升级层。

当前策略：

- 保留原有 `nethub_runtime.core.services.core_engine.AICore` 执行链路
- 在外层增加规则预判、本地优先策略、评估/外网兜底提示、数据分流、LoRA 训练信号
- 通过统一 provider 切换，默认不影响旧逻辑

切换方式：

- 默认：`NETHUB_CORE_ENGINE_VARIANT=legacy`
- 升级：`NETHUB_CORE_ENGINE_VARIANT=core_plus`

目标状态：所有运行入口都通过 provider 创建引擎，后续可整体切换到 `core+`。