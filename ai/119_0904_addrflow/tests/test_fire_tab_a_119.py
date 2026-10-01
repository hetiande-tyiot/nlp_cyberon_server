"""
垂片 A（建築物火警）照 0929 xlsx 重寫後的測試。

規格：docs/修改後_(all)火警垂片規格_關鍵要素與問句_0929.xlsx 的「01-垂片A_建築物火警」
  - 主動題：還不知道才問
  - 條件題：前置條件確定成立才問；不確定就不問
  - 被動題：不問，報案人講到才記
  - 有人受困：火警流程任何時候講出來都立刻轉人工
  - 換垂片：報案人已經回答過的內容全部保留

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過、轉人工」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import unittest

from fire_tab_map_119 import (
    SAFETY_MESSAGE,
    TAB_A,
    TAB_A_QUESTIONS,
    TAB_B1,
    TRAPPED_TRANSFER_MESSAGE,
    apply_subtype_identity_codes,
)
from handlers.火警通用 import HuoJingGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

# 垂片 A 各題的問句（取自題目表，xlsx 改問句時測試不必跟著改）
Q = {item.element: item.question for item in TAB_A_QUESTIONS}


class ScriptedIO(DialogueIO):
    """依序回答；每次被問時記下當下的流程階段。"""

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

    def __init__(self, extracted: dict[str, dict] | None = None,
                 remapped: dict | None = None):
        self.extracted = extracted or {}
        self.remapped = remapped or {}

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

    def remap_sop_fields_for_subcategory(self, **kwargs):
        return dict(self.remapped)


def _building_fire_engine(
    answers: list[str], extracted: dict[str, dict], **prefilled
) -> tuple[SopEngine119, ScriptedIO]:
    """已經知道是建築物火警（不問案類分析），直接從垂片 A 第一題開始。"""
    io = ScriptedIO(answers)
    engine = SopEngine119(io=io, llm_extractor=FakeLLM(extracted))  # type: ignore[arg-type]
    io.engine = engine
    engine.case.main_category = "火警"
    engine.case.fire_tab = TAB_A  # 已經在垂片 A
    for key, value in prefilled.items():
        setattr(engine.case, key, value)
    return engine, io


def _asked_elements(io: ScriptedIO) -> list[str]:
    """把 AI 說過的話換成「問了哪些關鍵要素」，方便比對順序。"""
    by_question = {question: element for element, question in Q.items() if question}
    return [by_question[m] for m in io.messages if m in by_question]


# 一通「透天厝、有火、黑煙、二樓、沒有受困」的標準回答
TOWNHOUSE_ANSWERS = {
    "透天厝": {"building_type_code": "10"},
    "住家": {"place_usage": "住家"},
    "火很大，煙也很多": {"fire_or_smoke": "有火"},
    "黑煙": {"smoke_color": "黑色煙"},
    "二樓": {"fire_floor": "2樓"},
    "還好沒燒過去": {"spread_status": "延燒可能性低"},
    "人都出來了": {"trapped_status": "無人受困"},
    "三層樓": {"building_total_floors": "3層樓"},
    "我是隔壁鄰居": {"caller_role": "鄰居"},
}


class TabAQuestionOrderTests(unittest.TestCase):

    def test_townhouse_with_fire_asks_in_xlsx_order(self) -> None:
        engine, io = _building_fire_engine(list(TOWNHOUSE_ANSWERS), TOWNHOUSE_ANSWERS)
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(_asked_elements(io), [
            "建築物類型", "場所用途", "火煙狀況", "濃煙顏色", "起火樓層",
            "延燒可能", "有無受困", "建物樓層", "報案人身分",
        ])
        # 透天厝不問構造、危險物品；有火不問氣味；沒人受困不問應門
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.sub_category, "透天厝")
        self.assertEqual(engine.case.fire_or_smoke, "有火")
        self.assertEqual(engine.case.caller_role, "鄰居")

    def test_stage_names_use_building_fire_prefix(self) -> None:
        engine, io = _building_fire_engine(list(TOWNHOUSE_ANSWERS), TOWNHOUSE_ANSWERS)
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.stages_when_asked[:3], [
            "建築物火警-建築物類型", "建築物火警-場所用途", "建築物火警-火煙狀況",
        ])

    def test_known_active_answers_are_not_asked_again(self) -> None:
        answers = {k: v for k, v in TOWNHOUSE_ANSWERS.items()
                   if k not in ("住家", "我是隔壁鄰居")}
        engine, io = _building_fire_engine(
            list(answers), answers, place_usage="住家", caller_role="路人",
        )
        HuoJingGenericHandler().run_generic_flow(engine)
        asked = _asked_elements(io)
        self.assertNotIn("場所用途", asked)
        self.assertNotIn("報案人身分", asked)
        self.assertEqual(engine.case.caller_role, "路人")


class FireSmokeConditionTests(unittest.TestCase):
    """
    火煙狀況的四種回答，各自追問哪些題。
    回答依「實際被問的順序」排列：火煙狀況之後的追問（after_fire）→ 有無受困 →
    建物樓層 → 報案人身分 → 最後的追問（at_end，例如氣味）。
    """

    def _run(
        self,
        fire_answer: tuple[str, str],
        after_fire: list[tuple[str, dict]],
        at_end: list[tuple[str, dict]] = (),
    ) -> list[str]:
        steps = [
            ("透天厝", {"building_type_code": "10"}),
            ("住家", {"place_usage": "住家"}),
            (fire_answer[0], {"fire_or_smoke": fire_answer[1]}),
            *after_fire,
            ("人都出來了", {"trapped_status": "無人受困"}),
            ("三層樓", {"building_total_floors": "3層樓"}),
            ("我是鄰居", {"caller_role": "鄰居"}),
            *at_end,
        ]
        engine, io = _building_fire_engine(
            [answer for answer, _ in steps], {answer: out for answer, out in steps},
        )
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        return _asked_elements(io)

    def test_only_smoke_asks_color_floor_spread(self) -> None:
        asked = self._run(("只看到煙", "只有煙"), [
            ("白煙", {"smoke_color": "白色煙"}),
            ("三樓", {"fire_floor": "3樓"}),
            ("應該不會", {"spread_status": "延燒可能性低"}),
        ])
        self.assertEqual(asked, [
            "建築物類型", "場所用途", "火煙狀況", "濃煙顏色", "起火樓層",
            "延燒可能", "有無受困", "建物樓層", "報案人身分",
        ])

    def test_no_fire_no_smoke_skips_visual_questions_and_asks_odor(self) -> None:
        asked = self._run(("火跟煙都沒看到，只有聞到味道", "無火無煙"), [], [
            ("有燒焦味", {"odor": "燒焦味"}),
        ])
        self.assertEqual(asked, [
            "建築物類型", "場所用途", "火煙狀況",
            "有無受困", "建物樓層", "報案人身分", "氣味",
        ])

    def test_unsure_skips_visual_questions_and_odor(self) -> None:
        asked = self._run(("我人不在現場，不知道", "不確定"), [])
        self.assertEqual(asked, [
            "建築物類型", "場所用途", "火煙狀況",
            "有無受困", "建物樓層", "報案人身分",
        ])

    def test_fire_but_no_smoke_skips_fire_floor(self) -> None:
        asked = self._run(("有看到火", "有火"), [
            ("沒有煙", {"smoke_color": "無煙"}),
            ("會燒到隔壁", {"spread_status": "極可能或已延燒"}),
        ])
        self.assertEqual(asked, [
            "建築物類型", "場所用途", "火煙狀況", "濃煙顏色",
            "延燒可能", "有無受困", "建物樓層", "報案人身分",
        ])

    def test_smoke_color_not_answered_skips_fire_floor(self) -> None:
        # 問了濃煙顏色但沒問出來 → 不確定 → 不問起火樓層
        asked = self._run(("有看到火", "有火"), [
            ("看不清楚", {}),
            ("應該不會", {"spread_status": "延燒可能性低"}),
        ])
        self.assertEqual(asked, [
            "建築物類型", "場所用途", "火煙狀況", "濃煙顏色",
            "延燒可能", "有無受困", "建物樓層", "報案人身分",
        ])


class WarehouseFactoryConditionTests(unittest.TestCase):

    def _asked_for(self, building_answer: str, code: str) -> list[str]:
        """回答依實際被問的順序排列；每一句回答都不重複，避免對應錯題。"""
        steps = [
            (building_answer, {"building_type_code": code}),
            ("做生意的地方", {"place_usage": "店家"}),
            ("我人不在現場", {"fire_or_smoke": "不確定"}),
            ("不清楚", {"trapped_status": "不確定"}),
            ("一層", {"building_total_floors": "1層樓"}),
            ("我是管理員", {"caller_role": "管理員或警衛"}),
        ]
        if code in ("12", "25"):
            steps += [
                ("是鐵皮的", {"building_construction": "鐵皮屋"}),
                ("有瓦斯桶", {"hazardous_materials": "有（瓦斯桶）"}),
            ]
        engine, io = _building_fire_engine(
            [answer for answer, _ in steps], {answer: out for answer, out in steps},
        )
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        return _asked_elements(io)

    BASE = ["建築物類型", "場所用途", "火煙狀況", "有無受困", "建物樓層", "報案人身分"]

    def test_warehouse_asks_construction_and_hazards(self) -> None:
        self.assertEqual(self._asked_for("倉庫", "12"), self.BASE + ["建物構造", "危險物品"])

    def test_factory_asks_construction_and_hazards(self) -> None:
        self.assertEqual(self._asked_for("是工廠", "25"), self.BASE + ["建物構造", "危險物品"])

    def test_apartment_does_not_ask_construction_or_hazards(self) -> None:
        self.assertEqual(self._asked_for("公寓", "11"), self.BASE)


class PeopleTrappedTransferTests(unittest.TestCase):

    def test_trapped_answer_transfers_immediately(self) -> None:
        extracted = {
            "透天厝": {"building_type_code": "10"},
            "住家": {"place_usage": "住家"},
            "有火": {"fire_or_smoke": "有火"},
            "黑煙": {"smoke_color": "黑色煙"},
            "二樓": {"fire_floor": "2樓"},
            "會": {"spread_status": "極可能或已延燒"},
            "三樓還有阿嬤出不來": {"trapped_status": "有人受困"},
        }
        engine, io = _building_fire_engine(list(extracted), extracted)
        with self.assertRaises(TransferToHumanError) as ctx:
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(ctx.exception.result, "human_transfer")
        self.assertEqual(io.messages[-1], TRAPPED_TRANSFER_MESSAGE)
        asked = _asked_elements(io)
        self.assertEqual(asked[-1], "有無受困")
        self.assertNotIn("起火戶應門", asked)
        self.assertNotIn("建物樓層", asked)

    def test_trapped_mentioned_in_incident_answer_transfers_before_tab_questions(self) -> None:
        io = ScriptedIO(["房子燒起來，裡面還有人出不來"])
        llm = FakeLLM({"房子燒起來，裡面還有人出不來": {"trapped_status": "有人受困"}})
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        with self.assertRaises(TransferToHumanError):
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages[-1], TRAPPED_TRANSFER_MESSAGE)
        self.assertEqual(_asked_elements(io), [])

    def test_trapped_known_before_fire_flow_transfers_without_asking(self) -> None:
        # 報地址時就講了有人受困
        engine, io = _building_fire_engine([], {}, trapped_status="有人受困")
        with self.assertRaises(TransferToHumanError):
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [TRAPPED_TRANSFER_MESSAGE])

    def test_unsure_trapped_does_not_transfer(self) -> None:
        extracted = dict(TOWNHOUSE_ANSWERS)
        extracted["人都出來了"] = {"trapped_status": "不確定"}
        engine, io = _building_fire_engine(list(TOWNHOUSE_ANSWERS), extracted)
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)


class PassiveAndFreeTextTests(unittest.TestCase):

    def test_passive_fields_are_recorded_but_never_asked(self) -> None:
        extracted = dict(TOWNHOUSE_ANSWERS)
        extracted["火很大，煙也很多"] = {
            "fire_or_smoke": "有火",
            "explosion_status": "有爆炸",
            "fire_extent": "整棟都在燒",
        }
        engine, io = _building_fire_engine(list(TOWNHOUSE_ANSWERS), extracted)
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.explosion_status, "有爆炸")
        self.assertEqual(engine.case.fire_extent, "整棟都在燒")
        for element in ("有無爆炸", "其他資訊", "延燒面積"):
            self.assertEqual(Q[element], "")  # 被動題在題目表裡沒有問句，AI 不會問
        self.assertNotIn("剛剛有沒有聽到爆炸的聲音？", io.messages)

    def test_answer_outside_reference_range_is_kept(self) -> None:
        extracted = dict(TOWNHOUSE_ANSWERS)
        extracted["住家"] = {"place_usage": "宮廟"}
        engine, io = _building_fire_engine(list(TOWNHOUSE_ANSWERS), extracted)
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.place_usage, "宮廟")


class FixedAnswerCheckTests(unittest.TestCase):
    """火煙狀況、有無受困：LLM 寫錯格式就不記（不載入模型，直接模擬 LLM 的輸出）。"""

    def _extract(self, llm_output: dict) -> dict:
        ext = object.__new__(LLMExtractor119)
        ext.extract_slots = lambda *args, **kwargs: dict(llm_output)  # type: ignore[method-assign]
        # 指定垂片 A：只會抽垂片 A 用得到的欄位
        return ext.extract_general_fields("測試", "測試", main_category="火警", fire_tab="A")

    def test_valid_fixed_answers_are_kept(self) -> None:
        out = self._extract({"fire_or_smoke": "只有煙", "trapped_status": "有人受困"})
        self.assertEqual(out["fire_or_smoke"], "只有煙")
        self.assertEqual(out["trapped_status"], "有人受困")

    def test_wrong_format_is_dropped(self) -> None:
        out = self._extract({"fire_or_smoke": "有火有煙", "trapped_status": "有人受困。"})
        self.assertNotIn("fire_or_smoke", out)
        self.assertNotIn("trapped_status", out)

    def test_other_fields_keep_free_text(self) -> None:
        out = self._extract({"place_usage": "宮廟", "smoke_color": "灰灰的"})
        self.assertEqual(out["place_usage"], "宮廟")
        self.assertEqual(out["smoke_color"], "灰灰的")


class TabSwitchKeepsAnswersTests(unittest.TestCase):

    def _filled_case_engine(self, remapped: dict | None = None) -> SopEngine119:
        engine = SopEngine119(io=ScriptedIO([]), llm_extractor=FakeLLM(remapped=remapped))  # type: ignore[arg-type]
        case = engine.case
        case.main_category = "火警"
        apply_subtype_identity_codes(case, "透天厝", update_tab=True)
        case.sub_category = "透天厝"
        case.fire_or_smoke = "有火"
        case.smoke_color = "黑色煙"
        case.caller_role = "路人"
        case.place_usage = "住家"
        return engine

    def test_switch_subtype_codes_keeps_answers(self) -> None:
        engine = self._filled_case_engine()
        apply_subtype_identity_codes(engine.case, "汽車", update_tab=True)
        case = engine.case
        self.assertEqual(case.fire_tab, TAB_B1)
        self.assertIsNone(case.building_type_code)  # 舊細類代碼清掉
        self.assertEqual(case.vehicle_wildfire_code, 0)
        self.assertEqual(case.fire_or_smoke, "有火")
        self.assertEqual(case.caller_role, "路人")

    def test_engine_switch_keeps_answers_and_remap_only_fills_blanks(self) -> None:
        engine = self._filled_case_engine(remapped={
            "fire_or_smoke": "只有煙",          # 已經有答案 → 不可蓋掉
            "vehicle_wildfire_code": 0,         # 空白 → 可以補
        })
        engine._switch_subcategory("透天厝", "汽車", 0.9)
        case = engine.case
        self.assertEqual(case.fire_tab, TAB_B1)
        self.assertEqual(case.sub_category, "汽車")
        self.assertEqual(case.fire_or_smoke, "有火")
        self.assertEqual(case.smoke_color, "黑色煙")
        self.assertEqual(case.caller_role, "路人")
        self.assertEqual(case.place_usage, "住家")


if __name__ == "__main__":
    unittest.main()
