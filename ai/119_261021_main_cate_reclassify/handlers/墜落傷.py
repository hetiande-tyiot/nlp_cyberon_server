"""
handlers/墜落傷.py
━━━━━━━━━━━━━━━━━
119 SOP — 墜落傷次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行墜落傷專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S2→S6→S4（三問），每步後進行觸發情境偵測與回應

注意：此次類別 S6（性別年齡）在 S4（類別專屬評估）之前詢問。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2  = "救護車已經派了。"
_R12 = "是不是有明顯外傷、大出血？外觀是否變形？"


class ZhuiLuoShangHandler(SubCategoryHandler):
    """墜落傷次類別 Handler。"""

    SOP_SLOTS: tuple[str, ...] = (
        "incident_description",
        "consciousness",
        "breathing",
        "abdomen_rise",
        "patient_count",
        "patient_gender",
        "patient_age",
        "injury_cause",
        "injury_severity",
    )

    # ── 墜落傷專屬完整問題流程 ────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        墜落傷次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → S2（隨機三選一）→ S6 → S4（三問）
        S6（性別年齡）先於 S4（類別評估）詢問。
        每步詢問後進行觸發情境偵測，並在 OHCA 判定前發送對應回應。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("墜落傷_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("墜落傷_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_consciousness="請問患者有沒有清醒？",
            q_breathing="是否有正常呼吸？",
            has_abdomen_followup=True,
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S2：反應/起伏（已清醒則只問起伏，避免重複問意識）──────────────
        engine._set_stage("墜落傷_S2")
        self._run_s2_response_or_abdomen(
            engine,
            reaction_options=[
                "叫他有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
                "大力捏患者肩膀有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
            ],
            abdomen_question="幫我看他的肚子有沒有一上、一下起伏。",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S6：性別與年齡（語境感知，見 base._run_s6_gender_age）────────
        self._run_s6_gender_age(
            engine,
            "墜落傷_S6",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S4：類別專屬評估（三問）─────────────────────────────────────────
        engine._set_stage("墜落傷_S4")
        engine._ensure_known_fields_from_history()

        # S4-Q1：墜落高度（skip if injury_cause 已填）
        if not engine._is_field_filled("injury_cause"):
            q4a = "大約從幾層樓高度墜落？"
            answer4a = engine._ask_and_extract(q4a)
            self._extract_s4_fall_height(answer4a, q4a, engine)
            self._check_and_respond_to_triggers(answer4a, engine)
        else:
            engine._debug_print("skip_S4_Q1", engine.case.injury_cause)

        # S4-Q2：明顯外傷（skip if injury_severity 已填）
        if not engine._is_field_filled("injury_severity"):
            q4b = "有沒有明顯血流不止的傷口、或骨頭變形？"
            answer4b = engine._ask_and_extract(q4b)
            self._extract_s4_injury_severity(answer4b, q4b, engine)
            self._check_and_respond_to_triggers(answer4b, engine)
        else:
            engine._debug_print("skip_S4_Q2", engine.case.injury_severity)

        # S4-Q3：報案人身份（無專屬欄位，永遠詢問，通用抽取捕捉）
        q4c = "你是家屬還是路人協助報案？"
        engine._ask_and_extract(q4c)

    # ── 其他抽取（S1/S2/OHCA 共用邏輯見 base.SubCategoryHandler）────────────

    def _extract_s4_fall_height(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q1 回答中抽取墜落高度，存入 injury_cause。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"injury_cause": "string|null"},
                rules=(
                    "- injury_cause：描述墜落高度或受傷機制\n"
                    "  （如「從5樓墜落」「約3層樓高」「從屋頂跌下」「不確定」）；\n"
                    "  未提及具體高度 → null。"
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

    def _extract_s4_injury_severity(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q2 回答中抽取外傷與骨骼變形情形，存入 injury_severity。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"injury_severity": "string|null"},
                rules=(
                    "- injury_severity：外傷、出血或骨骼變形的描述\n"
                    "  （如「大量出血」「頭部裂傷」「腿骨變形」「無明顯外傷」）；\n"
                    "  明確否認（沒有/沒）→ 輸出「無明顯外傷」；未提及 → null。"
                ),
                question=question,
            )
            val = result.get("injury_severity")
            if val:
                with engine._case_lock:
                    if not engine.case.injury_severity:
                        engine.case.injury_severity = str(val).strip()
                engine._notify_case_update()
                engine._debug_print("injury_severity", engine.case.injury_severity)
        except Exception as e:
            engine._debug_print("injury_severity_error", e)

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測墜落傷的 2 個觸發情境。

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
                "- t1：有人從高處墜落（掉下來、從幾樓墜落、從高處跌落、卡在上面、"
                "還在呼吸、可以說話、頭一直在流血、墜樓）\n"
                "- t2：躺在地上完全沒有動（躺在地上沒在動、沒有在動、一動也不動）\n"
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
            engine._debug_print("zhuiluo_trigger_check_error", e)
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
            engine._debug_print("zhuiluo_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應。"""

        if scenario_id in (1, 2):
            # 情境 1（高樓墜落）、情境 2（躺地不動）
            engine._say(_R2)
            self._ask_trigger_question(
                _R12, "injury_severity",
                schema={"injury_severity": "string|null"},
                rules=(
                    "- injury_severity：明顯外傷、大出血、外觀變形等傷勢描述；\n"
                    "  明確否認（沒有/沒）→ 輸出「無明顯外傷」；未提及 → null。"
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
                    str_val = str(val).strip()
                    if str_val:
                        with engine._case_lock:
                            if not engine._is_field_filled(field):
                                setattr(engine.case, field, str_val)
                        engine._notify_case_update()
                        engine._debug_print(f"trigger_{field}", str_val)
            except Exception as e:
                engine._debug_print(f"trigger_{field}_error", e)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """墜落傷使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
