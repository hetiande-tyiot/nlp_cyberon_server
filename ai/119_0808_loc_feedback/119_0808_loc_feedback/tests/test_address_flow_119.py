from __future__ import annotations

import unittest
from unittest.mock import patch

from location_validation_119 import JurisdictionResult
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError


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
        ask_questions=(
            "請先告訴我地址？樓層？",
            "請問事發地址在哪裡？樓層？",
        ),
    )


class AddressFlowTests(unittest.TestCase):
    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_missing_district_is_merged_then_validated(self, _query) -> None:
        io = ScriptedIO(["府中路32號", "板橋區", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "address")
        self.assertEqual(engine.case.address, "板橋區府中路32號")
        self.assertEqual(engine.case.address_district, "板橋區")
        self.assertEqual(engine.case.jurisdiction_office, "板橋分局")
        self.assertTrue(engine.case.address_confirmed)
        self.assertIn("請告訴我是那一區？", io.questions)

    def test_intersection_reasks_for_second_road(self) -> None:
        io = ScriptedIO(["板橋區仁化街路口", "文化路", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "intersection")
        self.assertEqual(engine.case.intersection_road1, "仁化街")
        self.assertEqual(engine.case.intersection_road2, "文化路")
        self.assertEqual(engine.case.address, "板橋區仁化街與文化路路口")
        self.assertTrue(engine.case.address_confirmed)

    def test_highway_reasks_for_name_direction_and_kilometer(self) -> None:
        io = ScriptedIO([
            "我在高速公路發生車禍了",
            "國道三號北向32.5公里處",
            "是",
        ])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "highway")
        self.assertEqual(engine.case.highway_name, "國道三號")
        self.assertEqual(engine.case.highway_direction, "北向")
        self.assertEqual(engine.case.highway_kilometer, "32.5")
        self.assertEqual(engine.case.address, "國道三號 北向 32.5公里處")

    @patch("sop_119_engine.validate_landmark", return_value=True)
    def test_landmark_uses_excel_validation(self, _validate) -> None:
        io = ScriptedIO(["板橋大觀市場旁邊", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "landmark")
        self.assertEqual(engine.case.address_validation_status, "valid")

    @patch("sop_119_engine.validate_mrt", return_value=True)
    def test_mrt_uses_station_csv_validation(self, _validate) -> None:
        io = ScriptedIO(["捷運頂埔站出口1", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "mrt")
        self.assertEqual(engine.case.address_validation_status, "valid")

    @patch(
        "sop_119_engine.query_jurisdiction",
        side_effect=[
            JurisdictionResult(False),
            JurisdictionResult(False),
        ],
    )
    def test_invalid_api_result_reasks_once_then_transfers(self, query) -> None:
        io = ScriptedIO([
            "新北市新店區中央路133巷",
            "新北市新店區中央路9999號",
        ])
        engine = SopEngine119(io=io)

        with self.assertRaises(TransferToHumanError):
            run_address_flow(engine)

        self.assertEqual(query.call_count, 2)
        self.assertTrue(engine.case.address_suspect_error)
        self.assertFalse(engine.case.address_confirmed)
        self.assertEqual(engine.case.address_validation_status, "invalid")
        self.assertFalse(io.answers)

    @patch(
        "sop_119_engine.query_jurisdiction",
        side_effect=[
            JurisdictionResult(None, error="timeout"),
            JurisdictionResult(None, error="timeout"),
        ],
    )
    def test_api_error_reasks_once_then_transfers(self, query) -> None:
        io = ScriptedIO([
            "新北市新店區中央路133巷",
            "新北市新店區中央路133巷",
        ])
        engine = SopEngine119(io=io)

        with self.assertRaises(TransferToHumanError):
            run_address_flow(engine)

        self.assertEqual(query.call_count, 2)
        self.assertEqual(engine.case.address_validation_status, "error")
        self.assertTrue(engine.case.address_suspect_error)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "新店分局"),
    )
    def test_confirmation_is_not_forced_true(self, _query) -> None:
        io = ScriptedIO([
            "新北市新店區中央路133巷",
            "不知道",
            "還是不知道",
        ])
        engine = SopEngine119(io=io)

        with self.assertRaises(TransferToHumanError):
            run_address_flow(engine)

        self.assertIs(engine.case.address_confirmed, False)
        self.assertTrue(engine.case.address_suspect_error)


if __name__ == "__main__":
    unittest.main()
