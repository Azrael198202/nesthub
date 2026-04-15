import pytest
from nethub_runtime.core.main import CoreEngine

def test_budget_scene():
    core = CoreEngine()
    input_text = "吃饭花了3000日元，两个人，在博多一兰拉面。今天买了咖啡500日元，还有买了书1200日元"
    result = core.handle(input_text)
    # 1. 能否正确理解自然语言输入
    assert result['task']['intent'] == 'record_expense'
    # 2. 能否拆分多条消费记录
    assert len(result['workflow']['steps']) >= 2
    # 3. 能否提取完整字段（结构化输出）
    for record in result['result']:
        assert 'amount' in record
        assert 'content' in record
    # 4. 支持模糊时间解析（可扩展，暂略）
    # 5. 支持自然语言查询（可扩展，暂略）
    # 6. 支持多维度聚合统计（可扩展，暂略）
    print("Test passed. Result:", result)

if __name__ == "__main__":
    test_budget_scene()
