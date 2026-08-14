from __future__ import annotations

import unittest
from unittest.mock import patch

from handlers.base import SubCategoryHandler
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError


CONSCIOUSNESS_QUESTION = "請問患者有沒有清醒？"
BREATHING_QUESTION = "是否有正常呼吸？"
ABDOMEN_QUESTION = "幫我看他的肚子有沒有一上、一下起伏。"

GENERIC_CONSCIOUSNESS_QUESTION = "請問人是否還有意識？"
GENERIC_BREATHING_QUESTION = "請你看一下他是否有呼吸？"
GENERIC_ABDOMEN_QUESTION = "請看一下他肚子有沒有起伏？"


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


class RescueVitalFlowTests(unittest.TestCase):
    def _run_subtype_vitals(
        self,
        answers: list[str],
        *,
        transcript: list[dict[str, str]] | None = None,
    ) -> tuple[SopEngine119, ScriptedIO]:
        io = ScriptedIO(answers)
        engine = SopEngine119(io=io)
        engine.case.main_category = "救護"
        if transcript is not None:
            engine.case.transcript = list(transcript)

        handler = SubCategoryHandler()
        handler._run_s1_consciousness_breathing(
            engine,
            q_consciousness=CONSCIOUSNESS_QUESTION,
            q_breathing=BREATHING_QUESTION,
            has_abdomen_followup=True,
        )
        handler._run_s2_response_or_abdomen(
            engine,
            reaction_options=("叫患者有反應嗎？",),
            abdomen_question=ABDOMEN_QUESTION,
        )
        return engine, io

    def test_subtype_stops_after_consciousness_is_yes(self) -> None:
        engine, io = self._run_subtype_vitals(["有意識"])

        self.assertEqual(io.messages, [CONSCIOUSNESS_QUESTION])
        self.assertIs(engine.case.consciousness, True)
        self.assertNotIn(BREATHING_QUESTION, io.messages)
        self.assertNotIn(ABDOMEN_QUESTION, io.messages)
        self.assertFalse(engine.case.is_ohca)

    def test_subtype_stops_when_consciousness_cannot_be_confirmed(self) -> None:
        io = ScriptedIO(["不知道"])
        engine = SopEngine119(io=io)
        handler = SubCategoryHandler()

        with self.assertRaises(TransferToHumanError):
            handler._run_s1_consciousness_breathing(
                engine,
                q_consciousness=CONSCIOUSNESS_QUESTION,
                q_breathing=BREATHING_QUESTION,
            )

        self.assertTrue(engine.case.is_ohca)
        self.assertNotIn(BREATHING_QUESTION, io.messages)

    def test_subtype_asks_breathing_after_no_consciousness_then_stops_on_yes(
        self,
    ) -> None:
        engine, io = self._run_subtype_vitals(["沒有意識", "有呼吸"])

        self.assertEqual(io.messages[:2], [CONSCIOUSNESS_QUESTION, BREATHING_QUESTION])
        self.assertNotIn(ABDOMEN_QUESTION, io.messages)
        self.assertIs(engine.case.consciousness, False)
        self.assertIs(engine.case.breathing, True)
        self.assertFalse(engine.case.is_ohca)

    def test_subtype_asks_abdomen_only_after_first_two_are_no(self) -> None:
        engine, io = self._run_subtype_vitals(
            ["沒有意識", "沒有呼吸", "有起伏"]
        )

        self.assertEqual(
            io.messages,
            [CONSCIOUSNESS_QUESTION, BREATHING_QUESTION, ABDOMEN_QUESTION],
        )
        self.assertIs(engine.case.consciousness, False)
        self.assertIs(engine.case.breathing, False)
        self.assertIs(engine.case.abdomen_rise, True)
        self.assertFalse(engine.case.is_ohca)

    def test_subtype_transfers_only_after_all_three_are_no(self) -> None:
        io = ScriptedIO(["沒有意識", "沒有呼吸", "沒有起伏"])
        engine = SopEngine119(io=io)
        handler = SubCategoryHandler()

        with self.assertRaises(TransferToHumanError) as raised:
            handler._run_s1_consciousness_breathing(
                engine,
                q_consciousness=CONSCIOUSNESS_QUESTION,
                q_breathing=BREATHING_QUESTION,
                has_abdomen_followup=True,
            )
            handler._run_s2_response_or_abdomen(
                engine,
                reaction_options=("叫患者有反應嗎？",),
                abdomen_question=ABDOMEN_QUESTION,
            )

        self.assertEqual(raised.exception.result, "ohca_transfer")
        self.assertEqual(
            io.messages[:3],
            [CONSCIOUSNESS_QUESTION, BREATHING_QUESTION, ABDOMEN_QUESTION],
        )
        self.assertTrue(engine.case.is_ohca)

    def test_subtype_without_abdomen_transfers_after_two_no_answers(self) -> None:
        io = ScriptedIO(["沒有意識", "沒有呼吸"])
        engine = SopEngine119(io=io)
        handler = SubCategoryHandler()

        with self.assertRaises(TransferToHumanError):
            handler._run_s1_consciousness_breathing(
                engine,
                q_consciousness=CONSCIOUSNESS_QUESTION,
                q_breathing=BREATHING_QUESTION,
            )

        self.assertEqual(io.messages[:2], [CONSCIOUSNESS_QUESTION, BREATHING_QUESTION])
        self.assertTrue(engine.case.is_ohca)

    def test_subtype_stops_on_vital_already_known_from_history(self) -> None:
        engine, io = self._run_subtype_vitals(
            [],
            transcript=[
                {
                    "role": "caller",
                    "text": "患者意識清醒。",
                }
            ],
        )

        self.assertEqual(io.messages, [])
        self.assertIs(engine.case.consciousness, True)
        self.assertIsNone(engine.case.breathing)
        self.assertIsNone(engine.case.abdomen_rise)

    def test_generic_flow_stops_after_consciousness_is_yes(self) -> None:
        class StopAfterVitals(Exception):
            pass

        io = ScriptedIO(["有意識"])
        engine = SopEngine119(io=io)

        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(
                engine,
                "_do_sub_classify",
                return_value=("未登錄子類", 1.0, "keyword"),
            ),
            patch.object(
                SubCategoryHandler,
                "run_post_vital",
                side_effect=StopAfterVitals,
            ),
            self.assertRaises(StopAfterVitals),
        ):
            engine._run_救護()

        self.assertIn(GENERIC_CONSCIOUSNESS_QUESTION, io.messages)
        self.assertNotIn(GENERIC_BREATHING_QUESTION, io.messages)
        self.assertNotIn(GENERIC_ABDOMEN_QUESTION, io.messages)

    def test_generic_flow_asks_next_question_only_after_no(self) -> None:
        class StopAfterVitals(Exception):
            pass

        io = ScriptedIO(["沒有意識", "有呼吸"])
        engine = SopEngine119(io=io)

        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(
                engine,
                "_do_sub_classify",
                return_value=("未登錄子類", 1.0, "keyword"),
            ),
            patch.object(
                SubCategoryHandler,
                "run_post_vital",
                side_effect=StopAfterVitals,
            ),
            self.assertRaises(StopAfterVitals),
        ):
            engine._run_救護()

        self.assertEqual(
            io.messages[:2],
            [GENERIC_CONSCIOUSNESS_QUESTION, GENERIC_BREATHING_QUESTION],
        )
        self.assertNotIn(GENERIC_ABDOMEN_QUESTION, io.messages)

    def test_generic_flow_transfers_after_all_three_are_no(self) -> None:
        io = ScriptedIO(["沒有意識", "沒有呼吸", "沒有起伏"])
        engine = SopEngine119(io=io)

        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(
                engine,
                "_do_sub_classify",
                return_value=("未登錄子類", 1.0, "keyword"),
            ),
            self.assertRaises(TransferToHumanError),
        ):
            engine._run_救護()

        self.assertEqual(
            io.messages[:3],
            [
                GENERIC_CONSCIOUSNESS_QUESTION,
                GENERIC_BREATHING_QUESTION,
                GENERIC_ABDOMEN_QUESTION,
            ],
        )
        self.assertTrue(engine.case.is_ohca)


if __name__ == "__main__":
    unittest.main()
