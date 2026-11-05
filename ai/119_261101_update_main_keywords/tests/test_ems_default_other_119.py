"""救護判不出次案類時，照救護-其它的題目問，不走廠商舊的通用流程。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sop_119_engine import DialogueIO, SopEngine119


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


class DefaultOtherTests(unittest.TestCase):
    def test_unknown_subcategory_asks_other_first_question(self) -> None:
        io = ScriptedIO([])
        engine = SopEngine119(io=io, llm_extractor=NoExtractLLM())
        engine.case.main_category = "救護"

        # 次案類模型出錯、關鍵字也沒命中：判次案類沒有結果
        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(engine, "_do_sub_classify", return_value=(None, None, None, None)),
            self.assertRaises(AssertionError),  # 問完第一題就沒有準備回答
        ):
            engine._run_救護()

        self.assertEqual(engine.case.sub_category, "其它")
        self.assertEqual(io.messages[-1], "請問患者是身體不舒服，還是受傷？")  # 其它第 1 題：主訴


if __name__ == "__main__":
    unittest.main()
