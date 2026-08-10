"""
handlers/base.py
━━━━━━━━━━━━━━━━
119 SOP — 次類別 Handler 基類

SubCategoryHandler 定義三個鉤子介面：
  run_pre_vital(engine)        — 生命征象前的次類別額外問題（預設：無）
  run_post_vital(engine)       — 生命征象後、患者資訊前的次類別額外問題（預設：無）
  collect_caller_info(engine)  — 報案人訊息收集（預設：通用版，問姓名+聯繫方式）

共用方法：
  _do_collect_caller_info(engine, include_address) — 供子類呼叫的帶住址版實作
  _run_s1_consciousness_breathing(...)            — S1 意識/呼吸（已填則跳過）
  _run_s2_response_or_abdomen(...)                — S2 反應/起伏（已清醒則只問起伏）

所有次類別 Handler 繼承此類，選擇性覆寫所需鉤子。
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, List, Sequence

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class SubCategoryHandler:
    """通用（無次類別）Handler：三個鉤子皆為預設版。"""

    def run_pre_vital(self, engine: "SopEngine119") -> None:
        """生命征象前的次類別額外問題。預設為空，子類視需要覆寫。"""
        pass

    def run_post_vital(self, engine: "SopEngine119") -> None:
        """生命征象後、患者資訊前的次類別額外問題。預設為空，子類視需要覆寫。"""
        pass

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """標準版報案人訊息收集（姓名 + 聯繫方式）。"""
        self._do_collect_caller_info(engine, include_address=False)

    # ── S1 / S2 共用生命征象流程 ──────────────────────────────────────────────

    def _run_s1_consciousness_breathing(
        self,
        engine: "SopEngine119",
        *,
        q_both: str,
        q_consciousness: str = "請問患者有沒有清醒？",
        q_breathing: str = "請問患者是不是有正常呼吸？",
        on_answer=None,
    ) -> None:
        """
        S1：意識與呼吸。
        - 兩者皆已填 → 跳過
        - 僅意識已填（如首輪已說「意識清醒」）→ 只問呼吸
        - 僅呼吸已填 → 只問意識
        - 皆未填 → 合問；若只答其中一項（如「清醒」），再追問缺的那項
        - 任一明確為 False → 立即 OHCA，無需等另一項
        """
        # 最多兩輪：合問/單問 → 若仍缺一項且非明確否定，再補問缺項
        for round_i in range(2):
            engine._ensure_known_fields_from_history()
            has_c = engine._is_field_filled("consciousness")
            has_b = engine._is_field_filled("breathing")

            with engine._case_lock:
                c_val = engine.case.consciousness
                b_val = engine.case.breathing

            # 明確否定任一項 → 不必再問，直接進 OHCA 判定
            if c_val is False or b_val is False:
                engine._debug_print(
                    "S1_explicit_negative",
                    f"consciousness={c_val}, breathing={b_val}",
                )
                break

            if has_c and has_b:
                if round_i == 0:
                    engine._debug_print(
                        "skip_S1",
                        f"consciousness={c_val}, breathing={b_val}",
                    )
                break

            if has_c and not has_b:
                q1 = q_breathing
                engine._debug_print(
                    "S1_partial", "consciousness known → ask breathing only"
                )
            elif has_b and not has_c:
                q1 = q_consciousness
                engine._debug_print(
                    "S1_partial", "breathing known → ask consciousness only"
                )
            else:
                q1 = q_both

            answer1 = engine._ask_and_extract(q1)
            self._extract_s1_vitals(answer1, q1, engine)
            if on_answer is not None:
                on_answer(answer1)

        self._check_ohca_after_s1(engine)

    def _run_s2_response_or_abdomen(
        self,
        engine: "SopEngine119",
        *,
        reaction_options: Sequence[str],
        abdomen_question: str,
        on_answer=None,
    ) -> None:
        """
        S2：反應或腹部起伏。
        - abdomen_rise 已填 → 跳過
        - 意識已確認為 True → 不再問叫/捏反應，只問腹部起伏
        - 否則從反應選項 + 起伏中隨機一題
        """
        engine._ensure_known_fields_from_history()

        if engine._is_field_filled("abdomen_rise"):
            engine._debug_print("skip_S2", engine.case.abdomen_rise)
            self._check_ohca_after_s2(engine)
            return

        with engine._case_lock:
            conscious = engine.case.consciousness is True

        if conscious:
            q2 = abdomen_question
            engine._debug_print("S2_skip_reaction", "consciousness=True → abdomen only")
        else:
            options: List[str] = list(reaction_options) + [abdomen_question]
            q2 = random.choice(options)

        answer2 = engine._ask_and_extract(q2)
        self._extract_s2_vitals(answer2, q2, engine)
        if on_answer is not None:
            on_answer(answer2)
        self._check_ohca_after_s2(engine)

    def _extract_s1_vitals(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """從 S1 回答抽取 consciousness / breathing（欄位專屬，避免串欄）。"""
        from sop_utils_119 import parse_vital_slot

        llm_result = {}
        if engine._llm:
            try:
                from llm_extractor_119 import _coerce_bool

                llm_result = engine._llm.extract_slots(
                    answer,
                    schema={
                        "consciousness": "true|false|null",
                        "breathing": "true|false|null",
                    },
                    rules=(
                        "受理員可能合問或單問意識與呼吸，需分別判斷。\n"
                        "- consciousness：清醒/有意識/有反應 → true；"
                        "沒有清醒/不清醒/昏迷/叫不醒/沒反應 → false；未提及 → null。\n"
                        "- breathing：有呼吸/正常呼吸 → true；"
                        "沒有正常呼吸/沒有呼吸/沒呼吸/停止呼吸 → false；未提及 → null。\n"
                        "- 『沒有清醒，沒有正常呼吸』→ 兩者皆為 false。\n"
                        "- 只說『清醒』或『意識清醒』而未提呼吸 → "
                        "consciousness=true、breathing 必須為 null（不可臆測有呼吸）。\n"
                        "- 只說『有呼吸/正常呼吸』而未提意識 → "
                        "breathing=true、consciousness 必須為 null。"
                    ),
                    question=question,
                    strict_tail=(
                        "\n\n【全局強約束（是/否確認）】\n"
                        "- 必須輸出 schema 中的所有 key\n"
                        "- 輸出必須為單行 JSON\n"
                    ),
                )
                engine._debug_print("S1_vitals", llm_result)
            except Exception as e:
                engine._debug_print("S1_vitals_error", e)
                llm_result = {}

        # S1 專項問答為權威來源：可覆蓋本輪 _ask_and_extract 規則誤填的值
        # 規則能判定時以規則為準，避免只答「清醒」被 LLM 臆測成有呼吸
        with engine._case_lock:
            for slot in ("consciousness", "breathing"):
                rule_val = parse_vital_slot(slot, answer, question)
                llm_val = None
                if llm_result:
                    from llm_extractor_119 import _coerce_bool
                    llm_val = _coerce_bool(llm_result.get(slot))
                if rule_val is not None:
                    val = rule_val
                elif llm_val is not None:
                    # 合問時僅答意識：禁止把 breathing 填成 true
                    if (
                        slot == "breathing"
                        and llm_val is True
                        and "呼吸" not in (answer or "")
                        and parse_vital_slot("consciousness", answer, question) is True
                    ):
                        val = None
                    elif (
                        slot == "consciousness"
                        and llm_val is True
                        and not any(
                            k in (answer or "")
                            for k in ("清醒", "意識", "意识", "反應", "反应")
                        )
                        and parse_vital_slot("breathing", answer, question) is True
                    ):
                        val = None
                    else:
                        val = llm_val
                else:
                    val = None
                if val is not None:
                    setattr(engine.case, slot, val)
        engine._notify_case_update()

    def _extract_s2_vitals(
        self, answer: str, question: str, engine: "SopEngine119"
    ) -> None:
        """
        從 S2 回答抽取。
        - 腹部起伏題 → abdomen_rise
        - 叫/捏反應題 → consciousness + abdomen_rise（有反應即通過 S2 檢查點）
        """
        from sop_utils_119 import is_reaction_vital_question, parse_vital_slot

        is_reaction = is_reaction_vital_question(question)
        llm_result = {}

        if engine._llm:
            try:
                from llm_extractor_119 import _coerce_bool

                if is_reaction:
                    llm_result = engine._llm.extract_slots(
                        answer,
                        schema={
                            "consciousness": "true|false|null",
                            "abdomen_rise": "true|false|null",
                        },
                        rules=(
                            "受理員詢問患者對刺激的反應（眼開/手動/發聲）。\n"
                            "- consciousness：有眼開/手動/出聲/有反應 → true；"
                            "無任何反應 → false；未提及 → null。\n"
                            "- abdomen_rise：有反應時填 true（視為通過生命征象檢查點）；"
                            "無反應填 false；未提及 → null。"
                        ),
                        question=question,
                        strict_tail=(
                            "\n\n【全局強約束（是/否確認）】\n"
                            "- 必須輸出 schema 中的所有 key\n"
                            "- 輸出必須為單行 JSON\n"
                        ),
                    )
                else:
                    llm_result = engine._llm.extract_slots(
                        answer,
                        schema={"abdomen_rise": "true|false|null"},
                        rules=(
                            "- abdomen_rise：肚子/腹部有無起伏。\n"
                            "  有起伏/有動 → true；沒有起伏/沒動 → false；未提及 → null。"
                        ),
                        question=question,
                        strict_tail=(
                            "\n\n【全局強約束（是/否確認）】\n"
                            "- 必須輸出 schema 中的所有 key\n"
                            "- 輸出必須為單行 JSON\n"
                        ),
                    )
                engine._debug_print("S2_vitals", llm_result)
            except Exception as e:
                engine._debug_print("S2_vitals_error", e)
                llm_result = {}

        with engine._case_lock:
            if is_reaction:
                for slot in ("consciousness", "abdomen_rise"):
                    if getattr(engine.case, slot) is not None:
                        continue
                    val = None
                    if llm_result:
                        from llm_extractor_119 import _coerce_bool
                        val = _coerce_bool(llm_result.get(slot))
                    if val is None:
                        val = parse_vital_slot(slot, answer, question)
                    if val is not None:
                        setattr(engine.case, slot, val)
                # 反應肯定但 abdomen_rise 仍空：以意識反應作為 S2 通過標記
                if engine.case.abdomen_rise is None and engine.case.consciousness is True:
                    engine.case.abdomen_rise = True
                if engine.case.abdomen_rise is None and engine.case.consciousness is False:
                    engine.case.abdomen_rise = False
            else:
                if engine.case.abdomen_rise is None:
                    val = None
                    if llm_result:
                        from llm_extractor_119 import _coerce_bool
                        val = _coerce_bool(llm_result.get("abdomen_rise"))
                    if val is None:
                        val = parse_vital_slot("abdomen_rise", answer, question)
                    if val is not None:
                        engine.case.abdomen_rise = val
        engine._notify_case_update()

    def _check_ohca_after_s1(self, engine: "SopEngine119") -> None:
        """
        S1 後 OHCA 判定（呼叫前應已盡量補問缺項）：
        - 兩者皆 True → 通過
        - 任一明確 False，或補問後仍缺項 → OHCA
        """
        with engine._case_lock:
            c = engine.case.consciousness
            b = engine.case.breathing
        if c is True and b is True:
            return
        with engine._case_lock:
            engine.case.is_ohca = True
        engine._notify_case_update()
        engine._say(
            "（判斷為OHCA）救護車已派出，請不要掛斷電話，我立即為您轉接專人。"
        )
        from sop_119_engine import TransferToHumanError
        raise TransferToHumanError("OHCA detected at S1", result="ohca_transfer")

    def _check_ohca_after_s2(self, engine: "SopEngine119") -> None:
        """S2 後：abdomen_rise 非 True → OHCA。"""
        with engine._case_lock:
            a = engine.case.abdomen_rise
        if a is not True:
            with engine._case_lock:
                engine.case.is_ohca = True
            engine._notify_case_update()
            engine._say(
                "（判斷為OHCA）救護車已派出，請不要掛斷電話，我立即為您轉接專人。"
            )
            from sop_119_engine import TransferToHumanError
            raise TransferToHumanError("OHCA detected at S2", result="ohca_transfer")

    # ── 共用實作 ──────────────────────────────────────────────────────────────

    def _do_collect_caller_info(
        self,
        engine: "SopEngine119",
        *,
        include_address: bool,
    ) -> None:
        """
        報案人訊息收集共用邏輯。

        include_address=False：問「姓名與聯繫方式」
        include_address=True ：問「姓名、聯繫方式與住址」，並多抽 caller_address

        此方法同時負責：
        - stage 設置
        - 詢問報警人
        - LLM 抽取
        - 無資訊時轉人工
        - 複讀確認
        - 結束語與流程終止事件
        """
        from sop_119_engine import TransferToHumanError

        engine._set_stage("救護_caller_info")

        if include_address:
            question = "救護車已派出，請問你的姓名、聯繫方式與住址？"
        else:
            question = "救護車已派出，請問你的姓名與聯繫方式？"

        # 每則報警人回答都走通用 LLM 全欄位抽取
        caller_info_text = engine._ask_and_extract(question)

        caller_name    = engine.case.caller_name
        caller_contact = engine.case.caller_contact
        caller_address = engine.case.caller_address if include_address else None
        # 專項再抽一輪報案人資訊（補強姓名/電話/住址）
        if engine._llm and caller_info_text.strip():
            try:
                ci = engine._llm.extract_caller_info(
                    question,
                    caller_info_text,
                    include_address=include_address,
                )
                caller_name    = ci.get("caller_name") or caller_name
                caller_contact = ci.get("caller_contact") or caller_contact
                if include_address:
                    caller_address = ci.get("caller_address") or caller_address
                engine._debug_print("caller_info", ci)
            except Exception as e:
                engine._debug_print("caller_info_error", e)

        with engine._case_lock:
            engine.case.caller_name    = caller_name
            engine.case.caller_contact = caller_contact
            if include_address:
                engine.case.caller_address = caller_address
        engine._notify_case_update()

        if not caller_name and not caller_contact:
            engine._say("無法確認報案人資訊，立即為您轉接專人，請稍候。")
            raise TransferToHumanError("caller_info_missing", result="human_transfer")

        parts = []
        if caller_name:
            parts.append(f"姓名：{caller_name}")
        if caller_contact:
            parts.append(f"聯繫方式：{caller_contact}")
        if caller_address:
            parts.append(f"住址：{caller_address}")
        engine._say("，".join(parts) + "，已為您記錄。")

        engine._say("請在現場耐心等待，確認入口通暢，並引導救護人員，謝謝。")
        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})
