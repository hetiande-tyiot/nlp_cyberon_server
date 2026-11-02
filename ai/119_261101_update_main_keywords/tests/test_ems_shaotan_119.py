"""
救護燒炭照 xlsx 題目表重寫後的測試。

規格：docs/(all)救護垂片規格_關鍵要素與問句_1028.xlsx 的「17-燒炭OK」
  - 主動題：還不知道才問；條件題：前置條件確定成立、而且還不知道才問
  - 本人報案：報案人位置就是在現場，不用問
  - 報案人在現場 → 問患者所在位置；不在現場 → 問現場進入條件
  - 炭盆尚未熄滅、患者還在裡面 → 講提醒（答案是前面就講過的也要講）
  - 需要破門 → 改判緊急救援
  - 意識清醒 → 不問呼吸；不清醒、沒有呼吸 → OHCA 轉人工
  - 不用觸發情境：不會講 xlsx 沒有的話

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過、提醒、改判」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import unittest
from pathlib import Path

import openpyxl

from ems_tab_map_119 import EMS_QUESTIONS
from handlers.燒炭 import ShaoTanHandler
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError
from sop_element_id_119 import PENDING_ANSWER, sop_element_ids

QUESTIONS = EMS_QUESTIONS["燒炭"]
CHARCOAL_REMINDER = "請先讓炭盆熄滅、移除，並注意您自己安全。"
VENTILATE_REMINDER = "如果可以，請將患者移到通風位置，並注意您自己安全。"
BREAK_IN_LINE = "這需要破門，我已為您加派消防車前往。"


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

    def generate_summary(self, transcript_texts, filled_fields):
        return "燒炭測試摘要"


def _run(steps: list[tuple[str, dict]], **prefilled):
    """已經知道是燒炭，直接從題目表第一題開始。steps：依實際被問的順序排列的 (回答, 抽出的欄位)。"""
    io = ScriptedIO([answer for answer, _ in steps])
    engine = SopEngine119(io=io, llm_extractor=FakeLLM(dict(steps)))  # type: ignore[arg-type]
    engine.case.main_category = "救護"
    engine.case.sub_category = "燒炭"
    for key, value in prefilled.items():
        setattr(engine.case, key, value)
    ShaoTanHandler().run_subtype_flow(engine)
    return engine, io


def _asked(io: ScriptedIO) -> list[str]:
    """AI 說過的話換成「問了哪些關鍵要素」；提醒語、破門也照順序列出來。"""
    by_question = {item.question: item.element for item in QUESTIONS if item.question}
    others = {CHARCOAL_REMINDER: "提醒熄滅炭盆", VENTILATE_REMINDER: "提醒移到通風處",
              BREAK_IN_LINE: "改判破門"}
    return [by_question.get(m) or others[m] for m in io.messages
            if m in by_question or m in others]


ON_SCENE = ("我在現場", {"caller_location": "在現場"})
NOT_THERE = ("我不在那邊，我在外面", {"caller_location": "不在現場"})
OUT = ("已經熄了", {"charcoal_status": "已滅火"})
NOT_OUT = ("還在燒", {"charcoal_status": "尚未熄滅"})
OUTSIDE = ("我把他拖出來了", {"patient_location": "已在外面"})
INSIDE = ("還在房間裡面", {"patient_location": "還在裡面"})
FAMILY = ("我是他哥哥", {"caller_relation": "家人"})
PASSER = ("我是路過的", {"caller_relation": "路過"})
MALE_30 = ("男生，三十歲", {"patient_gender": "男性", "patient_age": "30歲"})
AWAKE = ("他醒著", {"consciousness_level": "意識清醒"})
COMA = ("叫不醒", {"consciousness_level": "昏迷"})
BREATHING = ("有在呼吸", {"breathing": True})
NO_BREATHING = ("沒有呼吸了", {"breathing": False})
DOOR_OPEN = ("門沒鎖，進得去", {"scene_access": "門沒鎖，進得去"})
BREAK_IN = ("門反鎖了，要破門", {"scene_access": "需要破門"})


class ShaoTanFlowTests(unittest.TestCase):

    def test_on_scene_family_awake(self) -> None:
        """在現場、家人、清醒：問患者所在位置、不問現場進入條件；清醒不問呼吸。"""
        engine, io = _run([ON_SCENE, OUT, OUTSIDE, FAMILY, MALE_30, AWAKE])
        self.assertEqual(_asked(io), [
            "報案人位置", "炭盆狀況", "患者所在位置", "報案身分", "性別", "意識",
        ])
        self.assertFalse(engine.case.is_ohca)

    def test_reminders_right_after_answers(self) -> None:
        """炭盆還在燒、患者還在裡面：答完緊接著講提醒。"""
        _, io = _run([ON_SCENE, NOT_OUT, INSIDE, FAMILY, MALE_30, AWAKE])
        self.assertEqual(_asked(io), [
            "報案人位置", "炭盆狀況", "提醒熄滅炭盆", "患者所在位置", "提醒移到通風處",
            "報案身分", "性別", "意識",
        ])

    def test_reminder_when_answer_known_before(self) -> None:
        """報案人前面就說炭盆還在燒：這題不問，提醒照講。"""
        _, io = _run([ON_SCENE, OUTSIDE, FAMILY, MALE_30, AWAKE], charcoal_status="尚未熄滅")
        self.assertEqual(_asked(io)[:3], ["報案人位置", "提醒熄滅炭盆", "患者所在位置"])

    def test_not_on_scene_passer_by(self) -> None:
        """不在現場、路過：問現場進入條件；不問炭盆、患者位置、性別年齡、意識、呼吸。"""
        engine, io = _run([NOT_THERE, DOOR_OPEN, PASSER])
        self.assertEqual(_asked(io), ["報案人位置", "現場進入條件", "報案身分"])
        self.assertEqual(engine.case.main_category, "救護")

    def test_break_in_escalates_to_emergency(self) -> None:
        """需要破門：改判緊急救援，流程繼續問完。"""
        engine, io = _run([NOT_THERE, BREAK_IN, PASSER])
        self.assertEqual(_asked(io), [
            "報案人位置", "現場進入條件", "改判破門", "報案身分",
        ])
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_caller_is_patient(self) -> None:
        """本人報案：報案人位置記在現場、不問；本人不問意識。"""
        engine, io = _run([OUT, OUTSIDE, MALE_30], caller_relation="本人")
        self.assertEqual(_asked(io), ["炭盆狀況", "患者所在位置", "性別"])
        self.assertEqual(engine.case.caller_location, "在現場")

    def test_unresponsive_breathing_continues(self) -> None:
        engine, io = _run([ON_SCENE, OUT, OUTSIDE, FAMILY, MALE_30, COMA, BREATHING])
        self.assertEqual(_asked(io)[-2:], ["意識", "呼吸"])
        self.assertFalse(engine.case.is_ohca)

    def test_unresponsive_not_breathing_is_ohca(self) -> None:
        with self.assertRaises(TransferToHumanError):
            engine, _ = _run([ON_SCENE, OUT, OUTSIDE, FAMILY, MALE_30, COMA, NO_BREATHING])

    def test_no_trigger_lines(self) -> None:
        """不用觸發情境：沒呼吸以外，也不會講 xlsx 沒有的話（例如「打開大門在家休息」）。"""
        _, io = _run([ON_SCENE, NOT_OUT, INSIDE, FAMILY, MALE_30, COMA, BREATHING])
        known = {item.question for item in QUESTIONS} | {CHARCOAL_REMINDER, VENTILATE_REMINDER}
        self.assertEqual([m for m in io.messages if m not in known], [])


class ShaoTanElementIdTests(unittest.TestCase):

    def test_table_matches_case_type_qa(self) -> None:
        """題目表跟程式讀的 CaseTypeQA.xlsx 燒炭那幾列，逐題對得上（題號靠位置算）。"""
        path = Path(__file__).resolve().parents[1] / "scripts" / "CaseTypeQA.xlsx"
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        rows = [r for r in ws.iter_rows(values_only=True) if r[1] == "救護-燒炭"]
        self.assertEqual([r[5] for r in rows], [item.element for item in QUESTIONS])

    def test_pending_questions_sent_to_frontend(self) -> None:
        """在現場、還沒問到報案身分：該問的題目給「待問」，不用問的不給。"""
        io = ScriptedIO([])
        engine = SopEngine119(io=io)
        engine.case.main_category = "救護"
        engine.case.sub_category = "燒炭"
        engine.case.caller_location = "在現場"
        engine.case.charcoal_status = "已滅火"
        ids = sop_element_ids(engine.case.to_dict())
        self.assertEqual(ids["217-1"], "在現場")
        self.assertEqual(ids["217-2"], "已滅火")
        self.assertNotIn("217-3", ids)               # 在現場 → 不問現場進入條件
        self.assertEqual(ids["217-4"], PENDING_ANSWER)  # 在現場 → 要問患者所在位置
        self.assertEqual(ids["217-5"], PENDING_ANSWER)  # 報案身分是主動題


if __name__ == "__main__":
    unittest.main()
