"""
handlers/火警通用.py
━━━━━━━━━━━━━━━━━━━━
119 SOP — 火警大類通用流程（暫無子類 handler）

  run_generic_flow — 依序火/煙問診，每步後進行觸發情境偵測與回應
  collect_caller_info — 消防車話術收集報案人訊息
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


# ── 觸發情境回應文字（情境 2–14 共用）─────────────────────────────────────────

_R3 = "消防車已經派了唷。您不要緊張，再幫我確認一些事情。"

# (stage, field, question) — 火/煙問診順序
_SMOKE_QUESTIONS: List[Tuple[str, str, str]] = [
    ("火警_smoke_1", "fire_or_smoke", "請問看到火還是煙？"),
    ("火警_smoke_2", "smoke_color", "你看到黑煙還是白煙呢？"),
    ("火警_smoke_3", "smoke_trend", "煙持續冒還是變大？有消散嗎？"),
    ("火警_smoke_4", "flame_observation", "有看到火舌還是火花？"),
    ("火警_smoke_5", "burning_object",
     "你知道是燒什麼東西嗎？燒房子還是車子？還是雜草起火呢？"),
    ("火警_smoke_6", "fire_floor", "是幾樓在燒呢？"),
]


def _is_smoke_relevant(fire_or_smoke: Optional[str]) -> bool:
    """是否需問煙色/煙勢：明確僅火、無煙時可跳過。"""
    s = (fire_or_smoke or "").strip()
    if not s:
        return True
    has_smoke = any(k in s for k in ("煙", "烟"))
    has_fire_only = any(k in s for k in ("火",)) and not has_smoke
    # 「只有火」「只有火焰」等
    if has_fire_only and any(k in s for k in ("只有", "僅", "仅", "沒有煙", "没有烟", "無煙", "无烟")):
        return False
    if s in {"火", "有火", "看到火", "火焰", "火舌"}:
        return False
    return True


class HuoJingGenericHandler(SubCategoryHandler):
    """火警大類通用 Handler（不登記於子類 registry）。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """依序火/煙問診；每步後偵測觸發情境 2–14。"""
        engine._ensure_known_fields_from_history()

        for stage, field, question in _SMOKE_QUESTIONS:
            engine._ensure_known_fields_from_history()

            # 煙色/煙勢：若已明確無煙可跳過
            if field in ("smoke_color", "smoke_trend"):
                if not _is_smoke_relevant(engine.case.fire_or_smoke):
                    engine._debug_print(f"skip_{field}_no_smoke", engine.case.fire_or_smoke)
                    engine._set_stage(stage)
                    continue

            if engine._is_field_filled(field):
                engine._debug_print(f"skip_{field}", getattr(engine.case, field))
                engine._set_stage(stage)
                continue

            engine._set_stage(stage)
            answer = engine._ask_and_extract(question)
            self._check_and_respond_to_triggers(answer, engine)

    def _check_and_respond_to_triggers(
        self, caller_text: str, engine: "SopEngine119"
    ) -> None:
        """
        偵測本輪文本中的火警觸發情境 2–14。
        每個情境號只觸發一次；同一輪多個命中只說一遍 R3。
        """
        if not engine._llm or not (caller_text or "").strip():
            return

        try:
            already = list(engine.case.triggered_scenarios)
            new_ids = engine._llm.check_fire_trigger_scenarios(
                caller_text, already_triggered=already,
            )
            engine._debug_print("fire_triggers", {"new": new_ids, "already": already})
        except Exception as e:
            engine._debug_print("fire_triggers_error", e)
            return

        if not new_ids:
            return

        with engine._case_lock:
            for sid in new_ids:
                if sid not in engine.case.triggered_scenarios:
                    engine.case.triggered_scenarios.append(sid)
        engine._notify_case_update()

        # 情境 2–14 回應文字相同：本輪只說一次
        engine._say(_R3)

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """消防車話術收集報案人姓名與聯繫方式。"""
        from sop_119_engine import TransferToHumanError

        engine._set_stage("火警_caller_info")
        question = "消防車已派出，請問你的姓名與聯繫方式？"
        caller_info_text = engine._ask_and_extract(question)

        caller_name = engine.case.caller_name
        caller_contact = engine.case.caller_contact
        if engine._llm and caller_info_text.strip():
            try:
                ci = engine._llm.extract_caller_info(
                    question,
                    caller_info_text,
                    include_address=False,
                )
                caller_name = ci.get("caller_name") or caller_name
                caller_contact = ci.get("caller_contact") or caller_contact
                engine._debug_print("caller_info", ci)
            except Exception as e:
                engine._debug_print("caller_info_error", e)

        with engine._case_lock:
            engine.case.caller_name = caller_name
            engine.case.caller_contact = caller_contact
        engine._notify_case_update()

        if not caller_name and not caller_contact:
            engine._say("無法確認報案人資訊，立即為您轉接專人，請稍候。")
            raise TransferToHumanError("caller_info_missing", result="human_transfer")

        parts = []
        if caller_name:
            parts.append(f"姓名：{caller_name}")
        if caller_contact:
            parts.append(f"聯繫方式：{caller_contact}")
        engine._say("，".join(parts) + "，已為您記錄。")

        engine._say("請在現場耐心等待，確認入口通暢，並引導消防人員，謝謝。")
        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})
