"""
handlers/急病.py
━━━━━━━━━━━━━━━━
119 SOP — 急病次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行急病專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S2→S6，每步後進行觸發情境偵測與回應

報案人訊息：詢問姓名、聯繫方式與住址（含地址版）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2  = "救護車已經派了。"
_R3  = "請幫我將手機開擴音，我教你做急救。"
_R4  = "請您幫我打開大門，在家休息等救護車。"
_R5  = "你先不要緊張，先叫他咳嗽，看能不能咳出來。"
_R6  = "幫我看他的肚子有沒有一上、一下起伏。"
_R7  = "你看他肚子有沒有起伏、然後上、下數出來給我聽。"
_R8  = "患者本身有心臟病史嗎？"
_R11 = "可以幫患者量測過血糖嗎？血糖值為多少？"
_R14 = "請問抽搐多久？停止了嗎？是否有正常呼吸？"
_R16 = "是不是幫患者量測過血壓？血壓值為多少？"


class JiBingHandler(SubCategoryHandler):
    """急病次類別 Handler。"""

    # ── 急病專屬完整問題流程 ──────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        急病次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → S2（隨機三選一）→ S6
        每步詢問後進行觸發情境偵測，並在 OHCA 判定前發送對應回應。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("急病_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問現場發生什麼事？需要救護車嗎？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("急病_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_both="他是不是清醒呢？有沒有正常呼吸？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S2：反應/起伏（已清醒則只問起伏，避免重複問意識）──────────────
        engine._set_stage("急病_S2")
        self._run_s2_response_or_abdomen(
            engine,
            reaction_options=[
                "叫他有反應嗎？眼睛會不會打開、手會不會動、會不會發出聲音？",
                "大力捏他的肩膀有反應嗎？眼睛會不會打開、手會不會動、會不會發出聲音？",
            ],
            abdomen_question="幫我看他的肚子有沒有一上、一下起伏。",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S6：性別與年齡（skip if both patient_gender+patient_age 已填）────
        engine._set_stage("急病_S6")
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

    def _check_and_respond_to_triggers(
        self, caller_text: str, engine: "SopEngine119"
    ) -> None:
        """
        偵測本輪文本中的觸發情境，對新觸發的情境發送對應回應。
        每個情境只觸發一次（由 case.triggered_scenarios 記錄）。
        """
        if not engine._llm:
            return
        try:
            with engine._case_lock:
                already = list(engine.case.triggered_scenarios)
            new_triggers = engine._llm.check_trigger_scenarios(caller_text, already)
            for sid in new_triggers:
                with engine._case_lock:
                    engine.case.triggered_scenarios.append(sid)
                engine._notify_case_update()
                engine._debug_print("trigger_scenario", sid)
                self._send_trigger_responses(sid, engine)
        except Exception as e:
            engine._debug_print("trigger_check_error", e)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應（語句直接說出，問句詢問並抽取）。"""

        if scenario_id == 1:
            # 呼吸喘
            engine._say(_R2)

        elif scenario_id == 2:
            # 身體不適
            engine._say(_R2)
            engine._say(_R4)

        elif scenario_id == 3:
            # 胸悶、胸痛、心臟不適
            engine._say(_R2)
            self._ask_trigger_question(
                _R8, "medical_history",
                schema={"medical_history": "string|null"},
                rules=(
                    "- medical_history：患者心臟病史或其他慢性病史；"
                    "明確否認（沒有/不知道）→ 輸出「無」；未提及 → null。"
                ),
                engine=engine,
            )

        elif scenario_id == 4:
            # 冒冷汗、抽搐
            engine._say(_R2)
            self._ask_trigger_question(
                _R14, "seizure_info",
                schema={"seizure_info": "string|null"},
                rules=(
                    "- seizure_info：抽搐持續時間、是否已停止、呼吸狀況的描述；"
                    "未提及 → null。"
                ),
                engine=engine,
            )

        elif scenario_id == 5:
            # 昏迷
            engine._say(_R2)

        elif scenario_id == 6:
            # 低血糖
            engine._say(_R2)
            self._ask_trigger_question(
                _R11, "blood_glucose",
                schema={"blood_glucose": "string|null"},
                rules=(
                    "- blood_glucose：血糖量測值或相關描述；未量測/不知道 → null。"
                ),
                engine=engine,
            )

        elif scenario_id == 7:
            # 低血壓
            engine._say(_R2)
            engine._say(_R4)
            self._ask_trigger_question(
                _R16, "blood_pressure",
                schema={"blood_pressure": "string|null"},
                rules=(
                    "- blood_pressure：血壓量測值或相關描述；未量測/不知道 → null。"
                ),
                engine=engine,
            )

        elif scenario_id == 8:
            # 流鼻血
            engine._say(_R2)

        elif scenario_id == 9:
            # 噎到
            engine._say(_R2)
            engine._say(_R5)

        elif scenario_id == 10:
            # 叫沒反應、沒有呼吸
            engine._say(_R2)
            engine._say(_R3)
            # 回應6：問腹部起伏（skip if abdomen_rise 已填）
            if not engine._is_field_filled("abdomen_rise"):
                answer6 = engine._ask_and_extract(_R6)
                self._extract_s2_vitals(answer6, _R6, engine)
            else:
                engine._debug_print("skip_R6_abdomen_rise", engine.case.abdomen_rise)
            # 回應7：若腹部起伏仍未確認，再次詢問
            if not engine._is_field_filled("abdomen_rise"):
                answer7 = engine._ask_and_extract(_R7)
                self._extract_s2_vitals(answer7, _R7, engine)
            else:
                engine._debug_print("skip_R7_abdomen_rise", engine.case.abdomen_rise)

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
            engine._debug_print(f"skip_trigger_q_{field}", getattr(engine.case, field, None))
            return
        answer = engine._ask_and_extract(question)
        if engine._llm:
            try:
                result = engine._llm.extract_slots(answer, schema=schema, rules=rules, question=question)
                val = result.get(field)
                if val:
                    with engine._case_lock:
                        setattr(engine.case, field, str(val).strip())
                    engine._notify_case_update()
                    engine._debug_print(f"trigger_{field}", getattr(engine.case, field))
            except Exception as e:
                engine._debug_print(f"trigger_{field}_error", e)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def run_pre_vital(self, engine: "SopEngine119") -> None:
        """急病已改用 run_subtype_flow，此鉤子保留為空以避免意外調用。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """詢問報案人姓名、聯繫方式與住址；委派給基類共用實作。"""
        self._do_collect_caller_info(engine, include_address=false)
