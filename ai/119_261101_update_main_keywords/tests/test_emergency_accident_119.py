"""
緊急救援次案類「車禍救助」。

八題裡，人數看受傷或受困；當事人意識在已經知道是本人時不問。
問完八題收關係、性別年齡、呼吸，不再問一次意識。
"""

from __future__ import annotations

import types
import unittest

from emergency_accident_119 import (
    ACCIDENT_FIELDS,
    ACCIDENT_QUESTIONS,
    BREATHING_QUESTION,
    CONSCIOUSNESS_QUESTION,
    COUNT_QUESTION,
    DISPATCH_LINE,
    INJURY_NONE,
    PATIENT_QUESTION,
    RELATION_QUESTION,
    ROLE_PASSERBY,
    ROLE_SELF,
    TRAPPED_NONE,
    TRAPPED_YES,
)
from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119

Q = {item.element: item.question for item in ACCIDENT_QUESTIONS}
HEAD_INJURY = "頭部外傷流血(含頸部)"


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
        self.categories: list[str | None] = []

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        self.categories.append(main_category)
        return dict(self.extracted.get((caller_text or "").strip(), {}))

    def generate_summary(self, transcript_texts, filled_fields):
        return "車禍救助測試摘要"


class SubBERT:
    def __init__(self, label: str, conf: float = 0.9, second: float = 0.05):
        self.label = label
        self.conf = conf
        self.second = second

    def predict(self, text, main_cat):
        return types.SimpleNamespace(
            final_label=self.label,
            classifier_conf=self.conf,
            all_probs={self.label: self.conf, "其他": self.second},
        )


def _engine(steps: list[tuple[str, dict]], *, sub: str = "車禍救助", bert=None):
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm, sub_classifiers=bert)  # type: ignore[arg-type]
    engine.case.main_category = "緊急救援"
    engine.case.sub_category = sub
    engine.case.address_confirmed = True
    engine.case.incident_description = "兩台車撞在一起"
    return engine, io


def _asked(io: ScriptedIO) -> list[str]:
    known = set(Q.values()) | {
        RELATION_QUESTION, PATIENT_QUESTION, BREATHING_QUESTION, CONSCIOUSNESS_QUESTION,
        DISPATCH_LINE,
    }
    return [message for message in io.messages if message in known]


FULL_STEPS = [
    ("機車撞上汽車", {"accident_vehicle_type": "機車車禍"}),
    ("頭有流血", {"accident_injury": HEAD_INJURY}),
    ("有一個人卡在車裡", {"accident_trapped": TRAPPED_YES}),
    ("兩個受傷，一個受困", {"accident_casualty_count": "兩個受傷，一個受困"}),
    ("叫不醒", {"accident_consciousness": "昏迷"}),
    ("車頭冒黑煙", {"accident_burning": "車頭冒黑煙"}),
    ("我是路人", {"accident_caller_role": "我是路人"}),
    ("擋到一個車道，還過得去", {"accident_traffic_impact": "擋到一個車道，還過得去"}),
    ("他兒子", {"caller_relation": "兒子"}),
    ("男生，四十歲", {"patient_gender": "男", "patient_age": "四十歲"}),
    ("有在呼吸", {"breathing": True}),
]


class AccidentQuestionTests(unittest.TestCase):
    def test_full_order_skips_generic_consciousness(self) -> None:
        engine, io = _engine(FULL_STEPS)
        JinJiJiuYuanGenericHandler()._ask_accident(engine)
        JinJiJiuYuanGenericHandler()._ask_tail(engine)
        self.assertEqual(_asked(io), [
            Q["事故車種"], Q["受傷情形"], Q["有無受困"], Q["人數"],
            Q["當事人意識"], Q["燃燒情形"], Q["報案身分"], Q["影響範圍"],
            RELATION_QUESTION, PATIENT_QUESTION, BREATHING_QUESTION,
        ])
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.accident_vehicle_type, "機車車禍")
        self.assertEqual(engine.case.accident_casualty_count, "兩個受傷，一個受困")
        self.assertEqual(engine.case.accident_caller_role, ROLE_PASSERBY)
        self.assertEqual(engine.case.caller_relation, "兒子")
        self.assertEqual(engine.case.patient_gender, "男")
        self.assertEqual(engine.case.patient_age, "四十歲")
        self.assertIs(engine.case.breathing, True)

    def _fill_rest(self, engine: SopEngine119, **overrides) -> None:
        engine.case.accident_vehicle_type = "機車車禍"
        engine.case.accident_burning = "沒有冒煙"
        engine.case.accident_traffic_impact = "沒擋到"
        for key, value in overrides.items():
            setattr(engine.case, key, value)

    def test_no_injury_and_nobody_trapped_skips_count(self) -> None:
        engine, io = _engine([
            ("叫不醒", {"accident_consciousness": "昏迷"}),
            ("路人", {"accident_caller_role": "路人"}),
        ])
        self._fill_rest(engine, accident_injury=INJURY_NONE, accident_trapped=TRAPPED_NONE)
        JinJiJiuYuanGenericHandler()._ask_accident(engine)
        self.assertNotIn(COUNT_QUESTION, io.messages)
        self.assertIn(Q["當事人意識"], io.messages)

    def test_injury_without_trap_still_asks_count(self) -> None:
        engine, io = _engine([
            ("一個", {"accident_casualty_count": "一個"}),
        ])
        self._fill_rest(
            engine,
            accident_injury=HEAD_INJURY,
            accident_trapped=TRAPPED_NONE,
            accident_caller_role=ROLE_SELF,
        )
        JinJiJiuYuanGenericHandler()._ask_accident(engine)
        self.assertEqual(io.messages, [COUNT_QUESTION])
        self.assertNotIn(Q["當事人意識"], io.messages)

    def test_trapped_without_injury_asks_count(self) -> None:
        engine, io = _engine([
            ("一個人受困", {"accident_casualty_count": "一個人受困"}),
        ])
        self._fill_rest(
            engine,
            accident_injury=INJURY_NONE,
            accident_trapped=TRAPPED_YES,
            accident_caller_role=ROLE_SELF,
        )
        JinJiJiuYuanGenericHandler()._ask_accident(engine)
        self.assertEqual(io.messages, [COUNT_QUESTION])

    def test_passerby_asks_consciousness(self) -> None:
        engine, io = _engine([
            ("有反應", {"accident_consciousness": "對聲音有反應"}),
        ])
        self._fill_rest(engine, accident_caller_role=ROLE_PASSERBY, accident_injury=INJURY_NONE, accident_trapped=TRAPPED_NONE)
        JinJiJiuYuanGenericHandler()._ask_accident(engine)
        self.assertEqual(io.messages, [Q["當事人意識"]])
        self.assertEqual(engine.case.accident_consciousness, "對聲音有反應")

    def test_filled_vehicle_is_skipped(self) -> None:
        engine, io = _engine([])
        self._fill_rest(
            engine,
            accident_vehicle_type="自小客車車禍",
            accident_injury=INJURY_NONE,
            accident_trapped=TRAPPED_NONE,
            accident_caller_role=ROLE_SELF,
        )
        JinJiJiuYuanGenericHandler()._ask_accident(engine)
        self.assertEqual(io.messages, [])
        self.assertEqual(engine.case.accident_vehicle_type, "自小客車車禍")

    def test_other_subtype_asks_consciousness_and_skips_eight(self) -> None:
        engine, io = _engine([
            ("朋友", {"caller_relation": "朋友"}),
            ("女生，三十歲", {"patient_gender": "女", "patient_age": "三十歲"}),
            ("有清醒", {}),
            ("有呼吸", {"breathing": True}),
        ], sub="氣爆")
        handler = JinJiJiuYuanGenericHandler()
        handler._ask_tail(engine)
        self.assertEqual(_asked(io), [
            RELATION_QUESTION, PATIENT_QUESTION, CONSCIOUSNESS_QUESTION, BREATHING_QUESTION,
        ])
        self.assertIs(engine.case.consciousness, True)

    def test_flow_dispatches_before_questions_when_sub_is_confident(self) -> None:
        engine, io = _engine(FULL_STEPS, bert=SubBERT("車禍救助"))
        engine.case.sub_category = None
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        asked = _asked(io)
        self.assertEqual(asked[0], DISPATCH_LINE)
        self.assertEqual(asked[1], Q["事故車種"])
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.sub_category, "車禍救助")


class AccidentExtractionTests(unittest.TestCase):
    def _calls(self, main_category: str):
        calls = []

        def extract_slots(text, schema, rules, **_kwargs):
            calls.append((schema, rules))
            if "accident_vehicle_type" in schema:
                return {
                    "accident_vehicle_type": "腳踏車",
                    "accident_injury": HEAD_INJURY,
                    "accident_caller_role": "我是當事人",
                    "accident_consciousness": "醒著",
                }
            return {}

        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = extract_slots
        result = ext.extract_general_fields("測試", "測試", main_category=main_category)
        return calls, result

    def test_schema_only_for_emergency_and_bad_fixed_answers_dropped(self) -> None:
        calls, result = self._calls("緊急救援")
        schema, rules = next(call for call in calls if "accident_vehicle_type" in call[0])
        for field in (
            *ACCIDENT_FIELDS, "caller_relation", "patient_gender", "patient_age",
            "breathing", "consciousness",
        ):
            self.assertIn(field, schema)
            self.assertIn(field, rules)
        self.assertNotIn("accident_vehicle_type", result)
        self.assertNotIn("accident_consciousness", result)
        self.assertEqual(result["accident_injury"], HEAD_INJURY)
        self.assertEqual(result["accident_caller_role"], ROLE_SELF)

        rescue_calls, _ = self._calls("救護")
        for schema, _rules in rescue_calls:
            self.assertNotIn("accident_vehicle_type", schema)

    def test_leaving_emergency_clears_accident_fields(self) -> None:
        engine, _io = _engine([])
        engine.case.accident_vehicle_type = "機車車禍"
        engine.case.caller_relation = "兒子"
        engine._migrate_case_for_main_switch("緊急救援", "救護")
        self.assertIsNone(engine.case.accident_vehicle_type)
        self.assertIsNone(engine.case.sub_category)
        self.assertEqual(engine.case.caller_relation, "兒子")


if __name__ == "__main__":
    unittest.main()
