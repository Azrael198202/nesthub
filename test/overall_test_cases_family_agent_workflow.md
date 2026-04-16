# AI Core / LiteLLM / Workflow / Agent 整体测试用例（家庭成员场景）

## 1. 文档目标

本测试用例用于验证当前系统设计中 **AI Core、LiteLLM 路由、LangGraph Workflow、Agent、Blueprint、Memory、Tool/Feature** 之间的整体协同逻辑是否成立，并验证系统是否能够把“自然语言需求”转化为：

- 可持续对话式信息收集
- 智能体创建
- 蓝图创建或复用
- 工作流编排与执行
- 模型按任务类型自动路由
- 结构化数据写入与查询
- 提醒规则与事件触发
- 面向最终用户的自然语言问答

本测试文档基于当前项目设计：
- AI Core 作为认知/决策/编排中心，负责输入理解、任务拆解、工作流规划、蓝图匹配/生成、智能体生成与能力调度。fileciteturn0file1L11-L27
- Core 在执行时先做意图分析、任务拆解、工作流规划，再进行蓝图匹配、蓝图生成、智能体生成、能力解析与资源分配，最后执行并沉淀结果。fileciteturn0file1L112-L137
- Blueprint 是可复用执行逻辑，可预置、可自动生成、可动态创建，并可声明所需模型、工具、运行时与安装策略。fileciteturn0file0L86-L121
- LangGraph 框架中，系统需要支持 Workflow 状态管理、Blueprint 到 LangGraph 图的编译，以及 Agent 的持续推理循环。fileciteturn0file2L27-L53 fileciteturn0file2L145-L170 fileciteturn0file2L258-L276
- LiteLLM 路由层根据任务类型进行模型路由，例如 intent_analysis、task_planning、document_generation、agent_reasoning 等使用不同模型与回退策略。fileciteturn0file3L85-L93 fileciteturn0file3L165-L218

---

## 2. 测试范围

本轮测试范围覆盖以下 7 个层面：

1. **自然语言理解**：能否正确识别“创建 Agent / 创建 Blueprint / 记录消费 / 记录日程 / 创建提醒规则 / 数据查询”的意图。
2. **对话式信息收集**：在信息不足时，是否通过多轮会话补齐创建家庭成员 Agent 所需信息。
3. **智能体创建**：能否把“帮我创建家庭成员的智能体”转为 AgentSpec 与相关 Blueprint 集。
4. **工作流执行**：能否把消费记录、日程记录、提醒规则等转为可执行 Workflow。
5. **模型路由**：不同步骤是否选择合理模型，例如意图分析、任务规划、Agent 设计、Agent 推理、问答汇总。
6. **记忆与结构化存储**：创建的家庭成员、消费记录、日程记录、提醒规则是否可被后续步骤复用。
7. **查询与回答**：系统能否基于 Memory 正确回答跨记录的统计/检索类问题。

---

## 3. 测试场景总览

本次整体测试围绕以下主场景展开：

### 场景 A：创建家庭成员智能体
用户输入：
> 帮我创建家庭成员的智能体。

系统需要通过会话方式建议并采集需要保存的家庭成员信息，例如：
- 成员姓名
- 角色（爸爸/妈妈/孩子等）
- 称呼
- 默认币种
- 是否参与消费统计
- 是否参与日程提醒
- 特殊约束（儿童、学生、老人等）

直到形成完整的家庭成员 Agent / Profile。

### 场景 B：记录家庭成员消费
用户输入：
> 妈妈今天买菜消费了2000日元，昨天爸爸中午吃饭花了1000日元，昨天朱棣买糖花了500日元，4月11号小羽买书花了1200日元。

系统需要将自然语言拆解为多条消费记录，并与已存在的家庭成员资料关联。

### 场景 C：记录家庭成员日常安排
用户输入：
> 爸爸4月21号去大阪，妈妈4月20号PTA开会，朱棣本周六远足。

系统需要将自然语言拆解为多条日程记录，并与成员绑定。

### 场景 D：创建前一天提醒 Agent
用户输入：
> 给所有人的日程安排的前一天发出提醒。

系统需要创建一个提醒智能体或规则型 Blueprint，针对所有成员日程执行“前一天提醒”。

### 场景 E：创建即时消费提醒
用户输入：
> 如果爸爸的消费当天超过1000日元就发出提醒消费过高。

系统需要创建一个规则型 Agent / Workflow，对指定成员在指定时间窗口内的消费总额进行监测。

### 场景 F：自然语言查询与回答
用户输入示例：
> 4月份，全家总共消费多少？
>
> 4月21号爸爸有什么安排？

系统需要从 Memory 中检索并做聚合计算，然后以自然语言回答。

---

## 4. 测试前提

### 4.1 环境前提

- AI Core 已初始化，具备 Context Manager、Intent Analyzer、Task Decomposer、Workflow Planner、Blueprint Resolver、Blueprint Generator、Agent Designer、Capability Router、Execution Coordinator、Result Integrator 等模块。fileciteturn0file1L51-L78
- 系统支持 Workflow 与 Agent 两类执行模式，并可在决策层判断是否需要 Agent。fileciteturn0file2L10-L25 fileciteturn0file2L554-L582
- ModelRouter 已加载 routing_policies，至少覆盖 intent_analysis、task_planning、document_generation、general_chat、agent_reasoning 等任务类型。fileciteturn0file3L165-L218
- ToolRegistry、WorkflowExecutor、AgentBuilder、BlueprintCompiler 已在启动流程中初始化。fileciteturn0file2L479-L520
- 系统存在可写 Memory，用于保存家庭成员、消费记录、日程记录、提醒规则。

### 4.2 数据前提

测试开始时，默认系统中 **没有家庭成员信息**、**没有消费记录**、**没有日程记录**、**没有提醒规则**。

### 4.3 时间基准

为了便于验证，建议测试环境固定当前日期，例如：
- 当前日期：2026-04-16

这样可明确：
- “今天” = 2026-04-16
- “昨天” = 2026-04-15
- “本周六” 需根据系统周起始规则计算

---

## 5. 测试对象分层

### 5.1 Core 层验证点

- 是否识别当前请求属于一次性执行还是长期能力构建。Core 设计要求必须区分“一次性任务”和“长期可复用能力”。fileciteturn0file1L147-L158
- 是否在需要时创建 Agent，而不是简单地立即执行。
- 是否在缺少可复用逻辑时生成新 Blueprint。

### 5.2 Workflow 层验证点

- 是否将任务拆解为多个步骤，并形成执行图。
- 是否支持条件分支与继续执行判断。LangGraph 基础工作流包含 analyze_intent → plan_tasks → execute_step → integrate_results 的执行骨架。fileciteturn0file2L56-L139

### 5.3 Agent 层验证点

- 是否能生成 AgentSpec，包括角色、目标、能力、模型策略、工具策略、内存策略。fileciteturn0file2L206-L257
- 是否支持多轮信息收集与持续推理。

### 5.4 LiteLLM 层验证点

- intent_analysis 是否走快速模型。
- task_planning 是否走规划模型。
- agent_reasoning 是否走强推理模型。
- 普通查询是否走 general_chat / summarization 路由。

### 5.5 Memory / Query 层验证点

- 是否以结构化方式落库。
- 是否可对已记录数据做时间过滤、成员过滤、分类汇总与提醒判断。

---

## 6. 测试用例列表

以下测试用例分为：
- P0：主链路必须通过
- P1：重要补充链路
- P2：增强验证/边界验证

---

## 7. P0 主链路测试用例

### TC-P0-01 识别“创建家庭成员智能体”的长期能力意图

**目标**
验证系统能把“帮我创建家庭成员的智能体”识别为 **Agent 创建模式**，而不是普通问答或单次任务模式。

**输入**
> 帮我创建家庭成员的智能体

**期望处理逻辑**
1. Interface 将文本送入 Core。
2. Core 进行 Intent 分析。
3. Core 判断该需求属于“长期可复用角色/能力构建”，进入智能体生成模式。AI Core 设计中明确：当输入本质上在定义长期可复用角色时，应创建智能体。fileciteturn0file1L41-L49
4. Workflow / Decision Layer 返回 `requires_agent=true` 或等价语义。

**期望结果**
- 系统不直接生成一个静态答案。
- 系统进入“需要补充信息”的会话流程。
- 内部记录中出现：
  - intent = create_agent
  - domain = family_management 或等价领域
  - required_outputs 至少包含 agent

**判定标准**
- 通过：成功进入 Agent 创建链路。
- 失败：仅给出泛泛说明，未进入 Agent 设计或会话补充流程。

---

### TC-P0-02 家庭成员信息的多轮采集

**目标**
验证系统能通过多轮会话逐步收集创建家庭成员 Agent 所需信息。

**前置条件**
- 已通过 TC-P0-01。

**示例会话**
用户：帮我创建家庭成员的智能体

系统应继续提问并建议字段，例如：
- 这个家庭一共有几位成员？
- 每位成员的姓名和关系是什么？
- 是否都参与消费统计？
- 是否都参与日程提醒？
- 默认币种是什么？
- 是否需要记录年龄段/身份（学生、儿童等）？

用户依次回答，例如：
- 一共4个人：爸爸、妈妈、朱棣、小羽
- 爸爸和妈妈是家长，朱棣和小羽是孩子
- 都参与消费统计
- 都参与提醒
- 默认使用日元

**期望处理逻辑**
1. Agent Designer 或专门的信息收集 Blueprint 维护会话状态。
2. Context Manager 保存已确认字段。
3. 若关键信息不足，继续追问；信息足够后进入 AgentSpec 生成。

**期望结果**
- 形成结构化家庭成员资料，例如：
  - father
  - mother
  - zhu_di
  - xiao_yu
- 形成家庭管理 Agent 的目标与作用域。
- 形成相关 Blueprint 清单，例如：
  - member_profile_collect_blueprint
  - family_expense_record_blueprint
  - family_schedule_record_blueprint
  - reminder_rule_blueprint
  - family_query_blueprint

**判定标准**
- 通过：系统能在多轮对话中持续收集并确认，不丢失前文信息。
- 失败：只问一次就结束；或每轮重复已确认问题；或无法形成结构化结果。

---

### TC-P0-03 生成家庭成员 AgentSpec

**目标**
验证系统完成信息收集后，能够生成家庭成员管理 Agent 的规范定义。

**输入**
- 来自 TC-P0-02 的完整成员信息

**期望内部产物**
AgentSpec 至少包含：
- agent_id
- name
- role
- goals
- capabilities
- model_policy
- tool_policy
- memory_type
- max_iterations
- timeout_sec

这与 Agent 规范要求一致。fileciteturn0file2L206-L257

**示例期望能力**
- 维护家庭成员资料
- 记录消费
- 记录日程
- 生成提醒
- 按成员和日期查询
- 生成月度消费汇总

**模型策略示例**
- planning → task_planning
- extraction → fast_extraction / intent_analysis
- reasoning → agent_reasoning
- answering → general_chat / document_generation

**判定标准**
- 通过：成功产出 AgentSpec，并可被系统持久化。
- 失败：只有说明文字，没有可执行规范对象。

---

### TC-P0-04 自动创建或绑定相关 Blueprint

**目标**
验证系统在创建家庭成员 Agent 后，能够自动复用或生成所需 Blueprint。

**输入**
- TC-P0-03 的 AgentSpec

**期望处理逻辑**
1. Blueprint Resolver 检查是否已有可复用 Blueprint。fileciteturn0file1L64-L68
2. 若不存在，Blueprint Generator 自动生成新 Blueprint。fileciteturn0file1L69-L72
3. Blueprint 应声明所需模型、工具、运行时与安装策略。fileciteturn0file0L99-L121

**期望 Blueprint 类型**
- family_member_profile_collection
- family_expense_ingestion
- family_schedule_ingestion
- family_reminder_rule_engine
- family_nl_query

**判定标准**
- 通过：系统可输出 Blueprint 列表，并能说明是复用还是新建。
- 失败：Agent 创建完成，但没有执行逻辑载体。

---

### TC-P0-05 录入多条消费记录

**目标**
验证系统可将一段自然语言拆解为多条消费记录，并与成员关联。

**输入**
> 妈妈今天买菜消费了2000日元，昨天爸爸中午吃饭花了1000日元，昨天朱棣买糖花了500日元，4月11号小羽买书花了1200日元。

**期望处理逻辑**
1. Core 判断该请求属于“数据记录 / 批量抽取 / Workflow 执行”。
2. Task Decomposer 将输入拆解为 4 条原子消费记录。
3. Workflow Planner 生成 ingestion workflow。
4. Workflow 节点执行：
   - 时间表达式解析
   - 成员匹配
   - 金额提取
   - 币种推断
   - 消费内容分类
   - 写入 Memory

**期望结构化结果**
1. 妈妈 / 2026-04-16 / 买菜 / 2000 JPY
2. 爸爸 / 2026-04-15 / 中午吃饭 / 1000 JPY
3. 朱棣 / 2026-04-15 / 买糖 / 500 JPY
4. 小羽 / 2026-04-11 / 买书 / 1200 JPY

**判定标准**
- 通过：4 条记录完整落库，成员映射正确，日期换算正确。
- 失败：漏记录、金额错误、成员对不上、日期解释错误。

---

### TC-P0-06 消费记录依赖家庭成员 Memory

**目标**
验证消费记录步骤能够正确复用前一步创建的家庭成员信息，而非把名字当作普通字符串孤立存储。

**前置条件**
- TC-P0-02 / TC-P0-03 已通过。

**输入**
同 TC-P0-05。

**期望结果**
- 每条消费记录都包含 member_id 或等价的成员主键。
- 系统识别“妈妈”“爸爸”“朱棣”“小羽”为既有成员，不重复创建脏数据。
- 若成员不存在才进入补充/确认流程。

**判定标准**
- 通过：记录成功绑定到既有成员。
- 失败：创建出重复成员，或只存了文本名没有关联主数据。

---

### TC-P0-07 录入多条日程安排

**目标**
验证系统可将一段自然语言拆解为多条日程记录，并与成员绑定。

**输入**
> 爸爸4月21号去大阪，妈妈4月20号PTA开会，朱棣本周六远足。

**期望处理逻辑**
1. Core 识别为 schedule ingestion。
2. Workflow 拆解为 3 条日程。
3. 对时间表达式进行归一化：
   - 爸爸：2026-04-21
   - 妈妈：2026-04-20
   - 朱棣：本周六（根据当前日期换算）
4. 写入日程 Memory。

**期望结构化结果**
- 爸爸 / 2026-04-21 / 去大阪
- 妈妈 / 2026-04-20 / PTA开会
- 朱棣 / 对应周六日期 / 远足

**判定标准**
- 通过：3 条日程正确保存，时间解析一致。
- 失败：时间相对表达式解析错误；成员绑定错误。

---

### TC-P0-08 创建“前一天提醒”规则型 Agent / Blueprint

**目标**
验证系统能把“给所有人的日程安排的前一天发出提醒”转为可复用的规则能力。

**输入**
> 给所有人的日程安排的前一天发出提醒

**期望处理逻辑**
1. Core 识别为“长期提醒规则创建”，应进入 Agent 创建模式或 Blueprint 规则创建模式。
2. 自动绑定全部家庭成员。
3. 创建 ReminderSpec 或等价规则对象：
   - rule_type = schedule_pre_day_reminder
   - scope = all_members
   - trigger_time = event_date - 1 day
   - action = send_reminder

**期望结果**
- 系统保存提醒规则。
- 提醒规则可被调度器或 WorkflowExecutor 定时触发。
- 若系统采用 Agent 模式，应形成专门 Reminder Agent。

**判定标准**
- 通过：产生长期有效的提醒规则，而非只返回一句说明。
- 失败：只告诉用户“可以提醒”，没有创建任何规则对象。

---

### TC-P0-09 创建“当天消费超额提醒”规则型 Agent / Workflow

**目标**
验证系统能把阈值型自然语言规则转为事件监控能力。

**输入**
> 如果爸爸的消费当天超过1000日元就发出提醒消费过高

**期望处理逻辑**
1. Core 识别为 threshold-based monitoring rule。
2. 创建规则：
   - target_member = 爸爸
   - metric = daily_expense_total
   - comparator = >
   - threshold = 1000
   - currency = JPY
   - action = send_alert("消费过高")
3. 规则需能在当天有新消费写入后即时触发，或按事件驱动执行。

**期望结果**
- 规则对象落库。
- 规则与爸爸成员信息绑定。
- 后续写入一条新消费后，系统可自动评估是否触发提醒。

**判定标准**
- 通过：规则正确建立，并可被执行。
- 失败：没有形成可执行规则，只是文字备注。

---

### TC-P0-10 查询“4月份全家总共消费多少”

**目标**
验证系统能够基于 Memory 做聚合统计并自然语言回答。

**输入**
> 4月份，全家总共消费多少？

**前置条件**
- 已存在 TC-P0-05 中的 4 条消费记录。

**期望处理逻辑**
1. Core 识别为 query + aggregation。
2. Workflow 进行：
   - 时间范围过滤：2026-04-01 到 2026-04-30
   - 家庭全成员过滤
   - 求和
3. Result Integrator 生成自然语言回答。

**期望答案**
总消费 = 2000 + 1000 + 500 + 1200 = **4700 日元**

**判定标准**
- 通过：答案正确且可说明计算依据。
- 失败：金额错误、漏算、重复算。

---

### TC-P0-11 查询“4月21号爸爸有什么安排”

**目标**
验证系统可按成员 + 日期检索日程。

**输入**
> 4月21号爸爸有什么安排？

**前置条件**
- 已存在 TC-P0-07 中的日程记录。

**期望处理逻辑**
1. 识别为 schedule query。
2. 过滤 member = 爸爸。
3. 过滤 date = 2026-04-21。
4. 返回对应安排。

**期望答案**
> 爸爸在4月21号有一个安排：去大阪。

**判定标准**
- 通过：检索结果正确。
- 失败：查不到、查错人、查错日期。

---

### TC-P0-12 规则联动验证：爸爸消费触发即时提醒

**目标**
验证 TC-P0-09 的规则在新消费写入后会生效。

**前置条件**
- 已创建“爸爸当天消费超过1000日元提醒”规则。

**测试输入**
新增一条消费：
> 爸爸今天买工具花了200日元

与 TC-P0-05 中爸爸昨天的消费无关，因此建议另外加一组当天测试：
> 爸爸今天早餐花了600日元，今天晚餐花了500日元

**期望处理逻辑**
1. 新增消费进入 expense ingestion workflow。
2. 写入成功后触发 rule evaluation。
3. 汇总爸爸当天总消费。
4. 若总额 > 1000，则生成 alert。

**期望结果**
- 当天总额 1100 日元。
- 系统输出提醒：爸爸今天消费过高。
- Alert 记录写入系统。

**判定标准**
- 通过：达到阈值后自动提醒。
- 失败：规则存在但未触发，或阈值计算错误。

---

## 8. P1 重要补充测试用例

### TC-P1-01 模型路由验证：创建 Agent 时的模型分配

**目标**
验证在“创建家庭成员 Agent”过程中，系统按任务类型选择模型。

**验证点**
- intent_analysis → 快速模型
- task_planning → 规划模型
- agent_design / agent_reasoning → 强推理模型
- 普通追问 / 确认 → general_chat

**期望结果**
每个步骤的 model selection 与 LiteLLM routing_policies 基本一致。LiteLLM 设计要求按 task_type 自动选择 primary 与 fallback。fileciteturn0file3L268-L343

---

### TC-P1-02 Blueprint 编译为 Workflow 图

**目标**
验证已创建的家庭相关 Blueprint 能被编译为 LangGraph Workflow。

**验证点**
- Blueprint 包含 steps 与 edges。
- BlueprintCompiler 可将其转换为 StateGraph。
- 执行入口和出口正确设置。Blueprint 编译器设计中要求读取 YAML，添加节点和边，设置入口点，并编译为 workflow。fileciteturn0file2L145-L204

---

### TC-P1-03 Workflow 状态推进正确

**目标**
验证 Workflow 执行过程中 state 的 current_step、results、errors、retry_count、should_continue 等字段推进正确。

**期望结果**
符合 WorkflowState 设计。fileciteturn0file2L27-L53

---

### TC-P1-04 信息不足时的追问机制

**目标**
验证在记录消费时，若成员名不存在或含糊，系统会追问而不是错误写入。

**输入**
> 她今天买菜花了1200日元

**期望结果**
- 因“她”指代不明，系统要求用户确认是哪个成员。
- 不应直接写入错误数据。

---

### TC-P1-05 时间表达式歧义处理

**目标**
验证对“本周六”“下周六”“昨天”“4月11号”这类时间表达式的规范处理。

**期望结果**
- 归一化时间值可追踪。
- 若系统对周起始规则有设定，应统一。
- 必要时可在 UI 或日志中保留原始表达式与解析结果。

---

### TC-P1-06 提醒范围验证：所有成员日程均可被前一天提醒

**目标**
验证“前一天提醒”规则不是只作用于单人，而是覆盖所有参与提醒的家庭成员。

**期望结果**
- 爸爸、妈妈、朱棣、小羽后续新增日程都能自动纳入提醒范围。

---

### TC-P1-07 提醒规则与成员开关联动

**目标**
验证如果某个成员被设置为“不参与提醒”，则不应收到前一天提醒。

**说明**
这是对成员 profile 与 rule scope 联动的补充验证。

---

### TC-P1-08 问答回答引用最新 Memory

**目标**
验证当后续又追加新的消费/日程后，查询回答会基于最新数据，而不是停留在旧上下文缓存。

---

## 9. P2 增强与边界测试

### TC-P2-01 重复创建家庭成员 Agent 的幂等性

**目标**
验证同一个家庭已存在 Agent 时，再次输入“帮我创建家庭成员的智能体”，系统是复用还是增量更新，而不是重复创建多个冲突 Agent。

---

### TC-P2-02 重复录入消费的去重能力

**目标**
验证相同语句重复输入时，系统是否有去重提示或防重策略。

---

### TC-P2-03 多条输入中部分成功、部分失败的事务处理

**目标**
验证在 4 条消费中，若某一条成员无法识别，系统如何处理：
- 全部回滚
- 部分成功并提示失败项
- 暂存待确认

---

### TC-P2-04 阈值边界等于 1000 的处理

**目标**
验证规则 “超过1000日元” 是否严格为 `>` 而不是 `>=`。

**测试数据**
- 爸爸当天总消费 = 1000 → 不提醒
- 爸爸当天总消费 = 1001 → 提醒

---

### TC-P2-05 自然语言查询组合问题

**目标**
验证系统可处理组合问句：
> 4月份谁花得最多？爸爸和妈妈一共花了多少？

---

### TC-P2-06 支持扩展字段

**目标**
验证未来新增字段（例如消费地点、支付方式、备注）时，Agent 与 Blueprint 是否可扩展，而不破坏现有流程。

---

## 10. 端到端集成测试脚本建议

以下为推荐的端到端测试顺序：

### E2E-01 家庭管理能力构建
1. 输入：帮我创建家庭成员的智能体
2. 多轮补充：成员、关系、默认币种、是否参与统计、是否参与提醒
3. 验证：AgentSpec 已创建
4. 验证：Blueprint 已创建/绑定
5. 验证：家庭成员资料入库

### E2E-02 批量消费录入与查询
1. 输入消费自然语言
2. 验证 4 条消费落库
3. 查询 4 月全家消费
4. 验证回答 4700 日元

### E2E-03 批量日程录入与查询
1. 输入日程自然语言
2. 验证 3 条日程落库
3. 查询爸爸 4 月 21 日安排
4. 验证回答“去大阪”

### E2E-04 提醒规则创建与触发
1. 创建前一天提醒规则
2. 创建爸爸消费超额提醒规则
3. 新增测试消费
4. 验证即时提醒触发

---

## 11. 预期内部对象示例

### 11.1 家庭成员 AgentSpec 示例

```json
{
  "agent_id": "agent_family_manager_001",
  "name": "family_manager_agent",
  "role": "家庭成员、消费、日程与提醒管理智能体",
  "goals": [
    "维护家庭成员资料",
    "记录家庭消费",
    "记录家庭日程",
    "创建提醒规则",
    "回答家庭统计与查询问题"
  ],
  "model_policy": {
    "planning": "task_planning",
    "extraction": "fast_extraction",
    "reasoning": "agent_reasoning",
    "answering": "general_chat"
  },
  "tool_policy": [
    "memory_write",
    "memory_query",
    "rule_engine",
    "scheduler"
  ],
  "blueprints": [
    "family_member_profile_collection",
    "family_expense_ingestion",
    "family_schedule_ingestion",
    "family_reminder_rule_engine",
    "family_nl_query"
  ]
}
```

### 11.2 消费记录对象示例

```json
{
  "record_type": "expense",
  "member_name": "妈妈",
  "member_id": "member_mother",
  "date": "2026-04-16",
  "amount": 2000,
  "currency": "JPY",
  "category": "餐饮/食材",
  "description": "买菜",
  "source": "nl_ingestion"
}
```

### 11.3 日程记录对象示例

```json
{
  "record_type": "schedule",
  "member_name": "爸爸",
  "member_id": "member_father",
  "date": "2026-04-21",
  "title": "去大阪",
  "source": "nl_ingestion"
}
```

### 11.4 提醒规则对象示例

```json
{
  "rule_id": "rule_schedule_pre_day_all",
  "rule_type": "schedule_pre_day_reminder",
  "scope": "all_members",
  "trigger_offset": "-1_day",
  "action": "send_reminder"
}
```

---

## 12. 验收标准

### 12.1 功能验收

以下条件全部满足，视为整体测试通过：

1. 能通过会话式方式完成家庭成员 Agent 创建。
2. 能自动生成或复用相关 Blueprint。
3. 能将一段消费自然语言拆成多条结构化记录。
4. 能将一段日程自然语言拆成多条结构化记录。
5. 能创建前一天提醒规则。
6. 能创建当天消费超额提醒规则。
7. 能在新增数据后自动评估并触发提醒。
8. 能回答“4 月总消费”“某日某人的安排”等查询。

### 12.2 架构验收

以下架构行为应能被日志或 trace 观察到：

- Core 完成 intent → task → workflow / agent 决策链路。fileciteturn0file1L112-L137
- WorkflowState 或 AgentState 有状态推进。fileciteturn0file2L27-L53
- ModelRouter 根据 task_type 进行模型选择。fileciteturn0file3L268-L343
- Blueprint 在需要时被匹配或生成。fileciteturn0file1L64-L72

### 12.3 可复用性验收

- 第二次录入家庭消费时，不需要重新创建家庭成员 Agent。
- 第二次录入家庭日程时，可直接复用已有家庭成员与提醒规则。
- 查询时可复用既有 Memory 和 Blueprint。

---

## 13. 推荐的日志与观测点

建议在测试时输出以下 trace：

1. `intent_analysis_result`
2. `requires_agent`
3. `workflow_plan`
4. `selected_models_by_task`
5. `resolved_blueprints`
6. `generated_blueprints`
7. `agent_spec`
8. `memory_write_result`
9. `rule_evaluation_result`
10. `query_aggregation_trace`

这样可以对应 Core、LiteLLM、Workflow、Agent 四个层面的验证。

---

## 14. 结论

这组测试用例的核心，不只是验证“是否能回答问题”，而是验证系统是否真正具备以下能力：

- 把自然语言转成长期可复用的家庭管理 Agent
- 把自然语言记录转成结构化消费与日程数据
- 把自然语言规则转成可执行提醒逻辑
- 把自然语言查询转成聚合检索与回答
- 在整个过程中正确使用 Core、LiteLLM、Blueprint、Workflow、Agent、Memory 进行协作

这与当前设计文档中对 AI Core 的总目标一致：不是只回答一句话，而是“把用户意图转化为可执行、可复用、可演化的系统能力”。fileciteturn0file1L186-L190

