from __future__ import annotations

import unittest

from sop_119_engine import DialogueIO, SopEngine119


IDENTIFY_QUESTION = "請說出地址、案號、「車輛代號」、「帶隊官代號」或案類來確認案件。"


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


class InternalReportFlowTests(unittest.TestCase):
    def test_ordinary_incident_does_not_enter_internal_report_flow(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._apply_extracted_fields({"call_type": "一般案件"})

        self.assertFalse(engine._is_internal_report("有人受傷，需要救護車"))

    def test_internal_report_keywords_are_frozen(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))

        for text in ("板橋分隊回報", "局內回報", "同仁回報", "局内回报"):
            self.assertFalse(engine._is_internal_report(text))

    def test_squad_report_enters_new_report_flow(self) -> None:
        io = ScriptedIO([
            "板橋分隊回報",
            "文化路100號",
            "是",
            "現場補充",
            "接著一",
            "接著二",
            "接著三",
            "接著四",
            "接著五",
        ])
        engine = SopEngine119(io=io)

        engine.run()

        self.assertEqual(engine.case.main_category, "回報")
        self.assertNotEqual(engine.case.call_type, "局內回報")
        self.assertEqual(engine.case.result, "report_back_recorded")
        self.assertNotIn("長官您好，有什麼需要中心協助嗎？", io.messages)
        self.assertIn(IDENTIFY_QUESTION, io.messages)
        self.assertFalse(io.answers)


if __name__ == "__main__":
    unittest.main()
