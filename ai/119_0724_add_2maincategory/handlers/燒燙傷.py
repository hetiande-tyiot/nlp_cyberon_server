"""
handlers/燒燙傷.py
━━━━━━━━━━━━━━━━━━
119 SOP — 燒燙傷次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行燒燙傷專屬問題流程：
  run_subtype_flow — 依序 S0→S1→S4，每步後進行觸發情境偵測與回應

無 S2（腹部起伏）及 S6（性別年齡）步驟——燒燙傷患者通常清醒，
OHCA 僅由 S1 結果判斷。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
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
_R19 = "先到水龍頭下沖水。"


class ShaoTangShangHandler(SubCategoryHandler):
    """燒燙傷次類別 Handler。"""

    # ── 燒燙傷專屬完整問題流程 ────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        燒燙傷次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S1 → (觸發情境偵測 → OHCA 判斷) → S4
        每步詢問後進行觸發情境偵測，觸發回應在 OHCA 判定前送出。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("燒燙傷_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("燒燙傷_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_both="請問患者有沒有清醒？是否有正常呼吸？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S4：類別專屬評估（skip if injury_location+injury_severity 均已填）─
        engine._set_stage("燒燙傷_S4")
        engine._ensure_known_fields_from_history()

        if (
            engine._is_field_filled("injury_location")
            and engine._is_field_filled("injury_severity")
        ):
            engine._debug_print(
                "skip_S4",
                f"location={engine.case.injury_location}, "
                f"severity={engine.case.injury_severity}",
            )
        else:
            q4 = "有無起水泡，燒燙傷部位？"
            answer4 = engine._ask_and_extract(q4)
            self._extract_s4_burn_details(answer4, q4, engine)
            self._check_and_respond_to_triggers(answer4, engine)

    # ── 欄位抽取 ──────────────────────────────────────────────────────────────

    # ── 其他抽取（S1/OHCA 共用邏輯見 base.SubCategoryHandler）──────────────

    def _extract_s4_burn_details(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4 回答中同時抽取 injury_location + injury_severity。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={
                    "injury_location": "string|null",
                    "injury_severity": "string|null",
                },
                rules=(
                    "受理員問題同時詢問水泡與燒燙傷部位，需分別判斷。\n"
                    "- injury_location：燒燙傷部位描述\n"
                    "  （如「手」「肚子」「手臂」「臉部」「多處」）；\n"
                    "  未提及具體部位 → null。\n"
                    "- injury_severity：水泡或傷勢描述\n"
                    "  （如「有起水泡」「大量水泡」「輕微紅腫」「無水泡」）；\n"
                    "  明確否認水泡（沒有/沒）→ 輸出「無水泡」；未提及 → null。"
                ),
                question=question,
            )
            with engine._case_lock:
                if not engine.case.injury_location:
                    loc = result.get("injury_location")
                    if loc:
                        engine.case.injury_location = str(loc).strip()
                if not engine.case.injury_severity:
                    sev = result.get("injury_severity")
                    if sev:
                        engine.case.injury_severity = str(sev).strip()
            engine._notify_case_update()
            engine._debug_print("S4_burn_details", result)
        except Exception as e:
            engine._debug_print("S4_burn_details_error", e)

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測燒燙傷的 3 個觸發情境。

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
                "- t1：熱水燙傷且患者清醒（燙傷、熱水、燒傷、手燙到、肚子燙到、"
                "有起水泡、清醒、可以說話）\n"
                "- t2：工作時打翻熱湯（工作時、打翻熱湯、熱湯潑到、廚房、燙到）\n"
                "- t3：沒有呼吸（沒呼吸、沒有呼吸、停止呼吸、呼吸停止、沒有在呼吸）\n"
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
            engine._debug_print("shaotang_trigger_check_error", e)
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
            engine._debug_print("shaotang_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應（全部為陳述句，無問句）。"""

        if scenario_id in (1, 2):
            # 情境 1（熱水燙傷清醒）、2（工作時打翻熱湯）
            engine._say(_R2)
            engine._say(_R19)

        elif scenario_id == 3:
            # 情境 3（沒有呼吸）
            engine._say(_R2)
            engine._say(_R3)
            engine._say(_R4)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """燒燙傷使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
