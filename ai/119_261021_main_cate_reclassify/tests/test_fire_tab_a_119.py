"""
垂片 A（建築物火警）照 xlsx 重寫後的測試。

規格：docs/(all)火警垂片規格_關鍵要素與問句_1013.xlsx 的「01-垂片A_建築物火警」
  - 1013 版：第一題改問場所用途；建築物類型依是不是工廠分兩種問法；
    起火樓層「不是工廠，而且看得到火」才問；工廠看得到火改問燃燒物；拿掉氣味
  - 無火無煙 → 換到輕微火警（C）；A、C 之間只看火煙狀況，BERT 和 LLM 不能自己換
  - 主動題：還不知道才問
  - 條件題：前置條件確定成立才問；不確定就不問
  - 被動題：不問，報案人講到才記
  - 有人受困：火警流程任何時候講出來都立刻轉人工
  - 換垂片：報案人已經回答過的內容全部保留

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
    TAB_B1,
    TAB_C,
    TAB_C_QUESTIONS,
    TRAPPED_TRANSFER_MESSAGE,
    apply_subtype_identity_codes,
    tab_conflicts_with_fire_smoke,
)
from handlers.火警通用 import HuoJingGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

# 垂片 A 各題的問句（取自題目表，xlsx 改問句時測試不必跟著改）。
# 建築物類型有兩種問法，Q 只記得其中一種，所以另外用「問句 → 關鍵要素」對照
Q = {item.element: item.question for item in TAB_A_QUESTIONS}
QUESTION_NOT_FACTORY = TAB_A_QUESTIONS[1].question   # 是公寓還是大樓？
QUESTION_FACTORY = TAB_A_QUESTIONS[2].question       # 現場是什麼用途？
ELEMENT_BY_QUESTION = {
    item.question: f"{label}{item.element}"
    for label, questions in (("", TAB_A_QUESTIONS), ("C:", TAB_C_QUESTIONS))
    for item in questions if item.question
}
# A、C 共用同一句問句的題目（場所用途、建築物類型…）以 A 的名稱顯示
ELEMENT_BY_QUESTION.update({
    item.question: item.element for item in TAB_A_QUESTIONS if item.question
})


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


class StubbornBERT:
    """不管聽到什麼，都很有把握地說同一個次案類（用來測試 BERT 會不會被擋住）。"""

    def __init__(self, label: str):
        self.label = label

    def predict(self, text, main_cat):
        others = {"透天厝": 0.03, "警報器作響": 0.02}
        others.pop(self.label, None)
        return types.SimpleNamespace(
            final_label=self.label, classifier_conf=0.95,
            all_probs={self.label: 0.95, **others},
        )


def _building_fire_engine(
    answers: list[str], extracted: dict[str, dict], bert: str | None = None, **prefilled
) -> tuple[SopEngine119, ScriptedIO]:
    """已經知道是建築物火警（不問案類分析），直接從垂片 A 第一題開始。"""
    io = ScriptedIO(answers)
    engine = SopEngine119(io=io, llm_extractor=FakeLLM(extracted))  # type: ignore[arg-type]
    io.engine = engine
    engine._sub_clf = StubbornBERT(bert) if bert else None
    engine.case.main_category = "火警"
    engine.case.fire_tab = TAB_A  # 已經在垂片 A
    for key, value in prefilled.items():
        setattr(engine.case, key, value)
    return engine, io


def _run(steps: list[tuple[str, dict]], **kwargs) -> tuple[SopEngine119, ScriptedIO]:
    """steps：依「實際被問的順序」排列的 (報案人回答, LLM 抽出的欄位)，每一句回答都不重複。"""
    engine, io = _building_fire_engine(
        [answer for answer, _ in steps], {answer: out for answer, out in steps}, **kwargs,
    )
    HuoJingGenericHandler().run_generic_flow(engine)
    return engine, io


def _asked_elements(io: ScriptedIO) -> list[str]:
    """把 AI 說過的話換成「問了哪些關鍵要素」，方便比對順序；C 的題目前面標「C:」。"""
    return [ELEMENT_BY_QUESTION[m] for m in io.messages if m in ELEMENT_BY_QUESTION]


# 一通「住宅、透天厝、三層樓、有火有煙、黑煙、二樓、沒有受困」的標準回答（依被問的順序）
HOUSE = ("住宅", {"place_usage": "住宅"})
TOWNHOUSE = ("透天的", {"building_type_code": "10"})
THREE_FLOORS = ("三層樓", {"building_total_floors": "3層樓"})
FIRE_AND_SMOKE = ("火很大，煙也很多", {"fire_or_smoke": "有火有煙"})
BLACK = ("黑煙", {"smoke_color": "黑色煙"})
SECOND_FLOOR = ("二樓", {"fire_floor": "2樓"})
NO_SPREAD = ("還好沒燒過去", {"spread_status": "延燒可能性低"})
NEIGHBOR = ("我是隔壁鄰居", {"caller_role": "鄰居"})
ALL_OUT = ("人都出來了", {"trapped_status": "無人受困"})
TOWNHOUSE_CALL = [
    HOUSE, TOWNHOUSE, THREE_FLOORS, FIRE_AND_SMOKE, BLACK, SECOND_FLOOR,
    NO_SPREAD, NEIGHBOR, ALL_OUT,
]
HEAD = ["場所用途", "建築物類型", "建物總樓層", "火煙狀況"]
TAIL = ["報案人身分", "有無受困"]


class TabAQuestionOrderTests(unittest.TestCase):

    def test_house_with_fire_asks_in_xlsx_order(self) -> None:
        engine, io = _run(TOWNHOUSE_CALL)
        self.assertEqual(
            _asked_elements(io), HEAD + ["濃煙顏色", "起火樓層", "延燒可能"] + TAIL,
        )
        # 透天厝不問構造、危險物品；有火不問氣味；沒人受困不問應門
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.sub_category, "透天厝")
        self.assertEqual(engine.case.building_type, "透天厝")
        self.assertEqual(engine.case.fire_or_smoke, "有火有煙")

    def test_not_factory_asks_apartment_or_building(self) -> None:
        _, io = _run(TOWNHOUSE_CALL)
        self.assertIn(QUESTION_NOT_FACTORY, io.messages)
        self.assertNotIn(QUESTION_FACTORY, io.messages)

    def test_stage_names_use_building_fire_prefix(self) -> None:
        _, io = _run(TOWNHOUSE_CALL)
        self.assertEqual(io.stages_when_asked[:3], [
            "建築物火警-場所用途", "建築物火警-建築物類型", "建築物火警-建物總樓層",
        ])

    def test_known_answers_are_not_asked_again(self) -> None:
        steps = [s for s in TOWNHOUSE_CALL if s not in (HOUSE, NEIGHBOR)]
        engine, io = _run(steps, place_usage="住宅", caller_role="路人")
        asked = _asked_elements(io)
        self.assertNotIn("場所用途", asked)
        self.assertNotIn("報案人身分", asked)
        self.assertEqual(engine.case.caller_role, "路人")

    def test_subtype_known_from_bert_skips_building_type(self) -> None:
        # BERT 一開始就有把握說集合住宅 → 建築物類型已知，不問「公寓還是大樓」
        steps = [s for s in TOWNHOUSE_CALL if s is not TOWNHOUSE]
        engine, io = _run(steps, bert="集合住宅")
        self.assertNotIn("建築物類型", _asked_elements(io))
        self.assertEqual(engine.case.building_type, "集合住宅")


class FactoryTests(unittest.TestCase):

    def _factory_call(self, building: tuple[str, dict], extra: list[tuple[str, dict]]):
        return _run([
            ("是工廠", {"place_usage": "工廠"}),
            building,
            ("兩層", {"building_total_floors": "2層樓"}),
            FIRE_AND_SMOKE, BLACK,
            ("好像是紙箱", {"burning_object": "紙箱"}),
            NO_SPREAD,
            ("我是管理員", {"caller_role": "管理員或警衛"}),
            ALL_OUT,
            *extra,
        ])

    def test_factory_asks_usage_and_burning_object_not_fire_floor(self) -> None:
        engine, io = self._factory_call(("放貨的倉庫", {"building_type_code": "12"}), [])
        self.assertEqual(_asked_elements(io), HEAD + [
            "濃煙顏色", "燃燒物", "延燒可能",
        ] + TAIL)
        self.assertIn(QUESTION_FACTORY, io.messages)
        self.assertEqual(engine.case.sub_category, "倉庫")
        self.assertEqual(engine.case.burning_object, "紙箱")

    def test_illegal_building_or_market_asks_construction_and_hazards(self) -> None:
        _, io = self._factory_call(
            ("鐵皮違建工廠", {"building_type_code": "25"}),
            [("是鐵皮的", {"building_construction": "鐵皮屋"}),
             ("有瓦斯桶", {"hazardous_materials": "有（瓦斯桶）"})],
        )
        self.assertEqual(_asked_elements(io)[-2:], ["建物構造", "危險物品"])

    def test_warehouse_does_not_ask_construction_or_hazards(self) -> None:
        # 1013 版：建物構造、危險物品只看「大型違章建築區與傳統市場(含工廠)」，倉庫不問
        _, io = self._factory_call(("放貨的倉庫", {"building_type_code": "12"}), [])
        self.assertNotIn("建物構造", _asked_elements(io))
        self.assertNotIn("危險物品", _asked_elements(io))


class FireSmokeConditionTests(unittest.TestCase):
    """火煙狀況的 6 種回答，各自追問哪些題（無火無煙另外測換垂片）。"""

    def _asked(self, fire_answer: tuple[str, str], after_fire: list[tuple[str, dict]]):
        _, io = _run([
            HOUSE, TOWNHOUSE, THREE_FLOORS,
            (fire_answer[0], {"fire_or_smoke": fire_answer[1]}),
            *after_fire, NEIGHBOR, ALL_OUT,
        ])
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        return _asked_elements(io)

    def test_fire_and_smoke_asks_color_floor_spread(self) -> None:
        asked = self._asked(("火很大，煙也很多", "有火有煙"), [BLACK, SECOND_FLOOR, NO_SPREAD])
        self.assertEqual(asked, HEAD + ["濃煙顏色", "起火樓層", "延燒可能"] + TAIL)

    def test_fire_no_smoke_skips_color(self) -> None:
        asked = self._asked(("有火，沒什麼煙", "有火無煙"), [SECOND_FLOOR, NO_SPREAD])
        self.assertEqual(asked, HEAD + ["起火樓層", "延燒可能"] + TAIL)

    def test_smoke_no_fire_asks_color_only(self) -> None:
        # 看不到火 → 不問起火樓層、延燒可能
        asked = self._asked(("只看到煙", "無火有煙"), [BLACK])
        self.assertEqual(asked, HEAD + ["濃煙顏色"] + TAIL)

    def test_spark_only_skips_follow_ups_and_stays(self) -> None:
        asked = self._asked(("只有在噴火花", "只有火花"), [])
        self.assertEqual(asked, HEAD + TAIL)

    def test_unsure_skips_follow_ups_and_stays(self) -> None:
        asked = self._asked(("我人不在現場，不知道", "不確定"), [])
        self.assertEqual(asked, HEAD + TAIL)


class MoveBetweenBuildingAndMinorTests(unittest.TestCase):
    """建築物火警（A）和輕微火警（C）之間，只看火煙狀況換垂片。"""

    def test_no_fire_no_smoke_moves_to_minor_fire(self) -> None:
        engine, io = _run([
            HOUSE, TOWNHOUSE, THREE_FLOORS,
            ("火跟煙都沒看到", {"fire_or_smoke": "無火無煙"}),
            ("警報器在響", {"minor_fire_code": 3}),
            ("還在響", {"alarm_status": "仍在響"}),
            ("有燒焦味", {"odor": "燒焦味"}),
            ("我住這裡", {"caller_role": "住戶"}),
            ("沒聽到", {"trapped_status": "無人受困"}),
            ("不知道哪一戶", {"source_located": "聞得到但找不到來源"}),
        ])
        # 換到 C 後先問火警類型；建築物資料帶過去，不重問
        self.assertEqual(_asked_elements(io), HEAD + [
            "C:火警類型", "C:警報器狀態", "C:氣味類型", "C:報案人身分", "C:有無受困", "C:來源確認",
        ])
        self.assertEqual(engine.case.fire_tab, TAB_C)
        self.assertEqual(engine.case.sub_category, "警報器作響")
        self.assertEqual(engine.case.building_type, "透天厝")
        self.assertEqual(engine.case.building_total_floors, "3層樓")

    def test_bert_cannot_pull_building_fire_to_minor_fire(self) -> None:
        # BERT 一直說警報器作響，但有火有煙 → 留在 A
        engine, _ = _run(TOWNHOUSE_CALL, bert="警報器作響")
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.sub_category, "透天厝")

    def test_llm_alarm_code_does_not_pull_building_fire_to_minor_fire(self) -> None:
        steps = list(TOWNHOUSE_CALL)
        steps[3] = ("火很大，警報器也在響", {"fire_or_smoke": "有火有煙", "minor_fire_code": 3})
        engine, _ = _run(steps)
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.sub_category, "透天厝")

    def test_conflict_rule(self) -> None:
        self.assertTrue(tab_conflicts_with_fire_smoke(TAB_A, "透天厝", "無火無煙"))
        self.assertTrue(tab_conflicts_with_fire_smoke(TAB_C, "警報器作響", "無火有煙"))
        self.assertTrue(tab_conflicts_with_fire_smoke(TAB_C, "查看案件", "有火有煙"))
        # 垃圾、電線桿有火照樣留在 C；只有火花、不確定都不換
        self.assertFalse(tab_conflicts_with_fire_smoke(TAB_C, "垃圾", "有火有煙"))
        self.assertFalse(tab_conflicts_with_fire_smoke(TAB_C, "警報器作響", "只有火花"))
        self.assertFalse(tab_conflicts_with_fire_smoke(TAB_A, "透天厝", "不確定"))
        self.assertFalse(tab_conflicts_with_fire_smoke(TAB_B1, "汽車", "無火無煙"))


class PeopleTrappedTransferTests(unittest.TestCase):

    def test_trapped_answer_transfers_immediately(self) -> None:
        with self.assertRaises(TransferToHumanError) as ctx:
            _run([
                HOUSE, TOWNHOUSE, THREE_FLOORS, FIRE_AND_SMOKE, BLACK, SECOND_FLOOR,
                ("會", {"spread_status": "極可能或已延燒"}),
                ("三樓還有阿嬤出不來", {"trapped_status": "有人受困"}),
            ])
        self.assertEqual(ctx.exception.result, "human_transfer")

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
        steps = list(TOWNHOUSE_CALL)
        steps[-1] = ("不清楚", {"trapped_status": "不確定"})
        _, io = _run(steps)
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)


class PassiveAndFreeTextTests(unittest.TestCase):

    def test_passive_fields_are_recorded_but_never_asked(self) -> None:
        steps = list(TOWNHOUSE_CALL)
        steps[3] = ("火很大，煙也很多", {
            "fire_or_smoke": "有火有煙",
            "explosion_status": "有爆炸",
            "fire_extent": "整棟都在燒",
        })
        engine, io = _run(steps)
        self.assertEqual(engine.case.explosion_status, "有爆炸")
        self.assertEqual(engine.case.fire_extent, "整棟都在燒")
        for element in ("有無爆炸", "其他資訊", "延燒面積"):
            self.assertEqual(Q[element], "")  # 被動題在題目表裡沒有問句，AI 不會問

    def test_answer_outside_reference_range_is_kept(self) -> None:
        steps = list(TOWNHOUSE_CALL)
        steps[0] = ("是宮廟", {"place_usage": "宮廟"})
        engine, io = _run(steps)
        self.assertEqual(engine.case.place_usage, "宮廟")
        # 宮廟不是工廠 → 問「公寓還是大樓」
        self.assertIn(QUESTION_NOT_FACTORY, io.messages)


class FixedAnswerCheckTests(unittest.TestCase):
    """火煙狀況、有無受困：LLM 寫錯格式就不記（不載入模型，直接模擬 LLM 的輸出）。"""

    def _extract(self, llm_output: dict) -> dict:
        ext = object.__new__(LLMExtractor119)
        # 跳過初始化時要自己設定 backend；設成 gguf 讓欄位一組一組依序抽，不平行抽，測試結果才固定
        ext.backend = "gguf"
        ext.extract_slots = lambda *args, **kwargs: dict(llm_output)  # type: ignore[method-assign]
        # 指定垂片 A：只會抽垂片 A 用得到的欄位
        return ext.extract_general_fields("測試", "測試", main_category="火警", fire_tab="A")

    def test_valid_fixed_answers_are_kept(self) -> None:
        out = self._extract({"fire_or_smoke": "無火有煙", "trapped_status": "有人受困"})
        self.assertEqual(out["fire_or_smoke"], "無火有煙")
        self.assertEqual(out["trapped_status"], "有人受困")

    def test_wrong_format_is_dropped(self) -> None:
        # 「有火」是 1005 版以前的說法，現在不在固定說法裡
        out = self._extract({"fire_or_smoke": "有火", "trapped_status": "有人受困。"})
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
        case.fire_or_smoke = "有火有煙"
        case.smoke_color = "黑色煙"
        case.caller_role = "路人"
        case.place_usage = "住宅"
        return engine

    def test_switch_subtype_codes_keeps_answers(self) -> None:
        engine = self._filled_case_engine()
        apply_subtype_identity_codes(engine.case, "汽車", update_tab=True)
        case = engine.case
        self.assertEqual(case.fire_tab, TAB_B1)
        self.assertIsNone(case.building_type_code)  # 舊次案類代碼清掉
        self.assertEqual(case.vehicle_wildfire_code, 0)
        self.assertEqual(case.fire_or_smoke, "有火有煙")
        self.assertEqual(case.caller_role, "路人")

    def test_engine_switch_keeps_answers_and_remap_only_fills_blanks(self) -> None:
        engine = self._filled_case_engine(remapped={
            "fire_or_smoke": "無火有煙",        # 已經有答案 → 不可蓋掉
            "vehicle_wildfire_code": 0,         # 空白 → 可以補
        })
        engine._switch_subcategory("透天厝", "汽車", 0.9)
        case = engine.case
        self.assertEqual(case.fire_tab, TAB_B1)
        self.assertEqual(case.sub_category, "汽車")
        self.assertEqual(case.fire_or_smoke, "有火有煙")
        self.assertEqual(case.smoke_color, "黑色煙")
        self.assertEqual(case.caller_role, "路人")
        self.assertEqual(case.place_usage, "住宅")


if __name__ == "__main__":
    unittest.main()
