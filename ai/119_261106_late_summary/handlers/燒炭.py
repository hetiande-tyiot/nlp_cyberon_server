"""
handlers/燒炭.py
━━━━━━━━━━━━━━━━
119 SOP — 燒炭次類別 Handler

照 1028 xlsx「17-燒炭OK」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["燒炭"]、
base._ask_ems_questions）。xlsx 備註另外要求：
  - 本人報案 → 報案人位置就是在現場，不用問
  - 炭盆尚未熄滅 → 提醒先讓炭盆熄滅、移除，注意自己安全
  - 患者還在裡面 → 提醒把患者移到通風位置，注意自己安全
  - 現場進入條件需要破門 → 改判緊急救援（加派消防車破門）
提醒不管答案是剛問到的、還是報案人前面就講過，都會處理；
破門則是報案人哪一句講到都會改判（每一題前後都檢查）。
OK 表的案類不用觸發情境（每題答完判斷情境、講固定的話），所以這裡沒有。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import (
    CHARCOAL_NOT_OUT,
    EMS_QUESTIONS,
    PATIENT_STILL_INSIDE,
    RELATION_SELF,
)

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


SHAO_TAN_QUESTIONS = EMS_QUESTIONS["燒炭"]

# xlsx 備註的提醒語
_CHARCOAL_REMINDER = "請先讓炭盆熄滅、移除，並注意您自己安全。"
_VENTILATE_REMINDER = "如果可以，請將患者移到通風位置，並注意您自己安全。"


class ShaoTanHandler(SubCategoryHandler):
    """燒炭次類別 Handler。"""

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in SHAO_TAN_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；問完呼吸做 OHCA 判定（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, SHAO_TAN_QUESTIONS)

    def _ems_question_needed(self, engine: "SopEngine119", item, fields) -> bool:
        """本人報案：報案人位置就是在現場（xlsx 備註），直接記下來，不用問。"""
        if (
            item.field == "caller_location"
            and engine.case.caller_relation == RELATION_SELF
            and not engine._is_field_filled("caller_location")
        ):
            with engine._case_lock:
                engine.case.caller_location = "在現場"
            engine._notify_case_update()
        return super()._ems_question_needed(engine, item, fields)

    def _after_ems_item(self, engine: "SopEngine119", item) -> None:
        """xlsx 備註：炭盆沒熄、患者還在裡面要提醒（破門改判見 _check_escalation）。"""
        case = engine.case
        if item.field == "charcoal_status" and case.charcoal_status == CHARCOAL_NOT_OUT:
            engine._say(_CHARCOAL_REMINDER)
        elif item.field == "patient_location" and case.patient_location == PATIENT_STILL_INSIDE:
            engine._say(_VENTILATE_REMINDER)

    def _check_escalation(self, engine: "SopEngine119") -> None:
        """xlsx 備註：現場進入條件需要破門 → 改判緊急救援。報案人哪一句講到都算。"""
        if engine.case.scene_access:
            self._maybe_escalate_break_in(engine, engine.case.scene_access)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """燒炭使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
