# HomeHub External Bridge API 设计说明
## 1. 设计定位

这个 API **不是通用平台接口**，也**不是多家庭/多租户网关**。

它存在的唯一原因是：

> 为了让外部 IM 与家中的 HomeHub 在 **家庭网络无法绑定公网域名** 的情况下，仍然可以通过一个部署在外网的轻量 API 进行信息交互。

因此，这个 API 的角色应当被严格限定为：

- 单家庭专用
- 外网桥接
- 轻量转存与转发辅助
- 安全控制尽量简单直接
- 配置驱动，不做复杂后台管理

推荐部署位置：

- Railway
- Render
- VPS
- 其他可提供 HTTPS 公网地址的轻量环境

---

## 2. 核心目标

这个 API 只解决一个问题：

> **外部 IM 无法直接访问家中的 Hub，而家中的 Hub 又需要一个公网可访问的中转点。**

所以最终形成的通信模式是：

```text
IM -> External Bridge API -> HomeHub
HomeHub -> External Bridge API -> IM（如需要）
```

但这里的“转”不是复杂消息路由系统，而是：

- IM 把消息送到外网 API
- 家中 Hub 主动拉取或上报
- API 保存必要状态
- API 按配置把结果组织成 IM 可使用的格式

---

## 3. 设计边界

### 3.1 这个 API 要做的事

只做这些：

1. 接收来自外部 IM 的消息
2. 保存消息的最小必要信息
3. 允许家中的 Hub 读取待处理消息
4. 允许家中的 Hub 回传处理结果
5. 基于本地 config，把 IM 相关字段映射为 HomeHub 可识别的数据
6. 提供一个简单、安全、稳定的公网桥接接口

### 3.2 这个 API 不做的事

明确不做：

- 不做多租户
- 不做复杂路由
- 不做中间编排系统
- 不做 AI Core
- 不做 OCR / STT / 文件解析
- 不做 Blueprint 执行
- 不做任务规划
- 不做复杂权限系统
- 不做完整管理后台
- 不做动态数据库配置中心

也就是说：

> 这个 API 只是桥，不是大脑。

AI 处理、能力解析、运行时调度，都应继续放在家中的 HomeHub 内部完成。

### 3.3 与延迟文档处理链路的关系

当前桥接层已经支持“请求先到 / 附件后到”以及“附件先到 / 请求后到”的双阶段会话链路，但桥接层本身仍不负责 AI 分析。

桥接层只负责：

1. 把 LINE / 外部 IM 的文档或图片可靠落到 `received/`。
2. 维持稳定的会话 ID，让后续文本请求能命中同一个 session。
3. 在附件-only 场景下使用中性文案，例如 `收到文档: xxx`，避免桥接层抢先触发业务分析。

实际的等待窗口、待处理请求、OCR 与文档总结/翻译，全部由 NestHub runtime 内部处理。

---

## 4. 单家庭模型

由于只服务一个家庭，因此系统模型应该极简化。

无需设计：

- tenant_id
- org_id
- workspace_id
- routing_rule_id
- bridge_group
- multi-home registry

建议固定逻辑：

- 一个部署实例 = 一个家庭
- 一个配置文件 = 这个家庭当前全部桥接规则
- 一个认证 token = HomeHub 与外网 API 的共享密钥

这样能让整个系统简单、稳定、容易维护。

---

## 5. 安全模型

## 5.1 唯一核心认证

> API 与家中的 Hub 交互，为了安全，只需要 `HOMEHUB_EXTERNAL_BRIDGE_TOKEN`。

因此推荐安全策略如下：

- Hub 调用 API 时，必须携带：
  - `Authorization: Bearer <HOMEHUB_EXTERNAL_BRIDGE_TOKEN>`
- API 验证通过才允许：
  - 拉取 pending 消息
  - 回传处理结果
  - 读取桥接状态
  - 调用内部桥接接口

这个 token 是整个单家庭桥接系统的唯一核心认证凭证。

### 5.2 为什么这样设计足够

因为场景不是开放平台，而是：

- 你自己部署
- 只服务你家中的一个 Hub
- 没有多用户后台
- 没有复杂第三方接入生态

所以没必要引入：

- OAuth
- JWT 刷新机制
- 多角色权限树
- API Key 管理平台
- 复杂 RBAC

复杂安全模型只会增加维护成本。


## 6. 配置驱动原则

要求：

> 可以根据家中的 hub 进行追加 api 与 im 之间关联用的，主要是 key value 的格式，可以追加到专门为这个 api 用的 config 文件中，api 可以直接使用 config 文件中的设置。

这意味着：

### 6.1 配置文件应成为桥接规则中心

推荐把所有桥接相关设置集中在一个专用 config 文件中，例如：

- `api/public_api/config/bridge.yaml`
- 或 `api/public_api/config/bridge.json`

这个文件负责定义：

- bridge token
- 支持的 IM 平台
- IM 字段映射
- 默认 channel / conversation / target
- Hub 拉取策略相关参数
- 回传结果格式映射
- 其他 key-value 扩展项

### 6.2 配置文件特点

这个 config 文件应满足：

- 纯配置驱动
- key-value 易扩展
- 不依赖数据库才能运行
- API 启动时可直接加载
- 支持按需增加字段，不破坏原有结构

也就是说：

> API 的“IM 适配关系”不写死在代码里，而是由 config 文件描述。

---

## 7. 推荐配置文件结构

推荐示例：

```yaml
bridge:
  name: homehub-external-bridge
  mode: single_home
  token_env: HOMEHUB_EXTERNAL_BRIDGE_TOKEN

hub:
  family_id: home-001
  poll_interval_seconds: 5
  result_ttl_seconds: 86400

im:
  provider: line
  enabled: true
  mapping:
    user_id_key: sender_id
    chat_id_key: conversation_id
    message_text_key: text
    message_id_key: external_message_id
    timestamp_key: timestamp
  defaults:
    channel: default
    language: ja
  extra:
    reply_mode: passive
    allow_push_result: true

kv:
  home_name: my-homehub
  timezone: Asia/Tokyo
  im_label: family-im
  notes: single family deployment only
```

或者更通用一点：

```yaml
bridge:
  token_env: HOMEHUB_EXTERNAL_BRIDGE_TOKEN

im_bindings:
  line:
    enabled: true
    inbound_message_key: text
    inbound_user_key: userId
    inbound_chat_key: groupId
    outbound_target_key: replyToken
  slack:
    enabled: false
  telegram:
    enabled: false

custom_kv:
  family_code: A001
  homehub_mode: production
  preferred_locale: ja-JP
```

重点不是字段名字必须固定，而是：

- API 启动时读取 config
- 内部统一转换为标准 bridge config model
- 业务逻辑都从 config model 取值

---

## 8. API 的最小职责模型

### 8.1 inbound：IM -> API

职责：

- 接收 IM 送来的原始消息
- 按 config 提取关键字段
- 存成桥接消息记录
- 标记为 `pending`

最小记录建议：

- `bridge_message_id`
- `source_im`
- `external_user_id`
- `external_chat_id`
- `external_message_id`
- `text`
- `raw_payload`
- `status`
- `created_at`

### 8.2 pending：Hub -> API

职责：

- 家中的 Hub 通过 token 拉取待处理消息
- API 返回未处理消息列表

### 8.3 result：Hub -> API

职责：

- Hub 提交处理结果
- API 保存结果、状态、时间
- 如果 config 允许，也可生成 IM 回传所需字段

### 8.4 query：状态查询

职责：

- 通过 `bridge_message_id` 查询状态
- 查看是否已被 Hub 拉取
- 查看是否已处理完成

---

## 9. 推荐状态流转

推荐只保留最少状态：

```text
pending -> claimed -> completed
                    -> failed
```

说明：

- `pending`：IM 消息已进入桥接 API，等待 Hub 获取
- `claimed`：Hub 已拉取，正在家中处理
- `completed`：Hub 处理完成并已回写结果
- `failed`：Hub 处理失败

不要一开始就设计太多状态，否则对单家庭桥接没有意义。

---

## 10. 存储策略

由于这是单家庭轻量桥接，优先级建议：

### 第一阶段

可以先用：

- 内存 + JSON 文件
- 或 SQLite

优点：

- 部署简单
- Railway 也容易先跑起来
- 易调试

### 第二阶段

如果后续桥接消息增多，再换：

- PostgreSQL
- Redis + PostgreSQL

但不建议一开始就上复杂存储。

---

## 11. 推荐接口集合

### 11.1 IM 接入

```text
POST /api/bridge/im/inbound
```

用途：

- 外部 IM 调用
- 提交消息到桥接 API

### 11.2 Hub 拉取待处理消息

```text
GET /api/bridge/hub/pending
```

用途：

- 家中的 Hub 使用 token 拉取待处理消息
- API 返回未处理消息列表

---

## 16. 实际对接要点与常见问题

### 16.1 IM webhook 字段提取规范

以 LINE 为例，webhook payload 结构如下：

```json
{
  "events": [
    {
      "source": { "userId": "Uxxxx", "groupId": "Gxxxx" },
      "message": { "id": "123", "text": "hello" },
      ...
    }
  ]
}
```

API 必须从 `events[0].source.userId`、`events[0].source.groupId`、`events[0].message.id`、`events[0].message.text` 提取对应字段，不能直接用顶层字段。

### 16.2 主动推送原理

如需异步业务处理后再回复 IM 用户，需用 IM 官方 push API（如 LINE 的 `/v2/bot/message/push`），不能用 replyToken。API 会在 `/hub/result` 阶段自动用 userId 主动推送消息。

### 16.3 调试与日志建议

- `/im/inbound` 路由会详细打印 X-Line-Signature、原始 payload、提取字段、创建消息等日志，便于排查。
- 如推送失败，优先检查 userId 是否为真实 IM 用户 ID，access token 是否有效。

### 16.4 常见问题排查

1. **消息 claim/result 都 200，但 IM 没收到消息？**
   - 检查 `/im/inbound` 是否正确提取 userId。
   - 检查 `/hub/result` 是否有主动推送日志。
   - 检查 access token 权限。
2. **replyToken 回复无效？**
   - 只能在 webhook 首次收到时同步 reply，异步处理需用 push API。

---

### 11.3 Hub claim 消息

```text
POST /api/bridge/hub/claim
```

用途：

- 将消息标记为已拉取、处理中

### 11.4 Hub 回传结果

```text
POST /api/bridge/hub/result
```

用途：

- 保存 HomeHub 处理结果

### 11.5 查询桥接消息状态

```text
GET /api/bridge/messages/{bridge_message_id}
```

用途：

- 查看当前处理状态与结果摘要

### 11.6 健康检查

```text
GET /api/health
```

---

## 12. HomeHub 侧职责

HomeHub 应负责：

- 周期性调用 `/api/bridge/hub/pending`
- 取回待处理消息
- 组装成内部 Unified Context
- 调用自身 Core / Blueprint / Feature / Service
- 完成处理后调用 `/api/bridge/hub/result`

重点：

> 外网 API 不参与 HomeHub 内部智能处理，它只是把消息交到 Hub 手里。

---

## 13. 代码设计原则

这个模块应当尽量保持以下特点：

### 13.1 简单可读

- 单一职责
- 配置驱动
- 少抽象层级
- 不提前过度框架化

### 13.2 易扩展

- IM 字段映射通过 config 扩展
- key-value 参数追加即可生效
- 不需要改数据库结构才能加一批小配置

### 13.3 易部署

- Railway 一键部署
- 只依赖环境变量 + config 文件
- 默认 HTTPS 暴露接口

### 13.4 易让 AI 继续生成代码

目录、命名、接口、数据模型都要清晰直白。

---

## 14. 推荐目录设计

结合你现有结构，建议把外网桥接 API 控制在这里：

```text
api/
  public_api/
    app.py
    main.py
    routes/
      health.py
      bridge_im.py
      bridge_hub.py
      bridge_messages.py
    models/
      request.py
      response.py
      bridge_message.py
      config_model.py
    services/
      bridge_service.py
      config_service.py
      auth_service.py
    storage/
      base.py
      memory_store.py
      json_store.py
    config/
      bridge.yaml
```

这样后续 AI 一看就知道：

- route 负责接口
- service 负责逻辑
- storage 负责持久化
- config 负责桥接参数

---

## 15. 最终设计结论

这次应当采用的正确设计思想是：

> **HomeHub External Bridge API = 单家庭、外网部署、配置驱动、token 保护的轻量桥接接口。**

它不是平台，不是网关，不是多租户中转中心。

它只负责：

- 接 IM 消息
- 给家中 Hub 提供公网可访问入口
- 用 `HOMEHUB_EXTERNAL_BRIDGE_TOKEN` 做最小安全控制
- 通过 config 文件维护 IM 与 Hub 的字段映射及 key-value 扩展配置

换句话说：

> 它的存在意义，不是“做复杂系统”，而是“让外面的消息能安全、稳定地进到家里的 Hub，再把结果按需要带回来”。

