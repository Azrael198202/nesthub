# Overall Family Workflow Tests

这个目录把 [test/overall_test_cases_family_agent_workflow.md](../overall_test_cases_family_agent_workflow.md) 转成了可维护的自动化测试资产。

包含内容：

- `family_agent_workflow_cases.yaml`：结构化测试数据集，保留了文档中的 `P0/P1/P2` 用例，并区分 `active` 与 `pending`。
- `test_family_agent_workflow_dataset.py`：数据驱动 pytest 程序，读取 YAML 后执行当前可落地的 `/core/handle` 用例。

状态约定：

- `active`：当前系统已经具备自动验证入口，pytest 会实际执行。
- `pending`：文档中要求的能力仍被保留在数据集里，但当前仓库尚未提供稳定断言面，因此不会执行，只验证其说明是否完整。

当前已自动执行的主链路：

- `TC-P0-05`：批量消费记录抽取与写入前结构验证。
- `TC-P0-07`：批量日程记录抽取与结构验证。
- `TC-P0-10`：基于同一 session 的 4 月全家消费聚合查询。
- `TC-P0-11`：按成员和日期查询日程安排。

运行方式：

```bash
/usr/bin/python -m pytest test/overall/test_family_agent_workflow_dataset.py -q
```

后续扩展建议：

- 当家庭成员 agent/profile 有独立查询接口后，把 `TC-P0-01` 到 `TC-P0-04` 从 `pending` 升级到 `active`。
- 当 reminder / threshold rule 有稳定返回结构后，把对应场景加入 `steps + assertions`。
- 如果需要更强的跨步骤断言，可以在 YAML 中继续扩展 assertion 类型，而不用重写测试框架。