# Family Agent Workflow Pending Activation Evaluation Report

## 1. Purpose

This report evaluates whether selected `pending` scenarios in the family agent overall dataset can be promoted to `active` based on current `/core/handle` runtime behavior.

Evaluation date: `2026-04-16`
Evaluation timestamp: `20260416_135730`
Runtime endpoint: `/core/handle`
Execution mode: `use_langraph=false`

## 2. Evaluation Method

Representative inputs were executed directly against the current core runtime using `fastapi.testclient.TestClient`.

For each scenario, the evaluation checked:

1. whether intent classification matched expectation
2. whether `need_agent` / long-term capability routing matched expectation
3. whether a verifiable runtime artifact or output structure existed
4. whether the scenario is ready to be promoted from `pending` to `active`

## 3. Evaluated Pending Scenarios

### 3.1 TC-P0-01 识别创建家庭成员智能体为长期能力意图

**Probe Input**

```text
帮我创建家庭成员的智能体
```

**Expected (from test plan)**

- long-term capability intent
- agent creation semantics
- `need_agent=true`
- ideally `intent=create_agent` or equivalent

**Actual Runtime Result**

- `intent=general_task`
- `domain=general`
- `need_agent=true`
- generated `blueprint` artifact observed
- no `agent` output observed
- final output only contains `single_step`

**Assessment**

- partial signal exists: `need_agent=true`
- expectation not fully met: intent and domain are still too generic
- no stable family-agent creation output is exposed

**Promotion Decision**

- `DO NOT PROMOTE`

### 3.2 TC-P0-08 创建前一天提醒规则

**Probe Input**

```text
给所有人的日程安排的前一天发出提醒。
```

**Expected**

- reminder/rule creation path
- persistent or queryable rule output
- verifiable reminder capability object

**Actual Runtime Result**

- `intent=data_record`
- `domain=data_ops`
- `need_agent=false`
- workflow executed as record persistence path
- final output keys only contain `extract_records` and `persist_records`
- only `trace` artifact exposed

**Assessment**

- runtime treats the request as a record ingestion operation, not as rule creation
- no reminder rule entity or stable observable rule artifact exists

**Promotion Decision**

- `DO NOT PROMOTE`

### 3.3 TC-P0-09 创建当天消费超额提醒规则

**Probe Input**

```text
如果爸爸的消费当天超过1000日元就发出提醒消费过高。
```

**Expected**

- threshold rule creation path
- rule/monitoring object creation
- stable assertion surface for threshold logic

**Actual Runtime Result**

- `intent=data_record`
- `domain=data_ops`
- `need_agent=false`
- handled as ordinary record workflow
- final output keys only contain `extract_records` and `persist_records`
- only `trace` artifact exposed

**Assessment**

- threshold logic is not recognized as a rule definition path
- no monitoring rule or threshold policy object is returned

**Promotion Decision**

- `DO NOT PROMOTE`

### 3.4 TC-P0-12 爸爸消费触发即时提醒

**Probe Input**

```text
爸爸今天吃饭花了1200日元，如果超过1000日元就提醒我。
```

**Expected**

- event + threshold alert semantics
- alert-capable rule trigger or alert output
- stable observable alert result

**Actual Runtime Result**

- `intent=data_record`
- `domain=data_ops`
- `need_agent=false`
- ordinary record workflow executed
- no alert output exposed
- no rule artifact exposed

**Assessment**

- expense text is recognized, but alert semantics are not surfaced as a rule or event capability
- no automated assertion surface exists for expected alert behavior

**Promotion Decision**

- `DO NOT PROMOTE`

### 3.5 TC-P1-09 缺失能力时系统可自主写代码补齐功能

**Probe Input**

```text
系统缺少家庭提醒能力时，请自己写代码补齐并生成补丁。
```

**Expected**

- capability gap recognition
- autonomous implementation trigger
- stable generated patch / code artifact observation

**Actual Runtime Result**

- `intent=general_task`
- `domain=general`
- `need_agent=false`
- autonomous trace reports support exists
- `capability_gap_detected=false`
- no generated patch/code result exposed
- `blueprint` + `trace` artifacts observed only as generic runtime outputs

**Assessment**

- capability declaration exists in runtime
- explicit gap-triggered self-coding behavior is not stably observable from this path

**Promotion Decision**

- `DO NOT PROMOTE`

## 4. Summary Matrix

| Scenario | Expected Status | Actual Status | Meets Expectation | Promotion |
| --- | --- | --- | --- | --- |
| TC-P0-01 | Agent creation intent | Generic task + need_agent | No | No |
| TC-P0-08 | Reminder rule creation | Record ingestion | No | No |
| TC-P0-09 | Threshold rule creation | Record ingestion | No | No |
| TC-P0-12 | Alert trigger behavior | Record ingestion | No | No |
| TC-P1-09 | Capability-gap self-coding | Support declared only | No | No |

## 5. Final Conclusion

At the current implementation state, the evaluated `pending` scenarios should **not** be moved into `active` status.

Reason:

1. runtime behavior does not yet match the documented semantic expectation
2. stable assertion surfaces are still missing for rule creation, alert triggering, and family-agent creation
3. promoting these cases prematurely would create false failures and blur the distinction between regression and not-yet-implemented capability

## 6. Recommended Promotion Order

The next scenario most likely to become executable first is still:

1. `TC-P0-01` 识别创建家庭成员智能体为长期能力意图

Because current runtime already exposes one useful precursor signal:

- `need_agent=true`

But before promotion, at least one of the following should be stabilized:

- dedicated `intent=create_agent` or equivalent family-agent intent
- family-management domain classification
- stable `agent` object output or family-agent planning artifact
