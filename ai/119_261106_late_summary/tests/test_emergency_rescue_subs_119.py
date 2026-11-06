"""溺水、跳水、跳樓的專用題，以及和收尾不重複。"""

from __future__ import annotations

import unittest

from emergency_accident_119 import (
    BREATHING_QUESTION,
    CONSCIOUSNESS_QUESTION,
    PATIENT_QUESTION,
    RELATION_QUESTION,
)
from emergency_rescue_subs_119 import (
    DIVE_COUNT_QUESTION,
    DIVE_JUMPED,
    DIVE_NOT_YET,
    DIVE_QUESTIONS,
    DROWN_QUESTIONS,
    FALL_HIGH,
    FALL_QUESTIONS,
    SIGHT_GONE,
    SIGHT_IN_WATER,
    normalize_infant_age,
)
from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119


def _q(questions, element: str) -> str:
    return next(item.question for item in questions if item.element == element)


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

    def generate_summary(self, transcript_texts, filled_fields):
        return ""


def _engine(steps: list[tuple[str, dict]], sub: str) -> tuple[SopEngine119, ScriptedIO]:
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    engine.case.main_category = "緊急救援"
    engine.case.sub_category = sub
    return engine, io


class DrownTests(unittest.TestCase):
    def test_asks_in_sheet_order_and_not_the_passive_question(self) -> None:
        steps = [
            ("路人", {"drown_caller_role": "路人"}),
            ("玩水", {"drown_cause": "戲水"}),
            ("兩個", {"drown_count": "兩個"}),
            ("還看得到", {"drown_sight": SIGHT_IN_WATER}),
            ("十公尺", {"drown_distance": "十公尺"}),
            ("沒有", {"drown_flotation": "沒有"}),
            ("會動", {"drown_consciousness": "意識清醒"}),
            ("男生", {"drown_gender": "男性"}),
            ("一個月", {"drown_age": "一個月"}),
            ("紅衣服", {"drown_clothing": "紅衣服"}),
            ("他爸爸", {"caller_relation": "爸爸"}),
            ("有呼吸", {"breathing": True}),
        ]
        engine, io = _engine(steps, "溺水")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, DROWN_QUESTIONS)
        handler._ask_tail(engine)
        self.assertEqual(io.messages, [
            _q(DROWN_QUESTIONS, "報案身分"),
            _q(DROWN_QUESTIONS, "溺水原因"),
            _q(DROWN_QUESTIONS, "人數"),
            _q(DROWN_QUESTIONS, "目擊狀況"),
            _q(DROWN_QUESTIONS, "離岸距離"),
            _q(DROWN_QUESTIONS, "救生裝備"),
            _q(DROWN_QUESTIONS, "意識"),
            _q(DROWN_QUESTIONS, "性別"),
            _q(DROWN_QUESTIONS, "年齡"),
            _q(DROWN_QUESTIONS, "衣著特徵"),
            RELATION_QUESTION,
            BREATHING_QUESTION,
        ])
        self.assertNotIn("是跟團體一起來的嗎？有帶隊的人嗎？", io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.drown_caller_role, "路人")
        self.assertEqual(engine.case.drown_age, ".01")

    def test_infant_age_months(self) -> None:
        self.assertEqual(normalize_infant_age("一個月"), ".01")
        self.assertEqual(normalize_infant_age("十一個月"), ".11")
        self.assertEqual(normalize_infant_age("四十歲"), "四十歲")


class DiveTests(unittest.TestCase):
    def test_not_yet_jumped_skips_sight_count_and_consciousness(self) -> None:
        engine, io = _engine([
            ("還在欄杆外", {"dive_status": DIVE_NOT_YET}),
            ("路人", {"dive_caller_role": "路人"}),
            ("女生", {"dive_gender": "女性"}),
            ("二十歲", {"dive_age": "二十歲"}),
            ("白衣服", {"dive_clothing": "白衣服"}),
        ], "跳水")
        JinJiJiuYuanGenericHandler()._ask_sub(engine, DIVE_QUESTIONS)
        self.assertNotIn(_q(DIVE_QUESTIONS, "目擊狀況"), io.messages)
        self.assertNotIn(DIVE_COUNT_QUESTION, io.messages)
        self.assertNotIn(_q(DIVE_QUESTIONS, "意識"), io.messages)
        self.assertEqual(io.messages, [
            _q(DIVE_QUESTIONS, "跳水狀況"),
            _q(DIVE_QUESTIONS, "報案身分"),
            _q(DIVE_QUESTIONS, "性別"),
            _q(DIVE_QUESTIONS, "年齡"),
            _q(DIVE_QUESTIONS, "衣著特徵"),
        ])

    def test_in_water_asks_count_and_consciousness(self) -> None:
        engine, io = _engine([
            ("已經跳了", {"dive_status": DIVE_JUMPED}),
            ("還在水面載浮載沉", {"dive_sight": SIGHT_IN_WATER}),
            ("我是他朋友", {"dive_caller_role": "朋友"}),
            ("男生", {"dive_gender": "男性"}),
            ("三十歲", {"dive_age": "三十歲"}),
            ("黑衣服", {"dive_clothing": "黑衣服"}),
            ("一個人", {"dive_count": "一個人"}),
            ("會動", {"dive_consciousness": "意識清醒"}),
            ("朋友", {"caller_relation": "朋友"}),
            ("有呼吸", {"breathing": True}),
        ], "跳水")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, DIVE_QUESTIONS)
        handler._ask_tail(engine)
        self.assertEqual(io.messages, [
            _q(DIVE_QUESTIONS, "跳水狀況"),
            _q(DIVE_QUESTIONS, "目擊狀況"),
            _q(DIVE_QUESTIONS, "報案身分"),
            _q(DIVE_QUESTIONS, "性別"),
            _q(DIVE_QUESTIONS, "年齡"),
            _q(DIVE_QUESTIONS, "衣著特徵"),
            DIVE_COUNT_QUESTION,
            _q(DIVE_QUESTIONS, "意識"),
            RELATION_QUESTION,
            BREATHING_QUESTION,
        ])
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)

    def test_cannot_see_person_skips_count_and_consciousness(self) -> None:
        engine, io = _engine([
            ("跳下去了", {"dive_status": DIVE_JUMPED}),
            ("人不見了", {"dive_sight": SIGHT_GONE}),
        ], "跳水")
        engine.case.dive_caller_role = "路人"
        engine.case.dive_gender = "男性"
        engine.case.dive_age = "四十歲"
        engine.case.dive_clothing = "藍衣服"
        JinJiJiuYuanGenericHandler()._ask_sub(engine, DIVE_QUESTIONS)
        self.assertIn(_q(DIVE_QUESTIONS, "目擊狀況"), io.messages)
        self.assertNotIn(DIVE_COUNT_QUESTION, io.messages)
        self.assertNotIn(_q(DIVE_QUESTIONS, "意識"), io.messages)


class FallTests(unittest.TestCase):
    def test_still_high_asks_intent_and_tail_consciousness(self) -> None:
        engine, io = _engine([
            ("家人", {"fall_caller_role": "家人"}),
            ("還在頂樓", {"high_fall_status": FALL_HIGH}),
            ("說要跳", {"fall_intent": "說要跳"}),
            ("十二樓", {"fall_floor": "十二樓"}),
            ("男生", {"fall_gender": "男性"}),
            ("五十歲", {"fall_age": "五十歲"}),
            ("媽媽", {"caller_relation": "媽媽"}),
            ("有清醒", {}),
            ("有呼吸", {"breathing": True}),
        ], "跳樓")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, FALL_QUESTIONS)
        handler._ask_tail(engine)
        self.assertEqual(io.messages, [
            _q(FALL_QUESTIONS, "報案身分"),
            _q(FALL_QUESTIONS, "是否墜落"),
            _q(FALL_QUESTIONS, "輕生意圖"),
            _q(FALL_QUESTIONS, "所在樓層"),
            _q(FALL_QUESTIONS, "性別"),
            _q(FALL_QUESTIONS, "年齡"),
            RELATION_QUESTION,
            CONSCIOUSNESS_QUESTION,
            BREATHING_QUESTION,
        ])
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertIs(engine.case.consciousness, True)
        self.assertEqual(engine.case.fall_caller_role, "家人")

    def test_already_fallen_skips_intent(self) -> None:
        engine, io = _engine([
            ("已經掉下來了", {"high_fall_status": "已經掉下來"}),
        ], "跳樓")
        engine.case.fall_caller_role = "路人"
        engine.case.fall_floor = "一樓外面"
        engine.case.fall_gender = "女性"
        engine.case.fall_age = "二十歲"
        JinJiJiuYuanGenericHandler()._ask_sub(engine, FALL_QUESTIONS)
        self.assertEqual(io.messages, [_q(FALL_QUESTIONS, "是否墜落")])
        self.assertNotIn(_q(FALL_QUESTIONS, "輕生意圖"), io.messages)


class SubExtractionTests(unittest.TestCase):
    def test_bad_fixed_answers_dropped_and_only_for_emergency(self) -> None:
        calls = []

        def extract_slots(text, schema, rules, **_kwargs):
            calls.append(schema)
            if "drown_cause" in schema:
                return {
                    "drown_cause": "游泳",
                    "drown_gender": "男生",
                    "drown_age": "一個月",
                    "fall_caller_role": "路人",
                    "dive_status": "還在看",
                    "high_fall_status": "還在看",
                }
            return {}

        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = extract_slots
        result = ext.extract_general_fields("測試", "測試", main_category="緊急救援")
        self.assertNotIn("drown_cause", result)
        self.assertNotIn("dive_status", result)
        self.assertNotIn("high_fall_status", result)
        self.assertEqual(result["drown_gender"], "男性")
        self.assertEqual(result["drown_age"], ".01")
        self.assertEqual(result["fall_caller_role"], "路人")

        rescue = []

        def rescue_slots(text, schema, rules, **_kwargs):
            rescue.append(schema)
            return {}

        ext.extract_slots = rescue_slots
        ext.extract_general_fields("測試", "測試", main_category="救護")
        for schema in rescue:
            self.assertNotIn("drown_cause", schema)
            self.assertNotIn("high_fall_status", schema)
            self.assertNotIn("drown_cause", schema)


if __name__ == "__main__":
    unittest.main()
