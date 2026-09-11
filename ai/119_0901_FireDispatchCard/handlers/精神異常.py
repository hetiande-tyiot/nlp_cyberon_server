"""
handlers/精神異常.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 精神異常次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行精神異常專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S4（三問），每步後進行觸發情境偵測與回應

無 S2（腹部起伏）及 S6（性別年齡）步驟——精神異常患者通常清醒激動，
OHCA 由 S1 結果判斷；若觸發情境 3/4（叫不醒）則於觸發回應中問腹部起伏。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2 = "救護車已經派了。"
_R6 = "幫我看他的肚子有沒有一上、一下起伏。"


def _r1(engine: "SopEngine119") -> str:
    """回應1：重複確認目前已記錄的地址。"""
    return f"重複確認地址，這樣對嗎？地址是：{engine.case.display_address()}。"


class JingShenYiChangHandler(SubCategoryHandler):
    """精神異常次類別 Handler。"""

    # ── 精神異常專屬完整問題流程 ──────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        精神異常次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → (觸發情境偵測 → OHCA 判斷) → S4（三問）
        每步詢問後進行觸發情境偵測，觸發回應在 OHCA 判定前送出。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("精神異常_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("精神異常_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_consciousness="請問患者有沒有清醒？",
            q_breathing="有沒有正常呼吸呢？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S4：類別專屬評估（三問）─────────────────────────────────────────
        engine._set_stage("精神異常_S4")
        engine._ensure_known_fields_from_history()

        # S4-Q1：精神疾病病史（skip if medical_history 已填）
        if not engine._is_field_filled("medical_history"):
            q4a = "請問患者有精神疾病病史嗎？"
            answer4a = engine._ask_and_extract(q4a)
            self._extract_medical_history(answer4a, q4a, engine)
            self._check_and_respond_to_triggers(answer4a, engine)
        else:
            engine._debug_print("skip_S4_Q1", engine.case.medical_history)

        # S4-Q2：自傷或傷害他人行為（skip if current_condition 已填）
        if not engine._is_field_filled("current_condition"):
            q4b = "有自傷或傷害他人行為嗎？"
            answer4b = engine._ask_and_extract(q4b)
            self._extract_current_condition(answer4b, q4b, engine)
            self._check_and_respond_to_triggers(answer4b, engine)
        else:
            engine._debug_print("skip_S4_Q2", engine.case.current_condition)

        # S4-Q3：家屬陪同（無專屬欄位，永遠詢問，通用抽取捕捉回答）
        q4c = "現場有沒有家屬陪同？"
        answer4c = engine._ask_and_extract(q4c)
        self._check_and_respond_to_triggers(answer4c, engine)

    # ── 欄位抽取 ──────────────────────────────────────────────────────────────

    # ── 其他抽取（S1/OHCA 共用邏輯見 base.SubCategoryHandler）──────────────

    def _extract_medical_history(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q1 回答中抽取精神疾病病史。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"medical_history": "string|null"},
                rules=(
                    "- medical_history：患者精神疾病病史或慢性病史\n"
                    "  （如思覺失調、憂鬱症、躁鬱症、有定期就診、有服藥）；\n"
                    "  明確否認（沒有/不知道）→ 輸出「無」；未提及 → null。"
                ),
                question=question,
            )
            val = result.get("medical_history")
            if val:
                with engine._case_lock:
                    if not engine.case.medical_history:
                        engine.case.medical_history = str(val).strip()
                engine._notify_case_update()
                engine._debug_print("medical_history", engine.case.medical_history)
        except Exception as e:
            engine._debug_print("medical_history_error", e)

    def _extract_current_condition(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q2 回答中抽取自傷或傷人行為描述。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"current_condition": "string|null"},
                rules=(
                    "- current_condition：患者目前的自傷或傷害他人行為描述\n"
                    "  （如自傷、割腕、打人、攻擊、砸東西、有傷人傾向）；\n"
                    "  明確否認（沒有/沒有這些行為）→ 輸出「無自傷或傷人行為」；"
                    "未提及 → null。"
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
        偵測精神異常的 5 個觸發情境。

        使用 extract_slots 搭配五鍵 boolean schema（t1–t5）。
        返回新觸發的情境編號列表。
        """
        if not engine._llm:
            return []
        try:
            from llm_extractor_119 import _coerce_bool

            schema = {
                "t1": "true|false|null",
                "t2": "true|false|null",
                "t3": "true|false|null",
                "t4": "true|false|null",
                "t5": "true|false|null",
            }
            rules = (
                "從以下5個觸發情境中判斷哪些出現在【文本】裡，每項輸出 true/false/null。\n"
                "只要文本中出現對應描述（詞義相符即可，不必完全一致），該項輸出 true；\n"
                "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
                "情境定義：\n"
                "- t1：精神異常行為（大喊大叫、一直摔東西、一直哭、精神異常）\n"
                "- t2：須強制送醫（答非所問、情緒不穩、砸東西撞牆、攻擊行為、攻擊傾向、"
                "忘記吃藥、自殘行為、情緒激動、騷擾、想輕生、胡言亂語、一直撞牆）\n"
                "- t3：叫不醒或吞藥（叫不醒、無反應、吞安眠藥、吞藥、服藥過量）\n"
                "- t4：有精神科病史定期就診（思覺失調、憂鬱症、躁鬱症、定期在醫院看診）\n"
                "- t5：持械傷人（拿菜刀亂揮、動手打人、持刀、揮刀、攻擊他人）\n"
            )
            out = engine._llm.extract_slots(caller_text, schema=schema, rules=rules)
            already_set = set(already_triggered)
            new_triggers: List[int] = []
            for i, key in enumerate(("t1", "t2", "t3", "t4", "t5"), start=1):
                val = _coerce_bool(out.get(key))
                if val is True and i not in already_set:
                    new_triggers.append(i)
            return new_triggers
        except Exception as e:
            engine._debug_print("jingshen_trigger_check_error", e)
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
            engine._debug_print("jingshen_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應。"""

        if scenario_id in (1, 2, 5):
            # 情境 1（精神異常行為）、2（強制送醫）、5（持械傷人）
            engine._say(_r1(engine))
            engine._say(_R2)

        elif scenario_id in (3, 4):
            # 情境 3（叫不醒/吞藥）、4（精神科病史定期就診）
            engine._say(_r1(engine))
            engine._say(_R2)
            # 回應6：問腹部起伏（skip if abdomen_rise 已填）
            self._ask_trigger_question(
                _R6, "abdomen_rise",
                schema={"abdomen_rise": "true|false|null"},
                rules=(
                    "- abdomen_rise：肚子/腹部有無起伏。\n"
                    "  有起伏/有動 → true；沒有起伏/沒動 → false；未提及 → null。"
                ),
                engine=engine,
                is_vital=True,
            )

    def _ask_trigger_question(
        self,
        question: str,
        field: str,
        schema: dict,
        rules: str,
        engine: "SopEngine119",
        *,
        is_vital: bool = False,
    ) -> None:
        """
        觸發回應中的問句：若對應欄位已填則跳過，否則詢問並抽取。
        is_vital=True 時以布林值處理（如 abdomen_rise）。
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
                    answer, schema=schema, rules=rules, question=question,
                    strict_tail=(
                        "\n\n【全局強約束（是/否確認）】\n"
                        "- 必須輸出 schema 中的所有 key\n"
                        "- 輸出必須為單行 JSON\n"
                    ) if is_vital else None,
                )
                val = result.get(field)
                if val is not None:
                    if is_vital:
                        from llm_extractor_119 import _coerce_bool
                        from sop_utils_119 import parse_yes_no_for_question
                        bool_val = _coerce_bool(val)
                        if bool_val is None:
                            bool_val = parse_yes_no_for_question(question, answer)
                        if bool_val is not None:
                            with engine._case_lock:
                                if getattr(engine.case, field) is None:
                                    setattr(engine.case, field, bool_val)
                            engine._notify_case_update()
                            engine._debug_print(f"trigger_{field}", bool_val)
                    else:
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

    def run_pre_vital(self, engine: "SopEngine119") -> None:
        """精神異常已改用 run_subtype_flow，此鉤子保留為空以避免意外調用。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """精神異常使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
