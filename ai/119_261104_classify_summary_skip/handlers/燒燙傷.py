"""
handlers/燒燙傷.py
━━━━━━━━━━━━━━━━━━
119 SOP — 燒燙傷次類別 Handler

照 1028 xlsx「08-燒燙傷OK」的題目表逐題問（ems_tab_map_119.SHAO_TANG_SHANG_QUESTIONS、
base._ask_ems_questions）。xlsx 備註另外要求：
  - 小兒燒燙傷轉真人（小兒定義：14 歲（含）以前）
    轉人工講原程式 OHCA 轉人工那句「請不要掛斷電話，我立即為您轉接專人。」
OK 表的案類不用觸發情境，所以這裡沒有。
題目問完講提醒語表（docs/救護提醒語_問卷回饋_1030 改.xlsx）燒燙傷的 2 句。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import SHAO_TANG_SHANG_QUESTIONS, is_child_age

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# 提醒語表的句子
_COOL_WATER_REMINDER = "可以的話，請協助沖冷水到救護人員到達為止。"
_NO_MEDICINE_REMINDER = "燙到的地方先不要擦任何藥。"


class ShaoTangShangHandler(SubCategoryHandler):
    """燒燙傷次類別 Handler。"""

    # 題目表的欄位（切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(item.field for item in SHAO_TANG_SHANG_QUESTIONS)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；呼吸不正常、無呼吸轉真人（見 base._ask_ems_questions）；題目問完講提醒語。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, SHAO_TANG_SHANG_QUESTIONS)
        engine._say(_COOL_WATER_REMINDER)
        engine._say(_NO_MEDICINE_REMINDER)

    def _after_ems_item(self, engine: "SopEngine119", item) -> None:
        """
        xlsx 備註：小兒燒燙傷轉真人。
        年齡可能在任何一句講到（例如開頭就說「我兒子五歲」），所以每一題處理完都檢查。
        """
        if engine._bridged or not is_child_age(engine.case.patient_age):
            return
        from sop_119_engine import TransferToHumanError

        engine._debug_print("burn_child_transfer", engine.case.patient_age)
        engine._say("請不要掛斷電話，我立即為您轉接專人。")
        raise TransferToHumanError("burn_child", result="human_transfer")

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """燒燙傷使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
