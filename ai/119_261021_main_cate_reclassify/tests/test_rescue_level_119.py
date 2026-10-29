"""救護的派遣等級（level）：依傷病患人數，2 人以上 → 2，其他（1 人、沒講或看不出人數）→ 1。"""

from __future__ import annotations

import unittest

from case_info_119 import CaseInfo119
from sop_utils_119 import rescue_level


class RescueLevelTests(unittest.TestCase):
    def test_one_person_is_level_1(self) -> None:
        for text in ("1", "一位", "一個", "1人", "差不多一個"):
            self.assertEqual(rescue_level(text), 1, text)

    def test_two_or_more_is_level_2(self) -> None:
        for text in ("2", "3", "兩個", "兩三個", "至少兩三個", "三四個人"):
            self.assertEqual(rescue_level(text), 2, text)

    def test_many_people_without_a_number_is_level_2(self) -> None:
        # 「一群人」若直接解析人數會變成 1，要先認出是很多人
        for text in ("很多人", "幾位", "幾個", "一群人", "好幾個"):
            self.assertEqual(rescue_level(text), 2, text)

    def test_unknown_count_is_level_1(self) -> None:
        for text in (None, "", "0", "有人", "不確定"):
            self.assertEqual(rescue_level(text), 1, text)

    def test_case_json_follows_current_count(self) -> None:
        case = CaseInfo119(main_category="救護", sub_category="車禍", patient_count="兩個")
        self.assertEqual(case.to_dict()["level"], 2)

        # 報案人改口只有一個，等級跟著降
        case.patient_count = "一個"
        self.assertEqual(case.to_dict()["level"], 1)

    def test_rescue_without_count_is_1(self) -> None:
        self.assertEqual(CaseInfo119(main_category="救護").to_dict()["level"], 1)

    def test_fire_case_is_not_affected(self) -> None:
        case = CaseInfo119(main_category="火警", sub_category="集合住宅", level=2, patient_count="1")
        self.assertEqual(case.to_dict()["level"], 2)


if __name__ == "__main__":
    unittest.main()
