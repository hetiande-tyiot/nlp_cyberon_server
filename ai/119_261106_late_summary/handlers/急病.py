"""
handlers/急病.py
━━━━━━━━━━━━━━━━
119 SOP — 急病次類別 Handler

照 1028 xlsx「01-急病」的題目表逐題問（ems_tab_map_119.JI_BING_QUESTIONS、
base._ask_ems_questions）。這張表還沒標 OK，先照表問給承辦實測（11/02 使用者決定）。
使用者 11/02 決定拿掉廠商原本的：觸發情境（開擴音教急救、打開大門、咳嗽、問病史血糖血壓抽搐等）、
呼吸不是「有」時先問肚子起伏、叫不醒時探問服藥、病徵含糊重問。
呼吸 = 呼吸不正常、無呼吸 → 轉真人（見 base._check_breathing_transfer）。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import JI_BING_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class JiBingHandler(SubCategoryHandler):
    """急病次類別 Handler。"""

    # 題目表的欄位（切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(item.field for item in JI_BING_QUESTIONS)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, JI_BING_QUESTIONS)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """急病使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
