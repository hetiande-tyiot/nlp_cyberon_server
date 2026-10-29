from __future__ import annotations

import unittest
from unittest.mock import patch

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


class IncrementalAddressExtractor:
    def __init__(self) -> None:
        self.component_calls: list[tuple[str, str | None]] = []

    def extract_general_fields(
        self,
        caller_text: str,
        question: str | None = None,
        *,
        main_category: str | None = None,
        call_type: str | None = None,
    ) -> dict:
        mapping = {
            "板橋區": {
                "address": "板橋區",
                "location_type": "address",
                "address_district": "板橋區",
            },
            "府中路": {
                "address": "府中路",
                "address_road": "府中路",
            },
            "32號": {
                "address": "32號",
                "address_number": "32號",
            },
        }
        return mapping.get(caller_text, {})

    def extract_address(
        self,
        caller_text: str,
        use_question: bool = False,
        include_floor: bool = True,
    ) -> dict:
        return {"address": None}

    def extract_address_components(
        self,
        caller_text: str,
        *,
        current_address: str | None = None,
    ) -> dict:
        self.component_calls.append((caller_text, current_address))
        mapping = {
            "板橋區": {"address_district": "板橋區"},
            "府中路": {"address_road": "府中路"},
            "32號": {"address_number": "32號"},
        }
        return {
            "address": None,
            "address_district": None,
            "address_road": None,
            "address_number": None,
            **mapping.get(caller_text, {}),
        }

    def generate_summary(self, transcript_texts: list[str], filled_fields: dict) -> str:
        return "地址增量測試摘要"


def run_address_flow(
    engine: SopEngine119,
    *,
    include_floor: bool | None = None,
) -> None:
    if include_floor is None:
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


class AddressFloorQuestionTests(unittest.TestCase):
    def test_build_questions_uses_ji_lou(self) -> None:
        questions = build_address_ask_questions(include_floor=True, flow="救護")
        self.assertEqual(questions[0], "請先告訴我地址？幾樓？")
        self.assertEqual(questions[1], "請問事發地址在哪裡？幾樓？")
        self.assertNotIn("樓層", questions[0])

    def test_build_questions_without_floor(self) -> None:
        questions = build_address_ask_questions(include_floor=False, flow="救護")
        self.assertEqual(questions[0], "請先告訴我地址？")
        self.assertEqual(questions[1], "請問事發地址在哪裡？")

    def test_should_skip_floor_for_car_accident(self) -> None:
        self.assertFalse(address_ask_should_include_floor("救護車！這裡發生車禍"))

    def test_should_skip_floor_for_road_collapse(self) -> None:
        self.assertFalse(address_ask_should_include_floor("有人倒臥路邊"))
        self.assertFalse(address_ask_should_include_floor("路邊有人倒了"))

    def test_should_include_floor_for_general_illness(self) -> None:
        self.assertTrue(address_ask_should_include_floor("我先生心臟不舒服"))

    def test_should_skip_floor_for_outdoor_landmark(self) -> None:
        # 夜市/市場/攤販/廣場/公園等露天地標 → 不問樓層（見 a2766f5f）
        for txt in ("我在南亞夜市這邊", "夜市攤販失火了", "市場旁邊起火",
                    "路邊攤起火", "公園裡有人上吊", "廣場那邊冒煙"):
            with self.subTest(txt=txt):
                self.assertFalse(address_ask_should_include_floor(txt))

    def test_still_ask_floor_for_ordinary_building_address(self) -> None:
        self.assertTrue(address_ask_should_include_floor("板橋區文化路一段100號"))

    def test_street_name_guard_still_asks_floor(self) -> None:
        # 公園路/市場路/廣場街 是常見路名 → 屬正常門牌地址，仍要問樓層（路名防呆）
        for txt in ("公園路100號3樓", "市場路5號", "中正區廣場街12號", "市場街8號"):
            with self.subTest(txt=txt):
                self.assertTrue(address_ask_should_include_floor(txt))

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_car_accident_first_address_question_omits_floor(self, _query) -> None:
        io = ScriptedIO(["板橋區府中路32號", "是"])
        engine = SopEngine119(io=io)
        engine.case.transcript = [
            {"role": "assistant", "text": "119 您好，請問是火災還是救護"},
            {"role": "caller", "text": "救護車！這裡發生車禍"},
        ]
        run_address_flow(engine)
        self.assertEqual(io.questions[0], "請先告訴我地址？")
        self.assertNotIn("幾樓", io.questions[0])

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_night_market_first_address_question_omits_floor(self, _query) -> None:
        # 開場即提夜市 → 首次地址問句不帶「幾樓」（夜市是露天地標）
        io = ScriptedIO(["南亞夜市這邊", "是"])
        engine = SopEngine119(io=io)
        engine.case.transcript = [
            {"role": "assistant", "text": "119 您好，請問是火災還是救護"},
            {"role": "caller", "text": "火災！南亞夜市這邊有攤販失火"},
        ]
        run_address_flow(engine)
        self.assertEqual(io.questions[0], "請先告訴我地址？")
        self.assertNotIn("幾樓", io.questions[0])

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_general_case_first_address_question_includes_ji_lou(self, _query) -> None:
        io = ScriptedIO(["板橋區府中路32號", "是"])
        engine = SopEngine119(io=io)
        engine.case.transcript = [
            {"role": "assistant", "text": "119 您好，請問是火災還是救護"},
            {"role": "caller", "text": "救護車！我先生心臟不舒服"},
        ]
        run_address_flow(engine)
        self.assertEqual(io.questions[0], "請先告訴我地址？幾樓？")


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
        self.assertIn("請問是哪一區？", io.questions)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_missing_road_is_reasked_and_merged(self, _query) -> None:
        io = ScriptedIO(["板橋區32號", "府中路", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.address, "板橋區府中路32號")
        self.assertEqual(engine.case.address_road, "府中路")
        self.assertIn("請問是什麼路？", io.questions)
        self.assertTrue(engine.case.address_confirmed)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_missing_number_is_reasked_and_merged(self, _query) -> None:
        io = ScriptedIO(["板橋區府中路", "32號", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.address, "板橋區府中路32號")
        self.assertEqual(engine.case.address_number, "32號")
        self.assertIn("請問是幾號？", io.questions)
        self.assertTrue(engine.case.address_confirmed)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_address_components_accumulate_across_turns(self, _query) -> None:
        io = ScriptedIO(["板橋區", "府中路", "32號", "是"])
        llm = IncrementalAddressExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]

        run_address_flow(engine)

        self.assertEqual(engine.case.address, "板橋區府中路32號")
        self.assertEqual(engine.case.address_district, "板橋區")
        self.assertEqual(engine.case.address_road, "府中路")
        self.assertEqual(engine.case.address_number, "32號")
        self.assertEqual(
            [text for text, _current in llm.component_calls],
            ["板橋區", "府中路", "32號", "是"],
        )

    def test_each_missing_component_reasks_twice_then_continues(self) -> None:
        cases = (
            ("district", "府中路32號", "請問是哪一區？"),
            ("road", "板橋區32號", "請問是什麼路？"),
            ("number", "板橋區府中路", "請問是幾號？"),
        )
        for name, initial_address, expected_question in cases:
            with self.subTest(component=name):
                io = ScriptedIO([
                    initial_address,
                    "不知道",
                    "還是不知道",
                ])
                engine = SopEngine119(io=io)

                run_address_flow(engine)

                self.assertEqual(io.questions.count(expected_question), 2)
                self.assertFalse(engine.case.address_confirmed)
                self.assertEqual(engine.case.ImportantCase, 1)
                self.assertIn("地址搜尋失敗", engine.case.ImportantTag)

    @patch(
        "sop_119_engine.query_jurisdiction",
        side_effect=[
            JurisdictionResult(False),
            JurisdictionResult(True, "中和分局"),
        ],
    )
    def test_full_reask_replaces_old_address_components(self, query) -> None:
        io = ScriptedIO([
            "新北市板橋區府中路32號",
            "新北市中和區景平路100號",
            "是",
        ])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(query.call_count, 2)
        self.assertEqual(engine.case.address, "新北市中和區景平路100號")
        self.assertEqual(engine.case.address_district, "中和區")
        self.assertEqual(engine.case.address_road, "景平路")
        self.assertEqual(engine.case.address_number, "100號")

    def test_intersection_reasks_for_second_road(self) -> None:
        io = ScriptedIO(["板橋區仁化街路口", "文化路", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "intersection")
        self.assertEqual(engine.case.intersection_road1, "仁化街")
        self.assertEqual(engine.case.intersection_road2, "文化路")
        self.assertEqual(engine.case.address, "板橋區仁化街與文化路路口")
        self.assertTrue(engine.case.address_confirmed)

    @patch(
        "sop_119_engine.verify_address_detail",
        return_value=(True, "地址有效：國道三號北向32.5公里處", "valid"),
    )
    def test_highway_reasks_for_name_direction_and_kilometer(self, _verify) -> None:
        # 需要 mock：highway 分支會打 addrCheck。
        # 2026-09-04 前這個測試不 mock 也會過，是歪打正著——map_street.json 把
        # 「高速公路」映射成「復興路」，害它被判成 address 型態、繞過 highway
        # 驗證。街路映射延後後才走上正確分支。
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

    @patch(
        "sop_119_engine.verify_address_detail",
        return_value=(True, "地標比對成功：地標：大觀市場 → 新北市板橋區大觀市場", "valid"),
    )
    def test_landmark_uses_excel_validation(self, _validate) -> None:
        # 精確比對（hint 不含「（模糊比對）」）不該多問確認。
        io = ScriptedIO(["板橋大觀市場旁邊", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "landmark")
        self.assertEqual(engine.case.address_validation_status, "valid")

    @patch(
        "sop_119_engine.verify_address_detail",
        return_value=(True, "地標比對成功：地標：頂埔站 → 新北市土城區頂埔站", "valid"),
    )
    def test_mrt_uses_station_csv_validation(self, _validate) -> None:
        io = ScriptedIO(["捷運頂埔站出口1", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.location_type, "mrt")
        self.assertEqual(engine.case.address_validation_status, "valid")

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(False),
    )
    def test_invalid_api_result_reasks_once_then_marks_and_continues(self, query) -> None:
        # 2026-09-04 起 invalid 會走 hint 導向補問與引導式，驗證次數不再固定為 2；
        # 重點是最終仍收斂到「標記失敗並繼續流程」，且提問受總預算約束。
        io = ScriptedIO([
            "新北市新店區中央路133巷1號",
            "新北市新店區中央路9999號",
        ] + ["不知道"] * 12)
        engine = SopEngine119(io=io)
        engine.case.ImportantTag = ["地址搜尋失敗"]

        run_address_flow(engine)

        self.assertGreaterEqual(query.call_count, 2)
        self.assertLessEqual(
            engine._address_asks_used, engine._ADDRESS_ASK_BUDGET
        )
        self.assertTrue(engine.case.address_suspect_error)
        self.assertFalse(engine.case.address_confirmed)
        self.assertEqual(engine.case.address_validation_status, "invalid")
        self.assertEqual(engine.case.ImportantCase, 1)
        self.assertEqual(engine.case.ImportantTag, ["地址搜尋失敗"])
        # 回答刻意多備緩衝，流程應在預算內自行收斂，不必把回答用完。
        self.assertTrue(io.answers)

    @patch(
        "sop_119_engine.query_jurisdiction",
        side_effect=[
            JurisdictionResult(None, error="timeout"),
            JurisdictionResult(None, error="timeout"),
        ],
    )
    def test_api_error_reasks_once_then_marks_and_continues(self, query) -> None:
        io = ScriptedIO([
            "新北市新店區中央路133巷1號",
            "新北市新店區中央路133巷1號",
        ])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(query.call_count, 2)
        self.assertEqual(engine.case.address_validation_status, "error")
        self.assertTrue(engine.case.address_suspect_error)
        self.assertEqual(engine.case.ImportantCase, 1)
        self.assertIn("地址搜尋失敗", engine.case.ImportantTag)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "新店分局"),
    )
    def test_confirmation_failure_marks_and_continues(self, _query) -> None:
        io = ScriptedIO([
            "新北市新店區中央路133巷1號",
            "不知道",
            "還是不知道",
        ])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertIs(engine.case.address_confirmed, False)
        self.assertTrue(engine.case.address_suspect_error)
        self.assertEqual(engine.case.ImportantCase, 1)
        # 2026-09-04 起「API 查無」與「報案人沒明確確認」分開標記：
        # 這裡 API 回 valid，只是覆誦沒得到確認，標「地址未確認」而非
        # 「地址搜尋失敗」，免得受理員誤以為地址查不到。
        self.assertIn("地址未確認", engine.case.ImportantTag)
        self.assertNotIn("地址搜尋失敗", engine.case.ImportantTag)
        self.assertEqual(engine.case.address_validation_status, "valid")

    def test_all_main_flows_continue_after_address_failure(self) -> None:
        class ReachedNextStage(Exception):
            pass

        def mark_address_failure(engine: SopEngine119):
            def side_effect(**_kwargs) -> None:
                engine._mark_address_failure("測試地址搜尋失敗")

            return side_effect

        flow_cases = (
            ("救護", "_run_救護", "_do_sub_classify"),
            ("火警", "_run_火警", "handlers.火警通用.HuoJingGenericHandler.run_generic_flow"),
            (
                "緊急救援",
                "_run_緊急救援",
                "handlers.緊急救援通用.JinJiJiuYuanGenericHandler.run_generic_flow",
            ),
        )

        for name, flow_method, next_stage in flow_cases:
            with self.subTest(flow=name):
                engine = SopEngine119(io=ScriptedIO([]))
                with patch.object(
                    engine,
                    "_run_address_flow",
                    side_effect=mark_address_failure(engine),
                ):
                    if next_stage == "_do_sub_classify":
                        next_stage_patch = patch.object(
                            engine,
                            next_stage,
                            side_effect=ReachedNextStage,
                        )
                    else:
                        next_stage_patch = patch(
                            next_stage,
                            side_effect=ReachedNextStage,
                        )
                    with next_stage_patch:
                        with self.assertRaises(ReachedNextStage):
                            getattr(engine, flow_method)()

                self.assertEqual(engine.case.ImportantCase, 1)
                self.assertIn("地址搜尋失敗", engine.case.ImportantTag)


if __name__ == "__main__":
    unittest.main()
