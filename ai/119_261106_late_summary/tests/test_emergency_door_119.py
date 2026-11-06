"""電梯受困、破門的專用題。"""

from __future__ import annotations

import unittest

from emergency_accident_119 import (
    BREATHING_QUESTION,
    CONSCIOUSNESS_QUESTION,
    PATIENT_QUESTION,
    RELATION_QUESTION,
)
from emergency_rescue_subs_119 import DOOR_QUESTIONS, LIFT_QUESTIONS
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


def _engine(steps, sub: str):
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    engine.case.main_category = "緊急救援"
    engine.case.sub_category = sub
    return engine, io


class LiftTests(unittest.TestCase):
    def test_order_skips_passive_and_repeats_gender_not_consciousness(self) -> None:
        steps = [
            ("我本人", {"lift_caller_role": "我本人"}),
            ("大安社區 A 棟 2 號梯", {"lift_building": "大安社區 A 棟 2 號梯"}),
            ("停在三樓", {"lift_floor": "停在三樓"}),
            ("兩個人", {"lift_count": "兩個人"}),
            ("還沒打", {"lift_company": "還沒聯絡"}),
            ("都清醒", {"lift_consciousness": "意識清醒"}),
            ("他太太", {"caller_relation": "太太"}),
            ("男生四十歲", {"patient_gender": "男", "patient_age": "四十歲"}),
            ("有呼吸", {"breathing": True}),
        ]
        engine, io = _engine(steps, "電梯受困")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, LIFT_QUESTIONS)
        handler._ask_tail(engine)
        self.assertEqual(io.messages, [
            _q(LIFT_QUESTIONS, "報案身分"),
            _q(LIFT_QUESTIONS, "社區棟別"),
            _q(LIFT_QUESTIONS, "受困樓層"),
            _q(LIFT_QUESTIONS, "受困人數"),
            _q(LIFT_QUESTIONS, "電梯公司"),
            _q(LIFT_QUESTIONS, "意識"),
            RELATION_QUESTION,
            PATIENT_QUESTION,
            BREATHING_QUESTION,
        ])
        self.assertNotIn("裡面的人有沒有受傷或不舒服？", io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.lift_caller_role, "受困者本人")


class DoorTests(unittest.TestCase):
    def test_self_skips_response_gender_and_age(self) -> None:
        steps = [
            ("我本人", {"door_caller_role": "我本人"}),
            ("跌倒起不來", {"door_reason": "跌倒起不來"}),
            ("大門", {"door_kind": "大門"}),
            ("沒有鑰匙", {"door_locksmith": "沒有鑰匙"}),
            ("同意", {"door_consent": "同意"}),
            ("兒子", {"caller_relation": "兒子"}),
            ("有清醒", {}),
            ("有呼吸", {"breathing": True}),
        ]
        engine, io = _engine(steps, "破門")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, DOOR_QUESTIONS)
        handler._ask_tail(engine)
        self.assertNotIn(_q(DOOR_QUESTIONS, "有無回應"), io.messages)
        self.assertNotIn(_q(DOOR_QUESTIONS, "性別"), io.messages)
        self.assertNotIn(_q(DOOR_QUESTIONS, "年齡"), io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.door_caller_role, "本人")
        self.assertEqual(engine.case.door_reason, "跌倒起不來")
        self.assertIs(engine.case.consciousness, True)

    def test_family_asks_response_gender_and_age(self) -> None:
        steps = [
            ("我是家人", {"door_caller_role": "我是家人"}),
            ("屋裡沒人開門", {"door_reason": "屋裡沒人開門"}),
            ("沒有回應", {"door_response": "沒有回應"}),
            ("房門", {"door_kind": "房門"}),
            ("已經找鎖匠", {"door_locksmith": "已找鎖匠"}),
            ("人還沒到", {"door_consent": "家屬或屋主還沒到"}),
            ("女生", {"door_gender": "女生"}),
            ("八十歲", {"door_age": "八十歲"}),
            ("女兒", {"caller_relation": "女兒"}),
            ("有清醒", {}),
            ("有呼吸", {"breathing": True}),
        ]
        engine, io = _engine(steps, "破門")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, DOOR_QUESTIONS)
        handler._ask_tail(engine)
        self.assertEqual([
            _q(DOOR_QUESTIONS, "報案身分"),
            _q(DOOR_QUESTIONS, "擔心原因"),
            _q(DOOR_QUESTIONS, "有無回應"),
            _q(DOOR_QUESTIONS, "門的種類"),
            _q(DOOR_QUESTIONS, "鑰匙鎖匠"),
            _q(DOOR_QUESTIONS, "同意破門"),
            _q(DOOR_QUESTIONS, "性別"),
            _q(DOOR_QUESTIONS, "年齡"),
            RELATION_QUESTION,
            CONSCIOUSNESS_QUESTION,
            BREATHING_QUESTION,
        ], io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertEqual(engine.case.door_caller_role, "家人")
        self.assertEqual(engine.case.door_reason, "屋裡沒人開門")
        self.assertEqual(engine.case.door_gender, "女性")


class DoorExtractTests(unittest.TestCase):
    def test_bad_fixed_answers_dropped(self) -> None:
        def extract_slots(text, schema, rules, **_kwargs):
            if "lift_company" in schema:
                return {
                    "lift_company": "等一下再打",
                    "lift_discomfort": "受傷了",
                    "door_kind": "窗戶",
                    "door_consent": "同意",
                    "lift_caller_role": "警衛",
                }
            return {}

        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = extract_slots
        result = ext.extract_general_fields("測試", "測試", main_category="緊急救援")
        self.assertNotIn("lift_company", result)
        self.assertNotIn("door_kind", result)
        self.assertEqual(result["lift_discomfort"], "有")
        self.assertEqual(result["door_consent"], "同意")
        self.assertEqual(result["lift_caller_role"], "管理員或警衛")


if __name__ == "__main__":
    unittest.main()
