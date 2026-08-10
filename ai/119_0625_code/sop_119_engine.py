"""
sop_119_engine.py
━━━━━━━━━━━━━━━━━
119 報案受理 — SOP 對話引擎

架構原則：
  - LLM 只負責抽取，腳本負責對話流程（絕不讓 LLM 決定下一句話）
  - DialogueIO 抽象隔離 I/O（支援 CLI / Streamlit Queue 橋接）
  - 每輪報警人輸入後：通用字段嘗試抽取 + 案情摘要更新

使用方式（CLI 測試）::

    from sop_119_engine import SopEngine119, CliDialogueIO
    from llm_extractor_119 import LLMExtractor119
    from inference_pipeline import HierarchicalClassifier
    from classifier_with_llm import build_classifiers

    main_clf = HierarchicalClassifier()
    sub_clf  = build_classifiers()
    llm      = LLMExtractor119()

    engine = SopEngine119(
        io=CliDialogueIO(),
        main_classifier=main_clf,
        sub_classifiers=sub_clf,
        llm_extractor=llm,
    )
    engine.run()
    print(engine.case.to_dict())

使用方式（Streamlit Queue 橋接）::

    import queue, threading
    input_q  = queue.Queue()
    output_q = queue.Queue()
    io = QueueDialogueIO(input_q, output_q)
    engine = SopEngine119(io=io, ...)
    t = threading.Thread(target=engine.run, daemon=True)
    t.start()
"""

from __future__ import annotations

import queue
import re
import sys
import threading
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from case_info_119 import CaseInfo119
from llm_extractor_119 import LLMExtractor119, build_fallback_summary
from sop_utils_119 import (
    extract_address_hint,
    extract_patient_info_hint,
    looks_like_address_response,
    merge_address,
    parse_yes_no,
    parse_yes_no_for_question,
)


# ─── DialogueIO 抽象 ──────────────────────────────────────────────────────────

class DialogueIO(ABC):
    """I/O 抽象層：統一 say() / hear_text() 介面。"""

    @abstractmethod
    def say(self, text: str) -> None:
        """輸出一句話給使用者（不等待回應）。"""

    @abstractmethod
    def hear_text(self) -> str:
        """等待並讀取使用者的輸入文字。"""

    def ask(self, question: str) -> str:
        """say(question) + hear_text() 的組合。"""
        self.say(question)
        return self.hear_text()


class CliDialogueIO(DialogueIO):
    """CLI 調試用 I/O：say→print，hear_text→stdin。"""

    def say(self, text: str) -> None:
        print(f"\n【系統】{text}", flush=True)

    def hear_text(self) -> str:
        try:
            return input("【報警人】").strip()
        except EOFError:
            return ""


class QueueDialogueIO(DialogueIO):
    """
    Streamlit 線程橋接 I/O。

    output_q 事件格式
    -----------------
    {"type": "chat",           "role": "assistant"|"caller", "text": "..."}
    {"type": "case_update",    "case": {...}}
    {"type": "classification", "main": ..., "main_conf": ...,
                               "sub": ...,  "sub_conf": ...}
    {"type": "stage_update",   "stage": "..."}
    {"type": "stopped",        "result": "dispatched"|"ohca_transfer"|"error"}
    {"type": "error",          "message": "..."}
    """

    def __init__(
        self,
        input_q:  "queue.Queue[str]",
        output_q: "queue.Queue[Dict[str, Any]]",
    ):
        self._input_q  = input_q
        self._output_q = output_q

    def say(self, text: str) -> None:
        self._output_q.put({"type": "chat", "role": "assistant", "text": text})

    def hear_text(self) -> str:
        """等待報警人輸入（caller 訊息由 Streamlit UI 自行顯示，避免重複）。"""
        return self._input_q.get()

    def emit(self, event: Dict[str, Any]) -> None:
        """直接推送任意事件（非對話類事件）。"""
        self._output_q.put(event)


# ─── 轉人工例外 ──────────────────────────────────────────────────────────────

class TransferToHumanError(Exception):
    """觸發時立即中止 handler 並轉接真人接線員。"""


# ─── SOP 引擎 ─────────────────────────────────────────────────────────────────

class SopEngine119:
    """
    119 SOP 主引擎。

    參數
    ----
    io : DialogueIO
        I/O 實作（CLI / Queue）
    main_classifier : HierarchicalClassifier | None
        主分類器（None 時跳過分類，需在外部預設 case.main_category）
    sub_classifiers : _ClassifierRegistry | None
        子分類器 registry（None 時跳過子分類）
    llm_extractor : LLMExtractor119 | None
        LLM 抽取器（None 時跳過所有 LLM 步驟）
    debug : bool
        是否印出 LLM 輸入/輸出
    """

    def __init__(
        self,
        io: DialogueIO,
        main_classifier=None,
        sub_classifiers=None,
        llm_extractor: Optional[LLMExtractor119] = None,
        debug: bool = False,
    ):
        self._io          = io
        self._main_clf    = main_classifier
        self._sub_clf     = sub_classifiers
        self._llm         = llm_extractor
        self._debug       = debug
        self.case         = CaseInfo119()
        self._case_lock   = threading.Lock()
        self._extracted_caller_count = 0
        self._extracted_caller_count = 0

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _say(self, text: str) -> None:
        self._io.say(text)
        with self._case_lock:
            self.case.transcript.append({"role": "assistant", "text": text})

    def _hear(self) -> str:
        text = self._io.hear_text()
        with self._case_lock:
            self.case.transcript.append({"role": "caller", "text": text})
        return text

    def _get_last_assistant_question(self) -> Optional[str]:
        """從 transcript 取本輪對應的受理員問句（跳過最後一則報警人回答）。"""
        transcript = self.case.transcript or []
        if len(transcript) < 2:
            return None
        # transcript[-1] 為當前報警人回答，向前找最近受理員問句
        for turn in reversed(transcript[:-1]):
            if turn.get("role") == "assistant":
                q = (turn.get("text") or "").strip()
                if q:
                    return q
        return None

    def _iter_caller_qa_pairs(self) -> List[tuple]:
        """從 transcript 產生 (受理員問題, 報警人回答) 序列。"""
        pairs: List[tuple] = []
        last_q: Optional[str] = None
        for turn in self.case.transcript:
            role = turn.get("role")
            text = (turn.get("text") or "").strip()
            if role == "assistant" and text:
                last_q = text
            elif role == "caller" and text:
                pairs.append((last_q, text))
        return pairs

    def _is_field_filled(self, field: str) -> bool:
        with self._case_lock:
            return self.case.is_field_filled(field)

    def _ensure_known_fields_from_history(self) -> None:
        """
        從尚未處理的歷史報警人輸入中補抽各欄位。
        確保前輪長答中已提及的事件/現況等，能在後續跳過對應提問。
        """
        pairs = self._iter_caller_qa_pairs()
        if self._extracted_caller_count >= len(pairs):
            return

        new_pairs = pairs[self._extracted_caller_count:]
        for question, caller_text in new_pairs:
            if not caller_text:
                continue

            hints = extract_patient_info_hint(caller_text)
            if hints:
                with self._case_lock:
                    self._apply_extracted_fields(hints)

            if self._llm is not None:
                try:
                    extracted = self._llm.extract_general_fields(
                        caller_text,
                        question=question,
                    )
                    with self._case_lock:
                        self._apply_extracted_fields(extracted)
                except Exception as e:
                    self._debug_print("history_extract_error", e)

            self._try_extract_address(caller_text)

            # 生命征象：規則補抽（意識/呼吸/起伏問答）
            if question:
                for slot, keywords in (
                    ("consciousness", ("意識", "意识", "清醒")),
                    ("breathing", ("呼吸",)),
                    ("abdomen_rise", ("起伏", "肚子", "腹部")),
                ):
                    if any(k in question for k in keywords):
                        val = parse_yes_no_for_question(question, caller_text)
                        if val is not None:
                            with self._case_lock:
                                if getattr(self.case, slot) is None:
                                    setattr(self.case, slot, val)

        self._extracted_caller_count = len(pairs)
        self._notify_case_update()

    def _check_ohca_and_transfer(self, vital_val: Optional[bool], slot: str) -> None:
        """任一生命征象非 True → OHCA 轉人工。"""
        if vital_val is not True:
            with self._case_lock:
                self.case.is_ohca = True
            self._notify_case_update()
            self._say(
                "救護車已派出，請不要掛斷電話，我立即為您轉接專人。" #（判斷為ohca）
            )
            raise TransferToHumanError(f"OHCA detected at {slot}")

    def _ask(self, question: str) -> str:
        self._say(question)
        return self._hear()

    def _ask_and_extract(self, question: str) -> str:
        """詢問並以「本輪問題 + 報警人回答」觸發 LLM 跨欄位抽取。"""
        answer = self._ask(question)
        self._after_caller_input(answer, question=question)
        return answer

    def _emit(self, event: Dict[str, Any]) -> None:
        if isinstance(self._io, QueueDialogueIO):
            self._io.emit(event)

    def _notify_case_update(self) -> None:
        self._emit({"type": "case_update", "case": self.case.to_dict()})

    def _set_stage(self, stage: str) -> None:
        with self._case_lock:
            self.case.flow_stage = stage
        self._emit({"type": "stage_update", "stage": stage})

    def _debug_print(self, label: str, content: Any) -> None:
        if self._debug:
            print(f"[DEBUG][{label}] {content}", file=sys.stderr, flush=True)

    # ── LLM 每輪通用抽取 + 摘要更新 ──────────────────────────────────────────

    def _apply_extracted_fields(self, extracted: Dict[str, Any]) -> None:
        """將跨欄位抽取結果合併進 case（空欄位優先填入，地址允許升級）。"""
        _BOOL_FIELDS = {"consciousness", "breathing", "abdomen_rise"}

        for key, val in extracted.items():
            if val is None:
                continue
            current = getattr(self.case, key, None)

            if key in _BOOL_FIELDS:
                # 布林欄位：僅在尚未填入時寫入，後續專項問答可覆蓋
                if current is None:
                    setattr(self.case, key, val)
                continue

            if key == "address":
                new_addr = str(val).strip()
                if not new_addr:
                    continue
                if not current:
                    self.case.address = new_addr
                    continue
                merged = merge_address(str(current), new_addr)
                if merged and merged != current:
                    self.case.address = merged
                continue

            # 其他字串欄位：空欄位才填入
            if not current:
                setattr(self.case, key, val)

    def _try_extract_address(self, caller_text: str) -> bool:
        """專項地址抽取：規則備援 → LLM（不依賴當前問答類型）。"""
        if not (caller_text or "").strip():
            return False

        # 1) 規則備援（快速、對「地址在…」口語最穩）
        hinted = extract_address_hint(caller_text)
        if hinted:
            with self._case_lock:
                self._apply_extracted_fields({"address": hinted})
            self._debug_print("extract_address_rule", hinted)
            return True

        if self._llm is None:
            return False

        # 2) LLM 抽取（先原文、再帶地址問題上下文）
        try:
            result = self._llm.extract_address(caller_text, use_question=False)
            addr = result.get("address")
            if not addr:
                result = self._llm.extract_address(caller_text, use_question=True)
                addr = result.get("address")
            self._debug_print("extract_address_llm", result)
            if not addr:
                return False
            with self._case_lock:
                self._apply_extracted_fields({"address": addr})
            return True
        except Exception as e:
            self._debug_print("extract_address_error", e)
            return False

    def _resolve_address_correction(
        self,
        caller_text: str,
        question: str,
        current_address: str,
    ) -> Optional[str]:
        """
        地址確認環節：從報警人回答中抽取並合併更精確地址。

        報警人常不回「是/否」，而是直接補門牌，如「連城路347巷1弄2號附近」。
        """
        if not looks_like_address_response(caller_text):
            return None

        candidates: List[str] = []
        hinted = extract_address_hint(caller_text)
        if hinted:
            candidates.append(hinted)

        if self._llm is not None:
            try:
                llm_addr = self._llm.extract_address(
                    caller_text,
                    use_question=True,
                ).get("address")
                if llm_addr:
                    candidates.append(llm_addr)
                confirm_result = self._llm.extract_confirmation(
                    question=question,
                    caller_text=caller_text,
                    current_address=current_address,
                )
                new_addr = confirm_result.get("new_address")
                if new_addr:
                    candidates.append(new_addr)
            except Exception as e:
                self._debug_print("address_correction_error", e)

        merged = current_address
        changed = False
        for cand in candidates:
            next_addr = merge_address(merged, cand)
            if next_addr and next_addr != merged:
                merged = next_addr
                changed = True

        return merged if changed else None

    def _ensure_address_from_caller_history(self) -> None:
        """從已有報警人輸入中補抽地址（含第一輪），用於跳過地址詢問。"""
        if self.case.address:
            return
        for text in self.case.caller_texts():
            if self._try_extract_address(text):
                return
        blob = self.case.full_caller_text()
        if blob:
            self._try_extract_address(blob)

    def _after_caller_input(
        self,
        caller_text: str,
        question: Optional[str] = None,
    ) -> None:
        """每輪報警人輸入後觸發：跨欄位抽取所有欄位 + 案情摘要更新。"""
        if not (caller_text or "").strip():
            return

        # 取得本輪對應的受理員問題（Q&A 上下文）
        qa_question = question or self._get_last_assistant_question()

        # 1. 跨欄位抽取（有 LLM 時）
        if self._llm is not None:
            try:
                extracted = self._llm.extract_general_fields(
                    caller_text,
                    question=qa_question,
                )
                self._debug_print("general_extract", {
                    "question": qa_question,
                    "caller_text": caller_text,
                    "extracted": extracted,
                })
                with self._case_lock:
                    self._apply_extracted_fields(extracted)
            except Exception as e:
                self._debug_print("general_extract_error", e)

        # 1a. 規則備援：患者資訊/事件/現況（長答中常夾帶）
        hints = extract_patient_info_hint(caller_text)
        if hints:
            with self._case_lock:
                self._apply_extracted_fields(hints)

        # 1a2. 生命征象規則補抽（結合本輪問題）
        if qa_question:
            for slot, keywords in (
                ("consciousness", ("意識", "意识", "清醒")),
                ("breathing", ("呼吸",)),
                ("abdomen_rise", ("起伏", "肚子", "腹部")),
            ):
                if any(k in qa_question for k in keywords):
                    val = parse_yes_no_for_question(qa_question, caller_text)
                    if val is not None:
                        with self._case_lock:
                            if getattr(self.case, slot) is None:
                                setattr(self.case, slot, val)

        # 1b. 專項地址抽取（規則 + LLM，每輪必做）
        self._try_extract_address(caller_text)

        self._update_case_summary()
        self._extracted_caller_count = len(self._iter_caller_qa_pairs())
        self._notify_case_update()

    def _update_case_summary(self) -> None:
        """每輪更新案情摘要：LLM 優先，失敗則規則備援。"""
        with self._case_lock:
            caller_texts = self.case.caller_texts()
            filled_fields = self.case.filled_fields_for_summary()

        if not caller_texts and not filled_fields:
            return

        summary = ""
        if self._llm is not None:
            try:
                summary = self._llm.generate_summary(caller_texts, filled_fields)
                self._debug_print("summary", summary)
            except Exception as e:
                self._debug_print("summary_error", e)
        else:
            summary = build_fallback_summary(caller_texts, filled_fields)

        if not summary and self._llm is not None:
            summary = build_fallback_summary(caller_texts, filled_fields)

        if summary:
            with self._case_lock:
                self.case.case_summary = summary

    # ── 主流程 ────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        SOP 主流程入口。在工作線程中調用。
        異常時推送 error 事件，始終推送 stopped 事件。
        """
        try:
            self._run_main_flow()
        except TransferToHumanError:
            self._set_stage("ohca_transfer")
            with self._case_lock:
                self.case.result = "ohca_transfer"
            self._notify_case_update()
            self._emit({"type": "stopped", "result": "ohca_transfer"})
        except Exception as e:
            tb = traceback.format_exc()
            self._debug_print("run_error", tb)
            self._emit({"type": "error", "message": str(e)})
            with self._case_lock:
                self.case.result = "error"
            self._emit({"type": "stopped", "result": "error"})

    def _run_main_flow(self) -> None:
        # ── 第0輪：問第一個通用問題 ──────────────────────────────────────────
        self._set_stage("initial")
        first_q = "119你好，請問是火災還是救護？"
        first_input = self._ask_and_extract(first_q)

        # ── 主分類 ────────────────────────────────────────────────────────────
        self._set_stage("main_classifying")
        main_cat, main_conf = self._do_main_classify(first_input)
        with self._case_lock:
            self.case.main_category = main_cat
            self.case.main_conf     = main_conf
        self._emit({
            "type": "classification",
            "main": main_cat, "main_conf": main_conf,
            "sub": None, "sub_conf": None,
        })
        self._notify_case_update()
        self._set_stage("main_classified")

        # ── 按主類別派遣 handler ──────────────────────────────────────────────
        if main_cat == "救護":
            self._run_救護()
        else:
            # 其他類別：暫不支援，給出提示後結束
            self._say(f"已記錄您的{main_cat}報案，請稍候，即將轉接專人為您服務。")
            with self._case_lock:
                self.case.result = "dispatched"
            self._set_stage("completed")
            self._emit({"type": "stopped", "result": "dispatched"})

    def _do_main_classify(self, text: str):
        """調用主分類器，返回 (main_category, confidence)。"""
        if self._main_clf is not None:
            try:
                result = self._main_clf.predict(text)
                return result["main_category"], result["main_conf"]
            except Exception as e:
                self._debug_print("main_clf_error", e)
        # 無分類器時回退：依關鍵詞粗略判斷
        if any(kw in text for kw in ("救護", "救人", "救", "急救", "昏倒", "受傷", "受傷", "病")):
            return "救護", 0.9
        if any(kw in text for kw in ("火", "火災", "著火", "燒")):
            return "火警", 0.9
        return "救護", 0.5  # 預設

    def _do_sub_classify(self, text: str, main_cat: str):
        """調用子分類器，返回 (sub_category, confidence)。"""
        if self._sub_clf is not None:
            try:
                result = self._sub_clf.predict(text, main_cat)
                if result:
                    return result.final_label, result.classifier_conf
            except Exception as e:
                self._debug_print("sub_clf_error", e)
        return None, None

    # ── 救護 handler ──────────────────────────────────────────────────────────

    def _run_救護(self) -> None:
        """救護類別完整對話 SOP。"""

        # ════════════════════════════════════════════════════════
        # 階段 1：確認地址（循環直到報警人確認）
        # ════════════════════════════════════════════════════════
        self._set_stage("救護_location")

        # 先從歷史輸入（含第一輪）補抽地址；已有地址則跳過詢問
        self._ensure_address_from_caller_history()
        self._notify_case_update()

        if not self.case.address:
            addr_q = "請先告訴我地址？幾樓？"
            self._ask_and_extract(addr_q)
        else:
            self._debug_print("skip_address_ask", self.case.address)

        # 地址確認循環
        self._set_stage("救護_location_confirm")
        _confirm_attempts = 0
        while True:
            _confirm_attempts += 1
            current_addr_display = self.case.display_address()
            confirm_q = f"確定是{current_addr_display}這個地址嗎？"
            confirm_text = self._ask_and_extract(confirm_q)

            # 抽取階段可能已合併更新地址（每輪 _after_caller_input）
            if self.case.display_address() != current_addr_display:
                self._notify_case_update()
                continue

            # 地址修正：報警人補充/更正門牌時更新並重新確認
            addr_update = self._resolve_address_correction(
                confirm_text, confirm_q, self.case.address or "",
            )
            if addr_update:
                with self._case_lock:
                    self.case.address = addr_update
                self._notify_case_update()
                continue

            # 2) 規則：結合本輪問題語義判斷是/否
            confirmed = parse_yes_no_for_question(confirm_q, confirm_text)
            new_address = None

            # 3) LLM 抽取確認結果或新地址
            if self._llm:
                try:
                    confirm_result = self._llm.extract_confirmation(
                        question=confirm_q,
                        caller_text=confirm_text,
                        current_address=current_addr_display,
                    )
                    self._debug_print("extract_confirmation", confirm_result)
                    confirmed = confirm_result.get("confirmed")
                    new_address = confirm_result.get("new_address")
                except Exception as e:
                    self._debug_print("extract_confirmation_error", e)

            # 若有新地址 → 更新後重新確認
            if new_address:
                with self._case_lock:
                    merged = merge_address(self.case.address, new_address)
                    if merged:
                        self.case.address = merged
                self._notify_case_update()
                continue

            if confirmed is True:
                with self._case_lock:
                    self.case.address_confirmed = True
                self._notify_case_update()
                break

            # 無法確認：最多重試 3 次後強制通過
            if _confirm_attempts >= 3:
                with self._case_lock:
                    self.case.address_confirmed = True
                self._notify_case_update()
                break

        self._say("已確認地址，救護車已派出了喔。")

        # ════════════════════════════════════════════════════════
        # 此時：收集所有輪報警人文本 → 次分類器推理
        # ════════════════════════════════════════════════════════
        all_caller_text = self.case.full_caller_text()
        sub_cat, sub_conf = self._do_sub_classify(all_caller_text, "救護")
        with self._case_lock:
            self.case.sub_category = sub_cat
            self.case.sub_conf     = sub_conf
        self._emit({
            "type":     "classification",
            "main":     self.case.main_category,
            "main_conf": self.case.main_conf,
            "sub":      sub_cat,
            "sub_conf": sub_conf,
        })
        self._notify_case_update()
        self._set_stage("救護_sub_classified")

        # ════════════════════════════════════════════════════════
        # 階段 2：確認生命征象（3 問，已有值則跳過）
        # ════════════════════════════════════════════════════════
        self._ensure_known_fields_from_history()

        vital_questions = [
            ("救護_vital_1", "consciousness", "請問人是否還有意識？"),
            ("救護_vital_2", "breathing",     "請你看一下他是否有呼吸？"),
            ("救護_vital_3", "abdomen_rise",  "請看一下他肚子有沒有起伏？"),
        ]

        for stage, slot, question in vital_questions:
            self._ensure_known_fields_from_history()

            if self._is_field_filled(slot):
                with self._case_lock:
                    vital_val = getattr(self.case, slot)
                self._debug_print(f"skip_{slot}", vital_val)
                self._set_stage(stage)
                self._check_ohca_and_transfer(vital_val, slot)
                continue

            self._set_stage(stage)
            vital_text = self._ask_and_extract(question)

            vital_val = parse_yes_no_for_question(question, vital_text)
            if vital_val is None and self._llm:
                try:
                    vital_val = self._llm.extract_vital_sign(question, vital_text)
                    self._debug_print(f"vital_{slot}", vital_val)
                except Exception as e:
                    self._debug_print(f"vital_{slot}_error", e)

            with self._case_lock:
                setattr(self.case, slot, vital_val)
            self._notify_case_update()
            self._check_ohca_and_transfer(vital_val, slot)

        # ════════════════════════════════════════════════════════
        # 階段 3：詢問關鍵要素（已有值則跳過）
        # ════════════════════════════════════════════════════════
        self._ensure_known_fields_from_history()

        patient_questions = [
            ("救護_patient_1", ("patient_gender", "patient_age"), "請問患者的性別？年齡？"),
            ("救護_patient_2", ("incident_description",), "剛剛發生甚麼事？"),
            ("救護_patient_3", ("current_condition",), "請問他現在狀況如何？"),
        ]

        for stage, fields, question in patient_questions:
            self._ensure_known_fields_from_history()

            if all(self._is_field_filled(f) for f in fields):
                self._debug_print(f"skip_{stage}", {
                    f: getattr(self.case, f) for f in fields
                })
                self._set_stage(stage)
                continue

            self._set_stage(stage)
            pi_text = self._ask_and_extract(question)

            hints = extract_patient_info_hint(pi_text)
            if hints:
                with self._case_lock:
                    self._apply_extracted_fields(hints)

            if self._llm:
                try:
                    pi_result = self._llm.extract_patient_info(question, pi_text)
                    self._debug_print("patient_info", pi_result)
                    with self._case_lock:
                        for key, val in pi_result.items():
                            if val and getattr(self.case, key, None) is None:
                                setattr(self.case, key, val)
                    self._notify_case_update()
                except Exception as e:
                    self._debug_print("patient_info_error", e)

        # ════════════════════════════════════════════════════════
        # 階段 4：摘要確認循環
        # ════════════════════════════════════════════════════════
        self._set_stage("救護_summary_confirm")

        _summary_attempts = 0
        while True:
            _summary_attempts += 1

            self._update_case_summary()

            current_summary = self.case.case_summary or "（目前無案情摘要）"
            summary_confirm_q = f"根據您的描述，：{current_summary}。請問以上是否正確？"
            sum_text = self._ask_and_extract(summary_confirm_q)

            sum_confirmed = parse_yes_no_for_question(summary_confirm_q, sum_text)
            if sum_confirmed is None and self._llm:
                try:
                    sum_confirmed = self._llm.extract_summary_confirmation(
                        question=summary_confirm_q,
                        caller_text=sum_text,
                    )
                    self._debug_print("summary_confirmed", sum_confirmed)
                except Exception as e:
                    self._debug_print("summary_confirmation_error", e)

            if sum_confirmed is True:
                break

            # 未確認 → 請報警人重新描述
            if _summary_attempts >= 5:
                # 避免無限循環，超過5次後強制通過
                break

            retry_text = self._ask_and_extract("請您再說一次發生了甚麼事？")

        # ════════════════════════════════════════════════════════
        # 流程結束
        # ════════════════════════════════════════════════════════
        self._say(
            "救護車已派出，請在現場等待，確認入口通暢，並引導救護人員，謝謝。"
        )
        with self._case_lock:
            self.case.result = "dispatched"
        self._set_stage("completed")
        self._notify_case_update()
        self._emit({"type": "stopped", "result": "dispatched"})


# ─── CLI 快速測試入口 ─────────────────────────────────────────────────────────

def _cli_main():
    """CLI 快速測試（不加載 GPU 模型，僅測試對話流程）。"""
    import argparse, json as _json

    parser = argparse.ArgumentParser(description="119 SOP 引擎 CLI 測試")
    parser.add_argument("--no-main-clf", action="store_true", help="不加載主分類器")
    parser.add_argument("--no-sub-clf",  action="store_true", help="不加載子分類器")
    parser.add_argument("--no-llm",      action="store_true", help="不加載 LLM")
    parser.add_argument("--debug",       action="store_true", help="印出 LLM 輸入輸出")
    args = parser.parse_args()

    main_clf = None
    sub_clf  = None
    llm      = None

    if not args.no_main_clf:
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(__file__))
            from inference_pipeline import HierarchicalClassifier
            main_clf = HierarchicalClassifier()
            print("[INFO] 主分類器已加載")
        except Exception as e:
            print(f"[WARN] 主分類器加載失敗（跳過）: {e}")

    if not args.no_sub_clf:
        try:
            from classifier_with_llm import build_classifiers
            sub_clf = build_classifiers(enable_llm=False)
            print("[INFO] 子分類器已加載")
        except Exception as e:
            print(f"[WARN] 子分類器加載失敗（跳過）: {e}")

    if not args.no_llm:
        try:
            llm = LLMExtractor119()
            print("[INFO] LLM 已加載")
        except Exception as e:
            print(f"[WARN] LLM 加載失敗（跳過）: {e}")

    engine = SopEngine119(
        io=CliDialogueIO(),
        main_classifier=main_clf,
        sub_classifiers=sub_clf,
        llm_extractor=llm,
        debug=args.debug,
    )
    engine.run()

    print("\n" + "=" * 60)
    print("【最終案件資訊】")
    print(_json.dumps(engine.case.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli_main()
