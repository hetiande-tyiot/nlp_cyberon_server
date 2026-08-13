"""
handlers/上吊.py
━━━━━━━━━━━━━━━━
119 SOP — 上吊次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行上吊專屬問題流程：
  run_subtype_flow — 依序 S0→S3→S1→S6，每步後進行觸發情境偵測與回應

注意：
- 無 S2（腹部起伏）步驟——OHCA 僅由 S1 判斷。
- S3（現場安全：繩子是否解開）在 S1（生命征象）之前詢問。

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
_R20 = "可以看看能不能把他解下來呢？"


class ShangDiaoHandler(SubCategoryHandler):
    """上吊次類別 Handler。"""

    # ── 上吊專屬完整問題流程 ──────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        上吊次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → S3（現場安全）→ S1 → S6
        S3（繩子是否解開）先於 S1（意識呼吸）詢問。
        每步詢問後進行觸發情境偵測；OHCA 判定在觸發回應送出後執行。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("上吊_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── S3：現場安全（skip if current_condition 已填）────────────────────
        engine._set_stage("上吊_S3")
        engine._ensure_known_fields_from_history()

        if not engine._is_field_filled("current_condition"):
            q3 = "請問繩子已經解開了嗎？"
            answer3 = engine._ask_and_extract(q3)
            self._extract_s3_rope_released(answer3, q3, engine)
            self._check_and_respond_to_triggers(answer3, engine)
        else:
            engine._debug_print("skip_S3", engine.case.current_condition)

        # ── S1：意識與呼吸（已填則跳過；僅意識已知則只問呼吸）──────────────
        engine._set_stage("上吊_S1")
        self._run_s1_consciousness_breathing(
            engine,
            q_consciousness="請問他是不是清醒？",
            q_breathing="有正常呼吸嗎？",
            on_answer=lambda a: self._check_and_respond_to_triggers(a, engine),
        )

        # ── S6：性別與年齡（語境感知，見 base._run_s6_gender_age）────────
        self._run_s6_gender_age(engine, "上吊_S6")

    # ── 欄位抽取 ──────────────────────────────────────────────────────────────

    def _extract_s3_rope_released(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S3 回答中抽取繩子解開狀態，存入 current_condition。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"current_condition": "string|null"},
                rules=(
                    "- current_condition：繩子是否已解開的描述\n"
                    "  （如「已解開」「還吊著」「已經解下來」「還沒解開」「不清楚」）；\n"
                    "  明確否認已解開（沒有/還沒）→ 輸出「繩子尚未解開」；未提及 → null。"
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

    # ── 其他抽取（S1/OHCA 共用邏輯見 base.SubCategoryHandler）──────────────

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測上吊的 2 個觸發情境。

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
                "- t1：患者還吊在繩子上面（還吊著、還掛在繩子上、還沒解下來、"
                "吊在天花板、脖子還套著繩子）\n"
                "- t2：已解下來但沒有呼吸（已經解下來、解開了但沒呼吸、"
                "放下來了但沒呼吸、解下來後沒有呼吸）\n"
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
            engine._debug_print("shangdiao_trigger_check_error", e)
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
            engine._debug_print("shangdiao_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應（全部為陳述句，無問句）。"""

        if scenario_id == 1:
            # 還吊在繩子上面
            engine._say(_R2)
            engine._say(_R20)

        elif scenario_id == 2:
            # 已解下來但沒有呼吸
            engine._say(_R2)
            engine._say(_R3)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """上吊使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
