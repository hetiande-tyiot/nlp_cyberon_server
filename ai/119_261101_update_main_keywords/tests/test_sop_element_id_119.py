"""已填欄位回傳 SOP 要素編號（次案類編號-題號）對抽到的內容，例如 {"202-1": "機車追撞"}。"""

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

        # 只有受傷原因對得上車禍的題目；發生什麼事、地址不在車禍的關鍵要素裡
        self.assertEqual(ids, {"202-1": "機車追撞"})

    def test_same_label_uses_the_subtype_own_number(self) -> None:
        case = CaseInfo119(
            main_category="救護",
            sub_category="一般受傷",
            injury_cause="跌倒",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["210-1"], "跌倒")
        self.assertNotIn("202-1", ids)

    def test_fire_townhouse_smoke_is_101_5(self) -> None:
        case = CaseInfo119(
            main_category="火警",
            sub_category="透天厝",
            fire_or_smoke="有火有煙",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["101-5"], "有火有煙")  # 1013 版透天厝第 5 題：火煙狀況

    def test_yes_no_answers_are_written_as_text(self) -> None:
        case = CaseInfo119(
            main_category="救護",
            sub_category="一般受傷",
            consciousness=True,
            caller_is_patient=False,
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["210-8"], "是")  # 一般受傷第 8 題：意識
        self.assertEqual(ids["210-3"], "否")  # 一般受傷第 3 題：報案人與患者關係

    def test_building_structure_code_is_skipped_for_text_version(self) -> None:
        # building_structure 是派遣卡數字代碼（2＝鐵皮），同一題用文字的 building_construction
        case = CaseInfo119(
            main_category="火警",
            sub_category="透天厝",
            building_structure=2,
            building_construction="鐵皮屋",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["101-13"], "鐵皮屋")  # 1013 版透天厝第 13 題：建物構造

    def test_unmatched_field_and_summary_omit_the_map(self) -> None:
        case = CaseInfo119(
            main_category="救護",
            sub_category="車禍",
            injury_cause="機車追撞",
            current_condition="現場安全",
        )

        ids = case.to_dict()["sop_element_ids"]
        summary_fields = case.filled_fields_for_summary()

        # 目前狀況不是車禍的關鍵要素，不給編號
        self.assertEqual(list(ids), ["202-1"])
        self.assertNotIn("sop_element_ids", summary_fields)
        self.assertEqual(summary_fields["injury_cause"], "機車追撞")

    def test_fire_lists_questions_still_to_ask_as_pending(self) -> None:
        # 住宅、看得到火：非工廠的建築物類型、濃煙顏色、起火樓層要問；工廠才問的不列
        case = CaseInfo119(
            main_category="火警",
            sub_category="透天厝",
            place_usage="住宅",
            fire_or_smoke="有火有煙",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["101-1"], "住宅")
        self.assertEqual(ids["101-2"], "待問")  # 建築物類型（非工廠）：要問，還沒答
        self.assertNotIn("101-3", ids)  # 建築物類型（工廠）：不用問
        self.assertEqual(ids["101-6"], "待問")  # 濃煙顏色：看得到煙才問
        self.assertEqual(ids["101-7"], "待問")  # 起火樓層：非工廠、看得到火才問
        self.assertNotIn("101-8", ids)  # 燃燒物：工廠才問
        self.assertNotIn("101-15", ids)  # 有無爆炸：被動題，沒人講到就不列

    def test_fire_factory_answer_goes_to_factory_question(self) -> None:
        # 同一個欄位有兩題（非工廠、工廠）時，答案放在前置條件成立的那一題
        case = CaseInfo119(
            main_category="火警",
            sub_category="透天厝",
            place_usage="鐵皮工廠",
            building_type="大型違章建築區與傳統市場(含工廠)",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["101-3"], "大型違章建築區與傳統市場(含工廠)")
        self.assertNotIn("101-2", ids)

    def test_fire_conditions_not_met_are_left_out(self) -> None:
        # 垃圾、無火無煙：只有「氣味」要問；濃煙顏色、是否延燒都不列
        case = CaseInfo119(
            main_category="火警",
            sub_category="垃圾",
            fire_or_smoke="無火無煙",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["130-9"], "待問")  # 氣味
        self.assertNotIn("130-7", ids)  # 濃煙顏色
        self.assertNotIn("130-10", ids)  # 是否延燒

    def test_fire_tab_questions_match_case_type_qa_order(self) -> None:
        # 火警的編號用「垂片第幾題」當題號，所以垂片題目要跟 CaseTypeQA.xlsx 一題一題對得上。
        # 對不上代表改了其中一邊沒同步另一邊。
        from fire_tab_map_119 import TAB_QUESTIONS
        from sop_element_id_119 import _XLSX, _SHEET
        from openpyxl import load_workbook

        # 1106 xlsx 起兩邊名稱一致；只剩氣味類型在 CaseTypeQA 寫「氣味」（10/08 統一的名稱）
        unified = {
            "氣味類型": "氣味",
        }
        rows: dict = {}
        sheet = load_workbook(_XLSX, read_only=True)[_SHEET]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            rows.setdefault(row[1], []).append(row[5])  # 次案類 → 關鍵要素（依題號）
        for tab, subtype in (("A", "火警-透天厝"), ("B1", "火警-汽車"),
                             ("B2", "火警-山林田野(平地)"), ("C", "火警-垃圾")):
            with self.subTest(tab=tab):
                expected = [unified.get(q.element, q.element) for q in TAB_QUESTIONS[tab]]
                self.assertEqual(rows[subtype], expected)

    def test_emergency_questions_match_case_type_qa_order(self) -> None:
        # 緊急救援也用「題目表第幾題」當題號，題目表要跟 CaseTypeQA.xlsx 一題一題對得上
        from emergency_tab_map_119 import EMERGENCY_QUESTIONS, TRAPPED_ALIAS
        from sop_element_id_119 import _XLSX, _SHEET
        from openpyxl import load_workbook

        rows: dict = {}
        sheet = load_workbook(_XLSX, read_only=True)[_SHEET]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            rows.setdefault(row[1], []).append(row[5])  # 次案類 → 關鍵要素（依題號）
        for sub, questions in EMERGENCY_QUESTIONS.items():
            if sub == TRAPPED_ALIAS:
                continue
            with self.subTest(sub=sub):
                self.assertEqual(rows[f"緊急救援-{sub}"], [q.element for q in questions])

    def test_emergency_lists_questions_still_to_ask_as_pending(self) -> None:
        # 車禍救助，報案人位置還沒講到（算未提到）：要在現場才問的題目都列「待問」；
        # 意識要等報案身分確定不是本人、患者人數要等確定有人受傷或受困，所以不列
        case = CaseInfo119(
            main_category="緊急救援",
            sub_category="車禍救助",
            crash_vehicles="汽車撞機車",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids, {
            "301-1": "汽車撞機車",
            "301-2": "待問",   # 受傷部位
            "301-3": "待問",   # 傷勢
            "301-4": "待問",   # 人員受困
            "301-6": "待問",   # 報案身分
            "301-9": "待問",   # 火煙狀況
            "301-10": "待問",  # 交通影響
        })

    def test_emergency_caller_far_away_skips_on_scene_questions(self) -> None:
        case = CaseInfo119(
            main_category="緊急救援",
            sub_category="車禍救助",
            crash_vehicles="汽車撞機車",
            caller_relation="路過",
            caller_location="在遠處",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids, {
            "301-1": "汽車撞機車",
            "301-6": "路過",
            "301-10": "待問",
            "301-11": "在遠處",
        })

    def test_empty_case_has_no_ids(self) -> None:
        self.assertEqual(CaseInfo119().to_dict()["sop_element_ids"], {})


if __name__ == "__main__":
    unittest.main()
