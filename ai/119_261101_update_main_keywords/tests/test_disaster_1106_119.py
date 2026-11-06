"""
災害照 1106 xlsx 的 7 個關鍵要素問（使用者 11/06 決定）。

- 人員受傷、人員受困同一句問；報案人位置、報案身分同一句問；只答到一半就用 xlsx 的單問句補問
- 人員受困、火煙狀況共用火警的欄位，報案人位置、報案身分共用救護的欄位
- 火煙狀況是有火有煙、有火無煙、無火有煙就改判火警；只有火花不改判

這裡的 LLM 是假的：每一句要抽出什麼，由測試事先指定。
"""

from __future__ import annotations

import unittest

from disaster_flow_119 import DISASTER_QUESTIONS
from handlers.災害通用 import ZaiHaiGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, MainCategorySwitched, SopEngine119

Q = {item.element: item.question for item in DISASTER_QUESTIONS}


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError(f"測試回答已用盡，最後一句是：{self.messages[-1]}")
        return self.answers.pop(0)


class FakeLLM:
    def __init__(self, extracted: dict[str, dict]):
        self.extracted = extracted

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        return dict(self.extracted.get((caller_text or "").strip(), {}))

    def extract_caller_info(self, question, text, include_address=False):
        return {}

    def generate_summary(self, transcript_texts, filled_fields):
        return "災害測試摘要"


def _engine(steps: list[tuple[str, dict]]) -> tuple[SopEngine119, ScriptedIO]:
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    engine.case.main_category = "災害"
    return engine, io


class DisasterQuestionTests(unittest.TestCase):
    def test_wire_subtype_asks_xlsx_questions_in_order(self) -> None:
        steps = [
            ("有人被壓住出不來，沒受傷", {"disaster_injury": "無人受傷", "trapped_status": "有人受困"}),
            ("兩個人", {"disaster_trapped_count": "兩個人"}),
            ("車子過不去", {"traffic_impact": "完全無法通行"}),
            ("沒有火也沒有煙", {"fire_or_smoke": "無火無煙"}),
            ("我在現場，我是路過的", {"caller_location": "在現場", "caller_relation": "路過"}),
        ]
        engine, io = _engine(steps)
        engine.case.sub_category = "電線掉落"
        ZaiHaiGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [
            "有沒有人受傷？還是有人被困住出不來嗎？",
            "有幾個人被困住？",
            "有擋到路嗎？車子還過得去嗎？",
            "現場有沒有冒火花或冒煙？",
            "請問您還在現場嗎？是路過民眾嗎？",
        ])
        self.assertEqual(engine.case.main_category, "災害")
        self.assertEqual(engine.case.disaster_injury, "無人受傷")
        self.assertEqual(engine.case.trapped_status, "有人受困")
        self.assertEqual(engine.case.fire_or_smoke, "無火無煙")
        self.assertEqual(engine.case.caller_location, "在現場")
        self.assertEqual(engine.case.caller_relation, "路過")

    def test_half_answer_asks_single_question(self) -> None:
        steps = [
            ("沒有人受傷", {"disaster_injury": "無人受傷"}),
            ("沒有人被困住", {"trapped_status": "無人受困"}),
            ("沒擋到路", {"traffic_impact": "未影響交通"}),
            ("我還在", {"caller_location": "在現場"}),
            ("我是里長", {"caller_relation": "里長"}),
        ]
        engine, io = _engine(steps)
        engine.case.sub_category = "路樹傾倒"
        ZaiHaiGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [
            "有沒有人受傷？還是有人被困住出不來嗎？",
            "有沒有人被困住出不來？",
            "有擋到路嗎？車子還過得去嗎？",
            "請問您還在現場嗎？是路過民眾嗎？",
            "是路過民眾嗎？",
        ])
        # 路樹傾倒不問火煙狀況，無人受困不問受困人數
        self.assertNotIn(Q["火煙狀況"], io.messages)
        self.assertNotIn(Q["受困人數"], io.messages)


class DisasterSwitchToFireTests(unittest.TestCase):
    def test_fire_or_smoke_switches_to_fire(self) -> None:
        for state in ("有火有煙", "有火無煙", "無火有煙"):
            with self.subTest(state=state):
                steps = [
                    ("沒有人受傷也沒人被困", {"disaster_injury": "無人受傷", "trapped_status": "無人受困"}),
                    ("擋到一半", {"traffic_impact": "佔用部分車道"}),
                    ("在冒煙", {"fire_or_smoke": state}),
                ]
                engine, io = _engine(steps)
                engine.case.sub_category = "電線掉落"
                with self.assertRaises(MainCategorySwitched):
                    ZaiHaiGenericHandler().run_generic_flow(engine)
                self.assertEqual(engine.case.main_category, "火警")
                # 火警也用到的欄位留著，災害自己的清掉
                self.assertEqual(engine.case.fire_or_smoke, state)
                self.assertEqual(engine.case.trapped_status, "無人受困")
                self.assertIsNone(engine.case.traffic_impact)
                self.assertIsNone(engine.case.disaster_injury)
                # 改判時不對報案人講話，也不再問報案人位置
                self.assertEqual(io.messages[-1], Q["火煙狀況"])

    def test_spark_only_does_not_switch(self) -> None:
        steps = [
            ("沒有人受傷也沒人被困", {"disaster_injury": "無人受傷", "trapped_status": "無人受困"}),
            ("沒擋到", {"traffic_impact": "未影響交通"}),
            ("只有在閃火花", {"fire_or_smoke": "只有火花"}),
            ("我在現場，我是鄰居", {"caller_location": "在現場", "caller_relation": "鄰居"}),
        ]
        engine, _io = _engine(steps)
        engine.case.sub_category = "電線掉落"
        ZaiHaiGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.main_category, "災害")
        self.assertEqual(engine.case.fire_or_smoke, "只有火花")

    def test_fire_mentioned_before_questions_switches_at_once(self) -> None:
        engine, io = _engine([])
        engine.case.sub_category = "路樹傾倒"
        engine.case.fire_or_smoke = "有火有煙"
        with self.assertRaises(MainCategorySwitched):
            ZaiHaiGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.main_category, "火警")
        self.assertEqual(io.messages, [])


class DisasterSharedFieldTests(unittest.TestCase):
    def test_shared_fields_saved_in_disaster(self) -> None:
        engine, _io = _engine([])
        engine._apply_extracted_fields({
            "trapped_status": "有人受困",
            "fire_or_smoke": "只有火花",
            "caller_location": "不敢靠近",
            "caller_relation": "工人",
        })
        self.assertEqual(engine.case.trapped_status, "有人受困")
        self.assertEqual(engine.case.fire_or_smoke, "只有火花")
        self.assertEqual(engine.case.caller_location, "不敢靠近")
        self.assertEqual(engine.case.caller_relation, "工人")

    def test_shared_fields_still_blocked_in_other_categories(self) -> None:
        engine, _io = _engine([])
        engine.case.main_category = "緊急救援"
        engine._apply_extracted_fields({"fire_or_smoke": "有火有煙", "caller_location": "在現場"})
        self.assertIsNone(engine.case.fire_or_smoke)
        self.assertIsNone(engine.case.caller_location)

    def test_switch_to_rescue_keeps_rescue_fields_only(self) -> None:
        engine, _io = _engine([])
        engine.case.fire_or_smoke = "無火無煙"
        engine.case.trapped_status = "無人受困"
        engine.case.caller_location = "在現場"
        engine.case.caller_relation = "家人"
        engine.case.disaster_injury = "有人受傷"
        engine._migrate_case_for_main_switch("災害", "救護")
        self.assertIsNone(engine.case.fire_or_smoke)
        self.assertIsNone(engine.case.trapped_status)
        self.assertIsNone(engine.case.disaster_injury)
        self.assertEqual(engine.case.caller_location, "在現場")
        self.assertEqual(engine.case.caller_relation, "家人")


class DisasterExtractionTests(unittest.TestCase):
    def test_disaster_schema_has_xlsx_fields(self) -> None:
        calls = []

        def extract_slots(text, schema, rules, **_kwargs):
            calls.append((schema, rules))
            if "disaster_injury" in schema:
                return {
                    "disaster_injury": "有人受傷",
                    "trapped_status": "被壓到",
                    "fire_or_smoke": "有火有煙",
                    "caller_relation": "住在附近",
                }
            return {}

        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = extract_slots
        result = ext.extract_general_fields("測試", "測試", main_category="災害")
        schema, rules = next(call for call in calls if "disaster_injury" in call[0])
        self.assertEqual(set(schema), {
            "disaster_injury", "trapped_status", "disaster_trapped_count", "traffic_impact",
            "fire_or_smoke", "caller_location", "caller_relation",
        })
        self.assertIn("fire_or_smoke 火煙狀況", rules)
        self.assertEqual(result["disaster_injury"], "有人受傷")
        # 人員受困只能填固定說法；報案身分參考範圍不是選擇題，照報案人的話記
        self.assertNotIn("trapped_status", result)
        self.assertEqual(result["fire_or_smoke"], "有火有煙")
        self.assertEqual(result["caller_relation"], "住在附近")


if __name__ == "__main__":
    unittest.main()
