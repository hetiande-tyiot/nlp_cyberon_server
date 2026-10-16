"""
通知（轉報）110 查表規則測試。

規則來源 docs/localprogress/119案件通知110規則.md，
範圍與二元化決定見 docs/localprogress/119通知110對照清單.md。
"""

from __future__ import annotations

import unittest

from fire_tab_map_119 import FIRE_SUBTYPE_BY_NAME
from police_notify_119 import (
    NEED_POLICE_BY_CATEGORY,
    is_mandatory_notify,
    lookup_need_police,
)
from sop_119_engine import DialogueIO, SopEngine119


class ScriptedIO(DialogueIO):
    def say(self, text: str) -> None:
        pass

    def hear_text(self) -> str:
        raise AssertionError("本測試不應讀取輸入")


def _engine(main: str | None = None, sub: str | None = None) -> SopEngine119:
    engine = SopEngine119(io=ScriptedIO())
    engine.case.main_category = main
    engine.case.sub_category = sub
    return engine


class TestLookupTable(unittest.TestCase):
    def test_sop_mandatory_cases_return_true(self) -> None:
        for main, sub in (
            ("火警", "古蹟、文化財"),
            ("火警", "垃圾"),
            ("火警", "電線桿(電纜)"),
            ("火警", "山林田野(平地)"),
            ("火警", "山林田野(山地)"),
            ("救護", "路倒"),
            ("救護", "燒燙傷"),
            ("救護", "精神異常"),
            ("救護", "打架受傷"),
            ("救護", "吞食藥物"),
            ("救護", "割腕"),
            ("救護", "上吊"),
            ("救護", "燒炭"),
            ("救護", "墜落傷"),
            ("緊急救援", "電梯受困"),
            ("緊急救援", "跳水"),
            ("緊急救援", "跳樓"),
            ("緊急救援", "開瓦斯自殺"),
            ("緊急救援", "山難"),
        ):
            with self.subTest(sub=sub):
                self.assertIs(lookup_need_police(main, sub), True)
                self.assertTrue(is_mandatory_notify(main, sub))

    def test_conditional_and_unmentioned_cases_return_false(self) -> None:
        """SOP 的「視情況」與「未提及」一律收斂為不通知（只有要/不要）。"""
        for main, sub in (
            ("火警", "汽車"),
            ("火警", "機車"),
            ("火警", "軌道型交通工具"),
            ("火警", "船舶"),
            ("救護", "急病"),
            ("救護", "孕婦待產"),
            ("救護", "孕婦急產"),
            ("緊急救援", "瓦斯漏氣(建築物)"),
        ):
            with self.subTest(sub=sub):
                self.assertIs(lookup_need_police(main, sub), False)
                self.assertFalse(is_mandatory_notify(main, sub))

    def test_uncovered_labels_return_none(self) -> None:
        """標籤對不上 SOP 案類 → 本表不表意見，回 None。"""
        for main, sub in (
            ("火警", "集合住宅"),       # 火警-建築物：9 對 1，不在範圍
            ("火警", "警報器作響"),     # 規則表無對應案類
            ("救護", "一般受傷"),       # 救護-受傷：需「是否打架造成」子條件
            ("救護", "車禍"),           # 規則只寫「特殊重大車禍」
            ("救護", "其它"),
            ("緊急救援", "車禍救助"),
            ("緊急救援", "其他"),
            ("災害", "地震"),           # 主類別不在範圍（無子分類器）
            ("檢舉投訴", "爆竹煙火"),   # 同上
        ):
            with self.subTest(sub=sub):
                self.assertIsNone(lookup_need_police(main, sub))

    def test_missing_category_returns_none(self) -> None:
        self.assertIsNone(lookup_need_police(None, None))
        self.assertIsNone(lookup_need_police("救護", None))
        self.assertIsNone(lookup_need_police(None, "路倒"))
        self.assertIsNone(lookup_need_police("", ""))

    def test_table_scope_is_locked_down(self) -> None:
        """表的規模固定；要改範圍得先更新對照清單並改這個數字。"""
        mandatory = [k for k, v in NEED_POLICE_BY_CATEGORY.items() if v]
        not_needed = [k for k, v in NEED_POLICE_BY_CATEGORY.items() if not v]
        self.assertEqual(len(mandatory), 19)
        self.assertEqual(len(not_needed), 8)
        self.assertEqual(
            {k[0] for k in NEED_POLICE_BY_CATEGORY},
            {"火警", "救護", "緊急救援"},
        )

    def test_fire_keys_are_real_dispatch_card_subtypes(self) -> None:
        """火警的 sub_category 會被改寫成派遣卡細類名，key 必須用那組名稱。"""
        for main, sub in NEED_POLICE_BY_CATEGORY:
            if main == "火警":
                self.assertIn(sub, FIRE_SUBTYPE_BY_NAME)


class TestEngineApplies(unittest.TestCase):
    def test_mandatory_case_sets_true(self) -> None:
        engine = _engine("救護", "路倒")
        engine._apply_police_notify_rule()
        self.assertIs(engine.case.NeedPolice, True)

    def test_mandatory_case_cannot_be_downgraded_by_caller(self) -> None:
        """SOP 明訂的義務，不因報案人說「不用叫警察」而取消。"""
        engine = _engine("救護", "打架受傷")
        engine._apply_extracted_fields({"NeedPolice": False})
        self.assertIs(engine.case.NeedPolice, True)

    def test_not_needed_case_sets_false_when_caller_silent(self) -> None:
        engine = _engine("救護", "急病")
        engine._apply_police_notify_rule()
        self.assertIs(engine.case.NeedPolice, False)

    def test_caller_request_wins_over_not_needed_case(self) -> None:
        """表說不要、但報案人明確要警察 → 報案人贏。"""
        engine = _engine("救護", "急病")
        engine._apply_extracted_fields({"NeedPolice": True})
        self.assertIs(engine.case.NeedPolice, True)

    def test_uncovered_case_leaves_field_untouched(self) -> None:
        engine = _engine("火警", "集合住宅")
        engine._apply_police_notify_rule()
        self.assertIsNone(engine.case.NeedPolice)

        engine._apply_extracted_fields({"NeedPolice": True})
        self.assertIs(engine.case.NeedPolice, True)

        # 表不表意見時，LLM 的更正照舊生效。
        engine._apply_extracted_fields({"NeedPolice": False})
        self.assertIs(engine.case.NeedPolice, False)

    def test_cross_main_category_drowning_is_covered(self) -> None:
        """規則把溺水歸在救護（必須），程式唯一的落水標籤在緊急救援。"""
        engine = _engine("緊急救援", "跳水")
        engine._apply_police_notify_rule()
        self.assertIs(engine.case.NeedPolice, True)

    def test_recomputes_after_subcategory_change(self) -> None:
        """流程中改派 → 結論跟著重算。"""
        engine = _engine("救護", "急病")
        engine._apply_police_notify_rule()
        self.assertIs(engine.case.NeedPolice, False)

        engine.case.sub_category = "精神異常"
        engine._apply_police_notify_rule()
        self.assertIs(engine.case.NeedPolice, True)

    def test_every_turn_reapplies_the_rule(self) -> None:
        """每輪抽取都會重跑查表，不需要等改派。"""
        engine = _engine("緊急救援", "電梯受困")
        engine._apply_extracted_fields({"ImportantTag": ["救命"]})
        self.assertIs(engine.case.NeedPolice, True)


if __name__ == "__main__":
    unittest.main()
