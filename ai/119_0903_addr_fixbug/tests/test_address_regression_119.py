"""地址抽取／覆寫的事故迴歸測試。

事故一（2026-09-02 13:37）：「欸我住在那個辦土城區中央路3段61巷2號4樓」，
行政區被抽成「個辦土城區」，拼出的地址送 addrCheck 必然查無，
有效地址被要求重報，最終降級為轉真人。

事故二（2026-09-04 09:45）：孕婦急產案，救護車已派出後，
報案人回答「在哪裡產檢？」說「國泰醫院」，
`_apply_location_rules` 無條件把 address 覆寫成醫院名，派遣地址錯誤。
"""

from __future__ import annotations

import unittest

from location_validation_119 import (
    DEFAULT_ADDRCHECK_FAILURE_TEXT,
    addrcheck_failure_reason,
)
from address_mapper_119 import get_location_mapper
from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import (
    build_street_address,
    extract_address_district,
    extract_address_road,
    extract_street_address_components,
    looks_like_pregnancy_count,
)


class SilentIO(DialogueIO):
    def say(self, text: str) -> None:
        pass

    def hear_text(self) -> str:
        raise AssertionError("本測試不應觸發提問")


class DistrictExtractionTests(unittest.TestCase):
    def test_spoken_filler_before_district_is_dropped(self) -> None:
        self.assertEqual(
            extract_address_district("欸我住在那個辦土城區中央路3段61巷2號4樓"),
            "土城區",
        )

    def test_district_ignores_leading_noise(self) -> None:
        cases = {
            "呃我在中和區景平路100號": "中和區",
            "嗯那個板橋區文化路一段10號": "板橋區",
            "新北市板橋區大華街2號4樓": "板橋區",
            "就是三峽區大學路1號": "三峽區",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_address_district(text), expected)

    def test_district_outside_whitelist_falls_back_to_regex(self) -> None:
        self.assertEqual(
            extract_address_district("台中市西屯區台灣大道300號"), "西屯區"
        )

    def test_rebuilt_address_has_no_filler(self) -> None:
        text = "欸我住在那個辦土城區中央路3段61巷2號4樓"
        parts = extract_street_address_components(text)
        self.assertEqual(
            build_street_address(
                parts.get("address_district"),
                parts.get("address_road"),
                parts.get("address_number"),
                existing=text,
            ),
            "土城區中央路3段61巷2號4樓",
        )


class RoadExtractionTests(unittest.TestCase):
    def test_filler_before_road_is_dropped(self) -> None:
        cases = {
            "嗯，那個亞洲路3號2樓": "亞洲路",
            "土城區那個亞洲路3號2樓": "亞洲路",
            "就是中山北路二段5號": "中山北路二段",
            "我家在文化路一段10號": "文化路一段",
            "位於中正路100號": "中正路",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_address_road(text), expected)

    def test_stripping_never_produces_invalid_road(self) -> None:
        """剝到剩「路」「大道」等非法路名時必須保留原值。"""
        for text in ("那個路口", "那個大道3號"):
            with self.subTest(text=text):
                road = extract_address_road(text)
                self.assertTrue(road and len(road) > 1)


class AddressLockTests(unittest.TestCase):
    def _engine_with_settled_address(self) -> SopEngine119:
        engine = SopEngine119(SilentIO())
        engine.case.address = "土城區亞洲路3號2樓"
        engine.case.location_type = "address"
        engine.case.address_district = "土城區"
        engine.case.address_road = "亞洲路"
        engine.case.address_number = "3號"
        return engine

    def test_landmark_cannot_overwrite_after_address_flow(self) -> None:
        engine = self._engine_with_settled_address()
        engine._address_locked = True
        engine._apply_location_rules("國泰醫院")
        self.assertEqual(engine.case.address, "土城區亞洲路3號2樓")
        self.assertEqual(engine.case.location_type, "address")

    def test_landmark_still_applies_during_address_flow(self) -> None:
        """流程進行中行為不變，報案人仍可把地點改成地標。"""
        engine = self._engine_with_settled_address()
        engine._address_locked = False
        engine._apply_location_rules("國泰醫院")
        self.assertEqual(engine.case.address, "國泰醫院")
        self.assertEqual(engine.case.location_type, "landmark")

    def test_lock_still_allows_backfill_when_no_address(self) -> None:
        """地址抽取失敗的案件，上鎖後仍要能從後續對話補到地點。"""
        engine = SopEngine119(SilentIO())
        engine._address_locked = True
        engine._apply_location_rules("國泰醫院")
        self.assertEqual(engine.case.address, "國泰醫院")
        self.assertEqual(engine.case.location_type, "landmark")

    def test_address_flow_sets_lock(self) -> None:
        """內層任何 return 路徑離開後都必須上鎖。"""
        engine = SopEngine119(SilentIO())
        self.assertFalse(engine._address_locked)

        def boom(**_kwargs):
            raise RuntimeError("內層中斷")

        engine._run_address_flow_inner = boom
        with self.assertRaises(RuntimeError):
            engine._run_address_flow(
                stage_ask="x",
                stage_confirm="y",
                dispatch_line="z",
                ask_questions=("問地址？",),
            )
        self.assertTrue(engine._address_locked)


class AddrcheckReasonTests(unittest.TestCase):
    def test_known_reasons_map_to_readable_text(self) -> None:
        self.assertEqual(addrcheck_failure_reason("road_only"), "查無此門牌")
        self.assertEqual(addrcheck_failure_reason("not_found"), "查無此路段")

    def test_unknown_reason_uses_default(self) -> None:
        for value in (None, "", "brand_new_reason"):
            with self.subTest(value=value):
                self.assertEqual(
                    addrcheck_failure_reason(value),
                    DEFAULT_ADDRCHECK_FAILURE_TEXT,
                )

    def test_no_reason_text_mentions_jurisdiction(self) -> None:
        """119 走 addrCheck，不查管轄分局，訊息不該再提管轄單位。"""
        for text in (
            DEFAULT_ADDRCHECK_FAILURE_TEXT,
            addrcheck_failure_reason("road_only"),
            addrcheck_failure_reason("not_found"),
        ):
            with self.subTest(text=text):
                self.assertNotIn("管轄", text)


if __name__ == "__main__":
    unittest.main()


class NonDistrictWordTests(unittest.TestCase):
    """STT 誤聽產生的「不分區」等詞不可當成行政區。

    事故（2026-09-04 09:45）：報案人被問「請告訴我是那一區？」，
    STT 聽成「不分區」，regex 退路把它當區名 → 組出「不分區亞洲路3號」
    → addrCheck 必然查無 → 報案人被要求整段重報。
    """

    def test_non_district_words_are_rejected(self) -> None:
        for text in ("不分區", "不分區。", "學區", "社區", "工業區", "轄區"):
            with self.subTest(text=text):
                self.assertIsNone(extract_address_district(text))

    def test_non_district_word_in_sentence(self) -> None:
        self.assertIsNone(extract_address_district("不分區亞洲路3號2樓"))

    def test_real_districts_still_extracted(self) -> None:
        self.assertEqual(extract_address_district("土城區亞洲路3號"), "土城區")


class DistrictFuzzyGuessTests(unittest.TestCase):
    """行政區音近比對不得靜默改寫地址。

    原本 _fuzzy_match_district_by_tl 無門檻（best_score 由 -1.0 起跳），
    任何輸入都必定回傳某一區：「不分區」曾被比成「瑞芳區」。
    """

    def setUp(self) -> None:
        self.mapper = get_location_mapper()
        if self.mapper is None:
            self.skipTest("地址 mapper 未載入")

    def test_low_similarity_is_not_guessed(self) -> None:
        for text in ("不分區亞洲路3號2樓", "沒有區中山路1號"):
            with self.subTest(text=text):
                mapped, guess = self.mapper.map_location_detail(text)
                self.assertEqual(mapped, text)
                self.assertIsNone(guess)

    def test_guess_is_reported_not_silent(self) -> None:
        mapped, guess = self.mapper.map_location_detail("土成區中央路3段61巷2號")
        self.assertEqual(mapped, "土城區中央路3段61巷2號")
        self.assertEqual(guess, ("土成區", "土城區"))

    def test_exact_district_is_not_a_guess(self) -> None:
        _mapped, guess = self.mapper.map_location_detail("土城區亞洲路3號")
        self.assertIsNone(guess)


class DistrictGuessRevertTests(unittest.TestCase):
    def _engine(self) -> SopEngine119:
        engine = SopEngine119(SilentIO())
        engine.case.address = "土成區中央路3段61巷2號"
        engine.case.address_district = "土成區"
        engine._normalize_location_fields()
        return engine

    def test_guess_recorded_on_normalize(self) -> None:
        engine = self._engine()
        if engine._district_guess is None:
            self.skipTest("地址 mapper 未載入")
        self.assertEqual(engine.case.address_district, "土城區")
        self.assertEqual(engine._district_guess, ("土成區", "土城區"))

    def test_unconfirmed_guess_reverted_on_failure(self) -> None:
        """沒走完覆誦就失敗 → 猜測不得留在 case 裡誤導真人。"""
        engine = self._engine()
        if engine._district_guess is None:
            self.skipTest("地址 mapper 未載入")
        engine._mark_address_failure("地址查無")
        self.assertEqual(engine.case.address, "土成區中央路3段61巷2號")
        self.assertEqual(engine.case.address_district, "土成區")
        self.assertIsNone(engine._district_guess)


class PatientCountTests(unittest.TestCase):
    """胎數不是傷病患人數。

    事故（2026-09-04 09:45）：問「單胞胎還是雙胞胎？」答「三胞胎」，
    patient_count 被填成「三胞胎」（該通根本沒問過傷患人數）。
    """

    def test_pregnancy_counts_detected(self) -> None:
        for value in ("三胞胎", "雙胞胎", "單胞胎", "龍鳳胎", "雙胎"):
            with self.subTest(value=value):
                self.assertTrue(looks_like_pregnancy_count(value))

    def test_real_counts_pass(self) -> None:
        for value in ("1", "一個人", "兩位", "3人", None, ""):
            with self.subTest(value=value):
                self.assertFalse(looks_like_pregnancy_count(value))

    def test_engine_rejects_pregnancy_count(self) -> None:
        engine = SopEngine119(SilentIO())
        engine.case.main_category = "救護"
        engine._apply_extracted_fields({"patient_count": "三胞胎"})
        self.assertIsNone(engine.case.patient_count)

    def test_engine_accepts_real_count(self) -> None:
        engine = SopEngine119(SilentIO())
        engine.case.main_category = "救護"
        engine._apply_extracted_fields({"patient_count": "1"})
        self.assertEqual(engine.case.patient_count, "1")
