"""
handlers/打架受傷.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 打架受傷次類別 Handler

照 1028 xlsx「09-打架受傷」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["打架受傷"]、
base._ask_ems_questions）。這張表還沒標 OK，先照表問給承辦實測（11/02 使用者決定）。
照題目表問的案類不用觸發情境，所以原本講到打架、意識模糊、肚子起伏時重複確認地址、
問肚子起伏的觸發情境拿掉了。
提醒語表打架受傷的句子還沒定（待承辦填寫），不講提醒語。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import EMS_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


DA_JIA_QUESTIONS = EMS_QUESTIONS["打架受傷"]


class DaJiaShouShangHandler(SubCategoryHandler):
    """打架受傷次類別 Handler。"""

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in DA_JIA_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；問完呼吸做 OHCA 判定（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, DA_JIA_QUESTIONS)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """打架受傷使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
