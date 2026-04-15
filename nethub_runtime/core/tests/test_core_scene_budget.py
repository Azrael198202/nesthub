from __future__ import annotations

import unittest

from nethub_runtime.core.services.core_engine import AICore


class TestCoreSceneBudget(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.core = AICore()
        self.context = {"session_id": "scene_budget_test", "timezone": "Asia/Tokyo", "locale": "ja-JP"}

    async def test_record_split_and_persist(self) -> None:
        result = await self.core.handle("今天买了咖啡500日元，还有买了书1200日元", self.context)
        payload = result["execution_result"]["final_output"]
        self.assertEqual(payload["extract_records"]["count"], 2)
        self.assertEqual(payload["persist_records"]["saved"], 2)

    async def test_record_fields_and_category(self) -> None:
        result = await self.core.handle("吃饭花了3000日元，两个人，在博多一兰拉面", self.context)
        records = result["execution_result"]["final_output"]["extract_records"]["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount"], 3000)
        self.assertEqual(records[0]["participants"], 2)
        self.assertEqual(records[0]["label"], "food_and_drink")

    async def test_nl_query_aggregation(self) -> None:
        await self.core.handle("今天买了咖啡500日元，还有买了书1200日元", self.context)
        result = await self.core.handle("咖啡一共花了多少？", self.context)
        aggregation = result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]
        self.assertEqual(aggregation["total_amount"], 500)
        self.assertEqual(aggregation["count"], 1)

    async def test_location_aggregation(self) -> None:
        await self.core.handle("上周末和家人去博多超市买东西一共花了8000日元", self.context)
        result = await self.core.handle("博多地区消费总额是多少？", self.context)
        aggregation = result["execution_result"]["final_output"]["aggregate_query"]["aggregation"]
        self.assertEqual(aggregation["total_amount"], 8000)

    async def test_multimodal_ocr_routing(self) -> None:
        result = await self.core.handle("请对这张票据做OCR识别", {"session_id": "scene_budget_test", "metadata": {"input_type": "image"}})
        self.assertEqual(result["task"]["intent"], "ocr_task")
        step = result["execution_result"]["steps"][0]
        self.assertEqual(step["name"], "ocr_extract")
        self.assertEqual(step["capability"]["model_choice"]["model"], "paddleocr")


if __name__ == "__main__":
    unittest.main()
