# NestHub Budget Scene 详细白盒测试报告

- 生成时间: 2026-04-16 10:41:31
- 报告文件: core_budget_scene_detailed_report_20260416_104131.md
- 测试范围: 预算场景录入、中文查询解析、类别语义识别、semantic memory 学习保护、dashboard API/静态页
- 测试方式: 白盒测试为主，结合模块级回归测试与端到端接口测试
- 测试环境: Linux, Python 3.12.11, FastAPI TestClient, 本地代码工作区

## 1. 测试目标

本轮测试目标不是单纯验证接口可用，而是从代码内部实现逻辑出发，确认以下关键设计已经落地并稳定：

1. `execution_coordinator.py` 中业务关键词已尽量外置到 `semantic_policy.json`。
2. 中文语义分类在无外部模型参与时，仍能依赖 taxonomy、synonyms 和本地 lexical boosting 完成稳定识别。
3. 泛查询如“4月份一共花了多少钱”不会被误判到具体消费类别。
4. semantic memory 的候选学习机制具备白名单、黑名单、冲突抑制和回滚能力。
5. semantic memory dashboard 可通过 API 和静态页面查看当前策略记忆状态。

## 2. 白盒测试方法

本轮采用白盒测试方式，重点依据代码内部结构、关键分支和状态流设计测试，而非仅从外部输入输出黑盒验证。

### 2.1 白盒关注点

- `ExecutionCoordinator._semantic_label_from_text`
  - 验证 taxonomy 描述、examples、synonyms 是否共同参与标签评分。
  - 验证 lexical hint boosting 是否能修复短中文短语本地分类弱的问题。
- `ExecutionCoordinator._parse_query`
  - 验证泛查询不会错误写入 `filters["label"]`。
  - 验证 `group_by` 解析与时间条件解析可正常工作。
- `ExecutionCoordinator._should_accept_learning_candidate`
  - 验证允许学习的 key 白名单。
  - 验证 blocked terms 拦截。
  - 验证已有 canonical/alias/location marker 的冲突抑制。
- `SemanticPolicyStore.inspect_memory`
  - 验证 dashboard 可见信息与运行时真实策略一致。
- `/core/handle`
  - 验证预算场景从录入到聚合查询的完整链路。

### 2.2 使用的测试层级

- 模块级回归测试
  - 直接调用 `ExecutionCoordinator` 内部方法。
  - 优点: 可精准命中分支，定位问题根因。
- 服务级 API 测试
  - 使用 `FastAPI TestClient` 调用 `/core/handle` 与 `/core/admin/semantic-memory`。
  - 优点: 验证真实集成路径是否符合预期。
- 静态页面可用性测试
  - 验证 dashboard 页面是否可被服务挂载访问。

## 3. 执行的测试文件

本轮已执行并通过的重点测试文件如下：

1. `test/test_execution_coordinator_regression.py`
2. `test/test_budget_scene_e2e_regression.py`
3. `test/test_semantic_policy_memory.py`
4. `test/test_semantic_memory_dashboard_api.py`
5. `test/test_semantic_memory_dashboard_static.py`

## 4. 测试用例明细

### 用例 1: 泛中文查询不误判消费类别

- 用例名称: `test_generic_chinese_query_does_not_infer_label`
- 目标模块: `ExecutionCoordinator._parse_query`
- 测试输入: `4月份一共花了多少钱？`
- 预想结果:
  - `filters` 中不应出现 `label`
  - 查询文本应保留为原始泛查询
  - 系统不得将其错误归类为餐饮、购物等具体类别
- 实际结果:
  - `filters` 未出现 `label`
  - 查询保留原始文本
  - 测试通过
- 结论:
  - 通过，说明多语 embedding + margin + 本地规则的联合约束有效抑制了“泛查询误贴标签”问题。

### 用例 2: 中文交通消费可被本地语义识别

- 用例名称: `test_transportation_label_is_inferred_from_chinese_text`
- 目标模块: `ExecutionCoordinator._infer_label`
- 测试输入: `今天打车去机场花了120元`
- 预想结果:
  - 返回标签 `transportation`
- 实际结果:
  - 返回 `transportation`
- 结论:
  - 通过，说明 taxonomy 扩展和 lexical boosting 已生效。

### 用例 3: 中文医疗消费可被本地语义识别

- 用例名称: `test_healthcare_label_is_inferred_from_chinese_text`
- 目标模块: `ExecutionCoordinator._infer_label`
- 测试输入: `昨天去医院看病买药一共花了260元`
- 预想结果:
  - 返回标签 `healthcare`
- 实际结果:
  - 返回 `healthcare`
- 结论:
  - 通过，说明新增 taxonomy 类别不依赖外部模型也可命中。

### 用例 4: 类别聚合查询不应倒灌成类别过滤

- 用例名称: `test_category_group_query_matches_existing_records_without_false_label`
- 目标模块: `ExecutionCoordinator._parse_query`
- 测试输入: `今天按类别统计花了多少钱？`
- 预想结果:
  - `group_by == ["label"]`
  - `filters` 中不应出现错误的 `label`
- 实际结果:
  - `group_by` 正确解析为 `label`
  - `filters` 未出现错误标签
- 结论:
  - 通过，说明“统计维度”和“过滤条件”已被正确区分。

### 用例 5: 多条记录提取后的类别识别正确

- 用例名称: `test_extract_records_assigns_new_category_labels`
- 目标模块: `ExecutionCoordinator._extract_records`
- 测试输入: `今天打车花了80元。下午去医院买药花了35元。这个月交网费120元`
- 预想结果:
  - 输出 3 条记录
  - 标签依次为 `transportation`、`healthcare`、`utilities`
- 实际结果:
  - 提取 3 条记录
  - 标签与预期一致
- 结论:
  - 通过，新增类别扩展已稳定进入结构化记录流程。

### 用例 6: 学习保护拦截 generic term 与非法 key

- 用例名称: `test_learning_guard_rejects_generic_terms_and_disallowed_keys`
- 目标模块: `ExecutionCoordinator._should_accept_learning_candidate`
- 测试输入:
  - `label_taxonomy -> {"misc": {}}`
  - `ignored_query_tokens -> "多少"`
  - `ignored_query_tokens -> "报销"`
- 预想结果:
  - `label_taxonomy` 应被拒绝，因为不在学习白名单内
  - `多少` 应被拒绝，因为属于 blocked terms
  - `报销` 应允许通过，因为不在黑名单且满足规则
- 实际结果:
  - 与预期一致
- 结论:
  - 通过，说明 learning guard 没有形同虚设。

### 用例 7: actor 新别名学习不被误伤

- 用例名称: `test_learning_guard_allows_new_actor_aliases`
- 目标模块: `ExecutionCoordinator._should_accept_learning_candidate`
- 测试输入: `entity_aliases.actor -> {"roommate": ["室友", "合租人"]}`
- 预想结果:
  - 应允许通过，因为属于新 canonical 与新 alias
- 实际结果:
  - 允许通过
- 结论:
  - 通过，说明冲突抑制没有过度收紧，正常学习仍可发生。

### 用例 8: actor 冲突别名与已有 canonical 被正确拦截

- 用例名称: `test_learning_guard_rejects_conflicting_actor_aliases_and_existing_canonical`
- 目标模块: `ExecutionCoordinator._should_accept_learning_candidate`
- 测试输入:
  - `{"friend_circle": ["朋友"]}`
  - `{"家人": ["亲属"]}`
- 预想结果:
  - 第一项因 alias 与现有值冲突被拒绝
  - 第二项因 canonical 与现有值冲突被拒绝
- 实际结果:
  - 两项均被拒绝
- 结论:
  - 通过，说明 `entity_aliases.actor` 的冲突抑制符合设计。

### 用例 9: location marker 冲突抑制不误伤新值

- 用例名称: `test_learning_guard_blocks_existing_location_marker_but_accepts_new_one`
- 目标模块: `ExecutionCoordinator._should_accept_learning_candidate`
- 测试输入:
  - `location_markers -> "在"`
  - `location_markers -> "途经"`
- 预想结果:
  - 已有 marker `在` 被拒绝
  - 新 marker `途经` 允许通过
- 实际结果:
  - 与预期一致
- 结论:
  - 通过，location 维度的冲突抑制和正常学习边界正确。

### 用例 10: 预算场景端到端录入与类别聚合

- 用例名称: `test_budget_scene_category_aggregation_e2e`
- 目标模块: `/core/handle`
- 测试输入:
  - 录入: `今天打车花了80元。下午去医院买药花了35元。这个月交网费120元`
  - 查询: `今天按类别统计花了多少钱？`
- 预想结果:
  - 录入后记录标签分别为 `transportation`、`healthcare`、`utilities`
  - 查询后 `group_by == ["label"]`
  - 聚合结果中按 label 汇总为 `80 / 35 / 120`
  - 总金额为 `235`
- 实际结果:
  - 与预期一致
- 结论:
  - 通过，说明录入链路、持久化链路、查询链路与聚合链路整体打通。

### 用例 11: 预算场景端到端泛查询不误分类

- 用例名称: `test_budget_scene_generic_query_not_misclassified_e2e`
- 目标模块: `/core/handle`
- 测试输入:
  - 先录入预算记录
  - 再查询: `4月份一共花了多少钱？`
- 预想结果:
  - `filters == {}`
  - `group_by == []`
  - 不应凭空出现某个消费标签过滤
- 实际结果:
  - 与预期一致
- 结论:
  - 通过，说明端到端路径下泛查询仍然稳定。

### 用例 12: semantic memory API 返回学习规则

- 用例名称: `test_semantic_memory_api_exposes_learning_rules`
- 目标模块: `/core/admin/semantic-memory`
- 测试输入: GET 请求
- 预想结果:
  - 返回结果包含 `learning_rules`
  - `allowed_policy_keys` 与 `blocked_terms` 可见
- 实际结果:
  - 与预期一致
- 结论:
  - 通过，说明 dashboard 可基于运行时真实规则展示学习保护配置。

### 用例 13: dashboard 静态页面可被服务访问

- 用例名称: `test_semantic_memory_dashboard_is_served`
- 目标模块: `/examples/semantic-memory-dashboard/`
- 测试输入: GET 请求
- 预想结果:
  - 返回 200
  - 页面 HTML 中含 `Semantic Memory Dashboard`
- 实际结果:
  - 与预期一致
- 结论:
  - 通过，VS Code debug 与浏览器访问链路成立。

## 5. 实际执行结果汇总

### 已执行命令

```bash
/usr/bin/python -m pytest test/test_execution_coordinator_regression.py -q
/usr/bin/python -m pytest test/test_budget_scene_e2e_regression.py -q
/usr/bin/python -m pytest test/test_semantic_policy_memory.py -q
/usr/bin/python -m pytest test/test_semantic_memory_dashboard_api.py test/test_semantic_memory_dashboard_static.py -q
```

### 实际结果

- `test_execution_coordinator_regression.py`: 9 passed
- `test_budget_scene_e2e_regression.py`: 2 passed
- `test_semantic_policy_memory.py`: 6 passed
- `test_semantic_memory_dashboard_api.py` + `test_semantic_memory_dashboard_static.py`: 2 passed

### 总结

- 总计通过测试: 19
- 总计失败测试: 0
- 当前结论: 本轮修改后的预算场景、semantic memory 和记忆 dashboard 功能稳定可用

## 6. Bug 分析

本轮虽然最终测试全部通过，但白盒测试过程中实际暴露过几类真实 bug，这些 bug 对系统设计很关键。

### Bug 1: 新增 taxonomy 类别未被本地分类路径消费

- 现象:
  - 新增 `transportation`、`healthcare`、`utilities` 后，初始回归测试仍然得到 `other`
- 根因:
  - `ExecutionCoordinator._semantic_label_from_text` 只使用了 taxonomy 的 description/examples，未充分消费 `normalization.synonyms`
- 修复:
  - 将 `synonyms` 纳入 profile text，同时补 lexical hint boosting
- 风险:
  - 如果未来继续扩 taxonomy 但不扩 synonyms，本地路径仍可能弱化

### Bug 2: 纯 token similarity 对短中文短语过弱

- 现象:
  - `打车`、`买药`、`网费` 在关闭 embedding 的测试条件下仍然难以过阈值
- 根因:
  - 中文短语在 regex/jieba 分词后，简单 token overlap 对语义标签区分能力不足
- 修复:
  - 新增基于 examples/synonyms 的 lexical hit boosting，并且对 synonym 命中给予更高权重
- 风险:
  - 若 synonym 列表出现过宽词，可能抬高误判概率，因此 taxonomy 和 synonym 设计必须受控

### Bug 3: learning candidate 若无约束会污染 semantic memory

- 现象:
  - 模型驱动学习如果直接接收候选，可能把 `多少`、`今天`、`统计` 之类泛词纳入策略候选区
- 根因:
  - 初版学习逻辑只有“记录候选”，没有严格的业务约束层
- 修复:
  - 新增 `allowed_policy_keys`、`blocked_terms`、`min_candidate_text_length`、`reject_existing_conflicts`
- 风险:
  - 黑名单过短会漏拦，黑名单过长会误伤正常学习，需要继续观察

### Bug 4: 冲突抑制可能误伤合法 alias 学习

- 现象:
  - 如果冲突规则过于简单，可能把新的 actor alias 或 location marker 全部拒掉
- 根因:
  - 冲突抑制天然面临“防污染”和“保学习”之间的平衡问题
- 修复:
  - 增加专门回归测试，验证新 alias 可通过、旧 alias/旧 canonical 被拦截
- 风险:
  - 多语言或近义 alias 未来仍可能产生边界冲突

## 7. 当前风险与建议

### 当前剩余风险

1. `location` 提取逻辑仍偏启发式，例如 `下午去医院买药花了35元` 被解析出的 location 偏长，说明地点边界抽取还有优化空间。
2. 端到端查询中的时间 marker 仍可能保留轻微格式噪声，例如内部输出里曾出现过前导空格或被切分影响的文本。
3. taxonomy 扩展后，若未来继续大幅增加类别，`semantic_label_threshold` 和 `semantic_label_margin` 可能需要重新校准。
4. semantic memory 的学习候选目前仍依赖外部解析器给出候选结构，候选质量受模型输出稳定性影响。

### 后续建议

1. 增加 `location/content/time_marker` 的边界解析回归测试，继续压缩启发式误差。
2. 给 semantic memory dashboard 增加候选拒绝原因可视化，便于定位某个学习候选为何未入库。
3. 给 taxonomy 类别扩展增加专门基准集，避免类别变多后误判率上升。
4. 若后续上线真实多租户使用，建议把 semantic memory 的 SQLite 后端切换成 PostgreSQL，并保留当前 API/过滤逻辑不变。

## 8. 最终结论

从白盒测试结果看，本轮关于预算场景、中文语义分类、semantic memory 学习保护和 dashboard 可视化的改动已经达到可用状态：

- 中文泛查询不会再轻易误判成具体消费类别。
- 新增消费类别可在本地路径下完成识别与聚合。
- semantic memory 已具备基础防污染能力。
- dashboard 和 VS Code debug 启动链路可直接使用。

结论: 可以进入下一轮围绕 location/time 边界精度和 dashboard 诊断能力的增强阶段。
