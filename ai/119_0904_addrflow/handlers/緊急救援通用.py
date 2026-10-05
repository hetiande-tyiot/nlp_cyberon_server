"""
handlers/緊急救援通用.py
━━━━━━━━━━━━━━━━━━━━━━━━
119 SOP — 緊急救援大類通用流程（暫無子類 handler）

  run_generic_flow — 詢問發生什麼事情（incident_description）
  collect_caller_info — 救援人員話術收集報案人訊息
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class JinJiJiuYuanGenericHandler(SubCategoryHandler):
    """緊急救援大類通用 Handler（不登記於子類 registry）。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """補問事件描述；已填則跳過。"""
        engine._ensure_known_fields_from_history()
        engine._set_stage("緊急救援_incident")

        if engine._is_field_filled("incident_description"):
            engine._debug_print(
                "skip_incident_description", engine.case.incident_description
            )
            return

        engine._ask_and_extract("請問發生什麼事情。")

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """救援人員話術收集報案人姓名與聯繫方式。"""
        from sop_119_engine import TransferToHumanError

        engine._set_stage("緊急救援_caller_info")
        question = "救援人員已派出，請問你的姓名與聯繫方式？"
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
        # set_caller_contact 自己會拿 _case_lock（普通 Lock、不可重入），
        # 必須在 with 區塊外呼叫，否則死鎖。
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
        engine._say("，".join(parts) + "，已為您記錄。")

        engine._say("請在現場耐心等待，確認入口通暢，並引導救援人員，謝謝。")
        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})
