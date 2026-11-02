"""山難、卡住夾住、瓦斯漏氣的專用題。"""

from __future__ import annotations

import unittest

from emergency_accident_119 import (
    BREATHING_QUESTION,
    CONSCIOUSNESS_QUESTION,
    PATIENT_QUESTION,
    RELATION_QUESTION,
)
from emergency_rescue_subs_119 import (
    GAS_QUESTIONS,
    MOUNTAIN_QUESTIONS,
    TRAP_QUESTIONS,
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


def _engine(steps, sub: str):
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    engine.case.main_category = "緊急救援"
    engine.case.sub_category = sub
    return engine, io


class MountainTests(unittest.TestCase):
    def test_lost_skips_injury_and_does_not_repeat_tail(self) -> None:
        steps = [
            ("迷路了", {"mountain_cause": "迷路了"}),
            ("三個人", {"mountain_count": "三個人"}),
            ("不知道座標", {"mountain_location": "不知道座標"}),
            ("我本人", {"mountain_caller_role": "我本人"}),
            ("男生", {"mountain_gender": "男生"}),
            ("一個月", {"mountain_age": "一個月"}),
            ("清醒", {"mountain_consciousness": "意識清醒"}),
            ("早上八點從入口上", {"mountain_entry": "早上八點從入口上"}),
            ("走主線，經過涼亭", {"mountain_route": "走主線，經過涼亭"}),
            ("水還夠", {"mountain_supplies": "水還夠"}),
            ("他朋友", {"caller_relation": "朋友"}),
            ("有呼吸", {"breathing": True}),
        ]
        engine, io = _engine(steps, "山難")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, MOUNTAIN_QUESTIONS)
        handler._ask_tail(engine)
        self.assertNotIn(_q(MOUNTAIN_QUESTIONS, "受傷情形"), io.messages)
        self.assertNotIn("是自己來，還是跟團體一起？", io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertIn(RELATION_QUESTION, io.messages)
        self.assertIn(BREATHING_QUESTION, io.messages)
        self.assertEqual(engine.case.mountain_cause, "迷路")
        self.assertEqual(engine.case.mountain_caller_role, "本人")
        self.assertEqual(engine.case.mountain_age, ".01")
        self.assertEqual(engine.case.mountain_gender, "男性")

    def test_injured_asks_where(self) -> None:
        engine, io = _engine([
            ("腳扭到", {"mountain_cause": "腳扭到"}),
            ("腳痛沒有傷口", {"mountain_injury": "四肢疼痛，無明顯外傷"}),
        ], "山難")
        for field, value in {
            "mountain_count": "兩個",
            "mountain_location": "山上",
            "mountain_caller_role": "本人",
            "mountain_gender": "男性",
            "mountain_age": "三十歲",
            "mountain_consciousness": "意識清醒",
            "mountain_entry": "早上",
            "mountain_route": "步道",
            "mountain_supplies": "有水",
        }.items():
            setattr(engine.case, field, value)
        JinJiJiuYuanGenericHandler()._ask_sub(engine, MOUNTAIN_QUESTIONS)
        self.assertEqual(io.messages, [
            _q(MOUNTAIN_QUESTIONS, "山難原因"),
            _q(MOUNTAIN_QUESTIONS, "受傷情形"),
        ])
        self.assertEqual(engine.case.mountain_cause, "受傷")


class TrapTests(unittest.TestCase):
    def test_self_skips_consciousness(self) -> None:
        engine, io = _engine([
            ("我本人", {"trap_caller_role": "我本人"}),
            ("媽媽", {"caller_relation": "媽媽"}),
            ("有呼吸", {"breathing": True}),
        ], "其他")
        for field, value in {
            "trap_body_part": "手指",
            "trap_object": "戒指",
            "trap_freed": "還卡著",
            "trap_injury": "沒有",
            "trap_place": "住家",
            "trap_gender": "女性",
            "trap_age": "三十歲",
        }.items():
            setattr(engine.case, field, value)
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, TRAP_QUESTIONS)
        handler._ask_tail(engine)
        self.assertEqual(io.messages, [
            _q(TRAP_QUESTIONS, "報案身分"),
            RELATION_QUESTION,
            BREATHING_QUESTION,
        ])
        self.assertNotIn(_q(TRAP_QUESTIONS, "意識"), io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.trap_caller_role, "當事人(本人)")

    def test_alias_and_family_asks_consciousness(self) -> None:
        engine, io = _engine([
            ("家人", {"trap_caller_role": "家人"}),
            ("清醒", {"trap_consciousness": "意識清醒"}),
            ("媽媽", {"caller_relation": "媽媽"}),
            ("有呼吸", {"breathing": True}),
        ], "其他(卡住夾住)")
        for field, value in {
            "trap_body_part": "手",
            "trap_object": "機器",
            "trap_freed": "還卡著",
            "trap_injury": "有",
            "trap_place": "工廠",
            "trap_gender": "男性",
            "trap_age": "四十歲",
        }.items():
            setattr(engine.case, field, value)
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, TRAP_QUESTIONS)
        handler._ask_tail(engine)
        self.assertEqual(io.messages, [
            _q(TRAP_QUESTIONS, "報案身分"),
            _q(TRAP_QUESTIONS, "意識"),
            RELATION_QUESTION,
            BREATHING_QUESTION,
        ])


class GasTests(unittest.TestCase):
    def test_active_questions_and_tail_still_asks_person(self) -> None:
        steps = [
            ("透天厝", {"gas_building_use": "透天厝"}),
            ("我是住戶", {"gas_caller_role": "我是住戶"}),
            ("沒有火", {"gas_flame": "沒有"}),
            ("廚房", {"gas_smell_place": "廚房"}),
            ("很濃", {"gas_smell_strength": "很濃"}),
            ("天然氣", {"gas_type": "天然氣"}),
            ("丈夫", {"caller_relation": "丈夫"}),
            ("女生三十歲", {"patient_gender": "女", "patient_age": "三十歲"}),
            ("有清醒", {}),
            ("有呼吸", {"breathing": True}),
        ]
        engine, io = _engine(steps, "瓦斯漏氣(建築物)")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_sub(engine, GAS_QUESTIONS)
        handler._ask_tail(engine)
        self.assertNotIn("旁邊有房子或車子嗎？", io.messages)
        self.assertNotIn("有人身體不舒服嗎？", io.messages)
        self.assertEqual(io.messages[:6], [
            _q(GAS_QUESTIONS, "建物用途"),
            _q(GAS_QUESTIONS, "報案身分"),
            _q(GAS_QUESTIONS, "有無火煙"),
            _q(GAS_QUESTIONS, "聞到位置"),
            _q(GAS_QUESTIONS, "味道濃淡"),
            _q(GAS_QUESTIONS, "瓦斯種類"),
        ])
        self.assertIn(PATIENT_QUESTION, io.messages)
        self.assertIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.gas_caller_role, "住戶")
        self.assertIs(engine.case.consciousness, True)


class SceneExtractionTests(unittest.TestCase):
    def test_bad_fixed_answers_dropped(self) -> None:
        def extract_slots(text, schema, rules, **_kwargs):
            if "mountain_injury" in schema:
                return {
                    "mountain_injury": "擦傷",
                    "gas_building_use": "腳踏車",
                    "gas_discomfort": "頭暈",
                    "trap_freed": "還卡著",
                    "mountain_cause": "腳扭到",
                }
            return {}

        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = extract_slots
        result = ext.extract_general_fields("測試", "測試", main_category="緊急救援")
        self.assertNotIn("mountain_injury", result)
        self.assertNotIn("gas_building_use", result)
        self.assertNotIn("gas_discomfort", result)
        self.assertEqual(result["trap_freed"], "還卡著")
        self.assertEqual(result["mountain_cause"], "受傷")


if __name__ == "__main__":
    unittest.main()
