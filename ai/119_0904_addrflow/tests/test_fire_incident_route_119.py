"""
火警案類分析（單句分流）測試。

規格：docs/修改後_(all)火警垂片規格_關鍵要素與問句_0929.xlsx ＋ 火警流程圖
  地址確認後問「請問發生什麼事？是什麼東西在燒？」→ 直接分到垂片 A / B1 / B2 / C
  - 已知垂片就不問
  - 聽不清楚再問「不好意思，請您再說一次是什麼在燒？」
  - 問兩次仍分不出是哪種火災 → 先當成輕微火警（垂片 C）處理，
    並在 ImportantTag 記下「火災類型無法判斷，預設輕微火警」
"""

from __future__ import annotations

import unittest

from fire_tab_map_119 import (
    INCIDENT_Q,
    INCIDENT_REASK_Q,
    INCIDENT_STAGE,
    SAFETY_MESSAGE,
    TAB_A,
    TAB_B1,
    TAB_B2,
    TAB_C,
    UNRESOLVED_TAB_TAG,
    infer_tab,
)
from handlers.火警通用 import HuoJingGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119


class ScriptedIO(DialogueIO):
    """依序回答；每次被問時記下當下的問句與 flow_stage。"""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []
        self.stages_when_asked: list[str] = []
        self.engine: SopEngine119 | None = None

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError("測試回答已用盡")
        if self.engine is not None:
            self.stages_when_asked.append(self.engine.case.flow_stage)
        return self.answers.pop(0)


class FakeLLM:
    """
    只模擬本測試需要的 LLM 介面。
    tab_answers：caller_text → classify_fire_tab 的回傳值；未列出的回 None
    （模擬 LLM 判斷不出來，讓 handler 改用 infer_tab 的關鍵詞判斷）。
    extracted：caller_text → 每輪通用抽取的結果。
    """

    def __init__(
        self,
        tab_answers: dict[str, str | None] | None = None,
        extracted: dict[str, dict] | None = None,
        tab_raises: bool = False,
    ):
        self.tab_answers = tab_answers or {}
        self.extracted = extracted or {}
        self.tab_raises = tab_raises
        self.tab_calls: list[tuple[str, str | None]] = []

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None) -> dict:
        return dict(self.extracted.get(caller_text.strip(), {}))

    def classify_fire_tab(self, caller_text, question=None):
        self.tab_calls.append((caller_text, question))
        if self.tab_raises:
            raise RuntimeError("LLM 逾時")
        return self.tab_answers.get(caller_text.strip())

    def extract_address(self, caller_text, use_question=False, include_floor=True):
        return {}

    def check_fire_trigger_scenarios(self, caller_text, already_triggered):
        return []

    def generate_summary(self, transcript_texts, filled_fields):
        return "火災測試摘要"


def _make_engine(answers: list[str], llm: FakeLLM) -> tuple[SopEngine119, ScriptedIO]:
    io = ScriptedIO(answers)
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    io.engine = engine
    engine.case.main_category = "火警"
    return engine, io


def _asked(io: ScriptedIO) -> list[str]:
    return [m for m in io.messages if m in (INCIDENT_Q, INCIDENT_REASK_Q)]


class InferTabRuleTests(unittest.TestCase):
    """infer_tab：LLM 判斷不出來時改用的關鍵詞判斷。"""

    def test_each_tab(self) -> None:
        self.assertEqual(infer_tab("我家公寓燒起來了"), TAB_A)
        self.assertEqual(infer_tab("工廠冒很多煙"), TAB_A)
        self.assertEqual(infer_tab("我的機車燒起來"), TAB_B1)
        self.assertEqual(infer_tab("有一艘船在燒"), TAB_B1)
        self.assertEqual(infer_tab("山上雜草在燒"), TAB_B2)
        self.assertEqual(infer_tab("路邊空地燒起來"), TAB_B2)
        self.assertEqual(infer_tab("有人在燒垃圾"), TAB_C)
        self.assertEqual(infer_tab("警報器一直響"), TAB_C)

    def test_negated_part_is_ignored(self) -> None:
        self.assertEqual(infer_tab("不是房子啦，是車子"), TAB_B1)
        self.assertEqual(infer_tab("沒有看到火，是垃圾在燒"), TAB_C)

    def test_multiple_tabs_hit_returns_none(self) -> None:
        # 同時出現建築物和垃圾的關鍵詞 → 不自己猜，回傳 None 交給 LLM
        self.assertIsNone(infer_tab("房子旁邊的垃圾在燒"))

    def test_fire_truck_is_not_a_vehicle_fire(self) -> None:
        self.assertIsNone(infer_tab("快叫消防車來"))

    def test_unclear_returns_none(self) -> None:
        self.assertIsNone(infer_tab("好多煙，快點"))
        self.assertIsNone(infer_tab(""))

    def test_negation_without_punctuation_gives_up(self) -> None:
        # 語音轉文字沒斷句：整串被當成否定片段拿掉 → 不判斷，交給 LLM
        self.assertIsNone(infer_tab("不是房子是車子"))


class ClassifyFireTabLLMTests(unittest.TestCase):
    """LLMExtractor119.classify_fire_tab：檢查 LLM 的回答是否合法，不合法或出錯時改用關鍵詞判斷（不載入模型）。"""

    def _extractor(self, slots_result=None, raises: bool = False) -> LLMExtractor119:
        ext = object.__new__(LLMExtractor119)

        def fake_extract_slots(text, schema, rules, **kwargs):
            if raises:
                raise RuntimeError("LLM 逾時")
            return slots_result or {}

        ext.extract_slots = fake_extract_slots  # type: ignore[method-assign]
        return ext

    def test_llm_answer_is_used(self) -> None:
        self.assertEqual(self._extractor({"tab": "B2"}).classify_fire_tab("山頭冒煙"), TAB_B2)
        self.assertEqual(self._extractor({"tab": "b1"}).classify_fire_tab("車子燒起來"), TAB_B1)

    def test_invalid_llm_answer_falls_back_to_rules(self) -> None:
        ext = self._extractor({"tab": "D"})
        self.assertEqual(ext.classify_fire_tab("警報器在響"), TAB_C)

    def test_llm_null_and_rules_unclear_returns_none(self) -> None:
        self.assertIsNone(self._extractor({"tab": None}).classify_fire_tab("好多煙"))

    def test_llm_error_falls_back_to_rules(self) -> None:
        self.assertEqual(self._extractor(raises=True).classify_fire_tab("我家透天厝在燒"), TAB_A)

    def test_empty_text(self) -> None:
        self.assertIsNone(self._extractor({"tab": "A"}).classify_fire_tab("   "))


class ResolveTabFlowTests(unittest.TestCase):
    """handler._resolve_tab：問幾次、進哪張垂片、標記。"""

    def test_one_question_routes_to_each_tab(self) -> None:
        cases = {
            "我家公寓燒起來了": (TAB_A, 0, None),
            "我的機車燒起來": (TAB_B1, 1, 0),
            "山上雜草在燒": (TAB_B2, 1, 0),
            "有人在燒垃圾": (TAB_C, 1, 1),
        }
        for answer, (tab, incident_type, non_building) in cases.items():
            with self.subTest(answer=answer):
                llm = FakeLLM(tab_answers={answer: tab})
                engine, io = _make_engine([answer], llm)
                result = HuoJingGenericHandler()._resolve_tab(engine)
                self.assertEqual(result, tab)
                self.assertEqual(engine.case.fire_tab, tab)
                self.assertEqual(engine.case.fire_incident_type, incident_type)
                self.assertEqual(engine.case.non_building_fire, non_building)
                self.assertEqual(_asked(io), [INCIDENT_Q])
                self.assertEqual(io.stages_when_asked, [INCIDENT_STAGE])
                self.assertNotIn(UNRESOLVED_TAB_TAG, engine.case.ImportantTag)

    def test_llm_none_uses_keyword_rules(self) -> None:
        llm = FakeLLM()  # LLM 一律回 None
        engine, io = _make_engine(["我的汽車冒煙"], llm)
        self.assertEqual(HuoJingGenericHandler()._resolve_tab(engine), TAB_B1)
        self.assertEqual(_asked(io), [INCIDENT_Q])

    def test_llm_error_uses_keyword_rules(self) -> None:
        llm = FakeLLM(tab_raises=True)
        engine, io = _make_engine(["警報器一直響"], llm)
        self.assertEqual(HuoJingGenericHandler()._resolve_tab(engine), TAB_C)

    def test_known_tab_skips_question(self) -> None:
        llm = FakeLLM()
        engine, io = _make_engine([], llm)
        engine.case.fire_incident_type = 1
        engine.case.vehicle_wildfire_code = 1  # 報地址時已說「機車燒起來」
        self.assertEqual(HuoJingGenericHandler()._resolve_tab(engine), TAB_B1)
        self.assertEqual(_asked(io), [])
        self.assertEqual(llm.tab_calls, [])

    def test_known_building_skips_question(self) -> None:
        llm = FakeLLM()
        engine, io = _make_engine([], llm)
        engine.case.fire_incident_type = 0
        self.assertEqual(HuoJingGenericHandler()._resolve_tab(engine), TAB_A)
        self.assertEqual(_asked(io), [])

    def test_answer_extraction_fills_codes_without_llm_route(self) -> None:
        # 每一輪的欄位抽取已經從回答裡記下「山地火警」→ 直接決定垂片，不用再請 LLM 判斷
        answer = "山上那邊整片在燒"
        llm = FakeLLM(extracted={answer: {"fire_incident_type": 1,
                                           "non_building_fire": 0,
                                           "vehicle_wildfire_code": 8}})
        engine, io = _make_engine([answer], llm)
        self.assertEqual(HuoJingGenericHandler()._resolve_tab(engine), TAB_B2)
        self.assertEqual(llm.tab_calls, [])

    def test_unclear_first_answer_reasks_once(self) -> None:
        llm = FakeLLM(tab_answers={"是機車": TAB_B1})
        engine, io = _make_engine(["好多煙，快點", "是機車"], llm)
        self.assertEqual(HuoJingGenericHandler()._resolve_tab(engine), TAB_B1)
        self.assertEqual(_asked(io), [INCIDENT_Q, INCIDENT_REASK_Q])
        self.assertEqual(io.stages_when_asked, [INCIDENT_STAGE, INCIDENT_STAGE])
        self.assertNotIn(UNRESOLVED_TAB_TAG, engine.case.ImportantTag)

    def test_still_unclear_falls_back_to_minor_fire_with_tag(self) -> None:
        llm = FakeLLM()
        engine, io = _make_engine(["好多煙，快點", "我也不知道啦"], llm)
        self.assertEqual(HuoJingGenericHandler()._resolve_tab(engine), TAB_C)
        self.assertEqual(engine.case.fire_tab, TAB_C)
        self.assertEqual(engine.case.fire_incident_type, 1)
        self.assertEqual(engine.case.non_building_fire, 1)
        self.assertEqual(_asked(io), [INCIDENT_Q, INCIDENT_REASK_Q])
        self.assertIn(UNRESOLVED_TAB_TAG, engine.case.ImportantTag)
        self.assertEqual(engine.case.ImportantCase, 1)

    def test_old_route_questions_are_not_asked(self) -> None:
        llm = FakeLLM()
        engine, io = _make_engine(["好多煙，快點", "我也不知道啦"], llm)
        HuoJingGenericHandler()._resolve_tab(engine)
        for msg in io.messages:
            self.assertNotIn("房子在燒嗎", msg)
            self.assertNotIn("草木在燒", msg)


class GenericFlowEndToEndTests(unittest.TestCase):
    """run_generic_flow：案類分析接到垂片問題，最後播安全提示。"""

    def test_subtype_known_from_incident_answer_goes_straight_to_safety(self) -> None:
        # 「我的機車燒起來」→ B1 且細類已知 → B1 細類題跳過 → 安全提示
        answer = "我的機車燒起來"
        llm = FakeLLM(
            tab_answers={answer: TAB_B1},
            extracted={answer: {"fire_incident_type": 1,
                                "non_building_fire": 0,
                                "vehicle_wildfire_code": 1}},
        )
        engine, io = _make_engine([answer], llm)
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.fire_tab, TAB_B1)
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertFalse(io.answers)

    def test_tab_known_but_subtype_unknown_asks_tab_question(self) -> None:
        # 「垃圾那邊」→ C 但細類未抽到 → 問 C 垂片細類題，再播安全提示
        llm = FakeLLM(tab_answers={"有東西在燒，好像是輕微的": TAB_C})
        engine, io = _make_engine(["有東西在燒，好像是輕微的", "警報器在響"], llm)
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.fire_tab, TAB_C)
        self.assertEqual(_asked(io), [INCIDENT_Q])
        self.assertEqual(io.messages[-1], SAFETY_MESSAGE)
        self.assertEqual(len(io.messages), 3)  # 案類分析、C 細類題、安全提示


if __name__ == "__main__":
    unittest.main()
