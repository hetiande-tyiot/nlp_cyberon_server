"""
handlers/火警通用.py
━━━━━━━━━━━━━━━━━━━━
119 SOP — 火警案類分析與垂片 A / B1 / B2 / C

  run_generic_flow — 案類分析（一句分到垂片）→ 對應垂片詢問 → 統一安全提示
  collect_caller_info — 最後確認回撥電話與稱呼
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from fire_tab_map_119 import (
    INCIDENT_Q,
    INCIDENT_REASK_Q,
    INCIDENT_STAGE,
    MODE_CONDITIONAL,
    MODE_PASSIVE,
    OCCUPANTS_STILL_INSIDE,
    SAFETY_MESSAGE,
    TAB_C,
    TAB_QUESTIONS,
    TRAPPED_TRANSFER_MESSAGE,
    TRAPPED_YES,
    UNRESOLVED_TAB_TAG,
    infer_tab,
    resolve_fire_tab,
)
from important_tags_119 import merge_important_tags
from .base import SubCategoryHandler

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119


class HuoJingGenericHandler(SubCategoryHandler):
    """火警大類 Handler：案類分析分到垂片後，走對應垂片。"""

    def run_generic_flow(self, engine: "SopEngine119") -> None:
        """完成案類分析與垂片詢問，再播放統一安全提示。"""
        engine._ensure_known_fields_from_history()
        # 報地址時就講出有人受困 → 不必問案類，直接轉人工
        self._transfer_if_people_trapped(engine)
        self._resolve_tab(engine)
        self._backfill_earlier_answers_for_tab(engine)

        engine._sub_reclassify_enabled = True
        try:
            from sop_119_engine import SubCategorySwitched
            engine._refresh_fire_subtype_from_bert()
            engine._maybe_reclassify_sub()
            while True:
                try:
                    tab = engine.case.fire_tab
                    self._ask_tab_questions(engine, tab)
                    break
                except SubCategorySwitched as sw:
                    engine._debug_print(
                        "fire_tab_switched_restart",
                        {"old": sw.old, "new": sw.new, "tab": engine.case.fire_tab},
                    )
                    continue
        finally:
            engine._sub_reclassify_enabled = False

        engine._set_stage("火警_safety")
        engine._say(SAFETY_MESSAGE)

    def _transfer_if_people_trapped(self, engine: "SopEngine119") -> None:
        """
        有人出不來 → 說一句話後立刻轉接專人。以下任一情況都算：
        - 有無受困記成「有人受困」（建築物、輕微火警）
        - 乘客下車狀況記成「仍有人在車上」（交通工具火警）
        火警流程中每次報案人回答之後、每一題問之前都會檢查，不等問到那一題。
        已經轉接過（真人接手、系統只在旁聽）就不再處理。
        """
        case = engine.case
        people_inside = (
            case.trapped_status == TRAPPED_YES
            or case.occupants_status == OCCUPANTS_STILL_INSIDE
        )
        if not people_inside or engine._bridged:
            return
        from sop_119_engine import TransferToHumanError

        engine._debug_print(
            "fire_people_trapped_transfer",
            {"有無受困": case.trapped_status, "乘客下車狀況": case.occupants_status},
        )
        engine._say(TRAPPED_TRANSFER_MESSAGE)
        raise TransferToHumanError("fire_people_trapped", result="human_transfer")

    def _backfill_earlier_answers_for_tab(self, engine: "SopEngine119") -> None:
        """
        垂片剛決定時，把報案人前面說過的話，用這張垂片的欄位再抽一次。
        為什麼需要：還不知道垂片時（報地址、案類分析），每一輪只抽四張垂片共用的欄位，
        所以像「我家公寓三樓燒起來」裡的「三樓」當時沒被記下；不補抽的話，
        進了垂片 A 會再問一次「是幾樓在冒煙呢？」。
        只補還空白的欄位，已經有答案的不蓋掉；只收火警欄位，不動地址等其他欄位。
        每一句都連同它當時回答的受理員問題一起送，模型才分得出「4樓」是在回答地址、
        不是起火樓層。抽取失敗就跳過，流程照常繼續。
        """
        from fire_tab_map_119 import fire_fields_to_extract
        from sop_utils_119 import format_qa_for_llm

        qa_pairs = engine._iter_caller_qa_pairs()
        if engine._llm is None or not qa_pairs:
            return
        tab = engine.case.fire_tab
        try:
            extracted = engine._llm.extract_general_fields(
                "\n".join(format_qa_for_llm(q, a) for q, a in qa_pairs),
                question=None,
                main_category="火警",
                call_type=engine.case.call_type,
                fire_tab=tab,
            )
        except Exception as exc:
            engine._debug_print("fire_backfill_error", exc)
            return
        fire_fields = set(fire_fields_to_extract(tab))
        # 先查哪些欄位還空著（會短暫上鎖），再上鎖寫入；鎖不能重複上，所以分兩步
        blanks = {
            key: value
            for key, value in (extracted or {}).items()
            if key in fire_fields and value is not None
            and not engine._is_field_filled(key)
        }
        engine._debug_print("fire_backfill", {"tab": tab, "filled": blanks})
        if not blanks:
            return
        with engine._case_lock:
            engine._apply_extracted_fields(blanks)
        engine._notify_case_update()

    def _flag_fire_issue(self, engine: "SopEngine119", tag: str) -> None:
        """記錄無法判斷／資訊缺失，繼續流程、不轉人工。"""
        with engine._case_lock:
            engine.case.ImportantCase = 1
            engine.case.ImportantTag = merge_important_tags(
                engine.case.ImportantTag, [tag],
            )
        engine._debug_print("fire_issue_tag", tag)
        engine._notify_case_update()

    def _classify_tab(
        self,
        engine: "SopEngine119",
        question: str,
        answer: str,
    ) -> Optional[str]:
        tab = None
        if engine._llm is not None and hasattr(engine._llm, "classify_fire_tab"):
            try:
                tab = engine._llm.classify_fire_tab(answer, question=question)
            except Exception as exc:
                engine._debug_print("fire_tab_llm_error", exc)
        return tab or infer_tab(answer)

    def _classify_earlier_answers(self, engine: "SopEngine119") -> Optional[str]:
        """
        次案類還不知道時，用報案人前面說過的話判斷是哪張垂片，跟案類分析用同一個判斷。
        例如開頭說「我的機車燒起來」就判斷得出 B1，不必再問。
        只送報案人說的話，不含受理員問題（判斷不出來時改用關鍵詞，問題文字會被誤比對）。
        判斷不出來回傳 None，由案類分析去問。
        """
        caller_texts = engine.case.caller_texts()
        if not caller_texts:
            return None
        return self._classify_tab(engine, None, "\n".join(caller_texts))

    def _tab_already_known(self, engine: "SopEngine119") -> Optional[str]:
        """
        垂片已經決定，或已經知道次案類（次案類決定垂片），就直接用，不用再問。
        還不知道就回傳 None。
        """
        tab = resolve_fire_tab(engine.case)
        return tab if tab in TAB_QUESTIONS else None

    def _lock_tab(self, engine: "SopEngine119", tab: str) -> None:
        with engine._case_lock:
            engine.case.fire_tab = tab
        engine._notify_case_update()

    def _resolve_tab(self, engine: "SopEngine119") -> str:
        """
        案類分析：決定這通電話要走哪張垂片。
        - 已經知道次案類 → 用次案類所屬的垂片，不問
        - 次案類還不知道 → 先用報案人前面說過的話判斷是哪張垂片，判斷得出來就不問
        - 還是判斷不出來 → 問「請問發生什麼事？是什麼東西在燒？」
        - 聽不出來 → 再問「不好意思，請您再說一次是什麼在燒？」
        - 問兩次仍分不出是哪種火災 → 先當成輕微火警（垂片 C）處理，並在 ImportantTag
          記下原因，讓下游知道這通電話的火災類型是系統預設的，不是報案人說的
        """
        engine._ensure_known_fields_from_history()
        known = self._tab_already_known(engine) or self._classify_earlier_answers(engine)
        if known:
            self._lock_tab(engine, known)
            return known

        for question in (INCIDENT_Q, INCIDENT_REASK_Q):
            engine._set_stage(INCIDENT_STAGE)
            answer = engine._ask_and_extract(question)
            self._check_and_respond_to_triggers(answer, engine)
            self._transfer_if_people_trapped(engine)
            tab = self._tab_already_known(engine) or self._classify_tab(
                engine, question, answer,
            )
            if tab:
                self._lock_tab(engine, tab)
                return tab

        engine._debug_print("fire_tab_unresolved", "fallback_C")
        self._flag_fire_issue(engine, UNRESOLVED_TAB_TAG)
        self._lock_tab(engine, TAB_C)
        return TAB_C

    def _ask_tab_questions(self, engine: "SopEngine119", tab: str) -> None:
        """
        照 xlsx 的順序逐題處理：
        - 被動題：不問（報案人講到時，每一輪的欄位抽取會記下來）
        - 條件題：前置條件確定成立才問；不確定就當作不成立，不問
        - 主動題、條件成立的條件題：答案還不知道才問
        條件在輪到那一題時才判斷，因為要用到前面剛問到的答案。
        """
        for item in TAB_QUESTIONS.get(tab, ()):
            engine._ensure_known_fields_from_history()
            self._transfer_if_people_trapped(engine)
            if item.mode == MODE_PASSIVE:
                continue
            if item.mode == MODE_CONDITIONAL and not item.condition(engine.case):
                engine._debug_print(
                    f"skip_{item.stage}", {"前置條件不成立": item.condition_text},
                )
                continue
            self._ask_missing(engine, item.stage, (item.field,), item.question)

    def _ask_missing(
        self,
        engine: "SopEngine119",
        stage: str,
        fields: Iterable[str],
        question: str,
    ) -> Optional[str]:
        """只在任一关联字段未取得时提问，并统一经过 LLM 抽取。"""
        engine._ensure_known_fields_from_history()
        field_tuple = tuple(fields)
        engine._set_stage(stage)
        if all(engine._is_field_filled(field) for field in field_tuple):
            engine._debug_print(
                f"skip_{stage}",
                {field: getattr(engine.case, field) for field in field_tuple},
            )
            return None
        answer = engine._ask_and_extract(question)
        self._check_and_respond_to_triggers(answer, engine)
        self._transfer_if_people_trapped(engine)
        return answer

    def _check_and_respond_to_triggers(
        self, caller_text: str, engine: "SopEngine119"
    ) -> None:
        """
        偵測本輪文本中的火警觸發情境 2–14。
        每個情境號只記錄一次；記錄後直接進入下一個問題。
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

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """在火災問診末尾確認回撥電話與稱呼。"""
        from sop_utils_119 import parse_yes_no_for_question

        engine._set_stage("火警_caller_info")
        engine._ensure_known_fields_from_history()
        original_contact = engine.case.caller_contact
        if original_contact:
            question = (
                f"最後和您確認一下，連絡電話是 {original_contact} 嗎？"
                "請問是先生還是小姐呢？"
            )
        else:
            question = "最後請提供回撥電話，並告訴我是先生還是小姐。"
        answer = engine._ask_and_extract(question)
        self._extract_caller_info(answer, question, engine)
        self._transfer_if_people_trapped(engine)

        if original_contact:
            confirmed = parse_yes_no_for_question(question, answer)
            if confirmed is False and engine.case.caller_contact == original_contact:
                correction_q = "請重新提供正確的回撥電話。"
                correction = engine._ask_and_extract(correction_q)
                self._extract_caller_info(correction, correction_q, engine)
                self._transfer_if_people_trapped(engine)

        for _attempt in range(2):
            if engine._is_field_filled("caller_contact"):
                break
            phone_q = "請提供可以回撥的聯絡電話。"
            phone_answer = engine._ask_and_extract(phone_q)
            self._extract_caller_info(phone_answer, phone_q, engine)
            self._transfer_if_people_trapped(engine)
        for _attempt in range(2):
            if engine._is_field_filled("caller_salutation"):
                break
            salutation_q = "請問是先生還是小姐？"
            salutation_answer = engine._ask_and_extract(salutation_q)
            self._extract_caller_info(salutation_answer, salutation_q, engine)
            self._transfer_if_people_trapped(engine)

        if not engine._is_field_filled("caller_contact"):
            self._flag_fire_issue(engine, "回撥電話無法確認")
        if not engine._is_field_filled("caller_salutation"):
            self._flag_fire_issue(engine, "報案人稱呼無法確認")

        recap_parts = []
        if engine.case.caller_contact:
            recap_parts.append(f"連絡電話：{engine.case.caller_contact}")
        if engine.case.caller_salutation:
            recap_parts.append(f"稱呼：{engine.case.caller_salutation}")
        if recap_parts:
            engine._say("，".join(recap_parts) + "，已為您記錄。")

        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})

    @staticmethod
    def _extract_caller_info(
        caller_text: str, question: str, engine: "SopEngine119"
    ) -> None:
        if not engine._llm or not caller_text.strip():
            return
        try:
            ci = engine._llm.extract_caller_info(
                question, caller_text, include_address=False
            )
            engine._debug_print("caller_info", ci)
        except Exception as exc:
            engine._debug_print("caller_info_error", exc)
            return
        with engine._case_lock:
            if ci.get("caller_name"):
                engine.case.caller_name = ci["caller_name"]
            if ci.get("caller_contact"):
                engine.case.caller_contact = ci["caller_contact"]
            if ci.get("caller_salutation") in ("先生", "小姐"):
                engine.case.caller_salutation = ci["caller_salutation"]
        engine._notify_case_update()
