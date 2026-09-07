"""
handlers/路倒.py
━━━━━━━━━━━━━━━━
119 SOP — 路倒次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行路倒專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S2→S4→S6，每步後進行觸發情境偵測與回應

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R1 = "重複確認地址，這樣對嗎？"   # 重新確認地址
_R2 = "救護車已經派了。"


class LuDaoHandler(SubCategoryHandler):
    """路倒次類別 Handler。"""

    SOP_SLOTS: tuple[str, ...] = (
        "incident_description",
        "consciousness",
        "breathing",
        "abdomen_rise",
        "medical_history",
        "patient_count",
        "patient_gender",
        "patient_age",
    )

    # ── 路倒專屬完整問題流程 ──────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        路倒次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → S2（隨機三選一）→ S4 → S6
        每步詢問後進行觸發情境偵測，並在 OHCA 判定前發送對應回應。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("路倒_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("路倒_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_consciousness="請問患者有沒有清醒？",
            q_breathing="是否有正常呼吸？",
            has_abdomen_followup=True,
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S2：反應/起伏（已清醒則只問起伏，避免重複問意識）──────────────
        engine._set_stage("路倒_S2")
        self._run_s2_response_or_abdomen(
            engine,
            reaction_options=[
                "叫患者有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
                "大力捏患者肩膀有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
            ],
            abdomen_question="幫我看他的肚子有沒有一上、一下起伏。",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S4：類別專屬評估（skip if medical_history 已填）─────────────────
        # medical_history 在路倒中存放「家屬是否在場」；通用跨欄位抽取不會
        # 把「旁邊沒家屬」寫入此欄，故提問前先用專屬規則從歷史補抽。
        engine._set_stage("路倒_S4")
        engine._ensure_known_fields_from_history()
        self._ensure_family_from_history(engine)

        if not engine._is_field_filled("medical_history"):
            q4 = "請問身邊是否有家屬？"
            answer4 = engine._ask_and_extract(q4)
            self._extract_s4_family(answer4, q4, engine)
            self._check_and_respond_to_triggers(answer4, engine)
        else:
            engine._debug_print("skip_S4", engine.case.medical_history)

        # ── S6：性別與年齡（語境感知，見 base._run_s6_gender_age）────────
        self._run_s6_gender_age(
            engine,
            "路倒_S6",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

    # ── 其他抽取（S1/S2/OHCA 共用邏輯見 base.SubCategoryHandler）────────────

    def _ensure_family_from_history(self, engine: "SopEngine119") -> None:
        """
        若報警人稍早已說明家屬在場情形（如「旁邊沒家屬」），
        從歷史回答補抽到 medical_history，以便跳過 S4。
        """
        if engine._is_field_filled("medical_history"):
            return
        for question, caller_text in engine._iter_caller_qa_pairs():
            if not caller_text:
                continue
            self._extract_s4_family(caller_text, question or "", engine)
            if engine._is_field_filled("medical_history"):
                engine._debug_print(
                    "S4_family_from_history", engine.case.medical_history
                )
                return

    def _extract_s4_family(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從回答中抽取家屬在場情形，存入 medical_history 作為備用欄位。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"medical_history": "string|null"},
                rules=(
                    "- medical_history：記錄家屬是否在場及相關說明\n"
                    "  （如『有家屬在場』『無家屬，獨居』『家屬正趕來』）；\n"
                    "  明確否認（沒有/沒家屬/旁邊沒/獨居）→ 輸出「無家屬」；"
                    "未提及 → null。"
                ),
                question=question,
            )
            val = result.get("medical_history")
            if val:
                with engine._case_lock:
                    if not engine.case.medical_history:
                        engine.case.medical_history = str(val).strip()
                engine._notify_case_update()
                engine._debug_print("S4_family", engine.case.medical_history)
        except Exception as e:
            engine._debug_print("S4_family_error", e)

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測路倒的 1 個觸發情境。

        返回新觸發的情境編號列表。
        """
        if not engine._llm:
            return []
        try:
            from llm_extractor_119 import _coerce_bool

            schema = {"t1": "true|false|null"}
            rules = (
                "從以下觸發情境中判斷是否出現在【文本】裡，輸出 true/false/null。\n"
                "只要文本中出現對應描述（詞義相符即可，不必完全一致），輸出 true；\n"
                "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
                "情境定義：\n"
                "- t1：有人倒在公共場所（花園、人行道、趴在地上、喝醉倒地、"
                "躺在地上、倒在公車站椅子上、路邊倒地）\n"
            )
            out = engine._llm.extract_slots(caller_text, schema=schema, rules=rules)
            already_set = set(already_triggered)
            new_triggers: List[int] = []
            val = _coerce_bool(out.get("t1"))
            if val is True and 1 not in already_set:
                new_triggers.append(1)
            return new_triggers
        except Exception as e:
            engine._debug_print("ludao_trigger_check_error", e)
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
            engine._debug_print("ludao_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應。"""

        if scenario_id == 1:
            # 有人倒在公共場所：重複確認地址 + 救護車已派
            current_addr = engine.case.display_address()
            engine._say(f"{_R1}地址是：{current_addr}。")
            engine._say(_R2)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def run_post_vital(self, engine: "SopEngine119") -> None:
        """路倒已改用 run_subtype_flow，此鉤子保留為空以避免意外調用。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """路倒使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
