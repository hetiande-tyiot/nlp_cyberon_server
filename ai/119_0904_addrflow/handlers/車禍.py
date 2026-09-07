"""
handlers/車禍.py
━━━━━━━━━━━━━━━
119 SOP — 車禍次類別 Handler

取代原通用救護生命征象+患者資訊流程，執行車禍專屬問題流程：
  run_subtype_flow — 依序 S0→S3→S4（四問），每步後進行觸發情境偵測與回應

注意：
- 無 S1/S2（生命征象）及 S6（性別年齡）步驟——車禍流程以現場安全與事故評估為主。
- S0 後先發送現場安全叮嚀，再進入 S3（現場安全確認）與 S4（類別專屬評估）。

報案人訊息沿用基類預設（姓名 + 聯繫方式，無住址）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字 ──────────────────────────────────────────────────────────

_R2  = "救護車已經派了。"
_R22 = "請先到安全的地方。"

# ── 現場安全叮嚀語（S0 後、S3 前發送）───────────────────────────────────────

_SAFETY_REMINDERS = (
    "請注意後方來車，不要站在車道中間。",
    "請開啟雙黃燈，並儘量移到安全的路邊等候救護車。",
)


class CheHuoHandler(SubCategoryHandler):
    """車禍次類別 Handler。"""

    SOP_SLOTS: tuple[str, ...] = (
        "incident_description",
        "current_condition",
        "medical_history",
        "patient_count",
        "injury_severity",
        "injury_cause",
        "injury_location",
    )

    # ── 車禍專屬完整問題流程 ──────────────────────────────────────────────────

    def run_subtype_flow(self, engine: "SopEngine119") -> None:
        """
        車禍次類別完整問題流程（替代通用生命征象+患者資訊問答）。

        S0 → 安全叮嚀 → S3（現場安全）→ S4（四問）
        每步詢問後進行觸發情境偵測。
        已抽取的 SOP 欄位自動跳過對應問題。
        """
        engine._ensure_known_fields_from_history()

        # ── S0：現場發生什麼事（skip if incident_description 已填）────────────
        engine._set_stage("車禍_S0")
        if not engine._is_field_filled("incident_description"):
            q0 = "請問發生什麼事呢？"
            answer0 = engine._ask_and_extract(q0)
            self._check_and_respond_to_triggers(answer0, engine)
        else:
            engine._debug_print("skip_S0", engine.case.incident_description)

        # ── 現場安全叮嚀（陳述句，不對報案人提問）──────────────────────────
        engine._set_stage("車禍_safety_reminder")
        for line in _SAFETY_REMINDERS:
            engine._say(line)
        engine._debug_print("車禍_safety_reminder", list(_SAFETY_REMINDERS))

        # ── S3：現場安全（skip if current_condition 已填）────────────────────
        engine._set_stage("車禍_S3")
        engine._ensure_known_fields_from_history()

        if not engine._is_field_filled("current_condition"):
            q3 = "現場是不是安全呢？"
            answer3 = engine._ask_and_extract(q3)
            self._extract_s3_scene_safety(answer3, q3, engine)
            self._check_and_respond_to_triggers(answer3, engine)
        else:
            engine._debug_print("skip_S3", engine.case.current_condition)

        # ── S4：類別專屬評估（四問）─────────────────────────────────────────
        engine._set_stage("車禍_S4")
        engine._ensure_known_fields_from_history()

        # S4-Q1：報案人是否在現場（skip if medical_history 已填）
        if not engine._is_field_filled("medical_history"):
            q4a = "請問您在現場還是路過現場呢？"
            answer4a = engine._ask_and_extract(q4a)
            self._extract_s4_caller_position(answer4a, q4a, engine)
            self._check_and_respond_to_triggers(answer4a, engine)
        else:
            engine._debug_print("skip_S4_Q1", engine.case.medical_history)

        # S4-Q2：受傷人數與受困（skip if patient_count+injury_severity 均已填）
        if (
            engine._is_field_filled("patient_count")
            and engine._is_field_filled("injury_severity")
        ):
            engine._debug_print(
                "skip_S4_Q2",
                f"count={engine.case.patient_count}, trapped={engine.case.injury_severity}",
            )
        else:
            q4b = "現場有多少人受傷？有人受困在車內或車輛底下嗎？"
            answer4b = engine._ask_and_extract(q4b)
            self._extract_s4_injured_trapped(answer4b, q4b, engine)
            self._check_and_respond_to_triggers(answer4b, engine)

        # S4-Q3：車輛類型（skip if injury_cause 已填）
        if not engine._is_field_filled("injury_cause"):
            q4c = "現場是何種車輛的交通事故？"
            answer4c = engine._ask_and_extract(q4c)
            self._extract_s4_vehicle_type(answer4c, q4c, engine)
            self._check_and_respond_to_triggers(answer4c, engine)
        else:
            engine._debug_print("skip_S4_Q3", engine.case.injury_cause)

        # S4-Q4：是否拋出車外（skip if injury_location 已填）
        if not engine._is_field_filled("injury_location"):
            q4d = "有傷患被拋出車輛外嗎？"
            answer4d = engine._ask_and_extract(q4d)
            self._extract_s4_ejected(answer4d, q4d, engine)
            self._check_and_respond_to_triggers(answer4d, engine)
        else:
            engine._debug_print("skip_S4_Q4", engine.case.injury_location)

    # ── 欄位抽取 ──────────────────────────────────────────────────────────────

    def _extract_s3_scene_safety(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S3 回答中抽取現場安全狀況，存入 current_condition。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"current_condition": "string|null"},
                rules=(
                    "- current_condition：現場是否安全的描述\n"
                    "  （如「安全」「不安全」「還有車經過」「已移到路邊」）；\n"
                    "  明確否認安全（不安全/沒有）→ 輸出「現場不安全」；未提及 → null。"
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

    def _extract_s4_caller_position(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q1 回答中抽取報案人位置，存入 medical_history。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"medical_history": "string|null"},
                rules=(
                    "- medical_history：報案人是否在現場的描述\n"
                    "  （如「在現場」「路過現場」「我是駕駛」「我是路人」）；\n"
                    "  未提及 → null。"
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

    def _extract_s4_injured_trapped(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q2 回答中同時抽取 patient_count + injury_severity（受困）。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={
                    "patient_count":   "string|null",
                    "injury_severity": "string|null",
                },
                rules=(
                    "受理員問題同時詢問受傷人數與是否受困，需分別判斷。\n"
                    "- patient_count：現場受傷人數\n"
                    "  （如「1位」「兩個人」「3人」「很多人」）；未提及 → null。\n"
                    "- injury_severity：是否有人受困在車內或車輛底下\n"
                    "  （如「有人受困車內」「夾在車底」「無人受困」）；\n"
                    "  明確否認（沒有/沒）→ 輸出「無人受困」；未提及 → null。"
                ),
                question=question,
            )
            with engine._case_lock:
                if not engine.case.patient_count:
                    count = result.get("patient_count")
                    if count:
                        engine.case.patient_count = str(count).strip()
                if not engine.case.injury_severity:
                    sev = result.get("injury_severity")
                    if sev:
                        engine.case.injury_severity = str(sev).strip()
            engine._notify_case_update()
            engine._debug_print("S4_injured_trapped", result)
        except Exception as e:
            engine._debug_print("S4_injured_trapped_error", e)

    def _extract_s4_vehicle_type(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q3 回答中抽取車輛類型，存入 injury_cause。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"injury_cause": "string|null"},
                rules=(
                    "- injury_cause：交通事故涉及的車輛類型\n"
                    "  （如「小客車」「機車」「大貨車」「公車」「多車追撞」）；\n"
                    "  未提及具體車種 → null。"
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

    def _extract_s4_ejected(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S4-Q4 回答中抽取是否拋出車外，存入 injury_location。"""
        if not engine._llm:
            return
        try:
            result = engine._llm.extract_slots(
                answer,
                schema={"injury_location": "string|null"},
                rules=(
                    "- injury_location：傷患是否被拋出車輛外的描述\n"
                    "  （如「有人被拋出」「沒有拋出」「駕駛被甩出車外」）；\n"
                    "  明確否認（沒有/沒）→ 輸出「無人被拋出」；未提及 → null。"
                ),
                question=question,
            )
            val = result.get("injury_location")
            if val:
                with engine._case_lock:
                    if not engine.case.injury_location:
                        engine.case.injury_location = str(val).strip()
                engine._notify_case_update()
                engine._debug_print("injury_location", engine.case.injury_location)
        except Exception as e:
            engine._debug_print("injury_location_error", e)

    # ── 觸發情境偵測與回應 ────────────────────────────────────────────────────

    def _check_triggers(
        self,
        caller_text: str,
        already_triggered: List[int],
        engine: "SopEngine119",
    ) -> List[int]:
        """
        偵測車禍的 2 個觸發情境。

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
                "- t1：多車相撞（很多輛車撞在一起、多車追撞、連環車禍、好幾台車撞在一起）\n"
                "- t2：有人被夾在車內（夾在車內、受困車內、卡在車裡、被車壓住、"
                "困在車底、出不來）\n"
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
            engine._debug_print("chehuo_trigger_check_error", e)
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
            engine._debug_print("chehuo_trigger_scenario", sid)
            self._send_trigger_responses(sid, engine)

    def _send_trigger_responses(self, scenario_id: int, engine: "SopEngine119") -> None:
        """依情境編號發送對應回應（全部為陳述句，無問句）。"""

        if scenario_id in (1, 2):
            # 情境 1（多車相撞）、2（夾在車內）
            engine._say(_R2)
            engine._say(_R22)

    # ── 報案人訊息 ────────────────────────────────────────────────────────────

    def run_pre_vital(self, engine: "SopEngine119") -> None:
        """車禍已改用 run_subtype_flow，此鉤子保留為空以避免意外調用。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """車禍使用基類預設：詢問姓名與聯繫方式（無住址）。"""
        self._do_collect_caller_info(engine, include_address=False)
