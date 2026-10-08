"""
handlers/孕婦急產.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 孕婦急產次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行孕婦急產專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S4（七問），每步後進行觸發情境偵測與回應

注意：
- 無 S2（腹部起伏）步驟——孕婦患者通常有意識，OHCA 僅由 S1 判斷。
- 無 S6（性別年齡）步驟——孕婦性別已知，年齡可由後續抽取。
- S4 七問均為孕產科評估，均有對應新欄位（pregnancy_week / due_date 等）。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2  = "救護車已經派了。"
_R4  = "請您幫我打開大門，在家休息等救護車。"
_R18 = "拿毛巾先墊著。"


class YunFuJiChanHandler(SubCategoryHandler):
    """孕婦急產次類別 Handler。"""

    SOP_SLOTS: tuple[str, ...] = (
        "incident_description",
        "consciousness",
        "breathing",
        "pregnancy_week",
        "due_date",
        "multiple_pregnancy",
        "water_broken_bleeding",
        "contractions",
        "prenatal_history",
        "prenatal_clinic",
    )

    # ── 孕婦急產專屬完整問題流程 ──────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        孕婦急產次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → (觸發情境偵測 → OHCA 判斷) → S4（七問）
        每步詢問後進行觸發情境偵測；OHCA 判定在觸發回應送出後執行。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("孕婦急產_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("孕婦急產_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_consciousness="請問患者有沒有清醒？",
            q_breathing="是否有正常呼吸？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S4：孕產科評估（七問；長答可一次帶多欄，已填則跳過）──────────────
        engine._set_stage("孕婦急產_S4")

        s4_questions = (
            ("pregnancy_week", "懷孕第幾胎、幾週了？", True),
            ("due_date", "預產期是什麼時候？", True),
            ("multiple_pregnancy", "請問是單胞胎還是雙胞胎？", True),
            ("water_broken_bleeding", "有沒有破水？有沒有出血？", True),
            ("contractions", "有沒有規則宮縮？幾分鐘陣痛一次？", True),
            ("prenatal_history", "產檢有沒有異常？", True),
            ("prenatal_clinic", "在哪裡產檢？", False),  # 末問不另觸發情境
        )
        for field_name, question, do_trigger in s4_questions:
            engine._ensure_known_fields_from_history()
            if engine._is_field_filled(field_name):
                engine._debug_print(
                    f"skip_S4_{field_name}", getattr(engine.case, field_name)
                )
                continue
            answer = engine._ask_and_extract(question)
            # 長答可能同時帶預產期/單雙胎等 → 一次抽齊，供後續問題跳過
            self._extract_s4_ob_fields(answer, question, engine)
            if do_trigger:
                self._check_and_respond_to_triggers(answer, engine)

    # ── 欄位抽取 ──────────────────────────────────────────────────────────────

    # ── 其他抽取（S1/OHCA 共用邏輯見 base.SubCategoryHandler）──────────────

    _S4_OB_FIELDS = (
        "pregnancy_week",
        "due_date",
        "multiple_pregnancy",
        "water_broken_bleeding",
        "contractions",
        "prenatal_history",
        "prenatal_clinic",
        "patient_age",
    )

    def _extract_s4_ob_fields(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """
        從任一 S4 回答中抽取全部孕產欄位（含年齡）。
        規則備援優先，再以 LLM 補齊；已填欄位不覆蓋。
        """
        from sop_utils_119 import extract_pregnancy_info_hint

        hints = extract_pregnancy_info_hint(answer)
        if hints:
            with engine._case_lock:
                engine._apply_extracted_fields(hints)
            engine._debug_print("S4_ob_rule", hints)

        if not engine._llm:
            engine._notify_case_update()
            return

        try:
            schema = {k: "string|null" for k in self._S4_OB_FIELDS}
            result = engine._llm.extract_slots(
                answer,
                schema=schema,
                rules=(
                    "受理員可能只問其中一項，但報警人常一次回答多項，需全部抽取。\n"
                    "- pregnancy_week：胎次與週數（如「第1胎39週」）；未提及 → null。\n"
                    "- due_date：預產期（如「5月6日」）；未提及 → null。\n"
                    "- multiple_pregnancy：單胞胎/雙胞胎/多胞胎；未提及 → null。\n"
                    "- water_broken_bleeding：破水與出血；明確都沒有 →「無破水無出血」；"
                    "未提及 → null。\n"
                    "- contractions：宮縮頻率；明確沒有 →「無宮縮」；未提及 → null。\n"
                    "- prenatal_history：產檢異常；明確正常/沒有 →「產檢無異常」；"
                    "未提及 → null。\n"
                    "- prenatal_clinic：產檢醫院/診所名稱；未提及 → null。\n"
                    "- patient_age：年齡（如「39歲」）；未提及 → null。\n"
                    "例：「39歲，第一胎，39週，預產期5月6日，單胞胎，產檢都正常」→ "
                    "各欄皆應填入，不可只填 pregnancy_week。"
                ),
                question=question,
            )
            cleaned = {}
            for key in self._S4_OB_FIELDS:
                val = result.get(key)
                if val:
                    cleaned[key] = str(val).strip()
            if cleaned:
                with engine._case_lock:
                    engine._apply_extracted_fields(cleaned)
                engine._debug_print("S4_ob_llm", cleaned)
        except Exception as e:
            engine._debug_print("S4_ob_fields_error", e)

        engine._notify_case_update()

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測孕婦急產的 4 個觸發情境。

        使用 extract_slots 搭配四鍵 boolean schema（t1–t4）。
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
            }
            rules = (
                "從以下4個觸發情境中判斷哪些出現在【文本】裡，每項輸出 true/false/null。\n"
                "只要文本中出現對應描述（詞義相符即可，不必完全一致），該項輸出 true；\n"
                "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
                "情境定義：\n"
                "- t1：她快要生了（快要生、快生了、要生了、快臨盆、胎頭已出、寶寶快出來了）\n"
                "- t2：她現在還清醒、可以說話（有意識、有回應、清醒、可以講話）\n"
                "- t3：她沒有呼吸了（沒呼吸、停止呼吸、呼吸停止、沒有在呼吸）\n"
                "- t4：羊水破了、有流血、有規則陣痛或任何強烈產科症狀\n"
                "  （羊水破/破水、出血/流血、規則陣痛/宮縮、腹痛、30幾週、\n"
                "   第一胎、子癲前症、預產期、產檢、宮縮頻率）\n"
            )
            out = engine._llm.extract_slots(caller_text, schema=schema, rules=rules)
            already_set = set(already_triggered)
            new_triggers: List[int] = []
            for i, key in enumerate(("t1", "t2", "t3", "t4"), start=1):
                val = _coerce_bool(out.get(key))
                if val is True and i not in already_set:
                    new_triggers.append(i)
            return new_triggers
        except Exception as e:
            engine._debug_print("yunfu_trigger_check_error", e)
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
            engine._debug_print("yunfu_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應（全部為陳述句，無問句）。"""

        if scenario_id == 1:
            # 她快要生了
            engine._say(_R2)

        elif scenario_id == 2:
            # 她現在還清醒、可以說話
            engine._say(_R2)

        elif scenario_id == 3:
            # 她沒有呼吸了
            engine._say(_R2)
            engine._say(_R4)

        elif scenario_id == 4:
            # 羊水破了、有流血、有規則陣痛等產科症狀
            engine._say(_R2)
            engine._say(_R18)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """孕婦急產使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
