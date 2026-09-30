"""
垂片 B2（山林田野火警）照 0929 xlsx 重寫後的測試。

規格：docs/修改後_(all)火警垂片規格_關鍵要素與問句_0929.xlsx 的「03-垂片B2_山林田野」
規則同垂片 A（見 test_fire_tab_a_119.py 開頭說明）。

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import unittest

from fire_tab_map_119 import SAFETY_MESSAGE, TAB_B2, TAB_B2_QUESTIONS
from handlers.火警通用 import HuoJingGenericHandler
from sop_119_engine import DialogueIO, SopEngine119

# 垂片 B2 各題的問句（取自題目表，xlsx 改問句時測試不必跟著改）
Q = {item.element: item.question for item in TAB_B2_QUESTIONS}

# 細類代碼（vehicle_wildfire_code）：7＝山林田野(平地)、8＝山林田野(山地)
FLAT, MOUNTAIN = 7, 8


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []
        self.stages_when_asked: list[str] = []
        self.engine: SopEngine119 | None = None

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError(f"測試回答已用盡，最後一句是：{self.messages[-1]}")
        if self.engine is not None:
            self.stages_when_asked.append(self.engine.case.flow_stage)
        return self.answers.pop(0)


class FakeLLM:
    """extracted：報案人的每一句回答 → LLM 應該抽出的欄位（模擬 LLM 已正確理解語意）。"""

    def __init__(self, extracted: dict[str, dict]):
        self.extracted = extracted

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None) -> dict:
        return dict(self.extracted.get(caller_text.strip(), {}))

    def classify_fire_tab(self, caller_text, question=None):
        return None

    def extract_address(self, caller_text, use_question=False, include_floor=True):
        return {}

    def check_fire_trigger_scenarios(self, caller_text, already_triggered):
        return []

    def generate_summary(self, transcript_texts, filled_fields):
        return "火災測試摘要"


def _run_wildfire(steps: list[tuple[str, dict]], **prefilled):
    """
    已經知道是山林田野火警（不問案類分析），直接從垂片 B2 第一題開始。
    steps：依「實際被問的順序」排列的 (報案人回答, LLM 抽出的欄位)，每一句回答都不重複。
    """
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: out for answer, out in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    io.engine = engine
    case = engine.case
    case.main_category = "火警"
    case.fire_tab = TAB_B2
    case.fire_incident_type = 1
    case.non_building_fire = 0
    for key, value in prefilled.items():
        setattr(case, key, value)
    HuoJingGenericHandler().run_generic_flow(engine)
    return engine, io


def _asked(io: ScriptedIO) -> list[str]:
    by_question = {question: element for element, question in Q.items() if question}
    return [by_question[m] for m in io.messages if m in by_question]


ON_MOUNTAIN = ("在山上", {"vehicle_wildfire_code": MOUNTAIN})
WEEDS = ("雜草在燒", {"burning_object": "雜草"})
FIRE = ("有看到火", {"fire_or_smoke": "有火"})
WHITE = ("白煙", {"smoke_color": "白色煙"})
BIG = ("比籃球場還大", {"fire_extent": "一個籃球場以上"})
SPREADING = ("快燒到旁邊的樹林了", {"spread_status": "是"})
PASSERBY = ("我開車經過", {"caller_role": "路過"})


class TabB2QuestionOrderTests(unittest.TestCase):

    def test_asks_in_xlsx_order(self) -> None:
        engine, io = _run_wildfire([
            ON_MOUNTAIN, WEEDS, FIRE, WHITE, BIG, SPREADING, PASSERBY,
        ])
        self.assertEqual(_asked(io), [
            "山林火警", "燃燒物", "火煙狀況", "濃煙顏色", "燃燒面積", "是否延燒", "報案人身分",
        ])
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertEqual(engine.case.sub_category, "山林田野(山地)")
        self.assertEqual(io.stages_when_asked[0], "山林田野火警-山林火警")

    def test_known_subtype_is_not_asked(self) -> None:
        _, io = _run_wildfire(
            [WEEDS, FIRE, WHITE, BIG, SPREADING, PASSERBY],
            vehicle_wildfire_code=FLAT, sub_category="山林田野(平地)",
        )
        self.assertNotIn("山林火警", _asked(io))

    def test_unsure_fire_skips_smoke_color(self) -> None:
        _, io = _run_wildfire([
            ON_MOUNTAIN, WEEDS,
            ("遠遠的看不清楚", {"fire_or_smoke": "不確定"}),
            ("不知道多大", {"fire_extent": "未知"}),
            ("不清楚", {"spread_status": "不確定"}),
            PASSERBY,
        ])
        self.assertEqual(_asked(io), [
            "山林火警", "燃燒物", "火煙狀況", "燃燒面積", "是否延燒", "報案人身分",
        ])

    def test_passive_fields_recorded_but_not_asked(self) -> None:
        engine, io = _run_wildfire([
            ON_MOUNTAIN, WEEDS, FIRE, WHITE,
            ("大概一個籃球場，旁邊有條溪，地主在拿水管澆",
             {"fire_extent": "一個籃球場以上", "nearby_water_source": "有（溪）",
              "extinguish_status": "已在自行滅火"}),
            SPREADING, PASSERBY,
        ])
        self.assertEqual(engine.case.nearby_water_source, "有（溪）")
        self.assertEqual(engine.case.extinguish_status, "已在自行滅火")
        self.assertNotIn("滅火狀況", _asked(io))
        self.assertNotIn("水源狀況", _asked(io))

    def test_burning_object_outside_reference_range_is_kept(self) -> None:
        engine, _ = _run_wildfire([
            ON_MOUNTAIN, ("有人在燒金紙", {"burning_object": "金紙"}),
            FIRE, WHITE, BIG, SPREADING, PASSERBY,
        ])
        self.assertEqual(engine.case.burning_object, "金紙")


if __name__ == "__main__":
    unittest.main()
