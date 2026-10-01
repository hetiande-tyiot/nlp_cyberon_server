"""
火警欄位抽取「只送這一輪用得到的欄位」的測試。

為什麼：原本每一輪都把四張垂片全部欄位的規則一起送給 LLM（約 4,400 字），
太長可能超過模型上限，超過時火警欄位會一個都抽不到而且沒有錯誤訊息。
現在依目前垂片挑欄位：
  - 已經知道垂片：次案類代碼 + 轉人工欄位 + 這張垂片 xlsx 上的所有欄位
  - 還不知道垂片：次案類代碼 + 轉人工欄位 + 四張垂片共用的欄位
垂片一決定，就把報案人前面說過的話，用這張垂片的欄位再抽一次，只補空白欄位。
"""

from __future__ import annotations

import unittest

from fire_tab_map_119 import (
    FIRE_IDENTITY_FIELDS,
    FIRE_TRANSFER_FIELDS,
    TAB_A,
    TAB_A_QUESTIONS,
    TAB_QUESTIONS,
    fire_fields_to_extract,
)
from handlers.火警通用 import HuoJingGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119

# 0901 以前舊流程留下、已不再抽取的欄位
LEGACY_FIELDS = (
    "fire_trend", "fire_category", "caller_position", "people_trapped", "trapped_count",
    "fire_spread", "building_layout", "factory_scale_type", "factory_people_present",
    "vehicle_occupants", "vehicle_occupant_count", "road_type", "outdoor_fire_type",
    "affected_targets",
)
Q_A = {item.element: item.question for item in TAB_A_QUESTIONS}


class FieldsPerTabTests(unittest.TestCase):

    def test_identity_and_transfer_fields_always_included(self) -> None:
        for tab in (None, *TAB_QUESTIONS):
            with self.subTest(tab=tab):
                fields = fire_fields_to_extract(tab)
                for field in FIRE_IDENTITY_FIELDS + FIRE_TRANSFER_FIELDS:
                    self.assertIn(field, fields)

    def test_tab_fields_come_from_xlsx_question_table(self) -> None:
        for tab, questions in TAB_QUESTIONS.items():
            with self.subTest(tab=tab):
                fields = fire_fields_to_extract(tab)
                for item in questions:
                    if item.field != "sub_category":
                        self.assertIn(item.field, fields)

    def test_building_only_fields_not_sent_before_tab_known(self) -> None:
        fields = fire_fields_to_extract(None)
        self.assertIn("fire_or_smoke", fields)
        self.assertNotIn("fire_floor", fields)
        self.assertNotIn("building_construction", fields)

    def test_other_tab_fields_not_sent(self) -> None:
        fields = fire_fields_to_extract("B1")
        self.assertIn("vehicle_type", fields)
        self.assertNotIn("fire_floor", fields)       # A 專屬
        self.assertNotIn("alarm_status", fields)     # C 專屬

    def test_no_duplicates(self) -> None:
        for tab in (None, *TAB_QUESTIONS):
            fields = fire_fields_to_extract(tab)
            self.assertEqual(len(fields), len(set(fields)))


class ExtractorSendsOnlySelectedFieldsTests(unittest.TestCase):
    """不載入模型：把送給 LLM 的欄位定義與規則攔下來檢查。"""

    def _fire_call(self, tab):
        calls = []
        ext = object.__new__(LLMExtractor119)
        ext.extract_slots = lambda text, schema, rules, **kw: calls.append((schema, rules)) or {}
        ext.extract_general_fields("測試", "測試", main_category="火警", fire_tab=tab)
        return calls[-1]  # 最後一次呼叫是火警欄位那一組

    def test_schema_matches_selected_fields(self) -> None:
        for tab in (None, *TAB_QUESTIONS):
            with self.subTest(tab=tab):
                schema, rules = self._fire_call(tab)
                self.assertEqual(tuple(schema), fire_fields_to_extract(tab))
                for field in schema:
                    self.assertIn(field, rules)

    def test_legacy_fields_no_longer_extracted(self) -> None:
        for tab in (None, *TAB_QUESTIONS):
            schema, rules = self._fire_call(tab)
            for field in LEGACY_FIELDS:
                self.assertNotIn(field, schema)

    def test_prompt_fits_model_limit(self) -> None:
        # 模型上限 4,096 token，其中 512 留給模型回答。
        # 2026-10-01 用真的模型實測：垂片 A 的規則 2,851 字＋報案人 600 字，提示是 2,497 token，
        # 加上回答保留共 3,009 token，還剩約 1,000 token。
        # 上限訂 3,200 字：規則再長一點仍有足夠空間；超過就要先實測 token 再放寬。
        import json
        for tab in (None, *TAB_QUESTIONS):
            with self.subTest(tab=tab):
                schema, rules = self._fire_call(tab)
                total = len(json.dumps(schema, ensure_ascii=False)) + len(rules)
                self.assertLess(total, 3200)


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError(f"測試回答已用盡，最後一句是：{self.messages[-1]}")
        return self.answers.pop(0)


class TabAwareFakeLLM:
    """
    模擬「只抽目前垂片欄位」的 LLM：
    by_tab[(報案人的話, 垂片)] → 抽出的欄位。垂片還不知道時 tab 是 None。
    """

    def __init__(self, by_tab: dict):
        self.by_tab = by_tab
        self.fire_tabs_seen: list = []

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        self.fire_tabs_seen.append(fire_tab)
        return dict(self.by_tab.get((caller_text.strip(), fire_tab), {}))

    def classify_fire_tab(self, caller_text, question=None):
        return None

    def extract_address(self, caller_text, use_question=False, include_floor=True):
        return {}

    def check_fire_trigger_scenarios(self, caller_text, already_triggered):
        return []

    def generate_summary(self, transcript_texts, filled_fields):
        return "火災測試摘要"


class BackfillEarlierAnswersTests(unittest.TestCase):

    def _engine_after_address(self, early_text: str, llm: TabAwareFakeLLM, answers: list[str]):
        """模擬報地址時報案人已經說了 early_text（當時還不知道垂片）。"""
        io = ScriptedIO(answers)
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        engine.case.transcript.append({"role": "caller", "text": early_text})
        engine._extracted_caller_count = 1  # 這一句在報地址時已經抽過了（用共用欄位）
        return engine, io

    def test_floor_said_before_tab_known_is_not_asked_again(self) -> None:
        early = "我家公寓三樓燒起來，火很大"
        llm = TabAwareFakeLLM({
            # 報地址時（垂片還不知道）只抽得到共用欄位與次案類代碼
            (early, None): {"building_type_code": "11",
                            "fire_or_smoke": "有火"},
            # 垂片決定為 A 後補抽：這時才抽得到 A 的起火樓層
            (early, TAB_A): {"fire_floor": "3樓", "fire_or_smoke": "有火"},
        })
        engine, io = self._engine_after_address(early, llm, answers=[])
        engine.case.fire_tab = TAB_A
        engine.case.building_type_code = "11"
        engine.case.fire_or_smoke = "有火"
        engine.case.sub_category = "集合住宅"
        handler = HuoJingGenericHandler()
        handler._resolve_tab(engine)
        handler._backfill_earlier_answers_for_tab(engine)
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.fire_floor, "3樓")
        self.assertIn(TAB_A, llm.fire_tabs_seen)

    def test_backfill_does_not_overwrite_existing_answers(self) -> None:
        early = "我家公寓燒起來"
        llm = TabAwareFakeLLM({
            (early, TAB_A): {"fire_or_smoke": "只有煙", "place_usage": "住家"},
        })
        engine, io = self._engine_after_address(early, llm, answers=[])
        engine.case.fire_tab = TAB_A
        engine.case.fire_or_smoke = "有火"   # 報案人已經回答過
        handler = HuoJingGenericHandler()
        handler._resolve_tab(engine)
        handler._backfill_earlier_answers_for_tab(engine)
        self.assertEqual(engine.case.fire_or_smoke, "有火")   # 沒被蓋掉
        self.assertEqual(engine.case.place_usage, "住家")     # 空白的有補上

    def test_backfill_only_touches_fire_fields(self) -> None:
        early = "我家公寓燒起來"
        llm = TabAwareFakeLLM({
            (early, TAB_A): {"place_usage": "住家", "address": "不該被寫入的地址"},
        })
        engine, io = self._engine_after_address(early, llm, answers=[])
        engine.case.fire_tab = TAB_A
        handler = HuoJingGenericHandler()
        handler._resolve_tab(engine)
        handler._backfill_earlier_answers_for_tab(engine)
        self.assertEqual(engine.case.place_usage, "住家")
        self.assertNotEqual(engine.case.address, "不該被寫入的地址")

    def test_backfill_error_does_not_stop_flow(self) -> None:
        class BrokenLLM(TabAwareFakeLLM):
            def extract_general_fields(self, *args, **kwargs):
                raise RuntimeError("LLM 逾時")

        engine, io = self._engine_after_address("我家公寓燒起來", BrokenLLM({}), answers=[])
        engine.case.fire_tab = TAB_A
        handler = HuoJingGenericHandler()
        handler._resolve_tab(engine)
        handler._backfill_earlier_answers_for_tab(engine)  # 不應拋出錯誤
        self.assertEqual(engine.case.fire_tab, TAB_A)

    def test_full_flow_skips_floor_question_after_backfill(self) -> None:
        early = "我家公寓三樓燒起來，火很大"
        steps = [
            ("住家", {"place_usage": "住家"}),
            ("黑煙", {"smoke_color": "黑色煙"}),
            ("會燒到隔壁", {"spread_status": "極可能或已延燒"}),
            ("人都出來了", {"trapped_status": "無人受困"}),
            ("五層樓", {"building_total_floors": "5層樓"}),
            ("我是住戶", {"caller_role": "住戶(起火戶)"}),
        ]
        by_tab = {(early, TAB_A): {"fire_floor": "3樓"}}
        for answer, out in steps:
            by_tab[(answer, TAB_A)] = out
        llm = TabAwareFakeLLM(by_tab)
        engine, io = self._engine_after_address(early, llm, [a for a, _ in steps])
        engine.case.fire_tab = TAB_A
        engine.case.building_type_code = "11"
        engine.case.sub_category = "集合住宅"
        engine.case.fire_or_smoke = "有火"
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.fire_floor, "3樓")
        self.assertNotIn(Q_A["起火樓層"], io.messages)   # 前面講過三樓，不再問
        self.assertIn(Q_A["濃煙顏色"], io.messages)


if __name__ == "__main__":
    unittest.main()
