# NestHub AI Core HTTP API 调用示例

本节说明如何通过 HTTP 方式调用 AI Core 能力（如 /core/handle 接口），适用于 TVBox、外部服务等场景。

## 1. 请求示例

```bash
curl -X POST http://localhost:8000/core/handle \
  -H "Content-Type: application/json" \
  -d '{
    "input_text": "帮我规划今天的日程",
    "context": {"user_id": "demo_user"}
  }'
```

## 2. 请求参数
- `input_text`：用户输入文本。
- `context`：上下文信息（如 user_id、会话等）。

## 3. 返回结果
返回结构如下：
```json
{
  "result": {
    "task": ...,
    "workflow": ...,
    "execution_result": ...
  }
}
```

## 4. 说明
- 端口和路径需与实际部署一致。
- 可用 Postman、httpx、requests 等工具调用。
- 适合 TVBox 前端、第三方服务集成。

---

如需 Python 代码调用示例，可补充 requests/httpx 代码片段。
