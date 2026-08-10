"""
handlers/燒炭.py
━━━━━━━━━━━━━━━━
119 SOP — 燒炭次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行燒炭專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S2→S6→S4，每步後進行觸發情境偵測與回應

注意：此次類別 S6（性別年齡）在 S4（炭盆是否熄滅）之前詢問。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2 = "救護車已經派了。"
_R4 = "請您幫我打開大門，在家休息等救護車。"


class ShaoTanHandler(SubCategoryHandler):
    """燒炭次類別 Handler。"""

    # ── 燒炭專屬完整問題流程 ──────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        燒炭次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → S2（隨機三選一）→ S6 → S4
        S6（性別年齡）先於 S4（炭盆是否熄滅）詢問。
        每步詢問後進行觸發情境偵測，並在 OHCA 判定前發送對應回應。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("燒炭_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("燒炭_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_both="請問患者有沒有清醒？是否有正常呼吸？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S2：反應/起伏（已清醒則只問起伏，避免重複問意識）──────────────
        engine._set_stage("燒炭_S2")
        self._run_s2_response_or_abdomen(
            engine,
            reaction_options=[
                "叫患者有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
                "大力捏患者肩膀有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
            ],
            abdomen_question="幫我看他的肚子有沒有一上、一下起伏。",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S6：性別與年齡（skip if both patient_gender+patient_age 已填）────
        engine._set_stage("燒炭_S6")
        engine._ensure_known_fields_from_history()

        if engine._is_field_filled("patient_gender") and engine._is_field_filled("patient_age"):
            engine._debug_print(
                "skip_S6",
                f"gender={engine.case.patient_gender}, age={engine.case.patient_age}",
            )
        else:
            q6 = "請問他是男生還是女生、大約幾歲？"
            answer6 = engine._ask_and_extract(q6)
            self._extract_s6_patient(answer6, q6, engine)
            self._check_and_respond_to_triggers(answer6, engine)

        # ── S4：類別專屬評估（skip if current_condition 已填）────────────────
        engine._set_stage("燒炭_S4")
        engine._ensure_known_fields_from_history()

        if not engine._is_field_filled("current_condition"):
            q4 = "現場炭盆是否已熄滅？"
            answer4 = engine._ask_and_extract(q4)
            self._extract_s4_charcoal_extinguished(answer4, q4, engine)
            self._check_and_respond_to_triggers(answer4, engine)
        else:
            engine._debug_print("skip_S4", engine.case.current_condition)

    # ── 其他抽取（S1/S2/OHCA 共用邏輯見 base.SubCategoryHandler）────────────

    def _extract_s6_patient(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S6 回答中抽取 patient_gender + patient_age。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_patient_info(question, answer)
            with engine._case_lock:
                if not engine.case.patient_gender and result.get("patient_gender"):
                    engine.case.patient_gender = result["patient_gender"]
                if not engine.case.patient_age and result.get("patient_age"):
                    engine.case.patient_age = result["patient_age"]
            engine._notify_case_update()
            engine._debug_print("S6_patient", result)
        except Exception as e:
            engine._debug_print("S6_patient_error", e)

    def _extract_s4_charcoal_extinguished(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4 回答中抽取炭盆熄滅狀態，存入 current_condition。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"current_condition": "string|null"},
                rules=(
                    "- current_condition：現場炭盆是否已熄滅的描述\n"
                    "  （如「已熄滅」「還沒熄」「已經熄了」「炭盆還在燒」「不知道」）；\n"
                    "  明確否認已熄滅（沒有/還沒）→ 輸出「炭盆未熄滅」；未提及 → null。"
                ),
                question=question,
            )
            val = result.get("current_condition")
            if val:
                with engine._case_lock:
                    if not engine.case.current_condition:
                        engine.case.current_condition = str(val).strip()
                engine._notify_case_update()
                engine._debug_print("current_condition", engine.case.current_condition)
        except Exception as e:
            engine._debug_print("current_condition_error", e)

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測燒炭的 2 個觸發情境。

        使用 extract_slots 搭配二鍵 boolean schema（t1–t2）。
        返回新觸發的情境編號列表。
        """
        if not engine._llm:
            return []
        try:
            from llm_extractor_119 import _coerce_bool

            schema = {"t1": "true|false|null", "t2": "true|false|null"}
            rules = (
                "從以下2個觸發情境中判斷哪些出現在【文本】裡，每項輸出 true/false/null。\n"
                "只要文本中出現對應描述（詞義相符即可，不必完全一致），該項輸出 true；\n"
                "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
                "情境定義：\n"
                "- t1：燒炭且患者還清醒可以說話\n"
                "  （燒炭、燒碳、炭盆、現場還有炭盆、炭盆已移到外面、已把窗戶打開、"
                "還清醒、可以說話、有意識）\n"
                "- t2：患者昏迷且好像沒呼吸\n"
                "  （昏迷、叫不醒、沒呼吸、好像沒呼吸、停止呼吸、沒有在呼吸）\n"
            )
            out = engine._llm.extract_slots(caller_text, schema=schema, rules=rules)
            already_set = set(already_triggered)
            new_triggers: List[int] = []
            for i, key in enumerate(("t1", "t2"), start=1):
                val = _coerce_bool(out.get(key))
                if val is True and i not in already_set:
                    new_triggers.append(i)
            return new_triggers
        except Exception as e:
            engine._debug_print("shaotan_trigger_check_error", e)
            return []

    def _check_and_respond_to_triggers(
        self, caller_text: str, engine: "SopEngine119"
    ) -> None:
        """
        偵測本輪文本中的觸發情境，對新觸發的情境發送對應回應。
        每個情境只觸發一次（由 case.triggered_scenarios 記錄）。
        """
        with engine._case_lock:
            already = list(engine.case.triggered_scenarios)
        new_triggers = self._check_triggers(caller_text, already, engine)
        for sid in new_triggers:
            with engine._case_lock:
                engine.case.triggered_scenarios.append(sid)
            engine._notify_case_update()
            engine._debug_print("shaotan_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應（全部為陳述句，無問句）。"""

        if scenario_id == 1:
            # 燒炭且還清醒可以說話
            engine._say(_R2)

        elif scenario_id == 2:
            # 昏迷好像沒呼吸
            engine._say(_R2)
            engine._say(_R4)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def run_pre_vital(self, engine: "SopEngine119") -> None:
        """燒炭已改用 run_subtype_flow，此鉤子保留為空以避免意外調用。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """燒炭使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
