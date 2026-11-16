from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
