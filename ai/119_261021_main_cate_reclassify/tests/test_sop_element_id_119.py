"""已填欄位回傳 SOP 要素編號（次案類編號-題號）。"""

from __future__ import annotations

import unittest

from case_info_119 import CaseInfo119


class SopElementIdTests(unittest.TestCase):
    def test_traffic_accident_injury_cause_is_202_1(self) -> None:
        case = CaseInfo119(
            main_category="救護",
            sub_category="車禍",
            injury_cause="機車追撞",
            incident_description="被車撞到",
            address="板橋區文化路一段1號",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["injury_cause"], {"id": "202-1", "value": "機車追撞"})
        self.assertNotIn("incident_description", ids)
        self.assertNotIn("address", ids)
        self.assertNotIn("patient_count", ids)

    def test_same_label_uses_the_subtype_own_number(self) -> None:
        case = CaseInfo119(
            main_category="救護",
            sub_category="一般受傷",
            injury_cause="跌倒",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["injury_cause"]["id"], "210-1")
        self.assertEqual(ids["injury_cause"]["value"], "跌倒")
        self.assertNotEqual(ids["injury_cause"]["id"], "202-1")

    def test_fire_townhouse_smoke_is_101_4(self) -> None:
        case = CaseInfo119(
            main_category="火警",
            sub_category="透天厝",
            fire_or_smoke="有火有煙",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(
            ids["fire_or_smoke"],
            {"id": "101-4", "value": "有火有煙"},
        )

    def test_unmatched_field_and_summary_omit_the_map(self) -> None:
        case = CaseInfo119(
            main_category="救護",
            sub_category="車禍",
            injury_cause="機車追撞",
            current_condition="現場安全",
        )

        ids = case.to_dict()["sop_element_ids"]
        summary_fields = case.filled_fields_for_summary()

        self.assertNotIn("current_condition", ids)
        self.assertNotIn("sop_element_ids", summary_fields)
        self.assertEqual(summary_fields["injury_cause"], "機車追撞")

    def test_empty_case_has_no_ids(self) -> None:
        self.assertEqual(CaseInfo119().to_dict()["sop_element_ids"], {})


if __name__ == "__main__":
    unittest.main()
