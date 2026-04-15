import json
from datetime import datetime
from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from nethub_runtime.core.main import app

client = TestClient(app)
OUTPUT_DIR = ROOT_DIR / "test"

# 只测试有问题的两个问答
input_text = "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。"
context = {"session_id": "budget_scene_e2e"}
report_lines = []

report_lines.append("# 精简自动化测试报告\n")
report_lines.append("## 消费记录录入\n")
report_lines.append(f"**输入：** {input_text}\n")

payload = {"input_text": input_text, "context": context, "output_format": "dict", "use_langraph": False}
resp = client.post("/core/handle", json=payload)
assert resp.status_code == 200
record_data = resp.json()["result"]
report_lines.append("**输出：**\n")
report_lines.append(json.dumps(record_data, ensure_ascii=False, indent=2) + "\n")

# 只保留有问题的两个问答
questions = [
    "这个月餐饮花了多少？",
    "4月份一共花了多少钱？"
]

report_lines.append("## 查询问答\n")
for q in questions:
    payload = {"input_text": q, "context": context, "output_format": "dict", "use_langraph": False}
    resp = client.post("/core/handle", json=payload)
    assert resp.status_code == 200
    result = resp.json()["result"]
    report_lines.append(f"**问题：** {q}\n")
    report_lines.append("**输出：**\n")
    report_lines.append(json.dumps(result, ensure_ascii=False, indent=2) + "\n")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = OUTPUT_DIR / f"core_budget_scene_report_short_{timestamp}.md"

with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

print(f"精简测试完成，报告已生成 {output_path}")
