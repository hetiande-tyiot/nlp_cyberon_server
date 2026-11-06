"""
handlers/墜落傷.py
━━━━━━━━━━━━━━━━━
119 SOP — 墜落傷次類別 Handler

照 1028 xlsx「06-墜落傷OK」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["墜落傷"]、
base._ask_ems_questions）。xlsx 備註另外要求：
  - 尚未跳下 → 緊急救援-跳樓
  - 跳下來卡住 → 緊急救援-跳樓
OK 表的案類不用觸發情境，所以這裡沒有。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from emergency_tab_map_119 import FALL
from ems_tab_map_119 import EMS_QUESTIONS, FALL_NOT_YET, FALL_POSITION_STUCK, FALL_STATUS_STUCK

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


ZHUI_LUO_QUESTIONS = EMS_QUESTIONS["墜落傷"]


class ZhuiLuoShangHandler(SubCategoryHandler):
    """墜落傷次類別 Handler。"""

    # 題目表的欄位（切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(item.field for item in ZHUI_LUO_QUESTIONS)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；呼吸不正常、無呼吸轉真人（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, ZHUI_LUO_QUESTIONS)

    def _check_escalation(self, engine: "SopEngine119") -> None:
        """xlsx 備註：尚未跳下、跳下來卡住 → 改判緊急救援-跳樓並轉真人。報案人哪一句講到都算。"""
        case = engine.case
        if case.fall_status == FALL_NOT_YET:
            engine._escalate_main_to_emergency(FALL, reason="墜落傷尚未跳下", line=None)
        elif case.fall_status == FALL_STATUS_STUCK or case.fall_position == FALL_POSITION_STUCK:
            engine._escalate_main_to_emergency(FALL, reason="墜落傷卡住", line=None)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """墜落傷使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
