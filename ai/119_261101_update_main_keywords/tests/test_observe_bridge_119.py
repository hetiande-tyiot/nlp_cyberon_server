from __future__ import annotations

import unittest

from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError


class ScriptedIO(DialogueIO):
    def __init__(self):
        self.spoken: list[str] = []

    def say(self, text: str) -> None:
        self.spoken.append(text)

    def hear_text(self) -> str:
        return ""


class FakeExtractor:
    def __init__(self, outputs: list[dict] | None = None) -> None:
        self.outputs = list(outputs or [])
        self.general_calls: list[tuple[str, str | None]] = []
        self.summary_calls: list[list[str]] = []

    def extract_general_fields(
        self,
        caller_text: str,
        question: str | None = None,
        *,
        main_category: str | None = None,
        call_type: str | None = None,
    ) -> dict:
        del main_category, call_type
        self.general_calls.append((caller_text, question))
        if self.outputs:
            return self.outputs.pop(0)
        return {
            "address": "新北市板橋區文化路100號",
            "caller_name": "王小明",
        }

    def extract_address(self, caller_text: str, use_question: bool = False) -> dict:
        del caller_text, use_question
        return {}

    def generate_summary(self, transcript_texts: list[str], filled_fields: dict) -> str:
        del filled_fields
        self.summary_calls.append(list(transcript_texts))
        return "板橋區文化路有人身體不適，已轉接專人。"


class ObserveBridge119Tests(unittest.TestCase):
    def test_caller_observe_updates_fields_and_summary_without_saying(self) -> None:
        io = ScriptedIO()
        llm = FakeExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)
        engine.case.main_category = "救護"
        engine._bridged = True

        result = engine.observe_utterance(
            "caller",
            "我在新北市板橋區文化路100號，我叫王小明",
        )

        self.assertEqual(io.spoken, [])
        self.assertEqual(engine.case.transcript[-1]["role"], "caller")
        self.assertTrue(engine._bridged)
        self.assertEqual(engine.case.caller_name, "王小明")
        self.assertEqual(engine.case.case_summary, "板橋區文化路有人身體不適，已轉接專人。")
        self.assertEqual(result["case_summary"], engine.case.case_summary)
        self.assertTrue(llm.general_calls)
        self.assertEqual(llm.general_calls[-1][1], "")
        self.assertTrue(llm.summary_calls)

    def test_agent_observe_skips_extract(self) -> None:
        io = ScriptedIO()
        llm = FakeExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)
        engine.case.main_category = "救護"

        result = engine.observe_utterance("agent", "請問還有沒有其他人受傷")

        self.assertEqual(io.spoken, [])
        self.assertEqual(engine.case.transcript[-1]["role"], "agent")
        self.assertEqual(result["updated_fields"], [])
        self.assertFalse(llm.general_calls)
        self.assertFalse(llm.summary_calls)

    def test_bridged_ohca_check_does_not_raise_or_speak(self) -> None:
        io = ScriptedIO()
        engine = SopEngine119(io=io, llm_extractor=FakeExtractor())
        engine._bridged = True

        engine._check_ohca_and_transfer(False, "consciousness")

        self.assertTrue(engine.case.is_ohca)
        self.assertEqual(io.spoken, [])

    def test_observe_does_not_reraise_transfer(self) -> None:
        io = ScriptedIO()
        engine = SopEngine119(io=io, llm_extractor=FakeExtractor())
        engine._bridged = True
        try:
            engine.observe_utterance("caller", "病人沒有呼吸")
        except TransferToHumanError:
            self.fail("observe_utterance should not raise TransferToHumanError")
        self.assertEqual(io.spoken, [])


if __name__ == "__main__":
    unittest.main()
