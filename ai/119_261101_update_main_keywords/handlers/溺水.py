"""
handlers/溺水.py
━━━━━━━━━━━━━━━
119 SOP — 救護-溺水次類別 Handler

照 1102 xlsx「11-溺水」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["溺水"]、
base._ask_ems_questions）。這張表還沒標 OK，先照表問給承辦實測（11/03 使用者決定）。
溺水狀況 = 還在水裡（xlsx 備註）或看不到人（使用者 11/05 決定）→ 改判緊急救援（報案人哪一句講到都算）。
做法跟車禍有人受困一樣：只改主案類、不對報案人講話、溺水的題目照樣問完，次案類維持溺水。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import DROWNING_NOT_RESCUED

from .ems_table import EmsTableHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class NiShuiHandler(EmsTableHandler):
    """救護-溺水次類別 Handler。"""

    def __init__(self) -> None:
        super().__init__("溺水")

    def _check_escalation(self, engine: "SopEngine119") -> None:
        """還在水裡、看不到人 → 改判緊急救援（不講話）。報案人哪一句講到都算。"""
        if engine.case.drowning_status in DROWNING_NOT_RESCUED:
            engine._escalate_main_to_emergency(reason=f"溺水{engine.case.drowning_status}", line=None)
