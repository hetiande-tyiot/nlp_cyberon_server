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
    @patch("sop_119_engine.query_jurisdiction")
    def test_street_mapping_applied_only_after_api_miss(self, query) -> None:
        """2026-09-04 起街路映射延後：先拿報案人原話問 addrCheck，查無才套表。

        map_street.json 是 vendor 用臺語音近生成的，生成時沒排除「變體本身
        已是另一條真實路名」，實測 23 條會把講對的路改掉
        （重陽路→三和路、中山北路→中正北路…）。行政區映射不受影響。
        """
        query.side_effect = [
            JurisdictionResult(False, api_reason="not_found"),  # 原話：景興街
            JurisdictionResult(True, "三峽分局"),                # 套表後：景新街
        ]
        io = ScriptedIO(["三下區景興街32號", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        # 第一次查的是原話（區已映射、街未映射）
        self.assertEqual(query.call_args_list[0].args[0], "三峽區景興街32號")
        # 查無之後才套街路映射表重查
        self.assertEqual(query.call_args_list[1].args[0], "三峽區景新街32號")
        self.assertEqual(engine.case.address, "三峽區景新街32號")
        self.assertEqual(engine.case.address_road, "景新街")
        self.assertTrue(engine.case.address_confirmed)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "三峽分局"),
    )
    def test_correct_road_is_never_touched_by_mapping(self, query) -> None:
        """報案人講對的路名，addrCheck 查得到就不該讓映射表插手。"""
        io = ScriptedIO(["三下區景興街32號", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(query.call_count, 1)
        self.assertEqual(engine.case.address, "三峽區景興街32號")
        self.assertEqual(engine.case.address_road, "景興街")
        # 行政區映射不延後，「三下區」仍要修成「三峽區」
        self.assertEqual(engine.case.address_district, "三峽區")

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "三峽分局"),
    )
    def test_confirm_correction_is_revalidated(self, query) -> None:
        """覆誦時改報的地址要重新驗證（行政區映射照樣先套用）。"""
        io = ScriptedIO([
            "板橋區府中路32號",
            "不是，三下區景興街32號",
            "是",
        ])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertGreaterEqual(query.call_count, 2)
        self.assertEqual(query.call_args_list[0].args[0], "板橋區府中路32號")
        self.assertEqual(engine.case.address_district, "三峽區")
        self.assertIn("景", engine.case.address_road or "")

    def test_normalize_location_fields_maps_components(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.address = "三下區景興街32號"
        engine.case.address_district = "三下區"
        engine.case.address_road = "景興街"

        # 預設不套街路映射（延後到 addrCheck 查無才啟用）
        engine._normalize_location_fields()
        self.assertEqual(engine.case.address_district, "三峽區")
        self.assertEqual(engine.case.address_road, "景興街")

        # 明確要求時才套用
        engine._normalize_location_fields(include_street=True)
        self.assertEqual(engine.case.address, "三峽區景新街32號")
        self.assertEqual(engine.case.address_road, "景新街")


if __name__ == "__main__":
    unittest.main()
