"""
handlers/緊急救援通用.py
━━━━━━━━━━━━━━━━━━━━━━━━
119 SOP — 緊急救援大類

  run_generic_flow — 定次案類後，車禍救助走八題，再問關係、性別年齡、呼吸
  collect_caller_info — 救援人員話術收集報案人訊息
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from emergency_accident_119 import (
    ACCIDENT_QUESTIONS,
    BREATHING_QUESTION,
    CONSCIOUSNESS_QUESTION,
    DISPATCH_LINE,
    MODE_CONDITIONAL,
    PATIENT_QUESTION,
    RELATION_QUESTION,
    SUBCATEGORY,
    AccidentQuestion,
)
from emergency_rescue_subs_119 import (
    GENDER_AGE_SUBS,
    MODE_PASSIVE,
    OWN_CONSCIOUSNESS_SUBS,
    SUB_QUESTIONS,
    RescueSubQuestion,
)
from sop_utils_119 import parse_yes_no_for_question
from .base import CLOSING_LINE, SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class JinJiJiuYuanGenericHandler(SubCategoryHandler):
    """緊急救援大類通用 Handler（不登記於子類 registry）。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """次案類定了才派車。題目進行中若換成別的次案類，從新次案類重問還沒填的題。"""
        from sop_119_engine import SubCategorySwitched

        engine._ensure_known_fields_from_history()
        engine._settle_emergency_subcategory()
        engine._announce_dispatch(DISPATCH_LINE)
        engine._sub_reclassify_enabled = True
        try:
            while True:
                try:
                    self._ask_current_subtype(engine)
                    break
                except SubCategorySwitched as sw:
                    engine._debug_print(
                        "emergency_sub_switched_restart",
                        {"old": sw.old, "new": sw.new},
                    )
                    continue
        finally:
            engine._sub_reclassify_enabled = False

    def _ask_current_subtype(self, engine: "SopEngine119") -> None:
        if engine.case.sub_category == SUBCATEGORY:
            self._ask_accident(engine)
        elif engine.case.sub_category in SUB_QUESTIONS:
            self._ask_sub(engine, SUB_QUESTIONS[engine.case.sub_category])
        self._ask_tail(engine)

    def _ask_accident(self, engine: "SopEngine119") -> None:
        for item in ACCIDENT_QUESTIONS:
            engine._ensure_known_fields_from_history()
            if item.mode == MODE_CONDITIONAL and not item.condition(engine.case):
                engine._debug_print(
                    f"skip_{item.stage}", {"前置條件不成立": item.condition_text},
                )
                continue
            self._ask_missing(engine, item)

    def _ask_missing(
        self,
        engine: "SopEngine119",
        item: AccidentQuestion,
    ) -> Optional[str]:
        engine._ensure_known_fields_from_history()
        engine._set_stage(item.stage)
        if engine._is_field_filled(item.field):
            engine._debug_print(
                f"skip_{item.stage}",
                {item.field: getattr(engine.case, item.field)},
            )
            return None
        return engine._ask_and_extract(item.question)

    def _ask_sub(
        self,
        engine: "SopEngine119",
        questions: tuple,
    ) -> None:
        for item in questions:
            engine._ensure_known_fields_from_history()
            if item.mode == MODE_PASSIVE:
                continue
            if item.mode == MODE_CONDITIONAL and not item.condition(engine.case):
                engine._debug_print(
                    f"skip_{item.stage}", {"前置條件不成立": item.condition_text},
                )
                continue
            self._ask_sub_missing(engine, item)

    def _ask_sub_missing(
        self,
        engine: "SopEngine119",
        item: RescueSubQuestion,
    ) -> Optional[str]:
        engine._ensure_known_fields_from_history()
        engine._set_stage(item.stage)
        if engine._is_field_filled(item.field):
            engine._debug_print(
                f"skip_{item.stage}",
                {item.field: getattr(engine.case, item.field)},
            )
            return None
        return engine._ask_and_extract(item.question)

    def _ask_tail(self, engine: "SopEngine119") -> None:
        """關係、必要時的性別年齡與意識、呼吸。專用題問過的不再問。"""
        engine._ensure_known_fields_from_history()
        self._ask_text_field(
            engine, "緊急救援_relation", "caller_relation", RELATION_QUESTION,
        )
        if engine.case.sub_category not in GENDER_AGE_SUBS and not (
            engine._is_field_filled("patient_gender")
            and engine._is_field_filled("patient_age")
        ):
            engine._set_stage("緊急救援_patient")
            engine._ask_and_extract(PATIENT_QUESTION)
        if engine.case.sub_category not in OWN_CONSCIOUSNESS_SUBS:
            self._ask_bool_field(
                engine, "緊急救援_consciousness", "consciousness", CONSCIOUSNESS_QUESTION,
            )
        self._ask_bool_field(
            engine, "緊急救援_breathing", "breathing", BREATHING_QUESTION,
        )

    def _ask_text_field(
        self,
        engine: "SopEngine119",
        stage: str,
        field: str,
        question: str,
    ) -> None:
        engine._set_stage(stage)
        if engine._is_field_filled(field):
            return
        engine._ask_and_extract(question)

    def _ask_bool_field(
        self,
        engine: "SopEngine119",
        stage: str,
        field: str,
        question: str,
    ) -> None:
        engine._set_stage(stage)
        if engine._is_field_filled(field):
            return
        answer = engine._ask_and_extract(question)
        if engine._is_field_filled(field):
            return
        parsed = parse_yes_no_for_question(question, answer)
        if parsed is None:
            return
        with engine._case_lock:
            setattr(engine.case, field, parsed)
        engine._notify_case_update()

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
        engine._say(CLOSING_LINE)
        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})
