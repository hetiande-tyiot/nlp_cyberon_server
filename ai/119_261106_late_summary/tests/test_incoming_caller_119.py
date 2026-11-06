from __future__ import annotations

import unittest
from unittest.mock import patch

from incoming_caller_119 import classify_incoming_line
from location_validation_119 import JurisdictionResult
from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import (
    address_ask_should_include_floor,
    build_address_ask_questions,
)


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.questions: list[str] = []

    def say(self, text: str) -> None:
        self.questions.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError("測試回答已用盡")
        return self.answers.pop(0)


def run_address_flow(engine: SopEngine119) -> None:
    engine._run_address_flow(
        stage_ask="救護_location",
        stage_confirm="救護_location_confirm",
        dispatch_line="已確認地址，救護車已派出了喔。",
        ask_questions=build_address_ask_questions(
            include_floor=address_ask_should_include_floor(
                engine.case.full_caller_text()
            ),
            flow="救護",
        ),
    )


def _valid_jurisdiction(*_args, **_kwargs):
    return JurisdictionResult(True, "板橋分局")


class ClassifyIncomingLineTests(unittest.TestCase):
    def test_unknown(self) -> None:
        for phone in (None, "", "null", "None", "n/a", "abc"):
            with self.subTest(phone=phone):
                self.assertEqual(classify_incoming_line(phone), "unknown")

    def test_mobile(self) -> None:
        for phone in ("0912345678", "09-1234-5678", "+886912345678", "886912345678"):
            with self.subTest(phone=phone):
                self.assertEqual(classify_incoming_line(phone), "mobile")

    def test_landline(self) -> None:
        for phone in ("02-29681234", "0229681234", "+886229681234"):
            with self.subTest(phone=phone):
                self.assertEqual(classify_incoming_line(phone), "landline")


class IncomingCallerAddressTests(unittest.TestCase):
    def _load(self, engine: SopEngine119, phone, address: str) -> None:
        with patch(
            "sop_119_engine.fetch_incoming_caller",
            return_value={"phone": phone, "address": address},
        ):
            engine._load_incoming_caller()

    def test_fetch_failure_leaves_address_empty(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        with patch(
            "sop_119_engine.fetch_incoming_caller",
            side_effect=RuntimeError("down"),
        ):
            engine._load_incoming_caller()
        self.assertIsNone(engine.case.address)
        self.assertEqual(engine._incoming_line_type, "unknown")

    def test_null_phone_keeps_original_ask(self) -> None:
        io = ScriptedIO(["板橋區府中路32號", "是"])
        engine = SopEngine119(io=io)
        self._load(engine, None, "新北市板橋區文化路一段100號")
        self.assertIsNone(engine.case.address)

        with patch("sop_119_engine.query_jurisdiction", _valid_jurisdiction):
            run_address_flow(engine)

        self.assertIn("請先告訴我地址", io.questions[0])
        self.assertTrue(engine.case.address_confirmed)

    def test_mobile_prefills_district_and_still_asks(self) -> None:
        io = ScriptedIO(["板橋區府中路32號", "是"])
        engine = SopEngine119(io=io)
        self._load(engine, "0912345678", "新北市板橋區文化路一段100號")
        self.assertEqual(engine.case.address, "板橋區")
        self.assertEqual(engine.case.address_district, "板橋區")

        with patch("sop_119_engine.query_jurisdiction", _valid_jurisdiction):
            run_address_flow(engine)

        self.assertIn("請先告訴我地址", io.questions[0])
        self.assertNotIn("請問是", io.questions[0])
        self.assertEqual(engine.case.address, "板橋區府中路32號")
        self.assertTrue(engine.case.address_confirmed)

    def test_mobile_without_district_does_not_prefill(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        self._load(engine, "0912345678", "文化路一段100號")
        self.assertIsNone(engine.case.address)
        self.assertFalse(engine._mobile_district_prefill)

    def test_mobile_history_upgrades_past_district(self) -> None:
        io = ScriptedIO(["是"])
        engine = SopEngine119(io=io)
        engine.case.transcript = [
            {"role": "caller", "text": "我在板橋區府中路32號"},
        ]
        self._load(engine, "0912-345-678", "新北市板橋區文化路一段100號")
        self.assertEqual(engine.case.address, "板橋區")

        with patch("sop_119_engine.query_jurisdiction", _valid_jurisdiction):
            run_address_flow(engine)

        self.assertFalse(any("請先告訴我地址" in q for q in io.questions))
        self.assertTrue(any(q.startswith("確定是") for q in io.questions))
        self.assertEqual(engine.case.address, "板橋區府中路32號")

    def test_landline_yes_skips_second_confirm(self) -> None:
        address = "板橋區府中路32號"
        io = ScriptedIO(["是"])
        engine = SopEngine119(io=io)
        self._load(engine, "02-29681234", address)
        self.assertEqual(engine.case.address, address)

        engine._extract_all_fields_from_reply(
            "我在中和區景平路100號著火了",
            question="119 您好，請問是火災，還是救護",
        )
        self.assertEqual(engine.case.address, address)

        with patch("sop_119_engine.query_jurisdiction", _valid_jurisdiction):
            run_address_flow(engine)

        self.assertEqual(io.questions[0], f"請問是{address}這個地址嗎？")
        self.assertFalse(any("請先告訴我地址" in q for q in io.questions))
        self.assertFalse(any("請問事發地址" in q for q in io.questions))
        self.assertFalse(any(q.startswith("確定是") for q in io.questions))
        self.assertIn("已確認地址，救護車已派出了喔。", io.questions)
        self.assertEqual(engine.case.address, address)
        self.assertTrue(engine.case.address_confirmed)

    def test_landline_no_reasks_then_extracts(self) -> None:
        io = ScriptedIO(["不是", "中和區景平路100號", "是"])
        engine = SopEngine119(io=io)
        self._load(engine, "0229681234", "板橋區府中路32號")

        with patch("sop_119_engine.query_jurisdiction", _valid_jurisdiction):
            run_address_flow(engine)

        self.assertEqual(io.questions[0], "請問是板橋區府中路32號這個地址嗎？")
        self.assertIn("那麻煩告訴我正確的地址", io.questions)
        self.assertFalse(any("請先告訴我地址" in q for q in io.questions))
        self.assertEqual(engine.case.address, "中和區景平路100號")
        self.assertTrue(engine.case.address_confirmed)
        self.assertTrue(any(q.startswith("確定是") for q in io.questions))
