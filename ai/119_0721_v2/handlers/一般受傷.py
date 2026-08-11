"""
handlers/一般受傷.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 一般受傷次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行一般受傷專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S2→S4→S6，每步後進行觸發情境偵測與回應

報案人訊息：詢問姓名、聯繫方式與住址（含地址版）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2  = "救護車已經派了。"
_R9  = "機器先斷電，手有被夾住嗎？"
_R12 = "是不是有明顯外傷、大出血？外觀是否變形？"
_R17 = "是什麼原因導致患者受傷？玻璃割傷？機器切割傷？機器壓傷？"


class GeneralInjuryHandler(SubCategoryHandler):
    """一般受傷次類別 Handler。"""

    # ── 一般受傷專屬完整問題流程 ──────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        一般受傷次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → S2（隨機三選一）→ S4（兩問）→ S6
        每步詢問後進行觸發情境偵測，並在 OHCA 判定前發送對應回應。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("一般受傷_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("一般受傷_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_both="請問患者有沒有清醒？是不是有正常呼吸？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S2：反應/起伏（已清醒則只問起伏，避免重複問意識）──────────────
        engine._set_stage("一般受傷_S2")
        self._run_s2_response_or_abdomen(
            engine,
            reaction_options=[
                "叫患者有反應嗎？眼睛能不能打開、手會不會動、會不會發出聲音？",
                "大力捏患者肩膀有反應嗎？眼睛能不能打開、手會不會動、會不會發出聲音？",
            ],
            abdomen_question="幫我看他的肚子有沒有一上、一下起伏。",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S4：類別專屬評估（兩問，skip if injury_cause 已填）──────────────
        engine._set_stage("一般受傷_S4")
        engine._ensure_known_fields_from_history()

        # S4-Q1：跌倒類型
        if not engine._is_field_filled("injury_cause"):
            q4a = "請問患者是身體不舒服跌倒，還是不小心撞到跌倒呢？"
            answer4a = engine._ask_and_extract(q4a)
            self._extract_injury_cause(answer4a, q4a, engine)
            self._check_and_respond_to_triggers(answer4a, engine)

        # S4-Q2：工作受傷（skip if injury_cause 已填）
        if not engine._is_field_filled("injury_cause"):
            q4b = "是工作受傷嗎？"
            answer4b = engine._ask_and_extract(q4b)
            self._extract_injury_cause(answer4b, q4b, engine)
            self._check_and_respond_to_triggers(answer4b, engine)

        # ── S6：性別與年齡（skip if both patient_gender+patient_age 已填）────
        engine._set_stage("一般受傷_S6")
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

    # ── 其他抽取（S1/S2/OHCA 共用邏輯見 base.SubCategoryHandler）────────────

    def _extract_injury_cause(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4 回答中抽取 injury_cause。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"injury_cause": "string|null"},
                rules=(
                    "- injury_cause：描述受傷或事故的原因\n"
                    "  （如跌倒、工作受傷、被機器壓傷、身體不舒服跌倒、不小心撞到）；\n"
                    "  明確是工作受傷時需包含『工作受傷』字樣；未提及 → null。"
                ),
                question=question,
            )
            val = result.get("injury_cause")
            if val:
                with engine._case_lock:
                    if not engine.case.injury_cause:
                        engine.case.injury_cause = str(val).strip()
                engine._notify_case_update()
                engine._debug_print("injury_cause", engine.case.injury_cause)
        except Exception as e:
            engine._debug_print("injury_cause_error", e)

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

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測一般受傷的 3 個觸發情境。

        使用 extract_slots 搭配三鍵 boolean schema（t1、t2、t3）。
        返回新觸發的情境編號列表。
        """
        if not engine._llm:
            return []
        try:
            from llm_extractor_119 import _coerce_bool

            schema = {"t1": "true|false|null", "t2": "true|false|null", "t3": "true|false|null"}
            rules = (
                "從以下3個觸發情境中判斷哪些出現在【文本】裡，每項輸出 true/false/null。\n"
                "只要文本中出現對應描述（詞義相符即可，不必完全一致），該項輸出 true；\n"
                "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
                "情境定義：\n"
                "- t1：跌倒受傷（跌倒、摔倒、摔跤、滑倒、撞倒）\n"
                "- t2：工作受傷（職災、工作中受傷、上班受傷、工廠受傷、是工作受傷）\n"
                "- t3：斷肢或斷指（斷手、斷指、斷肢、手指斷掉、被切斷、截肢）\n"
            )
            out = engine._llm.extract_slots(caller_text, schema=schema, rules=rules)
            already_set = set(already_triggered)
            new_triggers: List[int] = []
            for i, key in enumerate(("t1", "t2", "t3"), start=1):
                val = _coerce_bool(out.get(key))
                if val is True and i not in already_set:
                    new_triggers.append(i)
            return new_triggers
        except Exception as e:
            engine._debug_print("injury_trigger_check_error", e)
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
            engine._debug_print("injury_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應（語句直接說出，問句詢問並抽取）。"""

        if scenario_id == 1:
            # 跌倒受傷
            engine._say(_R2)
            self._ask_trigger_question(
                _R12, "injury_severity",
                schema={"injury_severity": "string|null"},
                rules=(
                    "- injury_severity：明顯外傷、大出血、外觀變形等傷勢描述；"
                    "明確否認（沒有/沒）→ 輸出「無明顯外傷」；未提及 → null。"
                ),
                engine=engine,
            )

        elif scenario_id == 2:
            # 工作受傷
            engine._say(_R2)
            self._ask_trigger_question(
                _R12, "injury_severity",
                schema={"injury_severity": "string|null"},
                rules=(
                    "- injury_severity：明顯外傷、大出血、外觀變形等傷勢描述；"
                    "明確否認（沒有/沒）→ 輸出「無明顯外傷」；未提及 → null。"
                ),
                engine=engine,
            )
            self._ask_trigger_question(
                _R17, "injury_cause",
                schema={"injury_cause": "string|null"},
                rules=(
                    "- injury_cause：受傷原因（玻璃割傷、機器切割傷、機器壓傷等）；"
                    "未提及 → null。"
                ),
                engine=engine,
            )

        elif scenario_id == 3:
            # 斷肢/斷指
            engine._say(_R2)
            self._ask_trigger_question(
                _R9, "current_condition",
                schema={"current_condition": "string|null"},
                rules=(
                    "- current_condition：是否被機器夾住、夾傷部位及目前狀況；"
                    "未提及 → null。"
                ),
                engine=engine,
            )
            self._ask_trigger_question(
                _R12, "injury_severity",
                schema={"injury_severity": "string|null"},
                rules=(
                    "- injury_severity：明顯外傷、大出血、外觀變形等傷勢描述；"
                    "明確否認（沒有/沒）→ 輸出「無明顯外傷」；未提及 → null。"
                ),
                engine=engine,
            )
            self._ask_trigger_question(
                _R17, "injury_cause",
                schema={"injury_cause": "string|null"},
                rules=(
                    "- injury_cause：受傷原因（玻璃割傷、機器切割傷、機器壓傷等）；"
                    "未提及 → null。"
                ),
                engine=engine,
            )

    def _ask_trigger_question(
        self,
        question: str,
        field: str,
        schema: dict,
        rules: str,
        engine: "SopEngine119",
    ) -> None:
        """
        觸發回應中的問句：若對應欄位已填則跳過，否則詢問並抽取。
        """
        if engine._is_field_filled(field):
            engine._debug_print(
                f"skip_trigger_q_{field}", getattr(engine.case, field, None)
            )
            return
        answer = engine._ask_and_extract(question)
        if engine._llm:
            try:
                result = engine._llm.extract_slots(
                    answer, schema=schema, rules=rules, question=question
                )
                val = result.get(field)
                if val:
                    with engine._case_lock:
                        if not engine._is_field_filled(field):
                            setattr(engine.case, field, str(val).strip())
                    engine._notify_case_update()
                    engine._debug_print(
                        f"trigger_{field}", getattr(engine.case, field, None)
                    )
            except Exception as e:
                engine._debug_print(f"trigger_{field}_error", e)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def run_post_vital(self, engine: "SopEngine119") -> None:
        """一般受傷已改用 run_subtype_flow，此鉤子保留為空以避免意外調用。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """詢問報案人姓名、聯繫方式與住址；委派給基類共用實作。"""
        self._do_collect_caller_info(engine, include_address=false)
