"""
handlers/base.py
━━━━━━━━━━━━━━━━
119 SOP — 次類別 Handler 基類

SubCategoryHandler 定義的鉤子介面：
  collect_caller_info(engine)  — 報案人訊息收集（預設：通用版，問姓名+聯繫方式）

共用方法：
  _do_collect_caller_info(engine, include_address) — 供子類呼叫的帶住址版實作
  _ask_ems_questions(engine, questions)           — 照救護題目表逐題問

所有次類別 Handler 繼承此類，選擇性覆寫所需鉤子。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from sop_119_engine import SopEngine119

# 收完報案人資訊後講的結尾句（11/02 使用者給的句子），講的車跟各主案類的派車句對應：
# 火警講消防車；救護講救護車；緊急救援、災害講救護人員（11/06 使用者決定）
CLOSING_LINE = "已為您紀錄，消防車已經出勤，請保持電話暢通。如果現場狀況有變化，請立刻再撥 119 告訴我們，謝謝"
EMS_CLOSING_LINE = "已為您紀錄，救護車已經出勤，請保持電話暢通。如果現場狀況有變化，請立刻再撥 119 告訴我們，謝謝"
RESCUE_CLOSING_LINE = "已為您紀錄，救護人員已經出勤，請保持電話暢通。如果現場狀況有變化，請立刻再撥 119 告訴我們，謝謝"

# xlsx 用一句話問兩個關鍵要素的題目，承辦要求缺什麼問什麼：
# 兩個都不知道就照 xlsx 整句問；只缺一個時改問下面對應的句子（10/29 確認的說法）。
# 整句問完只答到一個時，也用下面的句子補問一次。
SINGLE_MISSING_QUESTIONS = {
    ("patient_gender", "patient_age"): {
        "patient_gender": "請問患者是男生還是女生？",
        "patient_age": "請問患者大概幾歲？",
    },
    ("injury_severity", "cutting_tool"): {
        "injury_severity": "請問是哪裡受傷？",
        "cutting_tool": "是用什麼工具受傷的？",
    },
    ("ingested_substance", "drug_amount"): {
        "ingested_substance": "請問是吃了什麼藥物？",
        "drug_amount": "知道大概吃了幾顆嗎？",
    },
    # 孕婦待產：句子照 xlsx 問句欄另外寫的單問句
    ("due_date", "pregnancy_week"): {
        "due_date": "預產期是什麼時候？",
        "pregnancy_week": "現在懷孕幾週了？",
    },
    # 災害：句子照 1106 xlsx 問句欄另外寫的單問句
    ("disaster_injury", "trapped_status"): {
        "disaster_injury": "有沒有人受傷？",
        "trapped_status": "有沒有人被困住出不來？",
    },
    ("caller_location", "caller_relation"): {
        "caller_location": "請問您還在現場嗎？",
        "caller_relation": "是路過民眾嗎？",
    },
}


class SubCategoryHandler:
    """通用（無次類別）Handler：三個鉤子皆為預設版。"""

    # 該子類會詢問、空了要補問的 SOP 槽位（切類遷移與 skip-if-filled 共用）
    SOP_SLOTS: tuple[str, ...] = (
        "incident_description",
        "consciousness",
        "breathing",
        "abdomen_rise",
        "patient_count",
        "patient_gender",
        "patient_age",
        "current_condition",
    )

    def collect_caller_info(self, engine: "SopEngine119") -> None:
        """標準版報案人訊息收集（姓名 + 聯繫方式）。"""
        self._do_collect_caller_info(engine, include_address=False)

    # ── 照救護題目表（ems_tab_map_119）逐題問 ─────────────────────────────────

    def _ask_ems_questions(self, engine: "SopEngine119", questions) -> None:
        """
        照 xlsx 的順序逐題處理，做法跟火警垂片一樣：
        - 被動題：不問（報案人講到時，每一輪的欄位抽取會記下來）
        - 條件題：前置條件確定成立才問；不確定就當作不成立，不問
        - 主動題、條件成立的條件題：答案還不知道才問
        - 沒有問句的題目（例如燒燙傷的年齡）跟上一題一起問：上一題的問句已經問到
        條件在輪到那一題時才判斷，因為要用到前面剛問到的答案。
        每一題之前、全部問完之後都做一次改判檢查（_check_escalation）和呼吸檢查（_check_breathing_transfer），
        因為報案人可能在任何一句講到要改判的內容或呼吸狀況，不一定是問到那一題時才講。
        """
        from fire_tab_map_119 import MODE_CONDITIONAL, MODE_PASSIVE

        for number, item in enumerate(questions):
            engine._ensure_known_fields_from_history()
            self._check_escalation(engine)
            self._check_breathing_transfer(engine)
            if item.mode == MODE_PASSIVE:
                # 被動題不問；報案人已經講到的話，xlsx 備註的處理（例如改判）照樣要做
                if engine._is_field_filled(item.field):
                    self._after_ems_item(engine, item)
                continue
            if not item.question:
                continue
            if item.mode == MODE_CONDITIONAL and not item.condition(engine.case):
                engine._debug_print(
                    f"skip_{item.stage}", {"前置條件不成立": item.condition_text},
                )
                continue
            # 後面緊接著、沒有問句的題目，答案也從這一題的問句來
            fields = [item.field]
            for later in questions[number + 1:]:
                if later.question or later.mode == MODE_PASSIVE:
                    break
                fields.append(later.field)
            engine._set_stage(item.stage)
            if self._ems_question_needed(engine, item, fields):
                question = item.question
                singles = self._single_missing_questions(engine, fields)
                missing = [field for field in fields if not engine._is_field_filled(field)]
                if singles and len(missing) == 1:
                    question = singles[missing[0]]
                engine._ask_and_extract(question)
                # 複合題問完還剩一個沒答到（例如只答「是女生」），用單問句再問一次
                missing = [field for field in fields if not engine._is_field_filled(field)]
                if singles and len(missing) == 1:
                    engine._ask_and_extract(singles[missing[0]])
            else:
                engine._debug_print(
                    f"skip_{item.stage}",
                    {field: getattr(engine.case, field) for field in fields},
                )
            self._after_ems_item(engine, item)
        self._check_escalation(engine)
        self._check_breathing_transfer(engine)

    def _single_missing_questions(self, engine: "SopEngine119", fields) -> Optional[dict]:
        """
        一句問兩個關鍵要素、只答到一個時的單問句 {欄位: 問句}；沒有就回傳 None。
        預設用 SINGLE_MISSING_QUESTIONS；問句用字不同的大類覆寫這裡（例如緊急救援部分表用「當事人」）。
        """
        return SINGLE_MISSING_QUESTIONS.get(tuple(fields))

    def _check_escalation(self, engine: "SopEngine119") -> None:
        """
        xlsx 備註要「改判緊急救援」時，各次案類覆寫這裡。預設不做事。
        只看目前記下來的答案，不管現在問到哪一題：報案人哪一句講到都要改判。
        已經改判過就不會重複改判、不會重複講話（見 engine._escalate_main_to_emergency）。
        """

    def _after_ems_item(self, engine: "SopEngine119", item) -> None:
        """
        每一題處理完（剛問到答案，或報案人前面已經講過、這題跳過）之後呼叫。
        xlsx 備註要「回答某個答案就提醒」時，各次案類覆寫這裡（改判寫在 _check_escalation）：
        不管答案是這一題問到的、還是前面就講過，都要處理。預設不做事。
        """

    def _ems_question_needed(self, engine: "SopEngine119", item, fields) -> bool:
        """有任何一個欄位還不知道就要問。"""
        return not all(engine._is_field_filled(field) for field in fields)

    def _check_breathing_transfer(self, engine: "SopEngine119") -> None:
        """
        呼吸 = 呼吸不正常、無呼吸 → 轉真人（使用者 11/02 決定，不再用 OHCA 判定）。
        轉接的做法統一在 engine._transfer_to_human。
        """
        from ems_tab_map_119 import BREATHING_TRANSFER

        if engine.case.breathing in BREATHING_TRANSFER:
            engine._transfer_to_human(f"breathing_transfer：{engine.case.breathing}")

    def _check_and_respond_to_triggers(self, caller_text: str, engine: "SopEngine119") -> None:
        """觸發情境偵測；預設沒有，由各次案類覆寫。"""

    # ── 上吊等自傷：流程中需破門 → 改判緊急救援（加派消防車）────────────────────

    def _maybe_escalate_break_in(self, engine: "SopEngine119", text: str) -> bool:
        """
        流程中發現需消防破門（如燒炭者反鎖在家）→ 改判緊急救援-破門、加派消防車，並轉真人。

        判斷用「關鍵字召回 + LLM 精準確認」，避免純關鍵字誤判：
          1. 否定感知關鍵字當便宜預篩——沒有未否定的破門訊號就直接跳過（不呼叫 LLM）。
          2. 有候選才交 LLM 判上下文：明確是假設/過去式/其實進得去 → LLM 否決、不升級。
        安全優先：唯有 LLM 明確判 false 才擋；確認/不確定/無 LLM 皆升級
        （漏判「人反鎖在裡面沒人破門」比誤判「多派一台消防車」危險）。
        """
        from sop_119_engine import BREAK_IN_KW
        from sop_utils_119 import _has_unnegated_token

        if engine.case.main_category == "緊急救援":
            return False
        # 1) 便宜預篩：沒有未被否定的破門關鍵字 → 不升級、不叫 LLM
        if not _has_unnegated_token(text or "", BREAK_IN_KW):
            return False
        # 2) 有候選 → LLM 判上下文，僅明確否定才擋
        if engine._llm is not None:
            try:
                from llm_extractor_119 import _coerce_bool
                out = engine._llm.extract_slots(
                    text,
                    schema={"need_break_in": "true|false|null"},
                    rules=(
                        "判斷【文本】是否表示『現在需要消防破門才能接觸到傷病患』。\n"
                        "- 當事人把自己反鎖在房間/屋內、門打不開、進不去、需要破門 → true\n"
                        "- 門開著/進得去/已經進去了/已破門進去/只是假設或擔心/過去發生"
                        "現已解決 → false\n"
                        "- 未提及或不確定 → null"
                    ),
                )
                if _coerce_bool(out.get("need_break_in")) is False:
                    engine._debug_print("break_in_llm_reject", text)
                    return False
            except Exception as e:
                engine._debug_print("break_in_llm_error", e)
        from emergency_tab_map_119 import DOOR

        return engine._escalate_main_to_emergency(
            DOOR, reason=f"{engine.case.sub_category or '救護'}需破門",
        )

    # ── 意識異常情境：主動探問服藥/中毒（C）────────────────────────────────────

    def _probe_cause_ingestion(self, engine: "SopEngine119", *, on_answer=None) -> None:
        """
        意識異常（迷糊/叫沒反應）情境下，主動探問是否吃錯藥/服藥過量/中毒。

        報案人常不會主動吐出「藥」字，急病與吞食藥物的表徵（半意識/無反應）又高度
        重疊，BERT 分不清、也不會切類。此探問補一句不依賴關鍵詞的成因問題，讓答案帶出
        服藥訊號後：
          - 若目前在急病等子類 → 每輪 sub-reclassify 有機會切到吞食藥物；
          - 若已在吞食藥物 → 交由呼叫端 on_answer 觸發 t1/t2 追問藥物種類。

        整通電話只探問一次（engine._cause_ingestion_probed 記錄）；已知服藥內容則跳過。
        注意：engine._ask_and_extract 可能因切類拋出 SubCategorySwitched，由 _run_救護
        的重入迴圈接手，屬預期行為。
        """
        if engine._is_field_filled("ingested_substance"):
            return
        if getattr(engine, "_cause_ingestion_probed", False):
            return
        engine._cause_ingestion_probed = True

        q = "知道是什麼原因嗎？有沒有可能吃錯藥、吃太多藥、或是中毒？"
        before_cause = engine.case.collapse_cause
        try:
            answer = engine._ask_and_extract(q)
        finally:
            # 切類時 _ask_and_extract 會拋 SubCategorySwitched，reset 必須在 finally
            # 才跑得到（collapse_cause 已在拋出前被填，見 90642da6）。
            self._reset_probe_question_echo(engine, q, before_cause)
        if on_answer is not None:
            on_answer(answer)

    def _reset_probe_question_echo(
        self, engine: "SopEngine119", question: str, before_value
    ) -> None:
        """
        C 探問問句列了「吃錯藥/吃太多藥/中毒」示範詞，抽取器可能把問句示範當成答案
        灌進 collapse_cause（見 90642da6：值＝問句片段而非報案人回答）。
        若探問後的新值只是問句的回聲，還原為探問前的值；真答案已進 ingested_substance。
        """
        cur = engine.case.collapse_cause
        if not cur or cur == before_value:
            return
        q_compact = "".join((question or "").split())
        if "".join(cur.split()) in q_compact:
            with engine._case_lock:
                engine.case.collapse_cause = before_value
            engine._notify_case_update()
            engine._debug_print("probe_collapse_cause_echo_reset", cur)

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
            question = "請問你的姓名、聯繫方式與住址？"
        else:
            question = "請問你的姓名與聯繫方式？"

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
            if include_address:
                engine.case.caller_address = caller_address
        engine.set_caller_contact(caller_contact)   # 含號碼格式檢查
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
        # 結束語「請在現場耐心等待…」拿掉（10/29 使用者決定）：報案人常不在現場，
        # 比照火警，覆誦完姓名、聯繫方式就結束
        # 11/02 使用者決定暫時不唸姓名、聯繫方式，要恢復就把下一行的註解拿掉
        # engine._say("，".join(parts) + "，已為您記錄。")
        engine._say(EMS_CLOSING_LINE)

        with engine._case_lock:
            engine.case.result = "dispatched"
        engine._set_stage("completed")
        engine._notify_case_update()
        engine._emit({"type": "stopped", "result": "dispatched"})
