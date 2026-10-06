"""
垂片 B1（交通工具火警）照 xlsx 重寫後的測試。

規格：docs/(all)火警垂片規格_關鍵要素與問句_1005.xlsx 的「02-垂片B1_交通工具」
規則同垂片 A（見 test_fire_tab_a_119.py 開頭說明），另外：
  - 乘客下車狀況答「仍有人在車上」→ 跟有人受困一樣，立刻轉人工
  - 載運物：交通工具是化學、毒劑交通工具，或車種是貨車，才問
  - 1005 版：看得到煙（有火有煙、無火有煙）才問濃煙顏色、車輛是否已熄火；
    看得到火（有火有煙、有火無煙）才問起火車輛數量、滅火狀況

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過、轉人工」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import unittest

from fire_tab_map_119 import (
    SAFETY_MESSAGE,
    TAB_B1,
    TAB_B1_QUESTIONS,
    TRAPPED_TRANSFER_MESSAGE,
)
from handlers.火警通用 import HuoJingGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

# 垂片 B1 各題的問句（取自題目表，xlsx 改問句時測試不必跟著改）
Q = {item.element: item.question for item in TAB_B1_QUESTIONS}

# 細類代碼（vehicle_wildfire_code）：LLM 抽到這個代碼後，程式會自動填好細類名稱
VEHICLE_CODE = {"汽車": 0, "機車": 1, "隧道": 2, "軌道型交通工具": 3,
                "化學、毒劑交通工具": 4, "船舶": 5, "航空器": 6}


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


def _run_vehicle_fire(steps: list[tuple[str, dict]], **prefilled):
    """
    已經知道是交通工具火警（不問案類分析），直接從垂片 B1 第一題開始。
    steps：依「實際被問的順序」排列的 (報案人回答, LLM 抽出的欄位)，每一句回答都不重複。
    """
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: out for answer, out in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    io.engine = engine
    case = engine.case
    case.main_category = "火警"
    case.fire_tab = TAB_B1
    case.fire_incident_type = 1
    case.non_building_fire = 0
    for key, value in prefilled.items():
        setattr(case, key, value)
    HuoJingGenericHandler().run_generic_flow(engine)
    return engine, io


def _asked(io: ScriptedIO) -> list[str]:
    by_question = {question: element for element, question in Q.items() if question}
    return [by_question[m] for m in io.messages if m in by_question]


def _vehicle(answer: str, name: str) -> tuple[str, dict]:
    return (answer, {"vehicle_wildfire_code": VEHICLE_CODE[name]})


# 共同的回答
FIRE = ("火很大", {"fire_or_smoke": "有火有煙"})
BLACK = ("黑煙", {"smoke_color": "黑色煙"})
PASSERBY = ("我是路過的", {"caller_role": "後方或路過駕駛"})
NO_SPREAD = ("沒有燒到旁邊", {"spread_status": "無"})
ONE_CAR = ("一台", {"vehicle_count": "一台"})
ENGINE_OFF = ("已經熄火了", {"engine_off_status": "已熄火"})
ALL_OUT = ("人都下車了", {"occupants_status": "人已全部下車"})
NO_INJURY = ("沒人受傷", {"injury_status": "無"})
NOBODY_FIGHTING = ("沒有人在滅火", {"extinguish_status": "無人"})


class TabB1QuestionOrderTests(unittest.TestCase):

    def test_car_asks_all_car_questions_in_xlsx_order(self) -> None:
        engine, io = _run_vehicle_fire([
            _vehicle("是我的汽車", "汽車"),
            ("一般油車", {"vehicle_type": "自小客車"}),
            FIRE, BLACK, PASSERBY, NO_SPREAD,
            ("引擎蓋那邊", {"fire_origin_part": "車頭或引擎"}),
            ONE_CAR, ENGINE_OFF, ALL_OUT, NO_INJURY, NOBODY_FIGHTING,
        ])
        self.assertEqual(_asked(io), [
            "交通工具", "車種", "火煙狀況", "濃煙顏色", "報案人身分", "是否延燒",
            "起火部位", "起火車輛數量", "車輛是否已熄火", "乘客下車狀況",
            "有無人員受傷", "滅火狀況",
        ])
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertEqual(engine.case.sub_category, "汽車")
        self.assertEqual(io.stages_when_asked[0], "交通工具火警-交通工具")

    def test_truck_also_asks_cargo(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("是一台汽車", "汽車"),
            ("是小貨車", {"vehicle_type": "貨車"}),
            FIRE, BLACK, PASSERBY, NO_SPREAD,
            ("後面車斗", {"fire_origin_part": "車廂或車斗"}),
            ONE_CAR, ENGINE_OFF, ALL_OUT, NO_INJURY,
            ("好像有載瓦斯桶", {"cargo": "易燃物（瓦斯桶）"}),
            NOBODY_FIGHTING,
        ])
        self.assertIn("載運物", _asked(io))

    def test_motorcycle_skips_car_only_questions(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("機車燒起來", "機車"),
            ("電動機車", {"vehicle_type": "電動機車"}),
            FIRE, BLACK, PASSERBY, NO_SPREAD,
            ONE_CAR, ENGINE_OFF, NO_INJURY, NOBODY_FIGHTING,
        ])
        self.assertEqual(_asked(io), [
            "交通工具", "車種", "火煙狀況", "濃煙顏色", "報案人身分", "是否延燒",
            "起火車輛數量", "車輛是否已熄火", "有無人員受傷", "滅火狀況",
        ])

    def test_boat_only_asks_questions_not_tied_to_vehicle_kind(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("港口有一艘船在燒", "船舶"),
            FIRE, BLACK, PASSERBY, NO_SPREAD,
            ONE_CAR, ENGINE_OFF, NOBODY_FIGHTING,
        ])
        self.assertEqual(_asked(io), [
            "交通工具", "火煙狀況", "濃煙顏色", "報案人身分", "是否延燒",
            "起火車輛數量", "車輛是否已熄火", "滅火狀況",
        ])

    def test_hazmat_vehicle_asks_cargo(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("化學槽車起火", "化學、毒劑交通工具"),
            FIRE, BLACK, PASSERBY, NO_SPREAD,
            ONE_CAR, ENGINE_OFF,
            ("載的是化學品", {"cargo": "化學品"}),
            NOBODY_FIGHTING,
        ])
        self.assertEqual(_asked(io)[-2:], ["載運物", "滅火狀況"])

    def test_fire_no_smoke_skips_color_and_engine_off(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("港口有一艘船在燒", "船舶"),
            ("有火，沒什麼煙", {"fire_or_smoke": "有火無煙"}),
            PASSERBY, NO_SPREAD, ONE_CAR, NOBODY_FIGHTING,
        ])
        self.assertEqual(_asked(io), [
            "交通工具", "火煙狀況", "報案人身分", "是否延燒", "起火車輛數量", "滅火狀況",
        ])

    def test_smoke_no_fire_asks_color_and_engine_off_only(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("港口有一艘船在冒煙", "船舶"),
            ("只看到煙，沒看到火", {"fire_or_smoke": "無火有煙"}),
            BLACK, PASSERBY, NO_SPREAD, ENGINE_OFF,
        ])
        self.assertEqual(_asked(io), [
            "交通工具", "火煙狀況", "濃煙顏色", "報案人身分", "是否延燒", "車輛是否已熄火",
        ])

    def test_unsure_fire_skips_visual_questions(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("聽說有汽車燒起來", "汽車"),
            ("不知道什麼車", {"vehicle_type": "不確定"}),
            ("我人不在現場", {"fire_or_smoke": "不確定"}),
            PASSERBY,
            ("不清楚", {"spread_status": "不確定"}),
            ("不知道", {"fire_origin_part": "不確定"}),
            ("應該都下車了吧", {"occupants_status": "不確定"}),
            ("不清楚有沒有人受傷", {"injury_status": "不確定"}),
        ])
        asked = _asked(io)
        for element in ("濃煙顏色", "起火車輛數量", "車輛是否已熄火", "滅火狀況"):
            self.assertNotIn(element, asked)

    def test_answers_carried_from_other_tab_are_not_asked_again(self) -> None:
        _, io = _run_vehicle_fire([
            _vehicle("是機車", "機車"),
            ("一般的", {"vehicle_type": "其他"}),
            BLACK, NO_SPREAD, ONE_CAR, ENGINE_OFF, NO_INJURY, NOBODY_FIGHTING,
        ], fire_or_smoke="有火有煙", caller_role="路人")
        asked = _asked(io)
        self.assertNotIn("火煙狀況", asked)
        self.assertNotIn("報案人身分", asked)


class OccupantsStillInsideTransferTests(unittest.TestCase):

    def test_people_still_in_car_transfers_immediately(self) -> None:
        with self.assertRaises(TransferToHumanError) as ctx:
            _run_vehicle_fire([
                _vehicle("汽車燒起來", "汽車"),
                ("自小客車", {"vehicle_type": "自小客車"}),
                FIRE, BLACK, PASSERBY, NO_SPREAD,
                ("引擎", {"fire_origin_part": "車頭或引擎"}),
                ONE_CAR, ENGINE_OFF,
                ("駕駛還卡在車上", {"occupants_status": "仍有人在車上"}),
            ])
        self.assertEqual(ctx.exception.result, "human_transfer")

    def test_transfer_message_is_said_before_transfer(self) -> None:
        io = ScriptedIO(["車上還有人出不來"])
        llm = FakeLLM({"車上還有人出不來": {"occupants_status": "仍有人在車上"}})
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        with self.assertRaises(TransferToHumanError):
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages[-1], TRAPPED_TRANSFER_MESSAGE)


class OccupantsFixedAnswerCheckTests(unittest.TestCase):
    """乘客下車狀況：LLM 寫錯格式就不記（不載入模型，直接模擬 LLM 的輸出）。"""

    def _extract(self, llm_output: dict) -> dict:
        ext = object.__new__(LLMExtractor119)
        ext.extract_slots = lambda *args, **kwargs: dict(llm_output)  # type: ignore[method-assign]
        # 指定垂片 B1：只會抽垂片 B1 用得到的欄位
        return ext.extract_general_fields("測試", "測試", main_category="火警", fire_tab="B1")

    def test_valid_answer_kept(self) -> None:
        self.assertEqual(
            self._extract({"occupants_status": "仍有人在車上"})["occupants_status"],
            "仍有人在車上",
        )

    def test_wrong_format_dropped(self) -> None:
        self.assertNotIn("occupants_status", self._extract({"occupants_status": "還有一個人"}))

    def test_vehicle_type_keeps_free_text(self) -> None:
        self.assertEqual(self._extract({"vehicle_type": "遊覽車"})["vehicle_type"], "遊覽車")


if __name__ == "__main__":
    unittest.main()
