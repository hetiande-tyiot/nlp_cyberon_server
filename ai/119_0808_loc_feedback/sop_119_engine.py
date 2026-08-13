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
import random
import re
import sys
import threading
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from case_info_119 import CaseInfo119
from handlers import get_handler
from important_tags_119 import match_important_tags, merge_important_tags
from llm_extractor_119 import LLMExtractor119, build_fallback_summary
from location_validation_119 import (
    load_landmark_names,
    load_mrt_location_names,
    query_jurisdiction,
    validate_landmark,
    validate_mrt,
)
from sop_utils_119 import (
    build_highway_address,
    build_intersection_address,
    classify_location_type,
    clean_address_fragment,
    ensure_city_prefix,
    extract_address_hint,
    extract_address_district,
    extract_highway_components,
    extract_intersection_roads,
    has_outdoor_location_hint,
    strip_floor_question,
    is_street_address,
    is_usable_address,
    extract_patient_info_hint,
    extract_pregnancy_info_hint,
    extract_vital_signs_hint,
    looks_like_address_response,
    merge_address,
    parse_vital_slot,
    parse_yes_no,
    parse_yes_no_for_question,
)
from subcategory_keywords_119 import match_rescue_subcategory


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
    {"type": "stopped",        "result": "dispatched"|"ohca_transfer"|
                                         "human_transfer"|"error"|"manual_end"}
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


# ─── 流程控制訊號 / 例外 ──────────────────────────────────────────────────────

# UI 主動結束時寫入 input_q 的哨兵值（不會當成報警人原話入 transcript）
END_FLOW_SENTINEL = "__END_FLOW__"


class TransferToHumanError(Exception):
    """觸發時立即中止 handler 並轉接真人接線員。"""

    def __init__(self, reason: str = "transfer", *, result: str = "human_transfer"):
        super().__init__(reason)
        self.reason = reason
        # result: "ohca_transfer" | "human_transfer"
        self.result = result


class FlowAbortedError(Exception):
    """操作員主動結束流程時拋出，優雅中止 SOP。"""


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

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _say(self, text: str) -> None:
        self._io.say(text)
        with self._case_lock:
            self.case.transcript.append({"role": "assistant", "text": text})

    def _hear(self) -> str:
        text = self._io.hear_text()
        if text == END_FLOW_SENTINEL:
            raise FlowAbortedError("manual end requested")
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
        每一則報警人回答都以 LLM 跨欄位抽取為準（與 _after_caller_input 一致）。
        """
        pairs = self._iter_caller_qa_pairs()
        if self._extracted_caller_count >= len(pairs):
            return

        new_pairs = pairs[self._extracted_caller_count:]
        for question, caller_text in new_pairs:
            if not caller_text:
                continue
            self._extract_all_fields_from_reply(caller_text, question=question)

        self._extracted_caller_count = len(pairs)
        self._notify_case_update()

    def _check_ohca_and_transfer(self, vital_val: Optional[bool], slot: str) -> None:
        """任一生命征象非 True → OHCA 轉人工。"""
        if vital_val is not True:
            with self._case_lock:
                self.case.is_ohca = True
            self._notify_case_update()
            self._say(
                "（判斷為OHCA）救護車已派出，請不要掛斷電話，我立即為您轉接專人。"
            )
            raise TransferToHumanError(
                f"OHCA detected at {slot}", result="ohca_transfer"
            )

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
        _INTERNAL_OVERWRITE_FIELDS = {
            "report_request_type",
            "field_report_content",
            "support_vehicle_type",
            "support_vehicle_count",
            "support_request_confirmed",
            "has_additional_request",
        }
        _FIRE_OVERWRITE_FIELDS = {
            "fire_or_smoke",
            "smoke_color",
            "burning_object",
            "fire_trend",
            "fire_extent",
            "fire_category",
            "caller_position",
            "caller_role",
            "people_trapped",
            "trapped_count",
            "building_total_floors",
            "fire_floor",
            "fire_spread",
            "building_layout",
            "factory_scale_type",
            "factory_people_present",
            "hazardous_materials",
            "vehicle_type",
            "vehicle_count",
            "vehicle_occupants",
            "vehicle_occupant_count",
            "road_type",
            "outdoor_fire_type",
            "nearby_water_source",
            "affected_targets",
            "caller_salutation",
        }

        for key, val in extracted.items():
            if val is None:
                continue
            current = getattr(self.case, key, None)

            if key == "ImportantCase":
                # 等級 0 預設 / 1 一般 / 2 緊急。
                # 允許依本輪明確新證據升級或降級：報警人更正誤聽的關鍵詞時
                # （如「不是持刀，是賭博」），等級必須跟著降回來。
                if (
                    not isinstance(val, bool)
                    and isinstance(val, int)
                    and val in (0, 1, 2)
                ):
                    self.case.ImportantCase = val
                continue

            if key == "ImportantTag":
                self.case.ImportantTag = merge_important_tags(
                    self.case.ImportantTag,
                    val,
                )
                continue

            if key == "NeedPolice":
                # 只有抽取器確認為明確布林證據時才覆蓋先前結果。
                if isinstance(val, bool):
                    self.case.NeedPolice = val
                continue

            if key == "call_type":
                # 一旦辨識為局內回報，不讓後續一般案情描述把通話模式改回去。
                if val == "局內回報" or not current:
                    self.case.call_type = val
                continue

            if key in _INTERNAL_OVERWRITE_FIELDS:
                # 局內回報需要接受覆誦更正，也要能處理同一通電話的下一項需求。
                setattr(self.case, key, val)
                continue

            if key in _FIRE_OVERWRITE_FIELDS:
                # 火災資訊以本輪明確新證據為準，允許報案人後續補充或更正。
                setattr(self.case, key, val)
                continue

            if key in _BOOL_FIELDS:
                # 布林欄位：僅在尚未填入時寫入，後續專項問答可覆蓋
                if current is None:
                    setattr(self.case, key, val)
                continue

            if key == "address":
                new_addr = clean_address_fragment(str(val).strip())
                if not is_usable_address(new_addr):
                    continue
                if not is_usable_address(current):
                    self.case.address = new_addr
                    continue
                merged = merge_address(str(current), new_addr)
                if is_usable_address(merged) and merged != current:
                    self.case.address = merged
                continue

            # 其他字串欄位：空欄位才填入
            if not current:
                setattr(self.case, key, val)

    def _apply_location_rules(self, caller_text: str) -> None:
        """以确定性规则补强本轮地点组件，并重组可显示地址。"""
        text = (caller_text or "").strip()
        if not text:
            return

        district = extract_address_district(text)
        roads = extract_intersection_roads(text)
        highway = extract_highway_components(text)
        explicit_type = classify_location_type(text)
        explicit_candidate = (
            clean_address_fragment(text)
            if explicit_type in {"intersection", "highway", "mrt", "landmark"}
            else ""
        )

        with self._case_lock:
            if district:
                self.case.address_district = district

            if explicit_type in {"intersection", "highway", "mrt", "landmark"}:
                self.case.location_type = explicit_type
                if explicit_candidate:
                    self.case.address = explicit_candidate

            if explicit_type == "intersection" or self.case.location_type == "intersection":
                if roads:
                    if not self.case.intersection_road1:
                        self.case.intersection_road1 = roads[0]
                    elif (
                        roads[0] != self.case.intersection_road1
                        and roads[0] not in self.case.intersection_road1
                        and self.case.intersection_road1 not in roads[0]
                        and not self.case.intersection_road2
                    ):
                        self.case.intersection_road2 = roads[0]
                    if len(roads) > 1:
                        self.case.intersection_road2 = roads[1]

            for key, value in highway.items():
                if value:
                    setattr(self.case, key, value)

            if highway:
                self.case.location_type = "highway"

            if (
                district
                and is_usable_address(self.case.address)
                and district not in (self.case.address or "")
                and self.case.location_type == "address"
            ):
                self.case.address = f"{district}{self.case.address}"

            intersection = build_intersection_address(
                self.case.address_district,
                self.case.intersection_road1,
                self.case.intersection_road2,
            )
            highway_address = build_highway_address(
                self.case.highway_name,
                self.case.highway_direction,
                self.case.highway_kilometer,
            )
            if intersection and self.case.location_type == "intersection":
                self.case.address = intersection
            elif highway_address and self.case.location_type == "highway":
                self.case.address = highway_address

            # 无 LLM 时，仍保留明确的地标、捷运或未完成路口/高速公路原话。
            if (
                not is_usable_address(self.case.address)
                and explicit_type in {"intersection", "highway", "mrt", "landmark"}
            ):
                candidate = clean_address_fragment(text)
                if candidate:
                    self.case.address = candidate

    def _refresh_location_type(self) -> Optional[str]:
        """结合名单与规则校正地点类别，明确规则优先于 LLM 猜测。"""
        address = self.case.address or ""
        try:
            mrt_names = list(load_mrt_location_names())
        except Exception as exc:
            self._debug_print("load_mrt_error", exc)
            mrt_names = []
        try:
            landmark_names = list(load_landmark_names())
        except Exception as exc:
            self._debug_print("load_landmarks_error", exc)
            landmark_names = []
        rule_type = classify_location_type(
            address,
            mrt_names=mrt_names,
            landmark_names=landmark_names,
        )
        with self._case_lock:
            if rule_type:
                self.case.location_type = rule_type
            elif not self.case.location_type and is_usable_address(address):
                self.case.location_type = "address"
            return self.case.location_type

    def _try_extract_address(self, caller_text: str) -> bool:
        """專項地址抽取：規則備援 → LLM（不依賴當前問答類型）。"""
        if not (caller_text or "").strip():
            return False

        # 1) 規則備援（快速、對「地址在…」口語最穩）
        hinted = extract_address_hint(caller_text)
        if is_usable_address(hinted):
            with self._case_lock:
                self._apply_extracted_fields({"address": hinted})
            self._debug_print("extract_address_rule", hinted)
            return is_usable_address(self.case.address)

        if self._llm is None:
            return False

        # 2) LLM 抽取（先原文、再帶地址問題上下文）
        try:
            result = self._llm.extract_address(caller_text, use_question=False)
            addr = result.get("address")
            if not is_usable_address(addr):
                result = self._llm.extract_address(caller_text, use_question=True)
                addr = result.get("address")
            self._debug_print("extract_address_llm", result)
            if not is_usable_address(addr):
                return False
            with self._case_lock:
                self._apply_extracted_fields({"address": addr})
            return is_usable_address(self.case.address)
        except Exception as e:
            self._debug_print("extract_address_error", e)
            return False

    def _clear_unusable_address(self) -> None:
        """若 address 為空或「未知」等佔位，清成 None，避免進入錯誤複讀。"""
        with self._case_lock:
            if not is_usable_address(self.case.address):
                self.case.address = None

    def _resolve_address_correction(
        self,
        caller_text: str,
        question: str,
        current_address: str,
    ) -> Optional[str]:
        """
        地址確認環節：從報警人回答中抽取並合併更精確地址。

        報警人常不回「是/否」，而是直接補門牌，如「連城路347巷1弄2號附近」；
        或否認後改報「不是，民權街二段87號一樓」。
        """
        if not looks_like_address_response(caller_text):
            return None

        candidates: List[str] = []
        hinted = extract_address_hint(caller_text)
        if hinted:
            candidates.append(hinted)

        confirmed_false = False
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
                if confirm_result.get("confirmed") is False:
                    confirmed_false = True
                new_addr = confirm_result.get("new_address")
                if new_addr:
                    candidates.append(new_addr)
            except Exception as e:
                self._debug_print("address_correction_error", e)

        # 規則：開頭否定也視為更正（LLM 未判出 confirmed=false 時備援）
        t = (caller_text or "").strip()
        if re.match(r"^(?:不是|不對|不对|錯了|错了)", t):
            confirmed_false = True

        cleaned_cands = [
            clean_address_fragment(c) for c in candidates if c
        ]
        cleaned_cands = [c for c in cleaned_cands if is_usable_address(c)]
        if not cleaned_cands:
            return None

        # 明確否認舊址時：優先採用含門牌的新址整段替換
        if confirmed_false:
            street_cands = [c for c in cleaned_cands if is_street_address(c)]
            pick = (street_cands or cleaned_cands)[0]
            # 取資訊量較大的門牌候選
            for c in (street_cands or cleaned_cands):
                if len(re.sub(r"\s+", "", c)) > len(re.sub(r"\s+", "", pick)):
                    pick = c
            if pick and re.sub(r"\s+", "", pick) != re.sub(
                r"\s+", "", current_address or ""
            ):
                return pick

        merged = current_address
        changed = False
        for cand in cleaned_cands:
            next_addr = merge_address(merged, cand)
            if next_addr and next_addr != merged:
                merged = next_addr
                changed = True

        return merged if changed else None

    def _ensure_address_from_caller_history(self) -> None:
        """從已有報警人輸入中補抽地址（含第一輪），用於跳過地址詢問。"""
        self._clear_unusable_address()
        if is_usable_address(self.case.address):
            return
        for text in self.case.caller_texts():
            if self._try_extract_address(text):
                return
        blob = self.case.full_caller_text()
        if blob:
            self._try_extract_address(blob)
        self._clear_unusable_address()

    def _extract_all_fields_from_reply(
        self,
        caller_text: str,
        question: Optional[str] = None,
    ) -> None:
        """
        對單則報警人回答做全欄位抽取並填入空欄位。

        原則：
        - 每一則回答都必須走 LLM，對所有業務欄位嘗試抽取
        - 生命征象可用規則校正（避免誤填導致 OHCA 誤判）
        - 僅當 LLM 不可用時，才用規則備援填患者/孕產欄位
        """
        if not (caller_text or "").strip():
            return

        qa_question = question or self._get_last_assistant_question()

        # 1) LLM 全欄位抽取（主路徑，每輪必做）
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
        else:
            # LLM 不可用：規則備援
            hints = extract_patient_info_hint(caller_text)
            if hints:
                with self._case_lock:
                    self._apply_extracted_fields(hints)
            preg_hints = extract_pregnancy_info_hint(caller_text)
            if preg_hints:
                with self._case_lock:
                    self._apply_extracted_fields(preg_hints)

        # 2) 全類型重要標籤規則補強（每輪執行、白名單、追加去重）
        matched_tags = match_important_tags(caller_text)
        if matched_tags:
            with self._case_lock:
                self._apply_extracted_fields({"ImportantTag": matched_tags})

        # 3) 生命征象規則校正（僅填補空值 / 校正明顯誤填風險）
        vital_hints = extract_vital_signs_hint(caller_text)
        if vital_hints:
            with self._case_lock:
                self._apply_extracted_fields(vital_hints)

        if qa_question:
            for slot, keywords in (
                ("consciousness", ("意識", "意识", "清醒", "反應", "反应", "捏", "肩膀")),
                ("breathing", ("呼吸",)),
                ("abdomen_rise", ("起伏", "肚子", "腹部", "反應", "反应", "捏", "肩膀")),
            ):
                if any(k in qa_question for k in keywords):
                    val = parse_vital_slot(slot, caller_text, qa_question)
                    if val is not None:
                        with self._case_lock:
                            if getattr(self.case, slot) is None:
                                setattr(self.case, slot, val)

        # 4) 專項地址抽取（規則 + LLM）
        self._try_extract_address(caller_text)
        self._apply_location_rules(caller_text)
        self._refresh_location_type()

    def _after_caller_input(
        self,
        caller_text: str,
        question: Optional[str] = None,
    ) -> None:
        """每輪報警人輸入後觸發：LLM 全欄位抽取 + 案情摘要更新。"""
        if not (caller_text or "").strip():
            return

        self._extract_all_fields_from_reply(caller_text, question=question)
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
        except FlowAbortedError:
            self._set_stage("manual_end")
            with self._case_lock:
                self.case.result = "manual_end"
            self._say("流程已由操作員結束，本次通話終止。")
            self._notify_case_update()
            self._emit({"type": "stopped", "result": "manual_end"})
        except TransferToHumanError as e:
            result = getattr(e, "result", None) or "human_transfer"
            if result not in ("ohca_transfer", "human_transfer"):
                result = "human_transfer"
            self._set_stage(result)
            with self._case_lock:
                self.case.result = result
            self._notify_case_update()
            self._emit({"type": "stopped", "result": result})
        except Exception as e:
            tb = traceback.format_exc()
            self._debug_print("run_error", tb)
            self._emit({"type": "error", "message": str(e)})
            with self._case_lock:
                self.case.result = "error"
            self._emit({"type": "stopped", "result": "error"})

    def _run_main_flow(self) -> None:
        # ── 第0輪：問第一個通用問題（三句開場白隨機擇一）──────────────────────
        self._set_stage("initial")
        first_q = random.choice([
            "119 您好，請問是火災還是救護",
            "119 您好，請問是需要消防車還是救護車",
            "119 您好，請問是要報火災還是有人身體不舒服",
        ])
        first_input = self._ask_and_extract(first_q)

        if self._is_internal_report(first_input):
            with self._case_lock:
                self.case.call_type = "局內回報"
                self.case.main_category = "局內回報"
                self.case.main_conf = 1.0
            self._emit({
                "type": "classification",
                "main": "局內回報", "main_conf": 1.0,
                "sub": None, "sub_conf": None,
            })
            self._notify_case_update()
            self._set_stage("main_classified")
            self._run_局內回報()
            return

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
        elif main_cat == "火警":
            self._run_火警()
        elif main_cat == "緊急救援":
            self._run_緊急救援()
        else:
            # 其他類別：暫不支援，給出提示後結束
            self._say(f"已記錄您的{main_cat}報案，請稍候，即將轉接專人為您服務。")
            with self._case_lock:
                self.case.result = "dispatched"
            self._set_stage("completed")
            self._emit({"type": "stopped", "result": "dispatched"})

    def _is_internal_report(self, text: str) -> bool:
        """以每輪 LLM 抽取結果為主，明確局內用語為降級備援。"""
        if self.case.call_type == "局內回報":
            return True
        normalized = re.sub(r"\s+", "", text or "")
        return any(
            keyword in normalized
            for keyword in ("分隊回報", "局內回報", "局内回报", "同仁回報", "同仁回报")
        )

    def _detect_report_request_type(self, text: str = "") -> Optional[str]:
        request_type = self.case.report_request_type
        if request_type in ("現場回報", "支援請求"):
            return request_type
        normalized = re.sub(r"\s+", "", text or "")
        if any(keyword in normalized for keyword in (
            "要車", "增派", "加派", "支援車", "支援车辆", "支援車輛",
        )):
            return "支援請求"
        if any(keyword in normalized for keyword in (
            "現場回報", "现场回报", "回報現場", "回报现场", "回報案情", "回报案情",
        )):
            return "現場回報"
        return None

    def _ask_internal_request_type(self, initial_text: str = "") -> str:
        request_type = self._detect_report_request_type(initial_text)
        while request_type is None:
            self._set_stage("局內回報_need")
            answer = self._ask_and_extract(
                "請問是要回報現場狀況，還是需要中心支援車輛？"
            )
            request_type = self._detect_report_request_type(answer)
        with self._case_lock:
            self.case.report_request_type = request_type
        self._notify_case_update()
        return request_type

    def _collect_internal_address(self) -> None:
        self._set_stage("局內回報_location")
        self._ask_and_extract("請先給我現場的完整地址。")
        while not is_usable_address(self.case.address):
            self._set_stage("局內回報_location_reask")
            self._ask_and_extract("目前地址資訊不足，請再提供現場的完整地址。")

    def _run_field_report(self) -> str:
        self._set_stage("局內回報_field_content")
        answer = self._ask_and_extract("請問要回報的內容（案情）是什麼？")
        if self._llm is None and answer.strip():
            with self._case_lock:
                self.case.field_report_content = answer.strip()
            self._notify_case_update()
        while not self._is_field_filled("field_report_content"):
            answer = self._ask_and_extract("請問要回報的內容（案情）是什麼？")
            if self._llm is None and answer.strip():
                with self._case_lock:
                    self.case.field_report_content = answer.strip()
                self._notify_case_update()
        self._say("收到，為您記錄。")
        return "report_recorded"

    def _run_support_request(self) -> str:
        while True:
            self._set_stage("局內回報_support_detail")
            self._ask_and_extract("現場需要什麼車？幾台？")
            while not (
                self._is_field_filled("support_vehicle_type")
                and self._is_field_filled("support_vehicle_count")
            ):
                self._ask_and_extract("現場需要什麼車？幾台？")

            vehicle_type = self.case.support_vehicle_type
            vehicle_count = self.case.support_vehicle_count
            with self._case_lock:
                self.case.support_request_confirmed = None

            self._set_stage("局內回報_support_confirm")
            confirm_answer = self._ask_and_extract(
                f"跟您確認，是否要 {vehicle_count} 台 {vehicle_type}嗎？"
            )
            confirmed = self.case.support_request_confirmed
            if confirmed is None:
                confirmed = parse_yes_no_for_question(
                    confirm_answer,
                    f"是否要 {vehicle_count} 台 {vehicle_type}",
                )
            if confirmed is True:
                with self._case_lock:
                    self.case.support_request_confirmed = True
                self._say(
                    f"好的，中心將為您派遣 {vehicle_count} 台 {vehicle_type}。"
                )
                self._notify_case_update()
                return "support_dispatched"
            if confirmed is False:
                with self._case_lock:
                    self.case.support_vehicle_type = None
                    self.case.support_vehicle_count = None
                    self.case.support_request_confirmed = False
                self._notify_case_update()
                continue
            self._say("抱歉，請明確告訴我以上車輛類型與數量是否正確。")

    def _clear_internal_task_fields(self) -> None:
        with self._case_lock:
            self.case.report_request_type = None
            self.case.field_report_content = None
            self.case.support_vehicle_type = None
            self.case.support_vehicle_count = None
            self.case.support_request_confirmed = None
            self.case.has_additional_request = None
            self.case.address = None
            self.case.address_confirmed = None
            self.case.location_type = None
            self.case.address_district = None
            self.case.intersection_road1 = None
            self.case.intersection_road2 = None
            self.case.highway_name = None
            self.case.highway_direction = None
            self.case.highway_kilometer = None

    def _run_局內回報(self) -> None:
        self._set_stage("局內回報_need")
        need_answer = self._ask_and_extract("長官您好，有什麼需要中心協助嗎？")
        last_result = "report_recorded"

        while True:
            request_type = self._ask_internal_request_type(need_answer)
            self._collect_internal_address()
            if request_type == "支援請求":
                last_result = self._run_support_request()
            else:
                last_result = self._run_field_report()

            with self._case_lock:
                previous_task = {
                    "report_request_type": self.case.report_request_type,
                    "field_report_content": self.case.field_report_content,
                    "support_vehicle_type": self.case.support_vehicle_type,
                    "support_vehicle_count": self.case.support_vehicle_count,
                    "support_request_confirmed": self.case.support_request_confirmed,
                    "address": self.case.address,
                    "address_confirmed": self.case.address_confirmed,
                    "location_type": self.case.location_type,
                    "address_district": self.case.address_district,
                    "intersection_road1": self.case.intersection_road1,
                    "intersection_road2": self.case.intersection_road2,
                    "highway_name": self.case.highway_name,
                    "highway_direction": self.case.highway_direction,
                    "highway_kilometer": self.case.highway_kilometer,
                }
            self._clear_internal_task_fields()
            self._set_stage("局內回報_more")
            more_answer = self._ask_and_extract("還有其他需要協助的嗎？")
            has_more = self.case.has_additional_request
            if has_more is None:
                has_more = parse_yes_no_for_question(
                    more_answer, "還有其他需要協助的嗎"
                )
            while has_more is None:
                with self._case_lock:
                    self.case.has_additional_request = None
                more_answer = self._ask_and_extract(
                    "請問是否還有其他需要中心協助的事項？"
                )
                has_more = self.case.has_additional_request
                if has_more is None:
                    has_more = parse_yes_no_for_question(
                        more_answer, "是否還有其他需要中心協助"
                    )
            if has_more is False:
                with self._case_lock:
                    for key, value in previous_task.items():
                        setattr(self.case, key, value)
                    self.case.has_additional_request = False
                    self.case.result = last_result
                self._update_case_summary()
                self._say("好的，已為您記錄，謝謝回報。")
                self._set_stage("completed")
                self._notify_case_update()
                self._emit({"type": "stopped", "result": last_result})
                return
            need_answer = more_answer
            if self._detect_report_request_type(need_answer) is None:
                self._set_stage("局內回報_need")
                need_answer = self._ask_and_extract("請問還需要中心協助什麼？")

    def _do_main_classify(self, text: str):
        """調用主分類器，返回 (main_category, confidence)。"""
        if self._main_clf is not None:
            try:
                result = self._main_clf.predict(text)
                return result["main_category"], result["main_conf"]
            except Exception as e:
                self._debug_print("main_clf_error", e)
        # 無分類器時回退：依關鍵詞粗略判斷（較短/較泛的「救」須放在緊急救援之後）
        if any(kw in text for kw in ("火", "火災", "著火", "燒")):
            return "火警", 0.9
        if any(
            kw in text
            for kw in (
                "緊急救援", "電梯", "受困", "瓦斯漏氣", "瓦斯外洩",
                "跳樓", "車禍救助",
            )
        ):
            return "緊急救援", 0.9
        if any(kw in text for kw in ("救護", "救人", "救", "急救", "昏倒", "受傷", "病")):
            return "救護", 0.9
        return "救護", 0.5  # 預設

    def _do_sub_classify(self, text: str, main_cat: str):
        """
        救護子類判定：高貼合關鍵詞直判優先，未命中再走子分類器。

        Returns
        -------
        (sub_category, confidence, source)
            source: "keyword" | "classifier" | None
        """
        if main_cat == "救護":
            kw_cat, kw_conf, kw = match_rescue_subcategory(text)
            if kw_cat:
                self._debug_print(
                    "sub_keyword_hit",
                    {"sub_category": kw_cat, "keyword": kw, "conf": kw_conf},
                )
                return kw_cat, kw_conf, "keyword"

        if self._sub_clf is not None:
            try:
                result = self._sub_clf.predict(text, main_cat)
                if result:
                    return result.final_label, result.classifier_conf, "classifier"
            except Exception as e:
                self._debug_print("sub_clf_error", e)
        return None, None, None

    # ── 共用：地址詢問 + 覆頌確認 ─────────────────────────────────────────────

    def _set_address_validation(
        self,
        status: str,
        *,
        office_name: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> None:
        with self._case_lock:
            self.case.address_validation_status = status
            self.case.jurisdiction_office = office_name
            self.case.address_error_reason = reason
        self._notify_case_update()

    def _mark_address_failure(self, reason: str) -> None:
        """向前端发布地址错误标签，并统一转人工。"""
        with self._case_lock:
            self.case.address_confirmed = False
            self.case.address_suspect_error = True
            self.case.address_error_reason = reason
            if self.case.address_validation_status not in {"invalid", "error"}:
                self.case.address_validation_status = "invalid"
        self._notify_case_update()
        self._say(
            "無法確認事發地址，請不要掛斷電話，我立即為您轉接專人。"
        )
        raise TransferToHumanError(reason, result="human_transfer")

    def _reset_location_for_correction(self) -> None:
        """清除旧地点，避免完整重报被 merge_address 保留为旧值。"""
        with self._case_lock:
            self.case.address = None
            self.case.address_confirmed = None
            self.case.location_type = None
            self.case.address_district = None
            self.case.intersection_road1 = None
            self.case.intersection_road2 = None
            self.case.highway_name = None
            self.case.highway_direction = None
            self.case.highway_kilometer = None
            self.case.address_validation_status = "pending"
            self.case.jurisdiction_office = None
            self.case.address_error_reason = None

    def _validate_location_once(
        self,
        *,
        allow_component_reasks: bool,
    ) -> tuple[bool, str, bool]:
        """
        完成并校验当前地点。

        返回 (成功, 原因, 是否允许完整重报一次)。组件补问本身最多两次，
        用尽后不再额外重报；外部名单/API 校验失败可完整重报一次。
        """
        location_type = self._refresh_location_type()
        if not location_type:
            return False, "無法判斷地址類別", False

        self._set_address_validation("pending")

        if location_type == "address":
            district = extract_address_district(self.case.address or "")
            if district:
                with self._case_lock:
                    self.case.address_district = district
            if not self.case.address_district and allow_component_reasks:
                for _ in range(2):
                    self._set_stage("location_district_reask")
                    self._ask_and_extract("請告訴我是那一區？")
                    if self.case.address_district:
                        break
            if not self.case.address_district:
                return False, "地址缺少行政區", False
            if self.case.address_district not in (self.case.address or ""):
                with self._case_lock:
                    self.case.address = (
                        f"{self.case.address_district}{self.case.address or ''}"
                    )
            # 報警人未報縣市 → 補上預設市級單位（預設新北市）
            with self._case_lock:
                self.case.address = ensure_city_prefix(self.case.address or "")

            self._set_stage("location_validating")
            result = query_jurisdiction(self.case.address or "")
            if result.valid is True:
                self._set_address_validation(
                    "valid", office_name=result.office_name
                )
                return True, "", False
            if result.valid is False:
                self._set_address_validation(
                    "invalid", reason="地址查無管轄單位"
                )
                return False, "地址查無管轄單位", True
            self._set_address_validation(
                "error", reason="地址轄區 API 無法使用"
            )
            return False, "地址轄區 API 無法使用", True

        if location_type == "intersection":
            self._apply_location_rules(self.case.address or "")
            if (
                not self.case.intersection_road2
                and allow_component_reasks
            ):
                for _ in range(2):
                    road1 = self.case.intersection_road1 or "這條路"
                    self._set_stage("location_intersection_reask")
                    self._ask_and_extract(
                        f"{road1}與哪條路或巷的路口？"
                    )
                    if self.case.intersection_road2:
                        break
            rebuilt = build_intersection_address(
                self.case.address_district,
                self.case.intersection_road1,
                self.case.intersection_road2,
            )
            if not rebuilt:
                return False, "交叉路口缺少第二條道路", False
            with self._case_lock:
                self.case.address = rebuilt
            self._set_address_validation("valid")
            return True, "", False

        if location_type == "highway":
            self._apply_location_rules(self.case.address or "")
            complete = build_highway_address(
                self.case.highway_name,
                self.case.highway_direction,
                self.case.highway_kilometer,
            )
            if not complete and allow_component_reasks:
                for _ in range(2):
                    self._set_stage("location_highway_reask")
                    self._ask_and_extract(
                        "請問在哪一條高速公路、南向或北向，以及幾公里處？"
                    )
                    complete = build_highway_address(
                        self.case.highway_name,
                        self.case.highway_direction,
                        self.case.highway_kilometer,
                    )
                    if complete:
                        break
            if not complete:
                return False, "高速公路地點資訊不完整", False
            with self._case_lock:
                self.case.address = complete
            self._set_address_validation("valid")
            return True, "", False

        if location_type == "landmark":
            self._set_stage("location_validating")
            try:
                valid = validate_landmark(self.case.address or "")
            except Exception as exc:
                self._debug_print("landmark_validation_error", exc)
                self._set_address_validation(
                    "error", reason="地標資料表無法讀取"
                )
                return False, "地標資料表無法讀取", True
            if valid:
                self._set_address_validation("valid")
                return True, "", False
            self._set_address_validation("invalid", reason="地標不在資料表中")
            return False, "地標不在資料表中", True

        if location_type == "mrt":
            self._set_stage("location_validating")
            try:
                valid = validate_mrt(self.case.address or "")
            except Exception as exc:
                self._debug_print("mrt_validation_error", exc)
                self._set_address_validation(
                    "error", reason="捷運車站資料無法讀取"
                )
                return False, "捷運車站資料無法讀取", True
            if valid:
                self._set_address_validation("valid")
                return True, "", False
            self._set_address_validation("invalid", reason="查無捷運車站")
            return False, "查無捷運車站", True

        return False, "不支援的地址類別", False

    def _complete_and_validate_location(self) -> tuple[bool, str]:
        ok, reason, retryable = self._validate_location_once(
            allow_component_reasks=True
        )
        if ok or not retryable:
            return ok, reason

        self._set_stage("location_validation_reask")
        self._reset_location_for_correction()
        self._notify_case_update()
        self._ask_and_extract("地址無法確認，請重新提供完整正確的事發地點。")
        if not is_usable_address(self.case.address):
            return False, "重新提供的地址仍無法抽取"
        ok, reason, _ = self._validate_location_once(
            allow_component_reasks=False
        )
        return ok, reason

    def _is_outdoor_case(self) -> bool:
        """已知在戶外地點（路口/高速公路，或報警人講過巷口、路邊、天橋等）。"""
        if self.case.location_type in {"intersection", "highway"}:
            return True
        blob = f"{self.case.full_caller_text()}{self.case.address or ''}"
        return has_outdoor_location_hint(blob)

    def _run_address_flow(
        self,
        *,
        stage_ask: str,
        stage_confirm: str,
        dispatch_line: str,
        ask_questions: tuple[str, ...],
    ) -> None:
        """
        询问地址 → 分类补问 → 数据/API 校验 → 覆诵确认。

        所有提问均经 _ask_and_extract，抽取失败或校验失败最多再问一遍；
        最终失败时发布地址错误标签并转人工。
        """
        self._set_stage(stage_ask)

        self._ensure_address_from_caller_history()
        self._notify_case_update()

        addr_asks = 0
        ask_max = min(2, len(ask_questions))
        while not is_usable_address(self.case.address) and addr_asks < ask_max:
            addr_q = ask_questions[addr_asks]
            # 報警人已表明在巷口/路邊/天橋等戶外地點 → 不再追問幾樓
            if self._is_outdoor_case():
                addr_q = strip_floor_question(addr_q)
            addr_asks += 1
            self._debug_print("address_ask", {"n": addr_asks, "q": addr_q})
            answer = self._ask_and_extract(addr_q)
            self._clear_unusable_address()
            if not is_usable_address(self.case.address):
                self._try_extract_address(answer)
                self._clear_unusable_address()
            self._notify_case_update()

        if not is_usable_address(self.case.address):
            self._debug_print("address_ask_exhausted", {"asks": addr_asks})
            self._mark_address_failure("地址抽取失敗")

        if addr_asks == 0:
            self._debug_print("skip_address_ask", self.case.address)

        valid, reason = self._complete_and_validate_location()
        if not valid:
            self._mark_address_failure(reason or "地址校驗失敗")

        self._set_stage(stage_confirm)
        for _confirm_attempt in range(2):
            current_addr_display = self.case.display_address()
            confirm_q = f"確定是{current_addr_display}這個地址嗎？"
            confirm_text = self._ask_and_extract(confirm_q)

            confirmed = parse_yes_no_for_question(confirm_q, confirm_text)
            new_address = None
            addr_update = self._resolve_address_correction(
                confirm_text, confirm_q, current_addr_display,
            )
            if self._llm:
                try:
                    confirm_result = self._llm.extract_confirmation(
                        question=confirm_q,
                        caller_text=confirm_text,
                        current_address=current_addr_display,
                    )
                    self._debug_print("extract_confirmation", confirm_result)
                    if confirm_result.get("confirmed") is not None:
                        confirmed = confirm_result.get("confirmed")
                    new_address = confirm_result.get("new_address")
                except Exception as exc:
                    self._debug_print("extract_confirmation_error", exc)

            corrected = addr_update or new_address
            if is_usable_address(corrected):
                with self._case_lock:
                    self.case.address = corrected
                    self.case.address_confirmed = None
                    self.case.location_type = None
                    self.case.address_district = None
                    self.case.intersection_road1 = None
                    self.case.intersection_road2 = None
                    self.case.highway_name = None
                    self.case.highway_direction = None
                    self.case.highway_kilometer = None
                    self.case.address_validation_status = "pending"
                    self.case.jurisdiction_office = None
                self._apply_location_rules(corrected or "")
                valid, reason = self._complete_and_validate_location()
                if not valid:
                    self._mark_address_failure(reason or "更正地址校驗失敗")
                continue

            if confirmed is True:
                with self._case_lock:
                    self.case.address_confirmed = True
                    self.case.address_suspect_error = False
                    self.case.address_error_reason = None
                self._notify_case_update()
                self._say(dispatch_line)
                return

        self._mark_address_failure("報警人未能明確確認地址")

    # ── 救護 handler ──────────────────────────────────────────────────────────

    def _run_救護(self) -> None:
        """救護類別完整對話 SOP。"""

        # ════════════════════════════════════════════════════════
        # 階段 1：詢問地址 → 複讀確認 → 告知救護車已派出
        # ════════════════════════════════════════════════════════
        self._run_address_flow(
            stage_ask="救護_location",
            stage_confirm="救護_location_confirm",
            dispatch_line="已確認地址，救護車已派出了喔。",
            ask_questions=(
                "請先告訴我地址？幾樓？",
                "請問事發地址在哪裡？幾樓？",
            ),
        )

        # ════════════════════════════════════════════════════════
        # 此時：收集所有輪報警人文本 → 關鍵詞直判 / 次分類器
        # ════════════════════════════════════════════════════════
        all_caller_text = self.case.full_caller_text()
        sub_cat, sub_conf, sub_source = self._do_sub_classify(all_caller_text, "救護")

        # 關鍵詞未命中且分類器置信度低於 70% → 最多追問兩遍「請問發生了什麼事」
        # 每次分類結果都保留，最終取置信度最高者再進入子類流程
        # （關鍵詞命中 conf=1.0，不會進入此分支）
        _SUB_CONF_THRESHOLD = 0.7
        _MAX_SUB_REASK = 2
        candidates: List[tuple] = []
        if sub_cat is not None:
            candidates.append((sub_cat, sub_conf if sub_conf is not None else 0.0, sub_source))

        for _reask_i in range(_MAX_SUB_REASK):
            if sub_source == "keyword":
                break
            if sub_conf is not None and sub_conf >= _SUB_CONF_THRESHOLD:
                break

            self._ask_and_extract("請問發生了什麼事？")
            all_caller_text = self.case.full_caller_text()
            sub_cat, sub_conf, sub_source = self._do_sub_classify(
                all_caller_text, "救護"
            )
            if sub_cat is not None:
                candidates.append(
                    (sub_cat, sub_conf if sub_conf is not None else 0.0, sub_source)
                )

        if candidates:
            sub_cat, sub_conf, sub_source = max(candidates, key=lambda x: x[1])
            self._debug_print(
                "sub_classify_best",
                {
                    "chosen": {"sub": sub_cat, "conf": sub_conf, "source": sub_source},
                    "candidates": [
                        {"sub": c, "conf": conf, "source": src}
                        for c, conf, src in candidates
                    ],
                },
            )

        with self._case_lock:
            self.case.sub_category = sub_cat
            self.case.sub_conf     = sub_conf
        self._emit({
            "type":       "classification",
            "main":       self.case.main_category,
            "main_conf":  self.case.main_conf,
            "sub":        sub_cat,
            "sub_conf":   sub_conf,
            "sub_source": sub_source,
        })
        self._notify_case_update()
        self._set_stage("救護_sub_classified")

        # ── 進入子類前：關鍵欄位若仍空，對最近一則回答再跑一次 LLM 全欄位抽取 ─
        if not self._is_field_filled("incident_description"):
            pairs = self._iter_caller_qa_pairs()
            if pairs:
                last_q, last_a = pairs[-1]
                self._extract_all_fields_from_reply(last_a, question=last_q)
                self._notify_case_update()

        # ── 取得次類別 handler ────────────────────────────────────────────────
        handler = get_handler(sub_cat)

        if hasattr(handler, "run_subtype_flow"):
            # ════════════════════════════════════════════════════════
            # 次類別專屬完整問題流程（替代通用生命征象+患者資訊問答）
            # ════════════════════════════════════════════════════════
            handler.run_subtype_flow(self)
        else:
            # ════════════════════════════════════════════════════════
            # 通用流程：前置問題 → 生命征象 → 後置問題 → 患者資訊
            # ════════════════════════════════════════════════════════
            handler.run_pre_vital(self)

            # 階段 2：確認生命征象（3 問，已有值則跳過）
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

            # 生命征象後次類別額外問題（如：一般受傷的傷因/部位/TOCC）
            handler.run_post_vital(self)

            # 階段 3：詢問關鍵要素（已有值則跳過）
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
        # 階段 4：案情摘要回填（不對報案人複誦，僅更新欄位供 UI 顯示）
        # ════════════════════════════════════════════════════════
        self._set_stage("救護_summary_confirm")
        self._update_case_summary()
        self._notify_case_update()

        # ════════════════════════════════════════════════════════
        # 階段 5：報案人訊息 + 流程結束（委派給次類別 handler）
        # ════════════════════════════════════════════════════════
        handler.collect_caller_info(self)

    # ── 火警 handler ──────────────────────────────────────────────────────────

    def _run_火警(self) -> None:
        """火警初期研判、四類燃燒標的分流與結案流程。"""
        from handlers.火警通用 import HuoJingGenericHandler

        # ════════════════════════════════════════════════════════
        # 階段 1：詢問地址（首問同救護；不可用再追問建物/路燈）→ 覆頌 → 派車
        # ════════════════════════════════════════════════════════
        self._run_address_flow(
            stage_ask="火警_location",
            stage_confirm="火警_location_confirm",
            dispatch_line="已確認地址，消防車已派出了喔。",
            ask_questions=(
                "請先告訴我地址？幾樓？",
                "地址在哪裡呢？附近有明顯建物或標示嗎？",
                "有路燈或電線桿嗎？給我路燈或電線桿上面的編號、大約靠近哪邊呢？",
            ),
        )

        # ════════════════════════════════════════════════════════
        # 階段 2：初期三題 + 四類燃燒標的分支
        # ════════════════════════════════════════════════════════
        handler = HuoJingGenericHandler()
        handler.run_generic_flow(self)

        # ════════════════════════════════════════════════════════
        # 階段 3：案情摘要回填
        # ════════════════════════════════════════════════════════
        self._set_stage("火警_summary_confirm")
        self._update_case_summary()
        self._notify_case_update()

        # ════════════════════════════════════════════════════════
        # 階段 4：回撥電話、稱呼確認 + 流程結束
        # ════════════════════════════════════════════════════════
        handler.collect_caller_info(self)

    # ── 緊急救援 handler ──────────────────────────────────────────────────────

    def _run_緊急救援(self) -> None:
        """緊急救援大類通用對話 SOP（暫不做子類識別）。"""
        from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler

        # ════════════════════════════════════════════════════════
        # 階段 1：詢問地址（首問同救護；不可用再追問建物/路燈）→ 覆頌 → 派員
        # ════════════════════════════════════════════════════════
        self._run_address_flow(
            stage_ask="緊急救援_location",
            stage_confirm="緊急救援_location_confirm",
            dispatch_line="已確認地址，救援人員已派出了喔。",
            ask_questions=(
                "請先告訴我地址？幾層？",
                "地址在哪裡呢？附近有明顯建物或標示嗎？",
                "有路燈或電線桿嗎？給我路燈或電線桿上面的編號、大約靠近哪邊呢？",
            ),
        )

        # ════════════════════════════════════════════════════════
        # 階段 2：詢問發生什麼事情
        # ════════════════════════════════════════════════════════
        handler = JinJiJiuYuanGenericHandler()
        handler.run_generic_flow(self)

        # ════════════════════════════════════════════════════════
        # 階段 3：案情摘要回填
        # ════════════════════════════════════════════════════════
        self._set_stage("緊急救援_summary_confirm")
        self._update_case_summary()
        self._notify_case_update()

        # ════════════════════════════════════════════════════════
        # 階段 4：報案人訊息 + 流程結束
        # ════════════════════════════════════════════════════════
        handler.collect_caller_info(self)


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
