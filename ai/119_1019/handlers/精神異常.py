"""
handlers/精神異常.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 精神異常次類別 Handler

照 1028 xlsx「13-精神異常OK」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["精神異常"]、
base._ask_ems_questions）。
意識、呼吸是被動題（承辦：精神異常有動作行為，基本上不用再問意識呼吸），
所以不問、也不做 OHCA 判定。
OK 表的案類不用觸發情境，所以這裡沒有。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import EMS_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


JING_SHEN_QUESTIONS = EMS_QUESTIONS["精神異常"]


class JingShenYiChangHandler(SubCategoryHandler):
    """精神異常次類別 Handler。"""

    # 題目表的欄位，加上「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in JING_SHEN_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, JING_SHEN_QUESTIONS)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """精神異常使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
