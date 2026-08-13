"""
handlers/吞食藥物.py
━━━━━━━━━━━━━━━━━━━
119 SOP — 吞食藥物次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行吞食藥物專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S2→S4→S6，每步後進行觸發情境偵測與回應

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2  = "救護車已經派了。"
_R6  = "幫我看他的肚子有沒有一上、一下起伏。"
_R13 = "服用何種藥物？大約幾顆？"


def _r1(engine: "SopEngine119") -> str:
    """回應1：重複確認目前已記錄的地址。"""
    return f"重複確認地址，這樣對嗎？地址是：{engine.case.display_address()}。"


class TunShiYaoWuHandler(SubCategoryHandler):
    """吞食藥物次類別 Handler。"""

    # ── 吞食藥物專屬完整問題流程 ──────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        吞食藥物次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → S2（隨機三選一）→ S4 → S6
        每步詢問後進行觸發情境偵測，並在 OHCA 判定前發送對應回應。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("吞食藥物_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("吞食藥物_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_consciousness="請問他有沒有清醒？",
            q_breathing="是否有正常呼吸？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S2：反應/起伏（已清醒則只問起伏，避免重複問意識）──────────────
        engine._set_stage("吞食藥物_S2")
        self._run_s2_response_or_abdomen(
            engine,
            reaction_options=[
                "叫他有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
                "大力捏患者肩膀有反應嗎？眼睛是否打開、手會不會動、會不會發出聲音？",
            ],
            abdomen_question="幫我看他的肚子有沒有一上、一下起伏。",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S4：酒精狀態（skip if current_condition 已填）───────────────────
        engine._set_stage("吞食藥物_S4")
        engine._ensure_known_fields_from_history()

        if not engine._is_field_filled("current_condition"):
            q4 = "他有喝酒嗎？"
            answer4 = engine._ask_and_extract(q4)
            self._extract_s4_alcohol(answer4, q4, engine)
            self._check_and_respond_to_triggers(answer4, engine)
        else:
            engine._debug_print("skip_S4", engine.case.current_condition)

        # ── S6：性別與年齡（語境感知，見 base._run_s6_gender_age）────────
        self._run_s6_gender_age(
            engine,
            "吞食藥物_S6",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

    # ── 其他抽取（S1/S2/OHCA 共用邏輯見 base.SubCategoryHandler）────────────

    def _extract_s4_alcohol(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4 回答中抽取酒精狀態，存入 current_condition。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"current_condition": "string|null"},
                rules=(
                    "- current_condition：患者是否有飲酒及相關狀況描述\n"
                    "  （如「有喝酒」「喝了很多酒」「沒有喝酒」「不知道」）；\n"
                    "  明確否認（沒有/沒）→ 輸出「未飲酒」；未提及 → null。"
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
        偵測吞食藥物的 4 個觸發情境。

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
                "- t1：明確吞食藥物或農藥（吞藥、吃藥、喝農藥、服藥、藥物中毒）\n"
                "- t2：大量服藥（吃了整包藥、整排藥、很多藥、過量服藥、精神科藥物、"
                "安眠藥、疑似吞食藥物、不知道吃了什麼藥）\n"
                "- t3：半意識或意識模糊（眼睛空洞迷糊、搖他手揮一下、問話只會哼、"
                "完全沒反應、叫他沒反應、叫不醒）\n"
                "- t4：腹部起伏狀況描述（肚子有在動、動得很慢、好像沒在動、起伏很慢、"
                "幾秒才起伏一次）\n"
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
            engine._debug_print("tunshi_trigger_check_error", e)
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
            engine._debug_print("tunshi_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應。"""

        if scenario_id in (1, 2):
            # 情境 1（吞食藥物/農藥）、2（大量服藥）
            engine._say(_r1(engine))
            engine._say(_R2)
            self._ask_trigger_question(
                _R13, "ingested_substance",
                schema={"ingested_substance": "string|null"},
                rules=(
                    "- ingested_substance：服用的藥物種類名稱與數量描述\n"
                    "  （如「安眠藥約20顆」「農藥不確定」「精神科藥物整排」）；"
                    "未提及 → null。"
                ),
                engine=engine,
            )

        elif scenario_id == 3:
            # 情境 3（半意識/迷糊）
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
                is_vital=True,
            )

        elif scenario_id == 4:
            # 情境 4（腹部起伏描述）
            engine._say(_r1(engine))
            engine._say(_R2)

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

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """吞食藥物使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
