"""救護判不出次案類時先追問兩句，還判不出來就轉真人（使用者 11/06 決定）；判得出來就不追問。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sop_119_engine import (
    EMS_SUB_REASK_QUESTIONS,
    TRANSFER_LINE,
    DialogueIO,
    SopEngine119,
    TransferToHumanError,
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


class NoExtractLLM:
    def extract_general_fields(self, *args, **kwargs):
        return {}

    def extract_slots(self, *args, **kwargs):
        return {}

    def generate_summary(self, *args, **kwargs):
        return ""


UNKNOWN = (None, None, None, None)
UNSURE = ("急病", 0.5, "classifier", 0.5)       # 模型信心不夠，算判不出來
CONFIDENT = ("急病", 0.95, "classifier", 0.5)   # 信心夠、跟第二名差得夠多


def _run(answers: list[str], classify_results: list[tuple]):
    io = ScriptedIO(answers)
    engine = SopEngine119(io=io, llm_extractor=NoExtractLLM())
    engine.case.main_category = "救護"
    with (
        patch.object(engine, "_run_address_flow"),
        patch.object(engine, "_do_sub_classify", side_effect=classify_results),
    ):
        try:
            engine._run_救護()
        except AssertionError:
            pass  # 進到次案類題目後就沒有準備回答
    return engine, io


class EmsSubReaskTests(unittest.TestCase):
    def test_still_unknown_after_two_questions_transfers_to_human(self) -> None:
        io = ScriptedIO(["我也不太清楚", "就是要救護車"])
        engine = SopEngine119(io=io, llm_extractor=NoExtractLLM())
        engine.case.main_category = "救護"
        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(engine, "_do_sub_classify", side_effect=[UNKNOWN, UNSURE, UNKNOWN]),
            self.assertRaises(TransferToHumanError),
        ):
            engine._run_救護()
        self.assertEqual(io.messages, [*EMS_SUB_REASK_QUESTIONS, TRANSFER_LINE])

    def test_settled_after_first_question_skips_second(self) -> None:
        engine, io = _run(["他吃了很多藥"], [UNKNOWN, CONFIDENT])
        self.assertEqual(io.messages[0], EMS_SUB_REASK_QUESTIONS[0])
        self.assertNotIn(EMS_SUB_REASK_QUESTIONS[1], io.messages)
        self.assertEqual(engine.case.sub_category, "急病")

    def test_settled_at_first_does_not_ask(self) -> None:
        engine, io = _run([], [CONFIDENT])
        for question in EMS_SUB_REASK_QUESTIONS:
            self.assertNotIn(question, io.messages)
        self.assertEqual(engine.case.sub_category, "急病")


if __name__ == "__main__":
    unittest.main()
