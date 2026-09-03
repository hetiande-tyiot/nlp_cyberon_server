from __future__ import annotations

import unittest
from unittest.mock import patch

from address_mapper_119 import get_location_mapper
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
    include_floor = address_ask_should_include_floor(engine.case.full_caller_text())
    engine._run_address_flow(
        stage_ask="救護_location",
        stage_confirm="救護_location_confirm",
        dispatch_line="已確認地址，救護車已派出了喔。",
        ask_questions=build_address_ask_questions(
            include_floor=include_floor,
            flow="救護",
        ),
    )


class AddressMapperUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        mapper = get_location_mapper()
        if mapper is None:
            raise unittest.SkipTest("三輪地址映射表未能載入")
        cls.mapper = mapper

    def test_district_round_maps_misheard_name(self) -> None:
        self.assertEqual(self.mapper.map_location("三下區"), "三峽區")

    def test_street_round_maps_misheard_name(self) -> None:
        self.assertEqual(self.mapper.map_location("景興街"), "景新街")

    def test_other_round_maps_misheard_name(self) -> None:
        self.assertEqual(self.mapper.map_location("線民大道"), "縣民大道")

    def test_three_rounds_on_full_address(self) -> None:
        self.assertEqual(
            self.mapper.map_location("三下區景興街32號"),
            "三峽區景新街32號",
        )

    def test_already_correct_address_is_unchanged(self) -> None:
        self.assertEqual(
            self.mapper.map_location("板橋區府中路32號"),
            "板橋區府中路32號",
        )


class AddressMapperFlowTests(unittest.TestCase):
    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "三峽分局"),
    )
    def test_misheard_address_is_mapped_before_jurisdiction_check(
        self,
        query,
    ) -> None:
        io = ScriptedIO(["三下區景興街32號", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        query.assert_called_with("三峽區景新街32號")
        self.assertEqual(engine.case.address, "三峽區景新街32號")
        self.assertEqual(engine.case.address_district, "三峽區")
        self.assertEqual(engine.case.address_road, "景新街")
        self.assertEqual(engine.case.address_number, "32號")
        self.assertTrue(engine.case.address_confirmed)
        self.assertIn("確定是三峽區景新街32號這個地址嗎？", io.questions)

    @patch(
        "sop_119_engine.query_jurisdiction",
        side_effect=[
            JurisdictionResult(True, "板橋分局"),
            JurisdictionResult(True, "三峽分局"),
        ],
    )
    def test_confirm_correction_is_mapped_before_recheck(self, query) -> None:
        io = ScriptedIO([
            "板橋區府中路32號",
            "不是，三下區景興街32號",
            "是",
        ])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(query.call_count, 2)
        self.assertEqual(query.call_args_list[0].args[0], "板橋區府中路32號")
        self.assertEqual(query.call_args_list[1].args[0], "三峽區景新街32號")
        self.assertEqual(engine.case.address, "三峽區景新街32號")
        self.assertEqual(engine.case.address_district, "三峽區")
        self.assertEqual(engine.case.address_road, "景新街")
        self.assertTrue(engine.case.address_confirmed)

    def test_normalize_location_fields_maps_components(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.address = "三下區景興街32號"
        engine.case.address_district = "三下區"
        engine.case.address_road = "景興街"

        engine._normalize_location_fields()

        self.assertEqual(engine.case.address, "三峽區景新街32號")
        self.assertEqual(engine.case.address_district, "三峽區")
        self.assertEqual(engine.case.address_road, "景新街")


if __name__ == "__main__":
    unittest.main()
