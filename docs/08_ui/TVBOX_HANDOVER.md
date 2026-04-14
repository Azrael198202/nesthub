# TVBox 模块交接文档（给后续 AI / 开发者）

最后更新：2026-04-14

## 1. 目标与当前状态
- 目标：`nethub_runtime/ui/tvbox` 提供一个可本地运行的 TV Dashboard（FastAPI + 原生前端）。
- 当前状态：可运行、可切换多语言（zh/en/ja）、支持 demo 数据驱动；但前端仍存在大量硬编码多语言文案未迁移，属于“半迁移状态”。

## 2. 目录结构与职责
```text
nethub_runtime/ui/tvbox/
├── main.py                         # FastAPI 入口 + demo API
├── components/
│   └── i18n.py                     # i18n JSON 扫描、locale 归一化、接口 payload 构建
├── i18n/
│   ├── locales/
│   │   ├── zh-CN.json
│   │   ├── en-US.json
│   │   └── ja-JP.json
│   └── settings_texts.py           # 旧方案（基本已废弃，保留中）
└── static/
    ├── index.html                  # 页面骨架
    ├── assets/
    │   ├── app.js                  # 主逻辑（状态、渲染、事件、API调用）
    │   └── app.css
    └── generated/vendor/three/     # Three.js 相关资源
```

额外 demo 数据来源：
- `examples/ui/dashboard.demo.json`
- `examples/ui/cortex_unpacked.demo.json`

## 3. 运行与数据流
### 3.1 启动入口
- 文件：`nethub_runtime/ui/tvbox/main.py`
- `main()` 中使用 `uvicorn.run(..., port=7788)` 启动。

### 3.2 前后端主流程
1. 前端 `app.js` 启动后请求 `/api/dashboard` 获取全量 dashboard 快照。
2. 读取 `languageSettings.current`，调用 `/api/i18n/settings?locale=...`。
3. 后端从 `i18n/locales/*.json` 扫描语言并返回：
   - `strings`（设置页等）
   - `uiText`（主界面文案）
   - `fallbackUiText`
4. 前端 `t(path)` 从 `UI_TEXT[currentLocale]` 查找文案，不命中再走 `en-US` fallback。

## 4. 后端 API 清单（main.py）
### GET
- `/`
- `/api/logs/latest`
- `/api/dashboard`
- `/api/i18n/settings`
- `/api/bootstrap/status`
- `/api/custom-agents`

### POST
- `/api/bootstrap/approve`
- `/api/cortex/unpacked`
- `/api/device/location`
- `/api/memory/reminders/complete`
- `/api/settings/language`
- `/api/settings/audio`
- `/api/settings/avatar`
- `/api/settings/audio-provider`
- `/api/settings/secrets`
- `/api/external-channels/email/sync`
- `/api/external-channels/email/send`
- `/api/audio/transcribe`
- `/api/voice/chat`
- `/api/custom-agents/intake`
- `/api/custom-agents/generate-feature`
- `/api/custom-agents/delete`
- `/api/custom-agents/delete-feature`

说明：多数是 demo/stub 行为，真实业务逻辑尚未接入。

## 5. i18n 现状（重点）
### 5.1 已完成
- `components/i18n.py` 改为扫描 `i18n/locales/*.json` 动态加载。
- `uiText` 与 `strings` 都可通过 `/api/i18n/settings` 返回。
- 新增 key 后可无代码支持新语言（只要放入新 locale JSON）。

### 5.2 未完成（核心技术债）
- `app.js` 仍有大量 `localizeInline(...)`、`currentLocale === "zh-CN" ? ...` 分支。
- 一些中文/日文/英文字符串仍写死在 `app.js`，未走 `t(...)`。
- `i18n/settings_texts.py` 为旧字典方案，已与 JSON 扫描方案重复。

## 6. 已知问题与改进清单
### P0（优先立刻处理）
- [ ] **统一默认语言配置来源**  
  当前默认值在多处存在：`main.py` fallback、`examples/ui/dashboard.demo.json`、`app.js` 中部分默认字段。需统一到单一来源。
- [ ] **完成前端文案全量迁移到 locale JSON**  
  将 `app.js` 的 `localizeInline(...)` 和三语对象全部替换为 `t("...")`。
- [ ] **移除 key 原样显示风险**  
  对关键区块加“缺失 key 监控/日志”（开发模式下告警）。

### P1（短期应完成）
- [ ] 清理 `i18n/settings_texts.py`（删除或标注 deprecated，避免误用）。
- [ ] 在 `main.py` 为接口补充请求/响应 schema（Pydantic），减少 422 与字段歧义。
- [ ] 为 `/api/settings/language` 增加持久化（当前仅内存态）。
- [ ] 为 i18n 增加单测：locale 扫描、fallback、缺 key 行为。

### P2（中期优化）
- [ ] 将 `app.js` 拆分模块（i18n、api、render、state、events）。
- [ ] 补充真实后端能力接入（邮件、agent、feature runtime）。
- [ ] 增加类型约束（TS 或 JSDoc 类型）降低大文件维护成本。

## 7. 后续 AI 接手建议（按任务入口）
### 7.1 想改语言文案
- 改 `nethub_runtime/ui/tvbox/i18n/locales/*.json`
- 检查 `app.js` 是否仍硬编码该文案。

### 7.2 想新增语言
1. 新增 `i18n/locales/<locale>.json`
2. 确保字段含 `locale/label/sample/strings/uiText`
3. 前端设置页会自动出现该语言（来自 `/api/i18n/settings` 的 `supportedLanguages`）

### 7.3 想改首页数据
- 改 `examples/ui/dashboard.demo.json`（demo 模式）
- 或改 `main.py` 中 `dashboard_fallback`

### 7.4 想改接口行为
- 改 `nethub_runtime/ui/tvbox/main.py`
- 保持 `app.js` 的 payload 字段兼容（尤其 `dashboard` 和 `voice/chat`）

## 8. 验证清单（每次改完建议执行）
- [ ] 切换中/英/日后，tab、top bar、settings、buddy 文案都正确。
- [ ] 页面不出现 `tabs.xxx / status.xxx / buddy.xxx` 这种 key 原样文本。
- [ ] `/api/i18n/settings?locale=xx` 返回的 `uiText` 非空且包含 `tabs/top/status`。
- [ ] `/api/settings/language` 返回 200，且 dashboard 的 `languageSettings.current` 同步更新。

## 9. 备注（关键历史问题）
- 之前出现过语言切换 422，原因与请求参数解析/注解处理有关；当前版本已通过 `Request` 解析兼容和接口容错逻辑处理。
- 之前出现过 i18n key 原样显示，根因是 locale 扫描时未把 `uiText` 放入 catalog；现已修复。

---
如果后续要继续重构，建议先做“全量文案迁移 + 删除旧 i18n 方案”，再进行 `app.js` 模块拆分。
