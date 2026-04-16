# Semantic Memory Dashboard Example

这是一个纯静态示例页面，用来查看 NestHub 的 semantic memory 状态。

## 目录

- `index.html`: 页面入口
- `styles.css`: 样式
- `app.js`: 调用 `/core/admin/semantic-memory` 的前端逻辑

## 使用方式

1. 先启动 NestHub FastAPI 服务。
2. 打开 `examples/semantic-memory-dashboard/index.html`。
3. 在页面中填入 API Base URL，例如 `http://127.0.0.1:8000`。
4. 可选设置 `policy_key` 和 `status` 过滤。
5. 点击 `Refresh` 查看候选区、激活区、回滚信息和版本快照。

## 接口依赖

页面依赖以下接口：

- `GET /core/admin/semantic-memory`
- `GET /core/admin/semantic-memory?policy_key=location_markers&status=active`

## 说明

- 这是示例目录下的独立 demo，不会改动系统主 UI。
- 如果浏览器直接打开静态文件时遇到跨域限制，建议用任意本地静态文件服务打开该目录。