"""
災害大類通用流程。

所有子類問同一套題。受困人數只在「有人受困」時問；
火花只在電線掉落、招牌掉落、電線桿傾倒時問。
子類辨識用跟火警一樣的門檻，不夠有把握就不寫，也不換題。

這裡的 LLM、子類模型都是假的：每一句要抽出什麼，由測試事先指定。
"""

from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from disaster_flow_119 import (
    DISASTER_FIELDS,
    DISASTER_QUESTIONS,
    DISPATCH_LINE,
    INJURY_HURT,
    INJURY_NONE,
    INJURY_TRAPPED,
    SPARK_SUBTYPES,
)
from handlers.災害通用 import ZaiHaiGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import build_address_ask_questions

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
        self.categories: list[str | None] = []

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        self.categories.append(main_category)
        return dict(self.extracted.get((caller_text or "").strip(), {}))

    def extract_caller_info(self, question, text, include_address=False):
        return dict(self.extracted.get((text or "").strip(), {}))

    def generate_summary(self, transcript_texts, filled_fields):
        return "災害測試摘要"


class SubBERT:
    """固定回傳一個子類。conf、第二名用來測門檻。"""

    def __init__(self, label: str, conf: float = 0.9, second: float = 0.05,
                 second_label: str = "路樹傾倒"):
        self.label = label
        self.conf = conf
        self.second = second
        self.second_label = second_label

    def predict(self, text, main_cat):
        return types.SimpleNamespace(
            final_label=self.label,
            classifier_conf=self.conf,
            all_probs={self.label: self.conf, self.second_label: self.second},
        )


class LateWireBERT:
    """報案人身分那句出現之前，信心不夠；出現之後才判成電線掉落。"""

    def predict(self, text, main_cat):
        if "我是住戶" in (text or ""):
            return types.SimpleNamespace(
                final_label="電線掉落",
                classifier_conf=0.92,
                all_probs={"電線掉落": 0.92, "路樹傾倒": 0.04},
            )
        return types.SimpleNamespace(
            final_label="路樹傾倒",
            classifier_conf=0.4,
            all_probs={"路樹傾倒": 0.4, "電線掉落": 0.3},
        )


def _engine(steps: list[tuple[str, dict]], bert=None) -> tuple[SopEngine119, ScriptedIO, FakeLLM]:
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    engine.case.main_category = "災害"
    engine._sub_clf = bert
    return engine, io, llm


def _asked(io: ScriptedIO) -> list[str]:
    known = set(Q.values())
    return [message for message in io.messages if message in known]


class DisasterQuestionTests(unittest.TestCase):
    def test_trapped_and_wire_asks_every_question_in_order(self) -> None:
        steps = [
            ("有人被壓住出不來", {"disaster_injury_or_trapped": INJURY_TRAPPED}),
            ("兩個人", {"disaster_trapped_count": "兩個"}),
            ("車子過不去", {"traffic_impact": "完全無法通行"}),
            ("有冒煙", {"electrical_hazard": "有火花或冒煙"}),
            ("我住這裡", {"disaster_caller_role": "屋主或住戶"}),
        ]
        engine, io, _llm = _engine(steps)
        engine.case.sub_category = "電線掉落"
        ZaiHaiGenericHandler().run_generic_flow(engine)
        self.assertEqual(_asked(io), [
            Q["受傷受困"], Q["受困人數"], Q["交通影響"],
            Q["有無火花冒煙或帶電"], Q["報案人身分"],
        ])
        self.assertEqual(engine.case.disaster_trapped_count, "兩個")
        self.assertEqual(engine.case.electrical_hazard, "有火花或冒煙")

    def test_hurt_but_not_trapped_skips_count(self) -> None:
        steps = [
            ("有人擦傷，人已經出來了", {"disaster_injury_or_trapped": INJURY_HURT}),
            ("沒擋到路", {"traffic_impact": "未影響交通"}),
            ("我路過", {"disaster_caller_role": "路過"}),
        ]
        engine, io, _llm = _engine(steps)
        engine.case.sub_category = "路樹傾倒"
        ZaiHaiGenericHandler().run_generic_flow(engine)
        self.assertEqual(_asked(io), [Q["受傷受困"], Q["交通影響"], Q["報案人身分"]])
        self.assertNotIn(Q["受困人數"], io.messages)
        self.assertNotIn(Q["有無火花冒煙或帶電"], io.messages)

    def test_spark_only_for_three_subtypes(self) -> None:
        for subtype in (*SPARK_SUBTYPES, "路樹傾倒", None):
            with self.subTest(subtype=subtype):
                steps = [
                    ("沒有人受傷", {"disaster_injury_or_trapped": INJURY_NONE}),
                    ("車還過得去", {"traffic_impact": "佔用部分車道"}),
                    ("有火花", {"electrical_hazard": "有火花或冒煙"}),
                    ("鄰居", {"disaster_caller_role": "鄰居或附近店家"}),
                ]
                if subtype not in SPARK_SUBTYPES:
                    steps = [step for step in steps if step[0] != "有火花"]
                engine, io, _llm = _engine(steps)
                engine.case.sub_category = subtype
                ZaiHaiGenericHandler().run_generic_flow(engine)
                if subtype in SPARK_SUBTYPES:
                    self.assertIn(Q["有無火花冒煙或帶電"], _asked(io))
                else:
                    self.assertNotIn(Q["有無火花冒煙或帶電"], io.messages)

    def test_already_filled_questions_are_skipped(self) -> None:
        engine, io, _llm = _engine([])
        engine.case.sub_category = "招牌掉落"
        engine.case.disaster_injury_or_trapped = INJURY_NONE
        engine.case.traffic_impact = "未影響交通"
        engine.case.electrical_hazard = "沒有"
        engine.case.disaster_caller_role = "里長或管理員"
        ZaiHaiGenericHandler().run_generic_flow(engine)
        self.assertEqual(_asked(io), [])

    def test_spark_asked_after_subtype_becomes_known(self) -> None:
        steps = [
            ("沒有人", {"disaster_injury_or_trapped": INJURY_NONE}),
            ("沒擋到", {"traffic_impact": "未影響交通"}),
            ("我是住戶，人還在現場", {"disaster_caller_role": "屋主或住戶"}),
            ("電線有冒煙", {"electrical_hazard": "有火花或冒煙"}),
        ]
        engine, io, _llm = _engine(steps, bert=LateWireBERT())
        ZaiHaiGenericHandler().run_generic_flow(engine)
        asked = _asked(io)
        self.assertEqual(asked[-2:], [Q["報案人身分"], Q["有無火花冒煙或帶電"]])
        self.assertEqual(engine.case.sub_category, "電線掉落")
        self.assertEqual(engine.case.electrical_hazard, "有火花或冒煙")


class DisasterDispatchTests(unittest.TestCase):
    def test_announces_after_subtype_attempt_even_if_unknown(self) -> None:
        steps = [
            ("沒有人受傷", {"disaster_injury_or_trapped": INJURY_NONE}),
            ("沒擋到路", {"traffic_impact": "未影響交通"}),
            ("我路過", {"disaster_caller_role": "路過"}),
            ("王小明 0912345678", {"caller_name": "王小明", "caller_contact": "0912345678"}),
        ]
        engine, io, _llm = _engine(steps, bert=SubBERT("路樹傾倒", conf=0.4, second=0.3))
        engine.case.address = "板橋區文化路一段10號"
        engine.case.address_confirmed = True
        engine._address_locked = True
        engine.case.transcript.append({"role": "caller", "text": "路樹倒在文化路"})
        engine._run_災害()
        self.assertLess(io.messages.index(DISPATCH_LINE), io.messages.index(Q["受傷受困"]))
        self.assertIsNone(engine.case.sub_category)
        self.assertNotIn(Q["有無火花冒煙或帶電"], io.messages)
        self.assertEqual(engine.case.result, "dispatched")
        self.assertEqual(engine.case.caller_name, "王小明")

    def test_main_classifier_enters_disaster_flow(self) -> None:
        class Reached(Exception):
            pass

        class Main:
            def predict(self, text):
                return {
                    "main_category": "災害",
                    "main_conf": 0.95,
                    "main_probs": {"災害": 0.95, "火警": 0.03},
                }

        io = ScriptedIO(["路樹倒了擋住路"])
        engine = SopEngine119(io=io, main_classifier=Main(), llm_extractor=FakeLLM({}))
        with patch.object(engine, "_run_災害", side_effect=Reached):
            with self.assertRaises(Reached):
                engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "災害")
        joined = "\n".join(io.messages)
        self.assertNotIn("即將轉接專人", joined)

    def test_outdoor_address_questions(self) -> None:
        self.assertEqual(
            build_address_ask_questions(include_floor=False, flow="災害"),
            build_address_ask_questions(include_floor=False, flow="火警"),
        )
        self.assertIn("路燈或電線桿", build_address_ask_questions(flow="災害")[2])


class DisasterSubtypeThresholdTests(unittest.TestCase):
    def test_low_confidence_does_not_write_subtype(self) -> None:
        engine, _io, _llm = _engine([])
        engine._sub_clf = SubBERT("電線掉落", conf=0.5, second=0.2)
        engine.case.transcript.append({"role": "caller", "text": "現場還在確認中"})
        engine._refresh_disaster_subtype_from_bert()
        self.assertIsNone(engine.case.sub_category)

    def test_narrow_margin_does_not_write_subtype(self) -> None:
        engine, _io, _llm = _engine([])
        engine._sub_clf = SubBERT("招牌掉落", conf=0.55, second=0.45, second_label="電線掉落")
        engine.case.transcript.append({"role": "caller", "text": "招牌快掉了"})
        engine._refresh_disaster_subtype_from_bert()
        self.assertIsNone(engine.case.sub_category)

    def test_confident_subtype_does_not_clear_answers(self) -> None:
        engine, _io, _llm = _engine([])
        engine.case.traffic_impact = "未影響交通"
        engine.case.sub_category = "路樹傾倒"
        engine._sub_clf = SubBERT("招牌掉落", conf=0.9, second=0.04)
        engine.case.transcript.append({"role": "caller", "text": "招牌掉下來了"})
        engine._refresh_disaster_subtype_from_bert()
        self.assertEqual(engine.case.sub_category, "招牌掉落")
        self.assertEqual(engine.case.traffic_impact, "未影響交通")


class DisasterFieldWriteTests(unittest.TestCase):
    def test_enums_overwrite_but_count_only_on_its_question(self) -> None:
        engine, _io, _llm = _engine([])
        engine.case.disaster_injury_or_trapped = INJURY_NONE
        engine.case.disaster_trapped_count = "兩個"
        engine._apply_extracted_fields({
            "disaster_injury_or_trapped": INJURY_TRAPPED,
            "disaster_trapped_count": "三個",
        })
        self.assertEqual(engine.case.disaster_injury_or_trapped, INJURY_TRAPPED)
        self.assertEqual(engine.case.disaster_trapped_count, "兩個")

        engine._pending_extract_question = Q["受困人數"]
        engine._apply_extracted_fields({"disaster_trapped_count": "三個"})
        self.assertEqual(engine.case.disaster_trapped_count, "三個")

    def test_other_main_category_does_not_keep_disaster_fields(self) -> None:
        engine, _io, _llm = _engine([])
        engine.case.main_category = "救護"
        engine._apply_extracted_fields({"traffic_impact": "未影響交通"})
        self.assertIsNone(engine.case.traffic_impact)

    def test_leaving_disaster_clears_exclusive_fields(self) -> None:
        engine, _io, _llm = _engine([])
        engine.case.address = "板橋區文化路一段10號"
        engine.case.traffic_impact = "完全無法通行"
        engine.case.sub_category = "電線掉落"
        engine._migrate_case_for_main_switch("災害", "救護")
        self.assertEqual(engine.case.address, "板橋區文化路一段10號")
        self.assertIsNone(engine.case.traffic_impact)
        self.assertIsNone(engine.case.sub_category)


class DisasterExtractionScopeTests(unittest.TestCase):
    def _calls(self, main_category: str):
        calls = []

        def extract_slots(text, schema, rules, **_kwargs):
            calls.append((schema, rules))
            if "disaster_injury_or_trapped" in schema:
                return {
                    "disaster_injury_or_trapped": "受傷了",
                    "disaster_trapped_count": "兩個",
                    "traffic_impact": "完全堵住",
                    "electrical_hazard": "有火花或冒煙",
                    "disaster_caller_role": "屋主",
                }
            return {}

        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = extract_slots
        result = ext.extract_general_fields("測試", "測試", main_category=main_category)
        return calls, result

    def test_disaster_schema_only_for_disaster(self) -> None:
        calls, result = self._calls("災害")
        schema, rules = next(call for call in calls if "disaster_injury_or_trapped" in call[0])
        self.assertEqual(tuple(schema), DISASTER_FIELDS)
        for field in DISASTER_FIELDS:
            self.assertIn(field, rules)
        self.assertNotIn("disaster_injury_or_trapped", result)
        self.assertNotIn("traffic_impact", result)
        self.assertNotIn("disaster_caller_role", result)
        self.assertEqual(result["disaster_trapped_count"], "兩個")
        self.assertEqual(result["electrical_hazard"], "有火花或冒煙")

        rescue_calls, _rescue_result = self._calls("救護")
        for schema, _rules in rescue_calls:
            self.assertNotIn("disaster_injury_or_trapped", schema)
            self.assertNotIn("traffic_impact", schema)


if __name__ == "__main__":
    unittest.main()
