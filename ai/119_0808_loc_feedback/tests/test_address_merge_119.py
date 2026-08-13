from __future__ import annotations

import unittest

from sop_utils_119 import (
    ensure_city_prefix,
    extract_address_hint,
    has_city_prefix,
    merge_address,
)


class MergeAddressSegmentTests(unittest.TestCase):
    """報警人先報路名、確認環節才補「幾段幾號幾樓」時不可丟失路名。"""

    def test_segment_continuation_keeps_road_name(self) -> None:
        self.assertEqual(
            merge_address("新北市土城區中央路", "2段1號3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_house_number_continuation_keeps_road_and_segment(self) -> None:
        self.assertEqual(
            merge_address("新北市土城區中央路2段", "1號3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_floor_only_continuation(self) -> None:
        self.assertEqual(
            merge_address("新北市土城區中央路2段1號", "3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_repeated_segment_is_not_duplicated(self) -> None:
        self.assertEqual(
            merge_address("新北市土城區中央路2段", "2段1號3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_chinese_numeral_continuation(self) -> None:
        self.assertEqual(
            merge_address("新北市土城區中央路", "二段一號三樓"),
            "新北市土城區中央路二段一號三樓",
        )

    def test_existing_lane_merge_unchanged(self) -> None:
        self.assertEqual(
            merge_address("中和區連城路347巷附近", "連城路347巷1弄2號附近"),
            "中和區連城路347巷1弄2號附近",
        )

    def test_different_road_still_replaces(self) -> None:
        self.assertEqual(
            merge_address("土城區裕民路142號", "永和區永平路148號"),
            "永和區永平路148號",
        )

    def test_landmark_replaced_by_street_address(self) -> None:
        self.assertEqual(
            merge_address("板橋分局後埔所", "民權街二段87號一樓"),
            "民權街二段87號一樓",
        )


class AddressHintSegmentTests(unittest.TestCase):
    """規則備援抽取不可在「段」之前截斷。"""

    def test_hint_keeps_segment_and_floor(self) -> None:
        self.assertEqual(
            extract_address_hint("新北市土城區中央路2段1號3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_hint_keeps_chinese_numeral_segment(self) -> None:
        self.assertEqual(
            extract_address_hint("新北市土城區中央路二段一號三樓"),
            "新北市土城區中央路二段一號三樓",
        )

    def test_hint_with_spoken_prefix(self) -> None:
        self.assertEqual(
            extract_address_hint("我在新北市土城區中央路2段1號3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_hint_without_district(self) -> None:
        self.assertEqual(
            extract_address_hint("中央路2段1號3樓"),
            "中央路2段1號3樓",
        )

    def test_hint_spaced_lane_form_unchanged(self) -> None:
        self.assertEqual(
            extract_address_hint("景興街 210 巷 2 弄 33 號 4 樓"),
            "景興街 210 巷 2 弄 33 號 4 樓",
        )


class CityPrefixTests(unittest.TestCase):
    """未報縣市時預設套用新北市。"""

    def test_prepends_default_city(self) -> None:
        self.assertEqual(
            ensure_city_prefix("土城區中央路2段1號3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_keeps_existing_new_taipei(self) -> None:
        self.assertEqual(
            ensure_city_prefix("新北市土城區中央路2段1號3樓"),
            "新北市土城區中央路2段1號3樓",
        )

    def test_does_not_override_other_city(self) -> None:
        self.assertEqual(
            ensure_city_prefix("台北市中正區忠孝東路一段1號"),
            "台北市中正區忠孝東路一段1號",
        )
        self.assertEqual(
            ensure_city_prefix("桃園市中壢區中大路300號"),
            "桃園市中壢區中大路300號",
        )

    def test_traditional_tai_variant_recognised(self) -> None:
        self.assertTrue(has_city_prefix("臺北市信義區市府路1號"))

    def test_market_word_is_not_a_city(self) -> None:
        self.assertFalse(has_city_prefix("士林夜市"))
        self.assertFalse(has_city_prefix("中央市場旁邊"))

    def test_empty_stays_empty(self) -> None:
        self.assertEqual(ensure_city_prefix(""), "")


if __name__ == "__main__":
    unittest.main()
