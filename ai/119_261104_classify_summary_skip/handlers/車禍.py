"""
handlers/車禍.py
━━━━━━━━━━━━━━━
119 SOP — 車禍次類別 Handler

照 1028 xlsx「02-車禍」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["車禍"]、
base._ask_ems_questions）。這張表還沒標 OK，先照表問給承辦實測（11/02 使用者決定）。
照題目表問的案類不用觸發情境，所以原本多車相撞、有人夾在車內講「請先到安全的地方。」的觸發情境
拿掉了；原本第一題後一律講的兩句安全叮嚀，提醒語表沒有車禍，使用者決定也拿掉。
xlsx 備註：人員受困 = 有人受困 → 改判緊急救援（報案人哪一句講到都算）。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import CRASH_TRAPPED_YES, EMS_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


CHE_HUO_QUESTIONS = EMS_QUESTIONS["車禍"]


class CheHuoHandler(SubCategoryHandler):
    """車禍次類別 Handler。"""

    # 題目表的欄位（切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(item.field for item in CHE_HUO_QUESTIONS)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；呼吸不正常、無呼吸轉真人（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, CHE_HUO_QUESTIONS)

    def _check_escalation(self, engine: "SopEngine119") -> None:
        """xlsx 備註：有人受困 → 改判緊急救援（不講話）。報案人哪一句講到都算。"""
        if engine.case.crash_trapped == CRASH_TRAPPED_YES:
            engine._escalate_main_to_emergency(reason="車禍有人受困", line=None)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """車禍使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
