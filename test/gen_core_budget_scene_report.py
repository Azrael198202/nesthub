from fastapi.testclient import TestClient
from nethub_runtime.core.main import app
import json

client = TestClient(app)

# 1. 消费记录录入
input_text = "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。"
context = {"session_id": "budget_scene_e2e"}
report_lines = []

report_lines.append("# 自动化测试报告\n")
report_lines.append("## 消费记录录入\n")
report_lines.append(f"**输入：** {input_text}\n")

payload = {"input_text": input_text, "context": context, "output_format": "dict"}
resp = client.post("/core/handle", json=payload)
assert resp.status_code == 200
record_data = resp.json()["result"]
report_lines.append("**输出：**\n")
report_lines.append(json.dumps(record_data, ensure_ascii=False, indent=2) + "\n")

# 2. 查询问答
questions = [
    "5月份第一周一共花了多少钱？",
    "这个月餐饮花了多少？",
    "我个人花了多少？",
    "家人花了多少？",
    "咖啡一共花了多少？",
    "博多地区消费总额是多少？"
]

report_lines.append("## 查询问答\n")
for q in questions:
    payload = {"input_text": q, "context": context, "output_format": "dict"}
    resp = client.post("/core/handle", json=payload)
    assert resp.status_code == 200
    result = resp.json()["result"]
    report_lines.append(f"**问题：** {q}\n")
    report_lines.append("**输出：**\n")
    report_lines.append(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

# 3. 保存报告
with open("test/core_budget_scene_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

print("测试完成，报告已追加到 test/core_budget_scene_report.md")
