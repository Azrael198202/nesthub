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
OUTPUT_DIR = ROOT_DIR / "test/reports"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_case(input_text: str, context: dict[str, str]) -> dict:
    payload = {
        "input_text": input_text,
        "context": context,
        "output_format": "dict",
        "use_langraph": False,
    }
    response = client.post("/core/handle", json=payload)
    assert response.status_code == 200
    return response.json()["result"]

# 1. 消费记录录入
input_text = "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元。上周末和家人去超市买东西一共花了8000日元。"
context = {"session_id": "budget_scene_e2e"}
report_lines = []

report_lines.append("# 自动化测试报告\n")
report_lines.append("## 测试说明\n")
report_lines.append("- 本报告强制使用 `use_langraph=false`，验证当前预算场景是否走到新的 `execution_coordinator` 逻辑。\n")
report_lines.append("- 验证点包括: 记录抽取、标签分类、泛查询防误判、地点查询、actor 查询，以及是否存在与旧工作流逻辑冲突。\n")
report_lines.append("## 消费记录录入\n")
report_lines.append(f"**输入：** {input_text}\n")

record_data = run_case(input_text, context)
assert record_data["task"]["intent"] == "data_record"
extract_records_output = record_data["execution_result"]["final_output"]["extract_records"]
assert extract_records_output["count"] == 4
record_labels = [item["label"] for item in extract_records_output["records"]]
assert record_labels.count("food_and_drink") >= 2
assert "shopping" in record_labels

report_lines.append("**输出：**\n")
report_lines.append(json.dumps(record_data, ensure_ascii=False, indent=2) + "\n")
report_lines.append("**预期结果：**\n")
report_lines.append("- 任务意图应识别为 `data_record`。\n")
report_lines.append("- 应抽取 4 条消费记录。\n")
report_lines.append("- 标签中应至少包含 2 条 `food_and_drink`，并包含 `shopping`。\n")
report_lines.append("**实际结果：**\n")
report_lines.append(f"- 任务意图: {record_data['task']['intent']}\n")
report_lines.append(f"- 抽取记录数: {extract_records_output['count']}\n")
report_lines.append(f"- 标签分布: {record_labels}\n")
report_lines.append("**判定：通过**\n")

# 2. 查询问答
questions = [
    "4月份一共花了多少钱？",
    "这个月餐饮花了多少？",
    "我个人花了多少？",
    "家人花了多少？",
    "咖啡一共花了多少？",
    "博多地区消费总额是多少？"
]

expectations = {
    "4月份一共花了多少钱？": {
        "assertions": lambda result: (
            result["task"]["intent"] == "data_query"
            and result["execution_result"]["final_output"]["parse_query"]["query"]["filters"] == {}
            and "label" not in result["execution_result"]["final_output"]["parse_query"]["query"]["filters"]
        ),
        "expected": [
            "任务意图为 `data_query`",
            "不应生成 `label` 过滤条件",
            "应保持为泛查询，不误判为餐饮类",
        ],
    },
    "这个月餐饮花了多少？": {
        "assertions": lambda result: (
            result["execution_result"]["final_output"]["parse_query"]["query"]["filters"].get("label") == "food_and_drink"
            and result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]["total_amount"] == 3500
        ),
        "expected": [
            "应识别 `food_and_drink` 标签过滤",
            "聚合金额应为 3500",
        ],
    },
    "我个人花了多少？": {
        "assertions": lambda result: (
            result["execution_result"]["final_output"]["parse_query"]["query"]["filters"].get("actor") == "self"
            and result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]["total_amount"] == 4700
        ),
        "expected": [
            "应识别 actor=self",
            "聚合金额应为 4700",
        ],
    },
    "家人花了多少？": {
        "assertions": lambda result: (
            result["execution_result"]["final_output"]["parse_query"]["query"]["filters"].get("actor") == "家人"
            and result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]["total_amount"] == 8000
        ),
        "expected": [
            "应识别 actor=家人",
            "聚合金额应为 8000",
        ],
    },
    "咖啡一共花了多少？": {
        "assertions": lambda result: (
            "咖啡" in result["execution_result"]["final_output"]["parse_query"]["query"]["terms"]
            and result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]["total_amount"] == 500
        ),
        "expected": [
            "应识别 terms 中包含 `咖啡`",
            "聚合金额应为 500",
        ],
    },
    "博多地区消费总额是多少？": {
        "assertions": lambda result: (
            result["execution_result"]["final_output"]["parse_query"]["query"]["filters"].get("location_keyword") == "博多"
            and result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]["total_amount"] == 3000
        ),
        "expected": [
            "应识别 location_keyword=博多",
            "聚合金额应为 3000",
        ],
    },
}

report_lines.append("## 查询问答\n")
for q in questions:
    result = run_case(q, context)
    assert expectations[q]["assertions"](result)
    report_lines.append(f"**问题：** {q}\n")
    report_lines.append("**预期结果：**\n")
    for item in expectations[q]["expected"]:
        report_lines.append(f"- {item}\n")
    report_lines.append("**输出：**\n")
    report_lines.append(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    parsed_query = result["execution_result"]["final_output"]["parse_query"]["query"]
    aggregation = result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]
    report_lines.append("**实际结果摘要：**\n")
    report_lines.append(f"- query.filters = {json.dumps(parsed_query.get('filters', {}), ensure_ascii=False)}\n")
    report_lines.append(f"- query.terms = {json.dumps(parsed_query.get('terms', []), ensure_ascii=False)}\n")
    report_lines.append(f"- aggregation.total_amount = {aggregation.get('total_amount')}\n")
    report_lines.append(f"- aggregation.grouped = {json.dumps(aggregation.get('grouped', {}), ensure_ascii=False)}\n")
    report_lines.append("**判定：通过**\n")

report_lines.append("## 冲突验证\n")
report_lines.append("**检查目标：** 新逻辑是否与旧默认工作流路径冲突。\n")
report_lines.append("**检查方法：** 本脚本强制传入 `use_langraph=false`，要求所有预算场景请求进入 `data_record/data_query -> execution_coordinator` 路径。\n")
report_lines.append("**验证结果：**\n")
report_lines.append(f"- 首次录入任务 intent = {record_data['task']['intent']}，已进入数据处理链路，而非 `general_task`。\n")
report_lines.append("- 查询路径返回 `parse_query` 与 `aggregate_query` 的 `final_output`，说明已进入新的解析与聚合逻辑。\n")
report_lines.append("- 泛查询、标签查询、actor 查询、location 查询均返回正确结果，说明新逻辑在原脚本场景中已生效且无功能冲突。\n")
report_lines.append("**判定：通过**\n")

report_lines.append("## 结论\n")
report_lines.append("- 经过修正后，`gen_core_budget_scene_report.py` 已真正采用新的预算处理逻辑。\n")
report_lines.append("- 新逻辑在原先测试问题场景上已生效，并得到正确结果。\n")
report_lines.append("- 在当前报告覆盖的录入、泛查询、标签、actor、location 场景下，未发现与原处理链路的冲突。\n")

# 3. 保存报告
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = OUTPUT_DIR / f"core_budget_scene_report_{timestamp}.md"

with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))

print(f"测试完成，报告已生成 {output_path}")
