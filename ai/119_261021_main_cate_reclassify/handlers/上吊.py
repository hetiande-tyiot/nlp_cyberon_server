"""
handlers/上吊.py
━━━━━━━━━━━━━━━━
119 SOP — 上吊次類別 Handler

照 1028 xlsx「16-上吊OK」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["上吊"]、
base._ask_ems_questions）。xlsx 備註另外要求：
  - 破門需求 = 需要破門 → 緊急救援-破門（講廠商原句「這需要破門，我已為您加派消防車前往。」）
  - 患者位置在橋墩、山上電塔 → 緊急救援-其他（不對報案人講話：轉緊急救援的銜接語
    還沒設計，使用者 10/28 決定先不講，待跟承辦討論）
OK 表的案類不用觸發情境，所以這裡沒有。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import BREAK_IN_NEEDED, EMS_QUESTIONS, HANGING_REMOTE_PLACES

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


SHANG_DIAO_QUESTIONS = EMS_QUESTIONS["上吊"]


class ShangDiaoHandler(SubCategoryHandler):
    """上吊次類別 Handler。"""

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in SHANG_DIAO_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；問完呼吸做 OHCA 判定（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, SHANG_DIAO_QUESTIONS)

    def _check_escalation(self, engine: "SopEngine119") -> None:
        """xlsx 備註：需要破門 → 緊急救援-破門；在橋墩、山上電塔 → 緊急救援-其他。報案人哪一句講到都算。"""
        case = engine.case
        if case.break_in_need == BREAK_IN_NEEDED:
            engine._escalate_main_to_emergency(reason="上吊需破門")
        elif any(
            place in (case.hanging_location or "") for place in HANGING_REMOTE_PLACES
        ):
            engine._escalate_main_to_emergency(reason="上吊在橋墩或電塔", line=None)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """上吊使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
