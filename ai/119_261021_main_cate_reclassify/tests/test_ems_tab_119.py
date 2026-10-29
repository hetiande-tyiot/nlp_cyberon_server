"""
救護急病、燒燙傷照 xlsx 題目表重寫後的測試。

規格：docs/(all)救護垂片規格_關鍵要素與問句_1018.xlsx 的「01-急病」「08-燒燙傷OK」
規則跟火警垂片一樣：
  - 主動題：還不知道才問
  - 條件題：前置條件確定成立、而且還不知道才問
  - 被動題：不問
  - 燒燙傷的年齡沒有問句，跟性別那一題一起問
OHCA：問完呼吸，呼吸不是「有」就轉人工；急病先多問一次肚子有沒有起伏。

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import unittest

from ems_tab_map_119 import JI_BING_QUESTIONS, SHAO_TANG_SHANG_QUESTIONS
from handlers.急病 import JiBingHandler
from handlers.燒燙傷 import ShaoTangShangHandler
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError
from sop_element_id_119 import PENDING_ANSWER, sop_element_ids

ABDOMEN_QUESTION = "幫我看他的肚子有沒有一上、一下起伏。"


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


class FakeLLM:
    """extracted：報案人的每一句回答 → LLM 應該抽出的欄位（模擬 LLM 已正確理解語意）。"""

    def __init__(self, extracted: dict[str, dict]):
        self.extracted = extracted

    def extract_general_fields(self, caller_text, question=None, **_kwargs) -> dict:
        return dict(self.extracted.get(caller_text.strip(), {}))

    def extract_slots(self, *_args, **_kwargs) -> dict:
        return {}

    def extract_patient_info(self, *_args, **_kwargs) -> dict:
        return {}

    def check_trigger_scenarios(self, caller_text, already_triggered):
        return []

    def extract_address(self, *_args, **_kwargs):
        return {}

    def generate_summary(self, transcript_texts, filled_fields):
        return "救護測試摘要"


def _run(handler, sub_category: str, steps: list[tuple[str, dict]], **prefilled):
    """
    已經知道次案類，直接從題目表第一題開始。
    steps：依「實際被問的順序」排列的 (報案人回答, LLM 抽出的欄位)，每一句回答都不重複。
    """
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: out for answer, out in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    case = engine.case
    case.main_category = "救護"
    case.sub_category = sub_category
    for key, value in prefilled.items():
        setattr(case, key, value)
    handler.run_subtype_flow(engine)
    return engine, io


def _asked(io: ScriptedIO, questions) -> list[str]:
    by_question = {item.question: item.element for item in questions if item.question}
    return [by_question.get(m, m) for m in io.messages
            if m in by_question or m == ABDOMEN_QUESTION]


# ─── 急病 ────────────────────────────────────────────────────────────────────

CHEST_PAIN = ("他突然胸口痛", {"incident_description": "突然胸口痛"})
SON = ("我是他兒子", {"caller_relation": "家人"})
AWAKE = ("他人是清醒的", {"consciousness_level": "意識清醒"})
COMA = ("叫他都沒反應", {"consciousness_level": "昏迷"})
DONT_KNOW = ("我不知道耶", {"consciousness_level": "未知"})
NOT_THERE = ("我不在他旁邊", {"caller_location": "不在現場"})
MALE = ("男生", {"patient_gender": "男"})
AGE_70 = ("七十歲", {"patient_age": "70歲"})
BREATHING = ("有在呼吸", {"breathing": True})
NO_BREATHING = ("好像沒有呼吸了", {"breathing": False})
NO_RISE = ("肚子也沒有在動", {"abdomen_rise": False})


def _run_ji_bing(steps, **prefilled):
    return _run(JiBingHandler(), "急病", steps, **prefilled)


class JiBingQuestionTests(unittest.TestCase):

    def test_awake_patient_asks_active_questions_in_xlsx_order(self) -> None:
        engine, io = _run_ji_bing([CHEST_PAIN, SON, AWAKE, MALE, AGE_70])
        self.assertEqual(_asked(io, JI_BING_QUESTIONS), [
            "病徵", "報案人與患者關係", "意識", "性別", "年齡",
        ])
        self.assertIs(engine.case.consciousness, True)  # 由意識程度補上，OHCA 用
        self.assertFalse(engine.case.is_ohca)

    def test_passive_questions_are_never_asked(self) -> None:
        _, io = _run_ji_bing([CHEST_PAIN, SON, AWAKE, MALE, AGE_70])
        passive = [item.question for item in JI_BING_QUESTIONS if item.mode == "被動"]
        self.assertTrue(passive)
        for question in passive:
            self.assertNotIn(question, io.messages)

    def test_unknown_consciousness_asks_caller_location_not_breathing(self) -> None:
        _, io = _run_ji_bing([CHEST_PAIN, SON, DONT_KNOW, NOT_THERE, MALE, AGE_70])
        self.assertEqual(_asked(io, JI_BING_QUESTIONS), [
            "病徵", "報案人與患者關係", "意識", "報案人是否在場", "性別", "年齡",
        ])

    def test_unresponsive_and_breathing_continues(self) -> None:
        engine, io = _run_ji_bing([CHEST_PAIN, SON, COMA, MALE, BREATHING, AGE_70])
        self.assertEqual(_asked(io, JI_BING_QUESTIONS), [
            "病徵", "報案人與患者關係", "意識", "性別", "呼吸", "年齡",
        ])
        self.assertFalse(engine.case.is_ohca)

    def test_unresponsive_and_not_breathing_checks_abdomen_then_ohca(self) -> None:
        with self.assertRaises(TransferToHumanError):
            _run_ji_bing([CHEST_PAIN, SON, COMA, MALE, NO_BREATHING, NO_RISE])

    def test_consciousness_already_known_is_not_asked_again(self) -> None:
        _, io = _run_ji_bing([CHEST_PAIN, SON, MALE, AGE_70], consciousness=True)
        self.assertNotIn("意識", _asked(io, JI_BING_QUESTIONS))

    def test_vague_description_is_asked_again(self) -> None:
        _, io = _run_ji_bing(
            [CHEST_PAIN, SON, AWAKE, MALE, AGE_70], incident_description="身體不舒服",
        )
        self.assertEqual(_asked(io, JI_BING_QUESTIONS)[0], "病徵")


class JiBingElementIdTests(unittest.TestCase):

    def test_pending_marks_follow_conditions(self) -> None:
        engine, _ = _run_ji_bing([CHEST_PAIN, SON, DONT_KNOW, NOT_THERE, MALE, AGE_70])
        ids = sop_element_ids(engine.case.to_dict())
        self.assertEqual(ids["201-1"], "突然胸口痛")
        self.assertEqual(ids["201-3"], "未知")
        self.assertEqual(ids["201-4"], "不在現場")
        self.assertNotIn("201-6", ids)   # 被動題沒人講到 → 不放
        self.assertNotIn("201-8", ids)   # 意識未知 → 不問呼吸

    def test_unanswered_active_question_is_pending(self) -> None:
        case = SopEngine119(io=ScriptedIO([])).case
        case.main_category = "救護"
        case.sub_category = "急病"
        case.consciousness_level = "昏迷"
        ids = sop_element_ids(case.to_dict())
        self.assertEqual(ids["201-1"], PENDING_ANSWER)
        self.assertEqual(ids["201-8"], PENDING_ANSWER)  # 昏迷 → 要問呼吸
        self.assertNotIn("201-4", ids)


# ─── 燒燙傷 ──────────────────────────────────────────────────────────────────

HOT_WATER = ("被熱水燙到", {"injury_cause": "熱水"})
BLISTER = ("手臂起水泡，一個巴掌大", {"injury_severity": "起水泡，一個巴掌大"})
MOM = ("是我媽媽", {"caller_relation": "家人"})
SELF = ("是我自己", {"caller_relation": "本人"})
PASSERBY = ("我路過看到的", {"caller_relation": "路過"})
FEMALE_60 = ("女生，六十歲", {"patient_gender": "女", "patient_age": "60歲"})
BURN_AWAKE = ("她很清醒", {"consciousness_level": "意識清醒"})
BURN_COMA = ("叫不醒", {"consciousness_level": "昏迷"})
BURN_NO_BREATHING = ("沒有呼吸", {"breathing": False})


def _run_burn(steps, **prefilled):
    return _run(ShaoTangShangHandler(), "燒燙傷", steps, **prefilled)


class ShaoTangShangQuestionTests(unittest.TestCase):

    def test_family_caller_asks_in_xlsx_order(self) -> None:
        engine, io = _run_burn([HOT_WATER, BLISTER, MOM, FEMALE_60, BURN_AWAKE])
        self.assertEqual(_asked(io, SHAO_TANG_SHANG_QUESTIONS), [
            "燒燙傷原因", "燙傷傷勢", "報案身分", "性別", "意識",
        ])
        self.assertEqual(engine.case.patient_age, "60歲")  # 年齡跟性別一起問到
        self.assertFalse(engine.case.is_ohca)

    def test_caller_is_patient_skips_consciousness(self) -> None:
        _, io = _run_burn([HOT_WATER, BLISTER, SELF, FEMALE_60])
        self.assertEqual(_asked(io, SHAO_TANG_SHANG_QUESTIONS), [
            "燒燙傷原因", "燙傷傷勢", "報案身分", "性別",
        ])

    def test_passerby_skips_gender_but_asks_consciousness(self) -> None:
        _, io = _run_burn([HOT_WATER, BLISTER, PASSERBY, BURN_AWAKE])
        self.assertEqual(_asked(io, SHAO_TANG_SHANG_QUESTIONS), [
            "燒燙傷原因", "燙傷傷勢", "報案身分", "意識",
        ])

    def test_passerby_on_scene_is_asked_gender(self) -> None:
        _, io = _run_burn(
            [HOT_WATER, BLISTER, PASSERBY, FEMALE_60, BURN_AWAKE], caller_location="在現場",
        )
        self.assertIn("性別", _asked(io, SHAO_TANG_SHANG_QUESTIONS))

    def test_unresponsive_and_not_breathing_is_ohca_without_abdomen(self) -> None:
        # 回答只準備到呼吸：如果還去問肚子起伏，會因為回答用盡而失敗，不是轉人工
        with self.assertRaises(TransferToHumanError):
            _run_burn([HOT_WATER, BLISTER, MOM, FEMALE_60, BURN_COMA, BURN_NO_BREATHING])


class ShaoTangShangElementIdTests(unittest.TestCase):

    def test_passerby_pending_marks(self) -> None:
        case = SopEngine119(io=ScriptedIO([])).case
        case.main_category = "救護"
        case.sub_category = "燒燙傷"
        case.injury_cause = "熱水"
        case.caller_relation = "路過"
        ids = sop_element_ids(case.to_dict())
        self.assertEqual(ids["208-1"], "熱水")
        self.assertEqual(ids["208-2"], PENDING_ANSWER)
        self.assertEqual(ids["208-3"], "路過")
        self.assertNotIn("208-4", ids)   # 路過、位置沒講 → 不問性別
        self.assertNotIn("208-5", ids)
        self.assertEqual(ids["208-6"], PENDING_ANSWER)  # ≠本人、位置未提到 → 要問意識
        self.assertNotIn("208-7", ids)
        self.assertNotIn("208-8", ids)


if __name__ == "__main__":
    unittest.main()
