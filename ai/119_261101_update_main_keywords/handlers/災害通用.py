"""
handlers/災害通用.py
━━━━━━━━━━━━━━━━━━━━
119 SOP — 災害大類通用流程

所有子類問同一套題。受困人數、火花兩題有前置條件。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from disaster_flow_119 import (
    DISASTER_QUESTIONS,
    MODE_CONDITIONAL,
    DisasterQuestion,
)
from .base import CLOSING_LINE, SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class ZaiHaiGenericHandler(SubCategoryHandler):
    """災害大類通用 Handler（不登記於子類 registry）。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """照題目順序問。主動題已有答案就跳過；條件不成立就不問。"""
        engine._ensure_known_fields_from_history()
        for item in DISASTER_QUESTIONS:
            engine._ensure_known_fields_from_history()
            if item.mode == MODE_CONDITIONAL and not item.condition(engine.case):
                engine._debug_print(
                    f"skip_{item.stage}", {"前置條件不成立": item.condition_text},
                )
                continue
            self._ask_missing(engine, item)
        # 火花題可能在問完身分之後，子類才辨成電線掉落等。那時補問一次。
        spark = next(item for item in DISASTER_QUESTIONS if item.field == "electrical_hazard")
        already_asked = any(
            turn.get("role") == "assistant" and (turn.get("text") or "") == spark.question
            for turn in engine.case.transcript
        )
        if (
            not already_asked
            and spark.condition(engine.case)
            and not engine._is_field_filled(spark.field)
        ):
            self._ask_missing(engine, spark)

    def _ask_missing(
        self,
        engine: "SopEngine119",
        item: DisasterQuestion,
    ) -> Optional[str]:
        """答案還不知道才問，並走 LLM 抽取。"""
        engine._ensure_known_fields_from_history()
        engine._set_stage(item.stage)
        if engine._is_field_filled(item.field):
            engine._debug_print(
                f"skip_{item.stage}",
                {item.field: getattr(engine.case, item.field)},
            )
            return None
        return engine._ask_and_extract(item.question)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """收報案人姓名與聯繫方式。記不到就轉專人。"""
        from sop_119_engine import TransferToHumanError

        engine._set_stage("災害_caller_info")
        question = "請問你的姓名與聯繫方式？"
        caller_info_text = engine._ask_and_extract(question)

        caller_name = engine.case.caller_name
        caller_contact = engine.case.caller_contact
        if engine._llm and caller_info_text.strip():
            try:
                ci = engine._llm.extract_caller_info(
                    question,
                    caller_info_text,
                    include_address=False,
                )
                caller_name = ci.get("caller_name") or caller_name
                caller_contact = ci.get("caller_contact") or caller_contact
                engine._debug_print("caller_info", ci)
            except Exception as e:
                engine._debug_print("caller_info_error", e)

        with engine._case_lock:
            engine.case.caller_name = caller_name
        engine.set_caller_contact(caller_contact)
        engine._notify_case_update()

        if not caller_name and not caller_contact:
            engine._say("無法確認報案人資訊，立即為您轉接專人，請稍候。")
            raise TransferToHumanError("caller_info_missing", result="human_transfer")

        parts = []
        if caller_name:
            parts.append(f"姓名：{caller_name}")
        if caller_contact:
            parts.append(f"聯繫方式：{caller_contact}")
        # 11/02 使用者決定暫時不唸姓名、聯繫方式，也不講「耐心等待」那句，
        # 要恢復就把下面兩行的註解拿掉
        # engine._say("，".join(parts) + "，已為您記錄。")
        # engine._say("請在現場耐心等待，確認入口通暢，並引導救援人員，謝謝。")
        engine._say(CLOSING_LINE)
        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})
