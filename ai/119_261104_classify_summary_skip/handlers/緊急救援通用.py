"""
handlers/緊急救援通用.py
━━━━━━━━━━━━━━━━━━━━━━━━
119 SOP — 緊急救援大類

  run_generic_flow — 定次案類、講派車，有次案類就照 1106 xlsx 題目表問（emergency_tab_map_119）
  collect_caller_info — 收集報案人訊息
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from emergency_tab_map_119 import (
    DISPATCH_LINE,
    PARTY_SINGLE_MISSING_QUESTIONS,
    PARTY_SUBS,
    TRANSFER_SUBS,
    questions_for_subtype,
    should_switch_to_fire,
)
from .base import RESCUE_CLOSING_LINE, SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class JinJiJiuYuanGenericHandler(SubCategoryHandler):
    """緊急救援大類通用 Handler（不登記於子類 registry）。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """
        次案類定了才派車（判不出來也在追問完之後講）。有次案類就照題目表問，判不出來就不再問，
        直接進收集報案人資訊（使用者 11/06 決定）。
        題目進行中若換成別的次案類，從新次案類的題目表重問還沒填的題。
        """
        from sop_119_engine import SubCategorySwitched

        engine._ensure_known_fields_from_history()
        engine._settle_emergency_subcategory()
        self._transfer_if_needed(engine)
        engine._announce_dispatch(DISPATCH_LINE)
        engine._sub_reclassify_enabled = True
        try:
            while True:
                try:
                    self._transfer_if_needed(engine)
                    self._ask_ems_questions(engine, questions_for_subtype(engine.case.sub_category))
                    break
                except SubCategorySwitched as sw:
                    engine._debug_print(
                        "emergency_sub_switched_restart",
                        {"old": sw.old, "new": sw.new},
                    )
                    continue
        finally:
            engine._sub_reclassify_enabled = False

    def _transfer_if_needed(self, engine: "SopEngine119") -> None:
        """判到要轉真人的次案類（見 TRANSFER_SUBS）就轉。定完次案類、題目進行中換次案類，都會檢查。"""
        if engine.case.sub_category in TRANSFER_SUBS:
            engine._transfer_to_human(f"緊急救援次案類轉真人：{engine.case.sub_category}")

    def _check_escalation(self, engine: "SopEngine119") -> None:
        """車禍救助、瓦斯漏氣：報案人哪一句講到有火或有煙都改判火警，不限問到火煙狀況那一題。"""
        tab = should_switch_to_fire(engine.case)
        if tab:
            engine._switch_emergency_to_fire(tab)

    def _single_missing_questions(self, engine: "SopEngine119", fields) -> Optional[dict]:
        """山難、卡住夾住、破門的整句用「當事人」，補問句也用「當事人」（使用者 11/05 決定）。"""
        if (
            engine.case.sub_category in PARTY_SUBS
            and tuple(fields) == ("patient_gender", "patient_age")
        ):
            return PARTY_SINGLE_MISSING_QUESTIONS
        return super()._single_missing_questions(engine, fields)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """救援人員話術收集報案人姓名與聯繫方式。"""
        from sop_119_engine import TransferToHumanError

        engine._set_stage("緊急救援_caller_info")
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
        # 11/02 使用者決定暫時不唸姓名、聯繫方式，也不講「耐心等待」那句，
        # 要恢復就把下面兩行的註解拿掉
        # engine._say("，".join(parts) + "，已為您記錄。")
        # engine._say("請在現場耐心等待，確認入口通暢，並引導救援人員，謝謝。")
        engine._say(RESCUE_CLOSING_LINE)
        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})
