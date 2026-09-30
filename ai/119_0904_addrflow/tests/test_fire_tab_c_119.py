"""
垂片 C（輕微火警）照 0929 xlsx 重寫後的測試。

規格：docs/修改後_(all)火警垂片規格_關鍵要素與問句_0929.xlsx 的「04-垂片C_輕微火警」
規則同垂片 A（見 test_fire_tab_a_119.py 開頭說明），另外：
  - 有無受困：細類是警報器作響、查看案件才問；答「有人受困」立刻轉人工
  - 來源確認：確定有聞到味道（氣味已記下且不是「無」），或細類是警報器作響，才問

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過、轉人工」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import unittest

from fire_tab_map_119 import (
    SAFETY_MESSAGE,
    TAB_C,
    TAB_C_QUESTIONS,
    TRAPPED_TRANSFER_MESSAGE,
)
from handlers.火警通用 import HuoJingGenericHandler
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

# 垂片 C 各題的問句（取自題目表，xlsx 改問句時測試不必跟著改）
Q = {item.element: item.question for item in TAB_C_QUESTIONS}

# 細類代碼（minor_fire_code）：LLM 抽到這個代碼後，程式會自動填好細類名稱
MINOR_CODE = {"垃圾": 0, "電線桿(電纜)": 1, "瓦斯漏氣": 2, "警報器作響": 3, "查看案件": 4}


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


def _run_minor_fire(steps: list[tuple[str, dict]], **prefilled):
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
    for key, value in prefilled.items():
        setattr(case, key, value)
    HuoJingGenericHandler().run_generic_flow(engine)
    return engine, io


def _asked(io: ScriptedIO) -> list[str]:
    by_question = {question: element for element, question in Q.items() if question}
    return [by_question[m] for m in io.messages if m in by_question]


def _minor(answer: str, name: str) -> tuple[str, dict]:
    return (answer, {"minor_fire_code": MINOR_CODE[name]})


NO_FIRE_NO_SMOKE = ("火跟煙都沒看到", {"fire_or_smoke": "無火無煙"})
RESIDENT = ("我住這裡", {"caller_role": "住戶"})
NOBODY_CALLING = ("沒聽到有人喊", {"trapped_status": "無人受困"})


class TabCQuestionOrderTests(unittest.TestCase):

    def test_alarm_without_fire_or_smoke(self) -> None:
        engine, io = _run_minor_fire([
            _minor("樓上的警報器一直響", "警報器作響"),
            ("還在響", {"alarm_status": "仍在響"}),
            NO_FIRE_NO_SMOKE,
            ("有一點燒焦味", {"odor": "燒焦味"}),
            RESIDENT, NOBODY_CALLING,
            ("好像是五樓", {"source_located": "已確認位置（五樓）"}),
        ])
        self.assertEqual(_asked(io), [
            "輕微火警", "警報器狀態", "火煙狀況", "氣味類型",
            "報案人身分", "有無受困", "來源確認",
        ])
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertEqual(engine.case.sub_category, "警報器作響")
        self.assertEqual(io.stages_when_asked[0], "輕微火警-輕微火警")

    def test_garbage_fire_with_flames(self) -> None:
        _, io = _run_minor_fire([
            _minor("有人在燒垃圾", "垃圾"),
            ("有看到火", {"fire_or_smoke": "有火"}),
            ("黑煙", {"smoke_color": "黑色煙"}),
            ("沒有燒到旁邊", {"spread_status": "無"}),
            ("我路過", {"caller_role": "路人"}),
        ])
        self.assertEqual(_asked(io), [
            "輕微火警", "火煙狀況", "濃煙顏色", "是否延燒", "報案人身分",
        ])

    def test_check_case_with_burning_smell_asks_source(self) -> None:
        _, io = _run_minor_fire([
            _minor("聞到燒焦味想請你們來看看", "查看案件"),
            NO_FIRE_NO_SMOKE,
            ("燒焦味", {"odor": "燒焦味"}),
            RESIDENT, NOBODY_CALLING,
            ("不知道是哪一戶", {"source_located": "聞得到但找不到來源"}),
        ])
        self.assertEqual(_asked(io), [
            "輕微火警", "火煙狀況", "氣味類型", "報案人身分", "有無受困", "來源確認",
        ])

    def test_check_case_with_no_smell_does_not_ask_source(self) -> None:
        _, io = _run_minor_fire([
            _minor("想請你們來看一下", "查看案件"),
            NO_FIRE_NO_SMOKE,
            ("沒有味道", {"odor": "無"}),
            RESIDENT, NOBODY_CALLING,
        ])
        self.assertNotIn("來源確認", _asked(io))

    def test_passive_target_object_recorded_but_not_asked(self) -> None:
        engine, io = _run_minor_fire([
            _minor("電線桿上面在冒煙", "電線桿(電纜)"),
            ("只看到煙，是電線桿上面的變壓器",
             {"fire_or_smoke": "只有煙", "target_object": "電線桿或電纜（變壓器）"}),
            ("白煙", {"smoke_color": "白色煙"}),
            ("沒有", {"spread_status": "無"}),
            ("我是路人", {"caller_role": "路人"}),
        ])
        self.assertEqual(engine.case.target_object, "電線桿或電纜（變壓器）")
        self.assertNotIn("標的物", _asked(io))


class TabCTrappedTransferTests(unittest.TestCase):

    def test_alarm_with_someone_calling_for_help_transfers(self) -> None:
        with self.assertRaises(TransferToHumanError) as ctx:
            _run_minor_fire([
                _minor("警報器在響", "警報器作響"),
                ("還在響", {"alarm_status": "仍在響"}),
                NO_FIRE_NO_SMOKE,
                ("沒什麼味道", {"odor": "無"}),
                RESIDENT,
                ("有聽到有人在喊救命", {"trapped_status": "有人受困"}),
            ])
        self.assertEqual(ctx.exception.result, "human_transfer")

    def test_transfer_message_is_said(self) -> None:
        io = ScriptedIO(["有聽到有人在喊救命"])
        llm = FakeLLM({"有聽到有人在喊救命": {"trapped_status": "有人受困"}})
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        engine.case.fire_tab = TAB_C
        engine.case.fire_incident_type = 1
        engine.case.non_building_fire = 1
        engine.case.minor_fire_code = 3
        engine.case.sub_category = "警報器作響"
        engine.case.alarm_status = "仍在響"
        engine.case.fire_or_smoke = "無火無煙"
        engine.case.odor = "無"
        engine.case.caller_role = "住戶"
        with self.assertRaises(TransferToHumanError):
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [Q["有無受困"], TRAPPED_TRANSFER_MESSAGE])


if __name__ == "__main__":
    unittest.main()
