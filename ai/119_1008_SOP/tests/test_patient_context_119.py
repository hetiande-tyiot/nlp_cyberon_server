from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from handlers.base import SubCategoryHandler
from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import (
    infer_caller_is_patient,
    infer_patient_gender_from_honorific,
    parse_patient_count,
)


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError("測試回答已用盡")
        return self.answers.pop(0)


class PatientContextRuleTests(unittest.TestCase):
    def test_honorific_male_third_party(self) -> None:
        self.assertEqual(
            infer_patient_gender_from_honorific("有一位先生倒在路邊"),
            "男",
        )

    def test_honorific_female_third_party(self) -> None:
        self.assertEqual(
            infer_patient_gender_from_honorific("路倒了一位女士"),
            "女",
        )

    def test_honorific_self_salutation_not_patient_gender(self) -> None:
        self.assertIsNone(infer_patient_gender_from_honorific("電話0912345678，我是先生"))

    def test_caller_is_patient_true(self) -> None:
        self.assertTrue(infer_caller_is_patient("我自己割腕了"))
        self.assertTrue(infer_caller_is_patient("我頭很痛"))

    def test_caller_is_patient_false(self) -> None:
        self.assertFalse(infer_caller_is_patient("我媽媽昏倒了"))
        self.assertFalse(infer_caller_is_patient("一位路人倒在路邊"))

    def test_parse_patient_count(self) -> None:
        self.assertEqual(parse_patient_count("2位"), 2)
        self.assertEqual(parse_patient_count("两个人"), 2)
        self.assertEqual(parse_patient_count("1人"), 1)
        self.assertIsNone(parse_patient_count(None))


class PatientContextS6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.handler = SubCategoryHandler()

    def test_sync_infers_gender_from_history(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.transcript = [
            {"role": "assistant", "text": "請問發生什麼事？"},
            {"role": "caller", "text": "有一位先生倒在路邊"},
        ]
        engine._extracted_caller_count = 0
        engine._ensure_known_fields_from_history()
        self.assertEqual(engine.case.patient_gender, "男")

    def test_build_question_asks_age_only_when_gender_known(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.patient_gender = "男"
        q = self.handler._build_patient_demo_question(engine)
        self.assertEqual(q, "請問他大約幾歲？")

    def test_build_question_caller_is_patient(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.caller_is_patient = True
        engine.case.patient_gender = "男"
        q = self.handler._build_patient_demo_question(engine)
        self.assertEqual(q, "請問您大約幾歲？")

    def test_build_question_multiple_casualties(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.patient_count = "2位"
        q = self.handler._build_patient_demo_question(engine)
        self.assertEqual(q, "可以描述一下傷者的性別和年齡嗎？")

    def test_run_s6_skips_gender_asks_age_only(self) -> None:
        io = ScriptedIO(["1人", "75歲"])
        engine = SopEngine119(io=io)
        engine.case.transcript = [
            {"role": "assistant", "text": "請問發生什麼事？"},
            {"role": "caller", "text": "有一位先生倒在路邊"},
        ]
        engine._extracted_caller_count = 1

        mock_llm = MagicMock()
        mock_llm.extract_patient_info.return_value = {
            "patient_gender": None,
            "patient_age": "75歲",
            "incident_description": None,
            "current_condition": None,
        }
        mock_llm.extract_slots.return_value = {"patient_count": "1人"}
        engine._llm = mock_llm

        self.handler._run_s6_gender_age(engine, "test_S6")

        self.assertEqual(engine.case.patient_gender, "男")
        self.assertEqual(engine.case.patient_age, "75歲")
        # 通用 handler（sub_category=None，非外傷）→ 中性人數問法（修2）
        self.assertIn("現場有幾位需要救護？", io.messages)
        self.assertIn("請問他大約幾歲？", io.messages)
        self.assertNotIn("男生還是女生", " ".join(io.messages))

    def test_run_s6_caller_patient_skips_when_both_filled(self) -> None:
        io = ScriptedIO(["1人"])
        engine = SopEngine119(io=io)
        engine.case.transcript = [
            {"role": "assistant", "text": "請問發生什麼事？"},
            {"role": "caller", "text": "我自己割腕了，25歲，男生"},
        ]
        engine._extracted_caller_count = 1
        engine.case.caller_is_patient = True
        engine.case.patient_gender = "男"
        engine.case.patient_age = "25歲"

        mock_llm = MagicMock()
        mock_llm.extract_slots.return_value = {"patient_count": "1人"}
        engine._llm = mock_llm

        self.handler._run_s6_gender_age(engine, "test_S6")

        self.assertNotIn("男生還是女生", " ".join(io.messages))
        self.assertNotIn("大約幾歲", " ".join(io.messages[1:]))

    def test_condition_question_caller_is_patient(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.caller_is_patient = True
        q = self.handler.build_patient_condition_question(engine)
        self.assertEqual(q, "請問您現在狀況如何？")


if __name__ == "__main__":
    unittest.main()
