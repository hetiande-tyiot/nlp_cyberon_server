"""
handlers/孕婦急產.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 孕婦待產次類別 Handler（次案類名稱統一用「孕婦待產」；檔名、類別名稱沿用廠商原本的「急產」）

照 1028 xlsx「12-孕婦待產」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["孕婦待產"]、
base._ask_ems_questions）。這張表還沒標 OK，先照表問給承辦實測（11/02 使用者決定）。
照題目表問的案類不用觸發情境，所以原本「沒有呼吸」「羊水破、流血、陣痛」時講固定句子的觸發情境拿掉了。
題目問完講提醒語表（docs/救護提醒語_問卷回饋_1030 改.xlsx）孕婦待產的句子：
  - 左側躺：孕婦清醒才講（提醒語表備註「派出+清醒」；次案類確定就已經派車，這裡只看清醒）。
    報案人是孕婦本人時不問意識，但能講電話就是清醒，也講（使用者 11/02 決定）
  - 墊毛巾：陣痛狀況是「已經破水」才講（提醒語表備註「羊水破才能問」）
  - 「電話拿給她旁邊的人」那句，使用者 11/02 決定先不加

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import CONTRACTIONS_WATER_BROKEN, EMS_QUESTIONS, RELATION_SELF

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


YUN_FU_QUESTIONS = EMS_QUESTIONS["孕婦待產"]

# 提醒語表的句子
_LIE_ON_LEFT_REMINDER = "請孕婦本人往左邊側躺，先不要用力。"
_TOWEL_REMINDER = "如果羊水破了，請拿乾淨的毛巾墊在孕婦屁股下方。"


class YunFuJiChanHandler(SubCategoryHandler):
    """孕婦待產次類別 Handler。"""

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」
    # （切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in YUN_FU_QUESTIONS
    ) + ("consciousness",)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；問完呼吸做 OHCA 判定（見 base._ask_ems_questions）；題目問完講提醒語。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, YUN_FU_QUESTIONS)
        if engine.case.consciousness is True or engine.case.caller_relation == RELATION_SELF:
            engine._say(_LIE_ON_LEFT_REMINDER)
        if engine.case.contractions == CONTRACTIONS_WATER_BROKEN:
            engine._say(_TOWEL_REMINDER)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """孕婦待產使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
