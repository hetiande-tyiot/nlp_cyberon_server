"""
handlers/火警通用.py
━━━━━━━━━━━━━━━━━━━━
119 SOP — 火警 Q1/Q2 分流與垂片 A / B1 / B2 / C

  run_generic_flow — 建物判斷 → 非建物細分 → 對應垂片詢問 → 統一安全提示
  collect_caller_info — 最後確認回撥電話與稱呼
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from fire_tab_map_119 import (
    ROUTE_Q1,
    ROUTE_Q2,
    SAFETY_MESSAGE,
    TAB_A,
    TAB_B1,
    TAB_B2,
    TAB_C,
    TAB_QUESTIONS,
    apply_route_q1,
    apply_route_q2,
    infer_route_q1,
    infer_route_q2,
    resolve_fire_tab,
)
from important_tags_119 import merge_important_tags
from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class HuoJingGenericHandler(SubCategoryHandler):
    """火警大類 Handler：Q1/Q2 分流後走對應垂片。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """完成分流與垂片詢問，再播放統一安全提示。"""
        engine._ensure_known_fields_from_history()

        self._resolve_route_q1(engine)
        tab = resolve_fire_tab(engine.case)
        if tab is None and engine.case.fire_incident_type is None:
            engine._debug_print("fire_tab_unresolved", "q1")
            self._flag_fire_issue(engine, "Q1 兩輪仍無法判斷")
        if tab != TAB_A:
            self._resolve_route_q2(engine)
            tab = resolve_fire_tab(engine.case)

        if tab not in TAB_QUESTIONS:
            engine._debug_print("fire_tab_unresolved", tab)
            self._flag_fire_issue(engine, "火災類別無法確認")
            with engine._case_lock:
                apply_route_q2(engine.case, "minor")
            engine._notify_case_update()
            tab = resolve_fire_tab(engine.case)

        with engine._case_lock:
            engine.case.fire_tab = tab
        engine._notify_case_update()

        engine._sub_reclassify_enabled = True
        try:
            from sop_119_engine import SubCategorySwitched
            engine._refresh_fire_subtype_from_bert()
            engine._maybe_reclassify_sub()
            while True:
                try:
                    tab = engine.case.fire_tab
                    self._ask_tab_questions(engine, tab)
                    break
                except SubCategorySwitched as sw:
                    engine._debug_print(
                        "fire_tab_switched_restart",
                        {"old": sw.old, "new": sw.new, "tab": engine.case.fire_tab},
                    )
                    continue
        finally:
            engine._sub_reclassify_enabled = False

        engine._set_stage("火警_safety")
        engine._say(SAFETY_MESSAGE)

    def _flag_fire_issue(self, engine: "SopEngine119", tag: str) -> None:
        """記錄無法判斷／資訊缺失，繼續流程、不轉人工。"""
        with engine._case_lock:
            engine.case.ImportantCase = 1
            engine.case.ImportantTag = merge_important_tags(
                engine.case.ImportantTag, [tag],
            )
        engine._debug_print("fire_issue_tag", tag)
        engine._notify_case_update()

    def _last_caller_text(self, engine: "SopEngine119") -> str:
        texts = engine.case.caller_texts()
        return texts[-1] if texts else ""

    def _classify_route(
        self,
        engine: "SopEngine119",
        which: str,
        question: str,
        answer: str,
    ) -> Optional[str]:
        route = None
        if engine._llm is not None and hasattr(engine._llm, "classify_fire_route"):
            try:
                route = engine._llm.classify_fire_route(
                    answer, question=question, which=which,
                )
            except Exception as exc:
                engine._debug_print("fire_route_llm_error", exc)
        if route:
            return route
        if which == "q1":
            return infer_route_q1(answer)
        return infer_route_q2(answer)

    def _resolve_route_q1(self, engine: "SopEngine119") -> None:
        engine._ensure_known_fields_from_history()
        if engine.case.fire_incident_type == 0:
            apply_route_q1(engine.case, "building")
            engine._notify_case_update()
            return
        if engine.case.fire_incident_type == 1:
            return

        answer = None
        for _attempt in range(2):
            answer = self._ask_missing(
                engine, "火警_route_1", ("fire_incident_type",), ROUTE_Q1,
            )
            if engine.case.fire_incident_type in (0, 1):
                break
            route = self._classify_route(
                engine, "q1", ROUTE_Q1, answer or self._last_caller_text(engine),
            )
            if route:
                with engine._case_lock:
                    apply_route_q1(engine.case, route)
                engine._notify_case_update()
                break
        else:
            route = self._classify_route(
                engine, "q1", ROUTE_Q1, answer or self._last_caller_text(engine),
            )
            if route:
                with engine._case_lock:
                    apply_route_q1(engine.case, route)
                engine._notify_case_update()

        if engine.case.fire_incident_type == 0:
            with engine._case_lock:
                apply_route_q1(engine.case, "building")
            engine._notify_case_update()

    def _q2_already_known(self, engine: "SopEngine119") -> Optional[str]:
        tab = resolve_fire_tab(engine.case)
        if tab in (TAB_B1, TAB_B2, TAB_C):
            return tab
        if engine.case.non_building_fire == 1:
            return TAB_C
        code = engine.case.vehicle_wildfire_code
        if code is not None and 0 <= code <= 6:
            return TAB_B1
        if code in (7, 8):
            return TAB_B2
        return None

    def _lock_tab(self, engine: "SopEngine119", tab: str) -> None:
        with engine._case_lock:
            engine.case.fire_tab = tab
            if tab == TAB_A:
                engine.case.fire_incident_type = 0
            elif tab == TAB_C:
                engine.case.fire_incident_type = 1
                engine.case.non_building_fire = 1
            else:
                engine.case.fire_incident_type = 1
                engine.case.non_building_fire = 0
        engine._notify_case_update()

    def _resolve_route_q2(self, engine: "SopEngine119") -> None:
        engine._ensure_known_fields_from_history()
        known = self._q2_already_known(engine)
        if known:
            self._lock_tab(engine, known)
            return

        answer = None
        for _attempt in range(2):
            engine._set_stage("火警_route_2")
            answer = engine._ask_and_extract(ROUTE_Q2)
            self._check_and_respond_to_triggers(answer, engine)
            known = self._q2_already_known(engine)
            if known:
                self._lock_tab(engine, known)
                return
            route = self._classify_route(engine, "q2", ROUTE_Q2, answer)
            if route:
                with engine._case_lock:
                    apply_route_q2(engine.case, route)
                engine._notify_case_update()
                return
        self._flag_fire_issue(engine, "Q2 兩輪仍無法判斷")
        with engine._case_lock:
            apply_route_q2(engine.case, "minor")
        engine._notify_case_update()

    def _ask_tab_questions(self, engine: "SopEngine119", tab: str) -> None:
        for field, stage, question in TAB_QUESTIONS.get(tab, ()):
            self._ask_missing(engine, stage, (field,), question)

    def _ask_missing(
        self,
        engine: "SopEngine119",
        stage: str,
        fields: Iterable[str],
        question: str,
    ) -> Optional[str]:
        """只在任一关联字段未取得时提问，并统一经过 LLM 抽取。"""
        engine._ensure_known_fields_from_history()
        field_tuple = tuple(fields)
        engine._set_stage(stage)
        if all(engine._is_field_filled(field) for field in field_tuple):
            engine._debug_print(
                f"skip_{stage}",
                {field: getattr(engine.case, field) for field in field_tuple},
            )
            return None
        answer = engine._ask_and_extract(question)
        self._check_and_respond_to_triggers(answer, engine)
        return answer

    def _check_and_respond_to_triggers(
        self, caller_text: str, engine: "SopEngine119"
    ) -> None:
        """
        偵測本輪文本中的火警觸發情境 2–14。
        每個情境號只記錄一次；記錄後直接進入下一個問題。
        """
        if not engine._llm or not (caller_text or "").strip():
            return

        try:
            already = list(engine.case.triggered_scenarios)
            new_ids = engine._llm.check_fire_trigger_scenarios(
                caller_text, already_triggered=already,
            )
            engine._debug_print("fire_triggers", {"new": new_ids, "already": already})
        except Exception as e:
            engine._debug_print("fire_triggers_error", e)
            return

        if not new_ids:
            return

        with engine._case_lock:
            for sid in new_ids:
                if sid not in engine.case.triggered_scenarios:
                    engine.case.triggered_scenarios.append(sid)
        engine._notify_case_update()

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """在火災問診末尾確認回撥電話與稱呼。"""
        from sop_utils_119 import parse_yes_no_for_question

        engine._set_stage("火警_caller_info")
        engine._ensure_known_fields_from_history()
        original_contact = engine.case.caller_contact
        if original_contact:
            question = (
                f"最後和您確認一下，連絡電話是 {original_contact} 嗎？"
                "請問是先生還是小姐呢？"
            )
        else:
            question = "最後請提供回撥電話，並告訴我是先生還是小姐。"
        answer = engine._ask_and_extract(question)
        self._extract_caller_info(answer, question, engine)

        if original_contact:
            confirmed = parse_yes_no_for_question(question, answer)
            if confirmed is False and engine.case.caller_contact == original_contact:
                correction_q = "請重新提供正確的回撥電話。"
                correction = engine._ask_and_extract(correction_q)
                self._extract_caller_info(correction, correction_q, engine)

        for _attempt in range(2):
            if engine._is_field_filled("caller_contact"):
                break
            phone_q = "請提供可以回撥的聯絡電話。"
            phone_answer = engine._ask_and_extract(phone_q)
            self._extract_caller_info(phone_answer, phone_q, engine)
        for _attempt in range(2):
            if engine._is_field_filled("caller_salutation"):
                break
            salutation_q = "請問是先生還是小姐？"
            salutation_answer = engine._ask_and_extract(salutation_q)
            self._extract_caller_info(salutation_answer, salutation_q, engine)

        if not engine._is_field_filled("caller_contact"):
            self._flag_fire_issue(engine, "回撥電話無法確認")
        if not engine._is_field_filled("caller_salutation"):
            self._flag_fire_issue(engine, "報案人稱呼無法確認")

        recap_parts = []
        if engine.case.caller_contact:
            recap_parts.append(f"連絡電話：{engine.case.caller_contact}")
        if engine.case.caller_salutation:
            recap_parts.append(f"稱呼：{engine.case.caller_salutation}")
        if recap_parts:
            engine._say("，".join(recap_parts) + "，已為您記錄。")

        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})

    @staticmethod
    def _extract_caller_info(
        caller_text: str, question: str, engine: "SopEngine119"
    ) -> None:
        if not engine._llm or not caller_text.strip():
            return
        try:
            ci = engine._llm.extract_caller_info(
                question, caller_text, include_address=False
            )
            engine._debug_print("caller_info", ci)
        except Exception as exc:
            engine._debug_print("caller_info_error", exc)
            return
        with engine._case_lock:
            if ci.get("caller_name"):
                engine.case.caller_name = ci["caller_name"]
            if ci.get("caller_salutation") in ("先生", "小姐"):
                engine.case.caller_salutation = ci["caller_salutation"]
        # set_caller_contact 自己會拿 _case_lock（普通 Lock、不可重入），
        # 必須在 with 區塊外呼叫，否則死鎖。
        if ci.get("caller_contact"):
            engine.set_caller_contact(ci["caller_contact"])
        engine._notify_case_update()
