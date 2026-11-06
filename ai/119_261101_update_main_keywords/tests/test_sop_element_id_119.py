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
        # 垃圾、無火無煙：只有「氣味類型」要問；濃煙顏色、是否延燒都不列
        case = CaseInfo119(
            main_category="火警",
            sub_category="垃圾",
            fire_or_smoke="無火無煙",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["130-9"], "待問")  # 氣味類型
        self.assertNotIn("130-7", ids)  # 濃煙顏色
        self.assertNotIn("130-10", ids)  # 是否延燒

    def test_question_tables_match_case_type_qa(self) -> None:
        # 編號用「題目表第幾題」當題號，前端再用題號去 CaseTypeQA 查題目名稱，
        # 所以每個次案類的題目表第 N 題，名稱要跟 CaseTypeQA.xlsx 該次案類第 N 題的關鍵要素一樣。
        # 對不上代表改了其中一邊沒同步另一邊。
        from disaster_flow_119 import DISASTER_QUESTIONS
        from emergency_tab_map_119 import EMERGENCY_QUESTIONS
        from ems_tab_map_119 import questions_for_subtype as ems_questions
        from fire_tab_map_119 import TAB_QUESTIONS, tab_for_subtype
        from openpyxl import load_workbook
        from sop_element_id_119 import _SHEET, _XLSX, case_type_key

        rows: dict = {}
        sheet = load_workbook(_XLSX, read_only=True)[_SHEET]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            rows.setdefault(row[1], []).append((row[4], row[5]))  # 次案類 → (題號, 關鍵要素)
        # 緊急救援的程式次案類名稱不一定跟表一樣（卡住夾住在表裡叫「緊急救援-其他」），用程式的對照找
        emergency = {
            case_type_key("緊急救援", sub): questions for sub, questions in EMERGENCY_QUESTIONS.items()
        }
        checked = set()
        for subtype, items in rows.items():
            main, _, sub = subtype.partition("-")
            if main == "火警":
                questions = TAB_QUESTIONS.get(tab_for_subtype(sub) or "", ())
            elif main == "救護" and sub not in ("", "未知"):
                questions = ems_questions(sub)
            elif main == "災害":
                questions = DISASTER_QUESTIONS
            elif main == "緊急救援":
                questions = emergency.get(subtype, ())
            else:
                continue  # 2 救護、救護-未知：次案類還沒定，程式沒有題目表
            with self.subTest(subtype=subtype):
                self.assertTrue(questions, "程式沒有這個次案類的題目表")
                self.assertEqual(
                    items, [(n, q.element) for n, q in enumerate(questions, start=1)],
                )
            checked.add(main)
        self.assertEqual(checked, {"火警", "救護", "災害", "緊急救援"})

    def test_case_type_qa_sql_matches_question_tables(self) -> None:
        # 前端拿到「次案類編號-第N題」後，是用 docs/CaseTypeQA.sql 匯入資料庫的那份表查題目名稱和問句。
        # 所以程式四個案類每個次案類的每一題，SQL 裡都要有同一個編號的一列，而且題目名稱要一樣；
        # SQL 也不能多出程式沒有的題目。對不上代表改了程式題目表或 CaseTypeQA.xlsx，卻沒重新產生 SQL。
        import re
        from pathlib import Path

        from disaster_flow_119 import DISASTER_QUESTIONS
        from emergency_tab_map_119 import EMERGENCY_QUESTIONS
        from ems_tab_map_119 import EMS_QUESTIONS
        from fire_tab_map_119 import FIRE_SUBTYPES, TAB_QUESTIONS, tab_for_subtype
        from sop_element_id_119 import case_type_key, load_element_index

        sql_path = Path(__file__).resolve().parents[3] / "docs" / "CaseTypeQA.sql"
        sql: dict = {}  # 「次案類編號-題號」→ 題目名稱
        pattern = re.compile(r"VALUES \((\d+), \d+, (\d+), N'((?:[^']|'')*)', N'(?:[^']|'')*', \d\);")
        for line in sql_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("INSERT"):
                match = pattern.search(line)
                self.assertIsNotNone(match, f"SQL 這一列格式看不懂：{line}")
                sql[f"{match.group(1)}-{match.group(2)}"] = match.group(3).replace("''", "'")

        # 次案類名稱 → 次案類編號：照程式送編號時的做法，從 CaseTypeQA.xlsx 的對照表取
        case_type_ids = {
            subtype: code.rsplit("-", 1)[0] for (subtype, _), code in load_element_index().items()
        }
        # 每個次案類用的題目表：火警依次案類所屬垂片、救護和緊急救援各自一張、災害所有次案類共用一張
        tables = {}
        for item in FIRE_SUBTYPES:
            tables[case_type_key("火警", item.name)] = TAB_QUESTIONS[tab_for_subtype(item.name)]
        for sub, questions in EMS_QUESTIONS.items():
            tables[case_type_key("救護", sub)] = questions
        for sub, questions in EMERGENCY_QUESTIONS.items():
            tables[case_type_key("緊急救援", sub)] = questions
        for subtype in case_type_ids:
            if subtype.startswith("災害-"):
                tables[subtype] = DISASTER_QUESTIONS

        expected = {}
        for subtype, questions in tables.items():
            with self.subTest(subtype=subtype):
                self.assertIn(subtype, case_type_ids, "CaseTypeQA.xlsx 找不到這個次案類的編號")
                for number, question in enumerate(questions, start=1):
                    expected[f"{case_type_ids[subtype]}-{number}"] = question.element

        for element_id, element in expected.items():
            with self.subTest(element_id=element_id):
                self.assertEqual(sql.get(element_id), element)
        # 2 救護、200 救護-未知：次案類還沒定，程式沒有題目表，SQL 保留原本的內容
        extra = sorted(
            element_id for element_id in sql
            if element_id not in expected and element_id.split("-")[0] not in ("2", "200")
        )
        self.assertEqual(extra, [], "SQL 有程式沒有的題目")

    def test_disaster_lists_questions_still_to_ask_as_pending(self) -> None:
        # 積水剛開始：人員受傷、人員受困、交通影響、報案人位置、報案身分都要問；
        # 受困人數要有人受困才問，火煙狀況只有電線掉落、招牌掉落、電線桿傾倒才問，都不列
        case = CaseInfo119(main_category="災害", sub_category="積水")

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids, {
            "501-1": "待問",  # 人員受傷
            "501-2": "待問",  # 人員受困：跟人員受傷同一句問，但有自己的題號
            "501-4": "待問",  # 交通影響
            "501-6": "待問",  # 報案人位置
            "501-7": "待問",  # 報案身分：跟報案人位置同一句問，但有自己的題號
        })

    def test_disaster_trapped_makes_count_pending(self) -> None:
        case = CaseInfo119(
            main_category="災害",
            sub_category="積水",
            disaster_injury="無人受傷",
            trapped_status="有人受困",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["501-1"], "無人受傷")
        self.assertEqual(ids["501-2"], "有人受困")
        self.assertEqual(ids["501-3"], "待問")  # 受困人數：有人受困才問
        self.assertNotIn("501-5", ids)  # 火煙狀況：積水不問

    def test_disaster_wire_subtype_asks_fire_or_smoke(self) -> None:
        case = CaseInfo119(
            main_category="災害",
            sub_category="電線掉落",
            trapped_status="無人受困",
            caller_location="在現場",
            caller_relation="路過",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids, {
            "511-1": "待問",
            "511-2": "無人受困",
            "511-4": "待問",
            "511-5": "待問",  # 火煙狀況：電線掉落要問
            "511-6": "在現場",
            "511-7": "路過",
        })

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

    def test_emergency_trapped_uses_309(self) -> None:
        # 卡住夾住在 CaseTypeQA 是 309「緊急救援-其他」，第 2 題是卡住物品
        case = CaseInfo119(
            main_category="緊急救援",
            sub_category="其他(卡住夾住)",
            trap_object="機器",
        )

        ids = case.to_dict()["sop_element_ids"]

        self.assertEqual(ids["309-2"], "機器")
        self.assertEqual(ids["309-1"], "待問")  # 卡住部位

    def test_emergency_other_transfers_without_ids(self) -> None:
        # 分類器判出的「其他」轉真人、不問卡住夾住的題目，所以不給編號
        case = CaseInfo119(
            main_category="緊急救援",
            sub_category="其他",
            trap_object="機器",
            caller_relation="家人",
        )

        self.assertEqual(case.to_dict()["sop_element_ids"], {})

    def test_empty_case_has_no_ids(self) -> None:
        self.assertEqual(CaseInfo119().to_dict()["sop_element_ids"], {})


if __name__ == "__main__":
    unittest.main()
