"""
handlers/路倒.py
━━━━━━━━━━━━━━━━
119 SOP — 路倒次類別 Handler

照 1028 xlsx「14-路倒」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["路倒"]、
base._ask_ems_questions）。這張表還沒標 OK，先照表問給承辦實測（11/02 使用者決定）。
照題目表問的案類不用觸發情境，所以原本講到公共場所就重複確認地址的觸發情境拿掉了。
xlsx 備註：路倒狀況回答「喝醉」時，是否飲酒也一起記成「有喝酒」。
提醒語表沒有路倒，不講提醒語。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import COLLAPSE_DRUNK, DRINKING_YES, EMS_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


LU_DAO_QUESTIONS = EMS_QUESTIONS["路倒"]


class LuDaoHandler(SubCategoryHandler):
    """路倒次類別 Handler。"""

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in LU_DAO_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；問完呼吸做 OHCA 判定（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, LU_DAO_QUESTIONS)

    def _after_ems_item(self, engine: "SopEngine119", item) -> None:
        """xlsx 備註：路倒狀況是喝醉，是否飲酒也記成有喝酒（報案人哪一句講到都算）。"""
        if engine.case.collapse_status == COLLAPSE_DRUNK and not engine._is_field_filled("drinking_status"):
            with engine._case_lock:
                engine.case.drinking_status = DRINKING_YES
            engine._notify_case_update()

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """路倒使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
