"""
垂片 C（輕微火警）照 xlsx 重寫後的測試。

規格：docs/(all)火警垂片規格_關鍵要素與問句_1013.xlsx 的「04-垂片C_輕微火警」
規則同垂片 A（見 test_fire_tab_a_119.py 開頭說明），另外：
  - 1013 版：第一題「火警類型」（就是次案類，拿掉瓦斯漏氣）；
    也問場所用途、建築物類型、建物總樓層，用來掌握現場狀況
  - C 裡問到的建築物類型（例如大樓 → 集合住宅）另外記，次案類維持警報器作響等，不換垂片
  - 警報器作響、查看案件看得到火或煙 → 換到建築物火警（A），次案類＝建築物類型；
    垃圾、電線桿有火照樣留在 C。A、C 之間只看火煙狀況，BERT 和 LLM 不能自己換
  - 有無受困每通都問；答「有人受困」立刻轉人工
  - 來源確認：警報器作響、查看案件才問
  - 燃燒範圍：垃圾、電線桿，而且看得到火才問

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過、換垂片、轉人工」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import types
import unittest

from fire_tab_map_119 import (
    SAFETY_MESSAGE,
    TAB_A,
    TAB_A_QUESTIONS,
    TAB_C,
    TAB_C_QUESTIONS,
    TRAPPED_TRANSFER_MESSAGE,
)
from handlers.火警通用 import HuoJingGenericHandler
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

# 垂片 C 各題的問句（取自題目表，xlsx 改問句時測試不必跟著改）
Q = {item.element: item.question for item in TAB_C_QUESTIONS}
# 問句 → 關鍵要素；換到 A 之後的題目前面標「A:」（A、C 問句相同的題目以 C 顯示）
ELEMENT_BY_QUESTION = {
    item.question: f"A:{item.element}" for item in TAB_A_QUESTIONS if item.question
}
ELEMENT_BY_QUESTION.update({
    item.question: item.element for item in TAB_C_QUESTIONS if item.question
})

# 次案類代碼（minor_fire_code）：LLM 抽到這個代碼後，程式會自動填好次案類名稱
MINOR_CODE = {"垃圾": 0, "電線桿(電纜)": 1, "警報器作響": 3, "查看案件": 4}


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


class StubbornBERT:
    """不管聽到什麼，都很有把握地說同一個次案類（用來測試 BERT 會不會被擋住）。"""

    def __init__(self, label: str):
        self.label = label

    def predict(self, text, main_cat):
        return types.SimpleNamespace(
            final_label=self.label, classifier_conf=0.95,
            all_probs={self.label: 0.95, "垃圾": 0.03, "電線桿(電纜)": 0.02},
        )


class FakeLLM:
    """extracted：報案人的每一句回答 → LLM 應該抽出的欄位（模擬 LLM 已正確理解語意）。"""

    def __init__(self, extracted: dict[str, dict]):
        self.extracted = extracted

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        return dict(self.extracted.get(caller_text.strip(), {}))

    def classify_fire_tab(self, caller_text, question=None):
        return None

    def extract_address(self, caller_text, use_question=False, include_floor=True):
        return {}

    def check_fire_trigger_scenarios(self, caller_text, already_triggered):
        return []

    def generate_summary(self, transcript_texts, filled_fields):
        return "火災測試摘要"


def _run_minor_fire(steps: list[tuple[str, dict]], bert: str | None = None, **prefilled):
    """
    已經知道是輕微火警（不問案類分析），直接從垂片 C 第一題開始。
    steps：依「實際被問的順序」排列的 (報案人回答, LLM 抽出的欄位)，每一句回答都不重複。
    """
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: out for answer, out in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    io.engine = engine
    case = engine.case
    case.main_category = "火警"
    case.fire_tab = TAB_C
    case.fire_incident_type = 1
    case.non_building_fire = 1
    engine._sub_clf = StubbornBERT(bert) if bert else None
    for key, value in prefilled.items():
        setattr(case, key, value)
    HuoJingGenericHandler().run_generic_flow(engine)
    return engine, io


def _asked(io: ScriptedIO) -> list[str]:
    return [ELEMENT_BY_QUESTION[m] for m in io.messages if m in ELEMENT_BY_QUESTION]


def _minor(answer: str, name: str) -> tuple[str, dict]:
    return (answer, {"minor_fire_code": MINOR_CODE[name]})


ALARM = _minor("樓上的警報器一直響", "警報器作響")
HOUSE = ("住宅", {"place_usage": "住宅"})
APARTMENT = ("大樓", {"building_type_code": "11"})
TWELVE_FLOORS = ("十二樓", {"building_total_floors": "12層樓"})
NO_FIRE_NO_SMOKE = ("火跟煙都沒看到", {"fire_or_smoke": "無火無煙"})
STILL_RINGING = ("還在響", {"alarm_status": "仍在響"})
BURNING_SMELL = ("有一點燒焦味", {"odor": "燒焦味"})
RESIDENT = ("我住這裡", {"caller_role": "住戶"})
NOBODY_CALLING = ("沒聽到有人喊", {"trapped_status": "無人受困"})
SOURCE = ("好像是五樓", {"source_located": "已確認位置（五樓）"})
HEAD = ["火警類型", "場所用途", "建築物類型", "建物總樓層", "火煙狀況"]
ALARM_CALL = [
    ALARM, HOUSE, APARTMENT, TWELVE_FLOORS, NO_FIRE_NO_SMOKE,
    STILL_RINGING, BURNING_SMELL, RESIDENT, NOBODY_CALLING, SOURCE,
]


class TabCQuestionOrderTests(unittest.TestCase):

    def test_alarm_without_fire_or_smoke(self) -> None:
        engine, io = _run_minor_fire(ALARM_CALL)
        self.assertEqual(_asked(io), HEAD + [
            "警報器狀態", "氣味類型", "報案人身分", "有無受困", "來源確認",
        ])
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertEqual(io.stages_when_asked[0], "輕微火警-火警類型")

    def test_apartment_is_recorded_as_building_type_and_stays_minor(self) -> None:
        engine, _ = _run_minor_fire(ALARM_CALL)
        self.assertEqual(engine.case.fire_tab, TAB_C)
        self.assertEqual(engine.case.sub_category, "警報器作響")
        self.assertEqual(engine.case.building_type, "集合住宅")

    def test_bert_cannot_pull_minor_fire_to_building_fire(self) -> None:
        # BERT 一直說集合住宅，但無火無煙 → 留在 C
        engine, _ = _run_minor_fire(ALARM_CALL, bert="集合住宅")
        self.assertEqual(engine.case.fire_tab, TAB_C)
        self.assertEqual(engine.case.sub_category, "警報器作響")

    def test_garbage_fire_stays_minor_and_asks_spread_and_extent(self) -> None:
        engine, io = _run_minor_fire([
            _minor("有人在燒垃圾", "垃圾"),
            ("路邊空地", {"place_usage": "其他"}),
            ("沒有房子", {"building_type_code": "00"}),
            ("不知道", {"building_total_floors": "不確定"}),
            ("有看到火", {"fire_or_smoke": "有火有煙"}),
            ("黑煙", {"smoke_color": "黑色煙"}),
            ("沒有燒到旁邊", {"spread_status": "無"}),
            ("一小堆", {"fire_extent": "一小堆"}),
            ("我路過", {"caller_role": "路人"}),
            NOBODY_CALLING,
        ])
        self.assertEqual(engine.case.fire_tab, TAB_C)
        self.assertEqual(engine.case.sub_category, "垃圾")
        self.assertEqual(_asked(io)[5:], [
            "濃煙顏色", "是否延燒", "燃燒範圍", "報案人身分", "有無受困",
        ])

    def test_utility_pole_smoke_without_fire(self) -> None:
        engine, io = _run_minor_fire([
            _minor("電線桿上面在冒煙", "電線桿(電纜)"),
            ("路邊", {"place_usage": "其他"}),
            ("透天", {"building_type_code": "10"}),
            ("三層", {"building_total_floors": "3層樓"}),
            ("只看到煙，是電線桿上面的變壓器",
             {"fire_or_smoke": "無火有煙", "target_object": "電線桿或電纜（變壓器）"}),
            ("白煙", {"smoke_color": "白色煙"}),
            ("我是路人", {"caller_role": "路人"}),
            NOBODY_CALLING,
        ])
        asked = _asked(io)
        # 看不到火 → 不問是否延燒、燃燒範圍；不是警報器、查看案件 → 不問來源確認
        for element in ("是否延燒", "燃燒範圍", "來源確認", "標的物"):
            self.assertNotIn(element, asked)
        # 標的物是被動題：報案人講到就記，但不問
        self.assertEqual(engine.case.target_object, "電線桿或電纜（變壓器）")


class MoveToBuildingFireTests(unittest.TestCase):

    def test_alarm_with_fire_moves_to_building_fire(self) -> None:
        engine, io = _run_minor_fire([
            ALARM, HOUSE, APARTMENT, TWELVE_FLOORS,
            ("有火有煙", {"fire_or_smoke": "有火有煙"}),
            ("黑煙", {"smoke_color": "黑色煙"}),
            ("三樓", {"fire_floor": "3樓"}),
            ("會", {"spread_status": "極可能或已延燒"}),
            ("我住這裡", {"caller_role": "住戶(起火戶)"}),
            ("沒有", {"trapped_status": "無人受困"}),
        ])
        # 換到 A：前面答過的不重問，接著問 A 的濃煙顏色、起火樓層…
        self.assertEqual(_asked(io), HEAD + [
            "A:濃煙顏色", "A:起火樓層", "A:延燒可能", "A:報案人身分", "A:有無受困",
        ])
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.sub_category, "集合住宅")
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)


class TabCTrappedTransferTests(unittest.TestCase):

    def test_someone_calling_for_help_transfers(self) -> None:
        with self.assertRaises(TransferToHumanError) as ctx:
            _run_minor_fire([
                ALARM, HOUSE, APARTMENT, TWELVE_FLOORS, NO_FIRE_NO_SMOKE,
                STILL_RINGING, BURNING_SMELL, RESIDENT,
                ("有聽到有人在喊救命", {"trapped_status": "有人受困"}),
            ])
        self.assertEqual(ctx.exception.result, "human_transfer")

    def test_garbage_also_asks_trapped(self) -> None:
        # 1013 版：有無受困每通都問（以前只問警報器作響、查看案件）
        _, io = _run_minor_fire([
            _minor("有人在燒垃圾", "垃圾"),
            ("路邊空地", {"place_usage": "其他"}),
            ("沒有房子", {"building_type_code": "00"}),
            ("不知道", {"building_total_floors": "不確定"}),
            ("只看到煙", {"fire_or_smoke": "無火有煙"}),
            ("黑煙", {"smoke_color": "黑色煙"}),
            ("我路過", {"caller_role": "路人"}),
            NOBODY_CALLING,
        ])
        self.assertIn("有無受困", _asked(io))

    def test_transfer_message_is_said(self) -> None:
        io = ScriptedIO(["有聽到有人在喊救命"])
        llm = FakeLLM({"有聽到有人在喊救命": {"trapped_status": "有人受困"}})
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        engine.case.fire_tab = TAB_C
        engine.case.minor_fire_code = 3
        engine.case.sub_category = "警報器作響"
        engine.case.place_usage = "住宅"
        engine.case.building_type = "集合住宅"
        engine.case.building_total_floors = "12層樓"
        engine.case.fire_or_smoke = "無火無煙"
        engine.case.alarm_status = "仍在響"
        engine.case.odor = "無"
        engine.case.caller_role = "住戶"
        with self.assertRaises(TransferToHumanError):
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [Q["有無受困"], TRAPPED_TRANSFER_MESSAGE])


if __name__ == "__main__":
    unittest.main()
