"""
handlers/ems_table.py
━━━━━━━━━━━━━━━━━━━━━
只要照題目表問、沒有提醒語的救護次案類，共用這個 Handler。

用的案類：刀傷(切割傷)、槍傷、壓傷、電擊傷、喝農藥、吸入廢氣、其它（登記在 handlers/__init__.py）。
題目在 ems_tab_map_119.EMS_QUESTIONS。
某一類之後要加提醒語或改判，就另外開自己的檔案（例如溺水.py）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ems_tab_map_119 import EMS_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class EmsTableHandler(SubCategoryHandler):
    """照題目表問的救護次案類 Handler；sub_category 是 EMS_QUESTIONS 裡的次案類名稱。"""

    def __init__(self, sub_category: str) -> None:
        self.questions = EMS_QUESTIONS[sub_category]
        # 題目表的欄位（切換次案類時用：沒列在這裡的欄位，從別的次案類切過來時會被清掉）
        self.SOP_SLOTS = tuple(item.field for item in self.questions)

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """照題目表逐題問；呼吸不正常、無呼吸轉真人（見 base._ask_ems_questions）。"""
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, self.questions)
