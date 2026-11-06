"""
handlers/一般受傷.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 一般受傷次類別 Handler

照 1028 xlsx「10-一般受傷」的題目表逐題問（ems_tab_map_119.EMS_QUESTIONS["一般受傷"]、
base._ask_ems_questions）。這張表還沒標 OK，先照表問給承辦實測（11/02 使用者決定）。
照題目表問的案類不用觸發情境，所以原本跌倒、工作受傷、斷指時追問的觸發情境拿掉了。
題目問完講提醒語表（docs/救護提醒語_問卷回饋_1030 改.xlsx）一般受傷的句子：
  - 止血那句，受傷原因或傷勢提到流血或傷口很深才講（使用者 11/06 決定；割腕維持一律講）
  - 斷指保存那句，受傷原因或傷勢講到斷指才講（提醒語表備註：當受傷原因為斷指時觸發）

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import EMS_QUESTIONS
from sop_utils_119 import _has_unnegated_token

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


GENERAL_INJURY_QUESTIONS = EMS_QUESTIONS["一般受傷"]

# 提醒語表的句子
_STOP_BLEEDING_REMINDER = "先拿乾淨的毛巾或衣服，用力壓住傷口止血。"
_SEVERED_FINGER_REMINDER = (
    "請將斷掉的手指用乾淨的塑膠袋裝好，再放進另一個裝冰水的袋子，"
    "不要直接碰到冰塊，等一下交給救護人員。"
)
# 受傷原因或傷勢出現這些字，就當作斷指
_SEVERED_WORDS = ("斷指", "斷掉", "切斷", "斷肢")
# 受傷原因或傷勢出現「血」或「很深」（前面沒有沒有、無、不是這類否定詞），就當作在流血
_BLEEDING_WORDS = ("血", "很深")
# 有「血」字但不是在流血的說法，判斷前先拿掉。
# 「沒流血」「不流血」這種單字否定，共用的否定判斷擋不到，所以列在這裡
_NOT_BLEEDING_WORDS = ("血壓", "血糖", "瘀血", "血腫", "沒流血", "不流血", "沒在流血", "沒什麼血", "沒出血")


class GeneralInjuryHandler(SubCategoryHandler):
    """一般受傷次類別 Handler。"""

    # 題目表的欄位（切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(item.field for item in GENERAL_INJURY_QUESTIONS)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；呼吸不正常、無呼吸轉真人（見 base._ask_ems_questions）；題目問完講提醒語。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, GENERAL_INJURY_QUESTIONS)
        injury_text = f"{engine.case.injury_cause or ''}{engine.case.injury_severity or ''}"
        bleeding_text = injury_text
        for word in _NOT_BLEEDING_WORDS:
            bleeding_text = bleeding_text.replace(word, "")
        if _has_unnegated_token(bleeding_text, _BLEEDING_WORDS):
            engine._say(_STOP_BLEEDING_REMINDER)
        if any(word in injury_text for word in _SEVERED_WORDS):
            engine._say(_SEVERED_FINGER_REMINDER)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """一般受傷使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
