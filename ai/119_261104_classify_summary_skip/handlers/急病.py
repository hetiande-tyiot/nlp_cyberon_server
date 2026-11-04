"""
handlers/急病.py
━━━━━━━━━━━━━━━━
119 SOP — 急病次類別 Handler

照 1018 xlsx 急病的題目表逐題問（ems_tab_map_119.JI_BING_QUESTIONS）：
  run_subtype_flow — 每題問完進行觸發情境偵測與回應，問完呼吸做 OHCA 判定

報案人訊息：詢問姓名、聯繫方式與住址（含地址版）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from ems_tab_map_119 import JI_BING_QUESTIONS

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

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

    # 題目表的欄位，加上 OHCA 判定用的「是否有意識」和肚子起伏（切換次案類時用：
    # 沒列在這裡的欄位，從別的次案類切過來時會被清掉）
    SOP_SLOTS: tuple[str, ...] = tuple(
        item.field for item in JI_BING_QUESTIONS
    ) + ("consciousness", "abdomen_rise")

    # ── 急病完整問題流程 ──────────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        照 1018 xlsx 急病的題目表逐題問（見 ems_tab_map_119.JI_BING_QUESTIONS、
        base._ask_ems_questions）。每題問完檢查觸發情境；問完呼吸做 OHCA 判定。
        """
        engine._ensure_known_fields_from_history()
        self._ask_ems_questions(engine, JI_BING_QUESTIONS)

    def _ems_question_needed(self, engine: "SopEngine119", item, fields) -> bool:
        """
        病徵已經有、但只是「身體不舒服」這類籠統說法時，仍問一次，
        讓真正的次案類（燙傷、要生了、吞藥…）浮現，觸發重新分類切出急病。
        """
        if item.field == "incident_description" and self._incident_is_vague(engine):
            return True
        return super()._ems_question_needed(engine, item, fields)

    def _check_ohca_after_breathing(self, engine: "SopEngine119") -> None:
        """
        呼吸不是「有」→ 先請報案人看肚子有沒有起伏，起伏也不是「有」才判 OHCA 轉人工。
        肚子起伏不在 xlsx 題目裡，是原本 OHCA 判定的最後一步，保留。
        """
        with engine._case_lock:
            breathing = engine.case.breathing
        if breathing is True:
            return
        engine._set_stage("急病-肚子起伏")
        if engine._is_field_filled("abdomen_rise"):
            engine._debug_print("skip_急病-肚子起伏", engine.case.abdomen_rise)
        else:
            answer = engine._ask_and_extract(_R6)
            self._extract_s2_vitals(answer, _R6, engine)
            self._check_and_respond_to_triggers(answer, engine)
        self._check_ohca_after_s2(engine)

    # ── 其他抽取（S1/S2/OHCA 共用邏輯見 base.SubCategoryHandler）────────────

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
            # 呼吸喘：原本只講「救護車已經派了」。
            # 派車改在次案類確定時講過了，這裡不用再說話。
            pass

        elif scenario_id == 2:
            # 身體不適
            engine._say(_R4)

        elif scenario_id == 3:
            # 胸悶、胸痛、心臟不適
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
            # C：昏迷成因常是服藥/中毒，報案人未必主動說 → 主動探問，帶出訊號後
            #    由每輪 sub-reclassify 有機會切到吞食藥物。
            self._probe_cause_ingestion(engine)

        elif scenario_id == 6:
            # 低血糖
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
            # 流鼻血：原本只講「救護車已經派了」。
            # 派車改在次案類確定時講過了，這裡不用再說話。
            pass

        elif scenario_id == 9:
            # 噎到
            engine._say(_R5)

        elif scenario_id == 10:
            # 叫沒反應、沒有呼吸
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
            # C：叫沒反應成因常是服藥/中毒 → 主動探問，帶出訊號後由每輪 sub-reclassify
            #    有機會切到吞食藥物。
            self._probe_cause_ingestion(engine)

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
        self._do_collect_caller_info(engine, include_address=False)
