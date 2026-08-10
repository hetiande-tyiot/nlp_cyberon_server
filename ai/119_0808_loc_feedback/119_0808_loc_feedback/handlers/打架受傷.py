"""
handlers/打架受傷.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 打架受傷次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行打架受傷專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S2→S6→S4，每步後進行觸發情境偵測與回應

注意：此次類別 S6（性別年齡）在 S4（現場人數）之前詢問。

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


class DaJiaShouShangHandler(SubCategoryHandler):
    """打架受傷次類別 Handler。"""

    # ── 打架受傷專屬完整問題流程 ──────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        打架受傷次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → S2（隨機三選一）→ S6 → S4
        S6（性別年齡）先於 S4（現場人數）詢問。
        每步詢問後進行觸發情境偵測，並在 OHCA 判定前發送對應回應。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("打架受傷_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("打架受傷_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_both="請問患者有沒有清醒？是否有正常呼吸？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S2：反應/起伏（已清醒則只問起伏，避免重複問意識）──────────────
        engine._set_stage("打架受傷_S2")
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
        engine._set_stage("打架受傷_S6")
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

        # ── S4：類別專屬評估（skip if patient_count 已填）──────────────────
        engine._set_stage("打架受傷_S4")
        engine._ensure_known_fields_from_history()

        if not engine._is_field_filled("patient_count"):
            q4 = "現場有幾個人受傷？"
            answer4 = engine._ask_and_extract(q4)
            self._extract_s4_patient_count(answer4, q4, engine)
            self._check_and_respond_to_triggers(answer4, engine)
        else:
            engine._debug_print("skip_S4", engine.case.patient_count)

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

    def _extract_s4_patient_count(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4 回答中抽取現場受傷人數。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"patient_count": "string|null"},
                rules=(
                    "- patient_count：現場受傷人數，保留原文數字或描述\n"
                    "  （如「1位」「兩個人」「3人」「很多人」）；未提及 → null。"
                ),
                question=question,
            )
            val = result.get("patient_count")
            if val:
                with engine._case_lock:
                    if not engine.case.patient_count:
                        engine.case.patient_count = str(val).strip()
                engine._notify_case_update()
                engine._debug_print("patient_count", engine.case.patient_count)
        except Exception as e:
            engine._debug_print("patient_count_error", e)

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測打架受傷的 3 個觸發情境。

        使用 extract_slots 搭配三鍵 boolean schema（t1–t3）。
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
            }
            rules = (
                "從以下3個觸發情境中判斷哪些出現在【文本】裡，每項輸出 true/false/null。\n"
                "只要文本中出現對應描述（詞義相符即可，不必完全一致），該項輸出 true；\n"
                "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
                "情境定義：\n"
                "- t1：打架或糾紛受傷（打架、糾紛、家庭糾紛、打架糾紛、糾紛受傷、"
                "家暴、被人毆打、自稱被打）\n"
                "- t2：清醒但意識模糊（叫他眼睛張開一下、眼神空洞、捏肩膀手會揮、"
                "無法說話、問話只會恩哼、完全沒反應）\n"
                "- t3：腹部起伏評估（肚子還在動但很慢、好幾秒才起伏一次、"
                "好像沒在動、肚子沒有起伏）\n"
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
            engine._debug_print("dajia_trigger_check_error", e)
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
            engine._debug_print("dajia_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應。"""

        if scenario_id in (1, 3):
            # 情境 1（打架受傷）、3（肚子起伏評估）
            engine._say(_r1(engine))
            engine._say(_R2)

        elif scenario_id == 2:
            # 情境 2（清醒但意識模糊）
            engine._say(_r1(engine))
            engine._say(_R2)
            self._ask_trigger_question(
                _R6, "abdomen_rise",
                schema={"abdomen_rise": "true|false|null"},
                rules=(
                    "- abdomen_rise：肚子/腹部有無起伏。\n"
                    "  有起伏/有動 → true；沒有起伏/沒動 → false；未提及 → null。"
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
        觸發回應中的問句（布林欄位）：若對應欄位已填則跳過，否則詢問並抽取。
        """
        if engine._is_field_filled(field):
            engine._debug_print(
                f"skip_trigger_q_{field}", getattr(engine.case, field, None)
            )
            return
        answer = engine._ask_and_extract(question)
        if engine._llm:
            try:
                from llm_extractor_119 import _coerce_bool
                from sop_utils_119 import parse_yes_no_for_question

                result = engine._llm.extract_slots(
                    answer, schema=schema, rules=rules, question=question,
                    strict_tail=(
                        "\n\n【全局強約束（是/否確認）】\n"
                        "- 必須輸出 schema 中的所有 key\n"
                        "- 輸出必須為單行 JSON\n"
                    ),
                )
                val = _coerce_bool(result.get(field))
                if val is None:
                    val = parse_yes_no_for_question(question, answer)
                if val is not None:
                    with engine._case_lock:
                        if getattr(engine.case, field) is None:
                            setattr(engine.case, field, val)
                    engine._notify_case_update()
                    engine._debug_print(f"trigger_{field}", val)
            except Exception as e:
                engine._debug_print(f"trigger_{field}_error", e)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def run_pre_vital(self, engine: "SopEngine119") -> None:
        """打架受傷已改用 run_subtype_flow，此鉤子保留為空以避免意外調用。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """打架受傷使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
