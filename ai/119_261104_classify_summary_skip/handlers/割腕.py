"""
handlers/割腕.py
━━━━━━━━━━━━━━━━
119 SOP — 割腕次類別 Handler

照 1028 xlsx「19-割腕OK」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["割腕"]、
base._ask_ems_questions）。xlsx 備註沒有另外的提醒或改判。
OK 表的案類不用觸發情境，所以這裡沒有。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import EMS_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


GE_WAN_QUESTIONS = EMS_QUESTIONS["割腕"]


class GeWanHandler(SubCategoryHandler):
    """割腕次類別 Handler。"""

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in GE_WAN_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；問完呼吸做 OHCA 判定（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, GE_WAN_QUESTIONS)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """割腕使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
