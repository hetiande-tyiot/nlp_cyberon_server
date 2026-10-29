"""
handlers/吞食藥物.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 吞食藥物次類別 Handler

照 1028 xlsx「15-吞食藥物OK」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["吞食藥物"]、
base._ask_ems_questions）。xlsx 備註另外要求：
  - 藥袋：結束通話前主動提醒「如果有發現藥袋，請一併提供給救護人員帶到醫院」
    （題目都問完、問報案人姓名電話之前講）
OK 表的案類不用觸發情境，所以這裡沒有。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import EMS_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


TUN_SHI_QUESTIONS = EMS_QUESTIONS["吞食藥物"]

# xlsx 藥袋備註的提醒語
_MEDICINE_BAG_REMINDER = "如果有發現藥袋，請一併提供給救護人員帶到醫院。"


class TunShiYaoWuHandler(SubCategoryHandler):
    """吞食藥物次類別 Handler。"""

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in TUN_SHI_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；問完呼吸做 OHCA 判定；題目問完講藥袋提醒。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, TUN_SHI_QUESTIONS)
        engine._say(_MEDICINE_BAG_REMINDER)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """吞食藥物使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
