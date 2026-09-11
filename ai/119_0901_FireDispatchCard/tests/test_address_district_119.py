"""行政區抽取與 addrCheck 失敗說明的迴歸測試。

來源事故：2026-09-02 13:37 通報「欸我住在那個辦土城區中央路3段61巷2號4樓」，
行政區被抽成「個辦土城區」，拼出的地址送 addrCheck 必然查無，
導致有效地址被要求重報並降級為轉真人。
"""

from __future__ import annotations

import unittest

from location_validation_119 import (
    DEFAULT_ADDRCHECK_FAILURE_TEXT,
    addrcheck_failure_reason,
)
from sop_utils_119 import (
    build_street_address,
    extract_address_district,
    extract_street_address_components,
)


class AddressDistrictTests(unittest.TestCase):
    def test_spoken_filler_before_district_is_dropped(self) -> None:
        self.assertEqual(
            extract_address_district("欸我住在那個辦土城區中央路3段61巷2號4樓"),
            "土城區",
        )

    def test_district_extraction_ignores_leading_noise(self) -> None:
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
            extract_address_district("台中市西屯區台灣大道300號"),
            "西屯區",
        )

    def test_rebuilt_address_has_no_filler(self) -> None:
        text = "欸我住在那個辦土城區中央路3段61巷2號4樓"
        parts = extract_street_address_components(text)
        rebuilt = build_street_address(
            parts.get("address_district"),
            parts.get("address_road"),
            parts.get("address_number"),
            existing=text,
        )
        self.assertEqual(rebuilt, "土城區中央路3段61巷2號4樓")


class AddrcheckFailureReasonTests(unittest.TestCase):
    def test_known_reasons_map_to_readable_text(self) -> None:
        self.assertEqual(addrcheck_failure_reason("road_only"), "查無此門牌")
        self.assertEqual(addrcheck_failure_reason("not_found"), "查無此路段")

    def test_unknown_reason_uses_default_text(self) -> None:
        for value in (None, "", "something_new"):
            with self.subTest(value=value):
                self.assertEqual(
                    addrcheck_failure_reason(value),
                    DEFAULT_ADDRCHECK_FAILURE_TEXT,
                )

    def test_default_text_no_longer_mentions_jurisdiction(self) -> None:
        texts = [
            DEFAULT_ADDRCHECK_FAILURE_TEXT,
            addrcheck_failure_reason("road_only"),
            addrcheck_failure_reason("not_found"),
        ]
        for text in texts:
            with self.subTest(text=text):
                self.assertNotIn("管轄單位", text)


if __name__ == "__main__":
    unittest.main()
