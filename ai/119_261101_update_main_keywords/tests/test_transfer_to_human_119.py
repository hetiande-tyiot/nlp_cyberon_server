"""
轉接真人統一做法（使用者 11/06 決定）：engine._transfer_to_human。

1. 已經轉接過就什麼都不做（真人接手後系統還在旁邊聽，條件可能再成立一次）
2. 講統一的那句「請不要掛斷電話，我馬上幫您轉接專人。」
3. 交給報案流程最外層收尾：結果記成 human_transfer，下游會跳轉接提示、不掛電話
"""

from __future__ import annotations

import unittest

from handlers.base import SubCategoryHandler
from sop_119_engine import TRANSFER_LINE, DialogueIO, SopEngine119, TransferToHumanError


class RecordingIO(DialogueIO):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        raise AssertionError("轉接測試不應該再問問題")


class TransferToHumanTests(unittest.TestCase):
    def test_says_unified_line_and_hands_over(self) -> None:
        io = RecordingIO()
        engine = SopEngine119(io=io)
        with self.assertRaises(TransferToHumanError) as raised:
            engine._transfer_to_human("測試原因")
        self.assertEqual(TRANSFER_LINE, "請不要掛斷電話，我馬上幫您轉接專人。")
        self.assertEqual(io.messages, [TRANSFER_LINE])
        self.assertEqual(raised.exception.result, "human_transfer")
        self.assertEqual(raised.exception.reason, "測試原因")
        # 講的話記進對話紀錄
        self.assertEqual(engine.case.transcript[-1], {"role": "assistant", "text": TRANSFER_LINE})

    def test_already_transferred_does_nothing(self) -> None:
        io = RecordingIO()
        engine = SopEngine119(io=io)
        engine._bridged = True
        engine._transfer_to_human("真人接手後條件又成立")
        self.assertEqual(io.messages, [])

    def test_breathing_condition_after_transfer_stays_silent(self) -> None:
        # 真人接手後報案人才說沒有呼吸：條件成立，但不講話、不再轉
        io = RecordingIO()
        engine = SopEngine119(io=io)
        engine._bridged = True
        engine.case.breathing = "無呼吸"
        SubCategoryHandler()._check_breathing_transfer(engine)
        self.assertEqual(io.messages, [])

    def test_outer_flow_records_human_transfer(self) -> None:
        io = RecordingIO()
        engine = SopEngine119(io=io)
        engine._run_main_flow = lambda: engine._transfer_to_human("測試原因")  # type: ignore[method-assign]
        engine.run()
        self.assertEqual(io.messages, [TRANSFER_LINE])
        self.assertEqual(engine.case.result, "human_transfer")
        self.assertEqual(engine.case.flow_stage, "human_transfer")
        self.assertTrue(engine._bridged)


if __name__ == "__main__":
    unittest.main()
