from __future__ import annotations

import unittest

from handlers import sop_slots_for
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119


IDENTIFY_QUESTION = "請說出地址、案號、「車輛代號」、「帶隊官代號」或案類來確認案件。"
CONTENT_QUESTION = "請說出要回報的內容(例如在哪邊燙傷?為何被燙傷？)"
CONTINUE_QUESTION = "請您接著說"
CLOSING = "收到您的回報內容，謝謝."
CONFIRM_QUESTION = "請問是14:32、新北市板橋區文化路一段100號的燒燙傷案件嗎?"


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


class ReportExtractor:
    def __init__(self):
        self.calls: list[dict] = []
        self.summaries = 0

    def extract_general_fields(
        self,
        caller_text: str,
        question: str | None = None,
        *,
        main_category: str | None = None,
        call_type: str | None = None,
        fire_tab: str | None = None,
        allowed_fields=None,
    ) -> dict:
        del call_type, fire_tab
        self.calls.append({
            "text": caller_text,
            "question": question,
            "main_category": main_category,
            "allowed_fields": None if allowed_fields is None else set(allowed_fields),
        })
        if "燙" in (caller_text or ""):
            return {"injury_cause": "熱水燙傷"}
        return {}

    def extract_address(
        self,
        caller_text: str,
        use_question: bool = False,
        include_floor: bool = True,
    ) -> dict:
        del caller_text, use_question, include_floor
        return {}

    def generate_summary(self, transcript_texts: list[str], filled_fields: dict) -> str:
        del transcript_texts, filled_fields
        self.summaries += 1
        return f"回報摘要{self.summaries}"


def _full_answers(first: str) -> list[str]:
    return [
        first,
        "案號119",
        "是",
        "左手被熱水燙到",
        "起了水泡",
        "左手",
        "範圍大約手掌",
        "人還清醒",
        "是家人報的",
    ]


class ReportBackFlowTests(unittest.TestCase):
    def test_first_turn_without_keyword_does_not_enter_report_back(self) -> None:
        io = ScriptedIO(["有人受傷，需要救護車"])
        engine = SopEngine119(io=io)

        self.assertFalse(engine._is_report_back("有人受傷，需要救護車"))
        engine.run()

        self.assertNotEqual(engine.case.main_category, "回報")
        self.assertNotIn(IDENTIFY_QUESTION, io.messages)

    def test_simplified_keyword_is_report_back(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        self.assertTrue(engine._is_report_back("我要回报"))

    def test_report_back_confirms_case_then_collects_five_continuations(self) -> None:
        io = ScriptedIO(_full_answers("我要回報"))
        llm = ReportExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]

        engine.run()

        self.assertEqual(engine.case.main_category, "回報")
        self.assertEqual(engine.case.main_conf, 1.0)
        self.assertIsNone(engine.case.sub_category)
        self.assertEqual(engine.case.report_case_time, "14:32")
        self.assertEqual(engine.case.report_case_address, "新北市板橋區文化路一段100號")
        self.assertEqual(engine.case.report_case_category, "燒燙傷")
        self.assertEqual(engine.case.injury_cause, "熱水燙傷")
        self.assertEqual(
            engine.case.report_content,
            "左手被熱水燙到\n起了水泡\n左手\n範圍大約手掌\n人還清醒\n是家人報的",
        )
        self.assertEqual(engine.case.result, "report_back_recorded")
        self.assertEqual(engine.case.flow_stage, "completed")
        self.assertEqual(io.messages[1], IDENTIFY_QUESTION)
        self.assertEqual(io.messages[2], CONFIRM_QUESTION)
        self.assertEqual(io.messages[3], CONTENT_QUESTION)
        self.assertEqual(io.messages[4:9], [CONTINUE_QUESTION] * 5)
        self.assertEqual(io.messages[9], CLOSING)
        self.assertFalse(io.answers)

        burn_calls = [call for call in llm.calls if call["text"] == "左手被熱水燙到"]
        self.assertEqual(len(burn_calls), 1)
        self.assertEqual(burn_calls[0]["main_category"], "救護")
        self.assertIn("injury_cause", burn_calls[0]["allowed_fields"])
        self.assertIn("injury_severity", burn_calls[0]["allowed_fields"])
        self.assertNotIn("pregnancy_week", burn_calls[0]["allowed_fields"])

        continue_calls = [
            call for call in llm.calls if call["question"] == CONTINUE_QUESTION
        ]
        self.assertEqual(len(continue_calls), 5)
        for call in continue_calls:
            self.assertEqual(call["main_category"], "救護")
            self.assertIn("injury_cause", call["allowed_fields"])
        # 開場、識別、對上後補摘要、確認、內容、五遍接話、收尾前再摘要。
        self.assertEqual(llm.summaries, 11)
        self.assertTrue(engine.case.case_summary)


class ReportExtractionScopeTests(unittest.TestCase):
    def test_allowed_fields_keep_general_and_case_slots(self) -> None:
        extractor = LLMExtractor119.__new__(LLMExtractor119)
        seen: list[dict] = []

        def fake_groups(schema_groups, caller_text, *, question, tail):
            del caller_text, question, tail
            seen.extend(schema for schema, _rules in schema_groups)
            return [{} for _ in schema_groups]

        extractor._extract_groups = fake_groups  # type: ignore[method-assign]
        extractor.extract_general_fields(
            "左手被熱水燙到",
            question=CONTENT_QUESTION,
            main_category="救護",
            allowed_fields=sop_slots_for("燒燙傷"),
        )
        keys = set().union(*(schema.keys() for schema in seen))
        self.assertIn("address", keys)
        self.assertIn("caller_name", keys)
        self.assertIn("injury_cause", keys)
        self.assertIn("injury_severity", keys)
        self.assertNotIn("pregnancy_week", keys)
        self.assertNotIn("hanging_status", keys)

        seen.clear()
        extractor.extract_general_fields("燙到", main_category="救護")
        open_keys = set().union(*(schema.keys() for schema in seen))
        self.assertIn("pregnancy_week", open_keys)


if __name__ == "__main__":
    unittest.main()
