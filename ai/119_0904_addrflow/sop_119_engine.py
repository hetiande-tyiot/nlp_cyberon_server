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

import os
import queue
import random
import re
import sys
import threading
import traceback
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from address_mapper_119 import get_location_mapper
from case_info_119 import CaseInfo119
from handlers import get_handler, sop_slots_for, SHARED_SEMANTIC_SLOTS
from important_tags_119 import match_important_tags, merge_important_tags
from llm_extractor_119 import LLMExtractor119, build_fallback_summary
from fuzzy_match_log_119 import (
    KIND_DISTRICT,
    KIND_LANDMARK,
    OUTCOME_CONFIRMED,
    OUTCOME_DENIED,
    OUTCOME_UNCONFIRMED,
    record_fuzzy_match,
)
from address_hint_119 import (
    ASK_DISTRICT,
    build_landmark_confirm_question,
    is_uncertain_answer,
    normalized_address_from_hint,
    phonetic_correction_note,
    parse_landmark_hint,
    ASK_FLOOR,
    ASK_NUMBER,
    ASK_ROAD,
    GENERIC_ADDRESS_RETRY,
    GUIDED_OPENING,
    build_hint_question,
    floor_suppress_reason,
    parse_address_hint,
)
from location_validation_119 import (
    addrcheck_failure_reason,
    load_landmark_names,
    load_mrt_location_names,
    query_jurisdiction,
    verify_address_detail,
    verify_address_status,
)
from sop_utils_119 import (
    address_ask_should_include_floor,
    build_address_ask_questions,
    dropped_address_details,
    is_bare_district_or_city,
    landmark_layer_from_hint,
    build_highway_address,
    build_intersection_address,
    build_street_address,
    classify_location_type,
    clean_address_fragment,
    compose_street_address,
    extract_address_hint,
    extract_address_district,
    extract_address_number,
    extract_address_road,
    extract_highway_components,
    extract_intersection_roads,
    extract_lane_alley,
    extract_road_section,
    extract_street_address_components,
    has_complete_street_address,
    is_street_address,
    is_usable_address,
    extract_patient_info_hint,
    extract_pregnancy_info_hint,
    extract_vital_signs_hint,
    looks_like_address_response,
    looks_like_pregnancy_count,
    merge_address,
    parse_vital_slot,
    parse_yes_no,
    parse_yes_no_for_question,
    road_has_lane,
    road_has_section,
    strip_district_prefix_from_road,
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

_RESCUE_SLOT_MEANINGS: Dict[str, str] = {
    "incident_description": "現場發生什麼事",
    "consciousness": "是否有意識",
    "breathing": "是否有呼吸",
    "abdomen_rise": "肚子是否有起伏",
    "patient_count": "傷病患人數",
    "patient_gender": "患者性別",
    "patient_age": "患者年齡",
    "current_condition": "目前狀況（依子類語義：傷情/現場安全/酒精/炭盆/繩子等）",
    "medical_history": "病史或現場陪同（依子類語義）",
    "collapse_cause": "路倒原因",
    "injury_cause": "受傷原因/機制",
    "injury_location": "受傷部位",
    "injury_severity": "傷勢",
    "tocc": "TOCC 旅遊職業接觸群聚史",
    "ingested_substance": "服藥種類與數量",
    "pregnancy_week": "胎次與孕週",
    "due_date": "預產期",
    "multiple_pregnancy": "單或雙胞胎",
    "water_broken_bleeding": "破水或出血",
    "contractions": "宮縮情況",
    "prenatal_history": "產檢異常史",
    "prenatal_clinic": "產檢醫院",
}


class TransferToHumanError(Exception):
    """觸發時立即中止 handler 並轉接真人接線員。"""

    def __init__(self, reason: str = "transfer", *, result: str = "human_transfer"):
        super().__init__(reason)
        self.reason = reason
        # result: "ohca_transfer" | "human_transfer"
        self.result = result


class FlowAbortedError(Exception):
    """操作員主動結束流程時拋出，優雅中止 SOP。"""


class SubCategorySwitched(Exception):
    """子類/垂片在對話中途切換，需中斷當前 handler 並重入新流程。"""

    def __init__(self, old: Optional[str], new: str):
        super().__init__(f"{old} -> {new}")
        self.old = old
        self.new = new


# ─── SOP 引擎 ─────────────────────────────────────────────────────────────────

# addrCheck 明確否決過的候選不得復活。最終挑選只比「哪個字多」，
# 而 LLM 整合出來的地址往往最長，被 API 否決後仍會在最後被撿回來。
# api_status 為 None 是「還沒驗過」，仍可復活（09-02 那通就是這種）。
_API_REJECTED_REASONS = frozenset(
    {"not_found", "road_only", "ambiguous", "invalid_format"}
)


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
        self._bridged     = False
        self._sub_reclassify_enabled = False
        # 地址流程跑完即上鎖，之後不再讓地標/捷運/路口關鍵字覆寫已成立的地點
        self._address_locked = False
        # 有沒有真的對報案人說過「車已派出」。轉真人的話術要看這個，
        # 不能寫死——2026-09-06 04:46 實測，申訴案沒問到地址、
        # 沒派任何車，卻對報案人說「救護車已派出」。
        self._dispatch_announced = False
        self._dropped_details_asked = False
        self._probed_result = None
        # 行政區若是臺語音近「猜」出來的，記 (原片段, 猜測值)，
        # 必須讓報案人覆誦確認；未確認前不得當成已知地址交給派遣或真人。
        self._district_guess: Optional[tuple] = None
        self._district_guess_score: Optional[float] = None
        # 同一次猜測只取樣一次，否則「否認 → 還原」會重複計數、污染統計。
        self._district_guess_sampled = False
        # 街路映射表預設不套用，查無才開啟
        # 街路映射表（map_street.json）的套用時機：
        #   defer（預設）先拿報案人原話問 addrCheck，查無才套表並自動重查
        #   eager        沿用舊行為，驗證前就先套表
        # 查無時是「套表 → 自動重查 API」，不會多問報案人。226 通離線重放
        # 顯示 defer 的提問平均由 4.30 降到 4.07（變少 53 通、變多 8 通）。
        # 若 STT 品質明顯變差、defer 反而拖長通話，設 STREET_MAPPING_MODE=eager
        # 即可切回舊行為，不必改程式。
        self._street_mapping_enabled = (
            os.getenv("STREET_MAPPING_MODE", "defer").strip().lower() == "eager"
        )
        # 最後一次 addrCheck hint 的解析結果，供引導式判斷哪些元件已獲確認
        self._last_hint_advice = None
        # 地址候選累積：重問不清空，失敗時整包交給受理員。
        # 每筆 {"text","source","turn","api_status","api_hint"}
        self._address_candidates: List[Dict[str, Any]] = []
        # 地址流程的總提問預算。五步流程各階段都會問，不設總上限的話
        # 最壞情況會問二十幾次——急案不能這樣拖。用完就直接進第五步。
        self._address_asks_used = 0

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _say(self, text: str) -> None:
        if self._bridged:
            return
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
        if self.case.main_category == "火警":
            self._refresh_fire_subtype_from_bert()
        self._sync_patient_context()

    def _sync_patient_context(self) -> None:
        """
        從通話歷史以規則補強患者語境（性別稱謂、報案人是否即患者）。
        僅在對應欄位尚未填入時寫入。
        """
        from sop_utils_119 import (
            infer_caller_is_patient,
            infer_patient_gender_from_honorific,
        )

        parts = [self.case.full_caller_text()]
        if self.case.incident_description:
            parts.append(self.case.incident_description)
        full_text = "\n".join(p for p in parts if p)

        with self._case_lock:
            if not self.case.patient_gender and full_text:
                gender = infer_patient_gender_from_honorific(full_text)
                if gender:
                    self.case.patient_gender = gender

            if self.case.caller_is_patient is None and full_text:
                is_patient = infer_caller_is_patient(full_text)
                if is_patient is not None:
                    self.case.caller_is_patient = is_patient

        self._notify_case_update()

    def _check_ohca_and_transfer(self, vital_val: Optional[bool], slot: str) -> None:
        """任一生命征象非 True → OHCA 轉人工。"""
        if vital_val is not True:
            with self._case_lock:
                self.case.is_ohca = True
            self._notify_case_update()
            if self._bridged:
                return
            self._say(
                "救護車已派出，請不要掛斷電話，我立即為您轉接專人。"
                if self._dispatch_announced
                else "請不要掛斷電話，我立即為您轉接專人。"
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
        _BOOL_FIELDS = {"consciousness", "breathing", "abdomen_rise", "caller_is_patient"}
        _RESCUE_FIELDS = {
            "consciousness",
            "breathing",
            "abdomen_rise",
            "patient_count",
            "patient_gender",
            "patient_age",
            "caller_is_patient",
            "current_condition",
            "medical_history",
            "collapse_cause",
            "injury_cause",
            "injury_location",
            "injury_severity",
            "tocc",
            "ingested_substance",
            "blood_glucose",
            "blood_pressure",
            "seizure_info",
            "pregnancy_week",
            "due_date",
            "multiple_pregnancy",
            "water_broken_bleeding",
            "contractions",
            "prenatal_history",
            "prenatal_clinic",
        }
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
            "fire_incident_type",
            "building_type_code",
            "has_flame",
            "smoke_color_code",
            "has_explosion",
            "spread_risk",
            "people_trapped_code",
            "building_floors_code",
            "fire_floor_code",
            "building_structure",
            "burn_area_code",
            "access_water_info",
            "non_building_fire",
            "vehicle_wildfire_code",
            "minor_fire_code",
        }

        from fire_tab_map_119 import FIRE_IDENTITY_CODE_FIELDS

        identity_updated = False
        for key, val in extracted.items():
            if val is None:
                continue
            current = getattr(self.case, key, None)

            # 專屬欄位只允許在對應案件流程寫入，避免 LLM 跨類型污染 JSON。
            if key in _RESCUE_FIELDS and self.case.main_category != "救護":
                continue
            if (
                key == "incident_description"
                and self.case.main_category not in {"救護", "緊急救援"}
            ):
                continue
            if key in _FIRE_OVERWRITE_FIELDS and self.case.main_category != "火警":
                continue

            # 胎數不是傷病患人數（「三胞胎」屬 multiple_pregnancy）。
            if key == "patient_count" and looks_like_pregnancy_count(val):
                self._debug_print("patient_count_rejected", val)
                continue
            if (
                key in _INTERNAL_OVERWRITE_FIELDS
                and self.case.call_type != "局內回報"
            ):
                continue

            if key == "ImportantCase":
                # 通用重要性允許依本輪明確新證據升級或降級。
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
                # 通話模式由主流程的確定性判斷建立；LLM 只可維持既有局內回報。
                if self.case.call_type == "局內回報" and val == "局內回報":
                    self.case.call_type = val
                continue

            if key in _INTERNAL_OVERWRITE_FIELDS:
                # 局內回報需要接受覆誦更正，也要能處理同一通電話的下一項需求。
                setattr(self.case, key, val)
                continue

            if key in _FIRE_OVERWRITE_FIELDS:
                # 火災資訊以本輪明確新證據為準，允許報案人後續補充或更正。
                setattr(self.case, key, val)
                if key in FIRE_IDENTITY_CODE_FIELDS:
                    identity_updated = True
                if key == "people_trapped_code" and val in (0, 1):
                    self.case.people_trapped = bool(val)
                elif key == "people_trapped" and isinstance(val, bool):
                    self.case.people_trapped_code = 1 if val else 0
                elif key == "spread_risk" and val in (0, 1):
                    self.case.fire_spread = bool(val)
                elif key == "fire_spread" and isinstance(val, bool):
                    self.case.spread_risk = 1 if val else 0
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
                # 地址流程結束後不再改寫已成立的地點。規則路徑本來就有這道
                # 檢查（_apply_location_rules），LLM 路徑漏了——派遣後的閒聊
                # 一樣會進 extract_slots，照樣改得動 case.address。
                if self._address_locked and is_usable_address(current):
                    continue
                if self._is_same_place_as_current(new_addr):
                    continue
                if not is_usable_address(current):
                    self.case.address = new_addr
                    self._adopt_llm_location_type(extracted)
                    continue
                merged = merge_address(str(current), new_addr)
                if is_usable_address(merged) and merged != current:
                    self.case.address = merged
                    if merged == new_addr:
                        # 舊地址被整個換掉（殘缺片段被地標名取代），
                        # 型別要跟著走，否則內容是地標、type 卻還是 address，
                        # 拿去當門牌驗證必然查無。
                        self._adopt_llm_location_type(extracted)
                continue

            # 其他字串欄位：空欄位才填入
            if not current:
                setattr(self.case, key, val)

        if identity_updated and self.case.main_category == "火警":
            self._sync_fire_sub_category_from_identity_codes()

    def _is_same_place_as_current(self, new_addr: str) -> bool:
        """新抽到的地址是不是「同一個地方的另一種講法」。

        2026-09-07 17:04 實測：報案人說「永和區永鎮路128號」，addrCheck 回
            「永鎮路128號」查無此路名，已依讀音修正為「永貞路128號」
        流程採用了正規化後的永貞路、覆誦也唸永貞路、報案人答「對。是的。」——
        然後**逐輪 LLM 從原話又抽一次「永鎮路」把它蓋回去**，存檔存了一條
        不存在的路。派遣資料就是錯的。

        判準是拿映射表把新地址正規化，看是不是就是現在這個。報案人真的改
        地址時兩者不會相等，所以不會擋掉正常的更正。
        """
        current = (self.case.address or "").strip()
        if not current or not new_addr:
            return False
        if new_addr.strip() == current:
            return True
        try:
            mapped = get_location_mapper().map_location(new_addr)
        except Exception as exc:
            self._debug_print("same_place_check_error", exc)
            return False
        return bool(mapped) and mapped.strip() == current

    def _adopt_llm_location_type(self, extracted: Dict[str, Any]) -> None:
        """採用 LLM 的地址時，型別要一起採用。

        `location_type` 走的是「空欄位才填入」的字串規則，所以一旦
        case.location_type 已經是 address，之後 LLM 說這是地標也改不動。
        地址內容換成地標名、type 卻停在 address，就會拿地標去做門牌驗證。
        """
        new_type = extracted.get("location_type")
        if new_type in {"address", "intersection", "landmark", "highway", "mrt"}:
            self.case.location_type = new_type

    def _sync_fire_sub_category_from_identity_codes(self) -> None:
        """身份編號寫入後反寫 sub_category。"""
        from fire_tab_map_119 import subtype_name_from_identity_codes

        name = subtype_name_from_identity_codes(self.case)
        if name and name != self.case.sub_category:
            self.case.sub_category = name

    def _apply_location_rules(self, caller_text: str) -> None:
        """以确定性规则补强本轮地点组件，并重组可显示地址。"""
        text = (caller_text or "").strip()
        if not text:
            return

        district = extract_address_district(text)
        street_components = extract_street_address_components(text)
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
                # 地址流程結束後，已成立的地點不再被後續對話裡的地標／捷運／
                # 路口字樣覆寫（曾發生「在哪裡產檢？」答「國泰醫院」蓋掉事發
                # 門牌、救護車已派遣仍改到醫院名的情況）。
                if self._address_locked and is_usable_address(self.case.address):
                    pass
                else:
                    self.case.location_type = explicit_type
                    if explicit_candidate:
                        self.case.address = explicit_candidate
            elif (
                explicit_type == "address"
                and self.case.location_type in {None, "address"}
                # 地址流程結束後不再讓後續對話改寫已成立的門牌。
                # 2026-09-04 實測：報案人講「我是路人，所以我沒有開車」
                # 被抽成「我是路人路」、「不知道他躺在路邊」被抽成
                # 「不知道他躺在路」，覆蓋掉已派遣的正確地址。
                and not (
                    self._address_locked
                    and is_usable_address(self.case.address)
                )
            ):
                self.case.location_type = "address"
                for key, value in street_components.items():
                    setattr(self.case, key, value)
                # 樓層來源：現有地址優先，沒有才從本輪原話補。
                # case.address 可能是 extract_address_hint 截斷過的殘值
                #（「板橋區南亞南路2段15號3樓」→「板橋區南亞南路2」），
                # 只看它會讓樓層在組地址時就消失（既有行為，0903 亦同）。
                floor_source = self.case.address or ""
                if not self._FLOOR_IN_TEXT_RE.search(floor_source):
                    floor_source = f"{floor_source}{text or ''}"
                partial_address = compose_street_address(
                    self.case.address_district,
                    self.case.address_road,
                    self.case.address_number,
                    existing=floor_source,
                )
                if partial_address:
                    self.case.address = partial_address

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
            # 規則判不出來時**不再預設 address**。原本落到 address 就會用
            # type=House 去查，API 把「板橋國小」切成「國小」找路名而查無；
            # 交給 addrCheck 自動判斷（_probe_location_type）反而全中。
            return self.case.location_type

    _LOCATION_MAP_FIELDS = (
        "address",
        "address_district",
        "address_road",
        "intersection_road1",
        "intersection_road2",
        "highway_name",
    )

    def _normalize_location_fields(self, *, include_street: bool = None) -> None:
        """對地址及相關組件執行三輪映射（行政區 → 街路 → 其他）。

        街路映射預設延後：先拿報案人原話問 addrCheck，查無才套 map_street。
        見 `_street_mapping_enabled`。
        """
        mapper = get_location_mapper()
        if mapper is None:
            return
        if include_street is None:
            include_street = self._street_mapping_enabled
        guess = None
        with self._case_lock:
            for field in self._LOCATION_MAP_FIELDS:
                value = getattr(self.case, field, None)
                if not value:
                    continue
                mapped, field_guess = mapper.map_location_detail(
                    value, include_street=include_street
                )
                if field_guess and guess is None:
                    guess = field_guess
                if mapped and mapped != value:
                    setattr(self.case, field, mapped)
        if guess:
            # mapper 回 (原片段, 猜出的區, 分數)；引擎其餘地方只用前兩項。
            self._district_guess = tuple(guess[:2])
            self._district_guess_score = guess[2] if len(guess) > 2 else None
            self._district_guess_sampled = False
            self._debug_print("district_fuzzy_guess", guess)

    def _update_street_address_from_input(self, caller_text: str) -> None:
        """以本輪 LLM + 規則元件增量更新門牌地址。"""
        if self.case.location_type != "address":
            return

        current_address = self.case.address or ""
        incoming: Dict[str, str] = {}

        component_extractor = getattr(
            self._llm,
            "extract_address_components",
            None,
        )
        if callable(component_extractor):
            try:
                llm_result = component_extractor(
                    caller_text,
                    current_address=current_address,
                )
                self._debug_print("extract_address_components", llm_result)
                llm_address = clean_address_fragment(
                    str(llm_result.get("address") or "")
                )
                if llm_address:
                    incoming.update(
                        extract_street_address_components(llm_address)
                    )
                district = extract_address_district(
                    str(llm_result.get("address_district") or "")
                )
                road = extract_address_road(
                    str(llm_result.get("address_road") or "")
                )
                number = extract_address_number(
                    str(llm_result.get("address_number") or "")
                )
                if district:
                    incoming["address_district"] = district
                if road:
                    incoming["address_road"] = road
                if number:
                    incoming["address_number"] = number
            except Exception as exc:
                self._debug_print("extract_address_components_error", exc)

        # 明確規則結果優先，並作為 LLM 不可用時的備援。
        incoming.update(extract_street_address_components(caller_text))

        with self._case_lock:
            existing = extract_street_address_components(
                self.case.address or ""
            )
            district = (
                incoming.get("address_district")
                or self.case.address_district
                or existing.get("address_district")
            )
            road = (
                incoming.get("address_road")
                or self.case.address_road
                or existing.get("address_road")
            )
            number = (
                incoming.get("address_number")
                or self.case.address_number
                or existing.get("address_number")
            )
            self.case.address_district = district
            self.case.address_road = road
            self.case.address_number = number
            rebuilt = compose_street_address(
                district,
                road,
                number,
                existing=self.case.address,
            )
            if rebuilt:
                self.case.address = rebuilt

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
        include_floor = address_ask_should_include_floor(self.case.full_caller_text())
        try:
            result = self._llm.extract_address(
                caller_text, use_question=False, include_floor=include_floor,
            )
            addr = result.get("address")
            if not is_usable_address(addr):
                result = self._llm.extract_address(
                    caller_text, use_question=True, include_floor=include_floor,
                )
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
            include_floor = address_ask_should_include_floor(self.case.full_caller_text())
            try:
                llm_addr = self._llm.extract_address(
                    caller_text,
                    use_question=True,
                    include_floor=include_floor,
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
        # 純巷弄補述不是「新地址」。報案人在覆誦時說「還有136巷8弄」，
        # 這裡曾把它合併成「新北市板橋區還有136巷8弄」，路名整個消失、
        # 覆誦又唸回「光武街16號」，報案人連講三次都沒被接住。
        # 巷弄補述由 _merge_lane_into_road 併回路名處理。
        cleaned_cands = [
            c for c in cleaned_cands
            if extract_address_road(c) or not extract_lane_alley(c)
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
            self._normalize_location_fields()
            return
        for text in self.case.caller_texts():
            if self._try_extract_address(text):
                self._normalize_location_fields()
                return
        blob = self.case.full_caller_text()
        if blob:
            self._try_extract_address(blob)
        self._clear_unusable_address()
        self._normalize_location_fields()

    def _extract_all_fields_from_reply(
        self,
        caller_text: str,
        question: Optional[str] = None,
    ) -> None:
        """
        對單則報警人回答依案件類型抽取欄位並填入空欄位。

        原則：
        - 每一則回答都走 LLM，但只抽通用欄位與目前案件類型欄位
        - 局內回報欄位只在 call_type=局內回報時抽取
        - 生命征象可用規則校正（避免誤填導致 OHCA 誤判）
        - 僅當 LLM 不可用時，才用規則備援填患者/孕產欄位
        """
        if not (caller_text or "").strip():
            return

        qa_question = self._get_last_assistant_question() if question is None else question

        # 1) LLM 全欄位抽取（主路徑，每輪必做）
        if self._llm is not None:
            try:
                extracted = self._llm.extract_general_fields(
                    caller_text,
                    question=qa_question,
                    main_category=self.case.main_category,
                    call_type=self.case.call_type,
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
        self._update_street_address_from_input(caller_text)
        self._normalize_location_fields()

    def _after_caller_input(
        self,
        caller_text: str,
        question: Optional[str] = None,
    ) -> None:
        """每輪報警人輸入後觸發：LLM 全欄位抽取 + 案情摘要更新。"""
        if not (caller_text or "").strip():
            return

        self._extract_all_fields_from_reply(caller_text, question=question)
        if self.case.main_category == "火警":
            self._refresh_fire_subtype_from_bert()
        switched = self._maybe_reclassify_sub()
        self._update_case_summary()
        self._extracted_caller_count = len(self._iter_caller_qa_pairs())
        self._notify_case_update()
        if switched is not None:
            raise SubCategorySwitched(switched[0], switched[1])

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

    def observe_utterance(self, role: str, text: str) -> Dict[str, Any]:
        """轉接專人後旁聽：append transcript，抽取 SOP、更新摘要，不產生對話。"""
        self._bridged = True
        role_n = (role or "").strip().lower()
        if role_n not in {"caller", "agent"}:
            raise ValueError("role must be 'caller' or 'agent'")
        text_n = (text or "").strip()
        if not text_n:
            raise ValueError("text must not be empty")

        before = self.case.to_dict()
        with self._case_lock:
            self.case.transcript.append({"role": role_n, "text": text_n})
        if role_n == "caller":
            self._extract_all_fields_from_reply(text_n, question="")
            self._update_case_summary()
        self._notify_case_update()
        after = self.case.to_dict()
        updated = sorted(
            k for k in after if k != "transcript" and before.get(k) != after[k]
        )
        return {
            "updated_fields": updated,
            "transcript_size": len(self.case.transcript),
            "case_summary": self.case.case_summary,
        }

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
            self._bridged = True
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
            "一一九您好，請問是火災還是救護",
            "一一九您好，請問是需要消防車還是救護車",
            "一一九您好，請問是要報火災還是有人身體不舒服",
        ])
        first_input = self._ask_and_extract(first_q)

        if self._is_internal_report(first_input):
            with self._case_lock:
                self.case.call_type = "局內回報"
                self.case.main_category = "局內回報"
                self.case.main_conf = 1.0
            # 首輪輸入發生在通話類型確立前；以局內 schema 補抽一次。
            self._extract_all_fields_from_reply(first_input, question=first_q)
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
        # 首輪輸入發生在主類別確立前；以目前類別 schema 補抽一次。
        self._extract_all_fields_from_reply(first_input, question=first_q)
        if main_cat == "火警":
            self._refresh_fire_subtype_from_bert()
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
            self.case.address_road = None
            self.case.address_number = None
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

    def _refresh_fire_subtype_from_bert(self) -> None:
        """拼接全部報案人文本，BERT 細類置信度 > 0.5 時填入垂片代碼。"""
        from fire_tab_map_119 import (
            FIRE_BERT_CONF_THRESHOLD,
            apply_bert_subtype_to_case,
        )

        if self.case.main_category != "火警":
            return
        text = (self.case.full_caller_text() or "").strip()
        if not text:
            return
        sub_cat, sub_conf, sub_source = self._do_sub_classify(text, "火警")
        if not sub_cat or sub_conf is None or sub_conf <= FIRE_BERT_CONF_THRESHOLD:
            self._debug_print(
                "fire_bert_skip",
                {"sub": sub_cat, "conf": sub_conf, "source": sub_source},
            )
            return
        with self._case_lock:
            apply_bert_subtype_to_case(self.case, sub_cat, sub_conf)
        self._debug_print(
            "fire_bert_fill",
            {
                "sub": self.case.sub_category,
                "conf": self.case.sub_conf,
                "tab": self.case.fire_tab,
                "source": sub_source,
            },
        )
        self._emit({
            "type": "classification",
            "main": self.case.main_category,
            "main_conf": self.case.main_conf,
            "sub": self.case.sub_category,
            "sub_conf": self.case.sub_conf,
            "sub_source": sub_source,
        })
        self._notify_case_update()

    def _maybe_reclassify_sub(self) -> Optional[tuple]:
        """
        子類鎖定後每輪重跑分類器。
        若本輪 P(新) > P(當前) 則切類並遷移 SOP。
        返回 (old, new) 表示已切換；否則 None。
        """
        if not self._sub_reclassify_enabled:
            return None
        main_cat = self.case.main_category
        if main_cat not in ("救護", "火警"):
            return None
        current = self.case.sub_category
        from fire_tab_map_119 import (
            FIRE_BERT_CONF_THRESHOLD,
            TAB_QUESTIONS,
            apply_bert_subtype_to_case,
            tab_for_subtype,
        )
        fire_tab_locked = (
            main_cat == "火警" and self.case.fire_tab in TAB_QUESTIONS
        )
        if not current and not fire_tab_locked:
            return None
        if self._sub_clf is None:
            return None
        text = (self.case.full_caller_text() or "").strip()
        if not text:
            return None

        try:
            result = self._sub_clf.predict(text, main_cat)
        except Exception as e:
            self._debug_print("sub_reclassify_error", e)
            return None
        if not result:
            return None

        all_probs = dict(getattr(result, "all_probs", None) or {})
        if not all_probs:
            return None

        new_label = max(all_probs, key=all_probs.get)
        p_new = float(all_probs[new_label])
        if not current:
            if p_new <= FIRE_BERT_CONF_THRESHOLD:
                self._debug_print(
                    "sub_reclassify_fire_below_threshold",
                    {"new": new_label, "p_new": p_new},
                )
                return None
            predicted_tab = tab_for_subtype(new_label)
            if predicted_tab == self.case.fire_tab:
                with self._case_lock:
                    apply_bert_subtype_to_case(self.case, new_label, p_new)
                self._debug_print(
                    "fire_sub_initial_fill",
                    {
                        "sub": self.case.sub_category,
                        "conf": p_new,
                        "tab": self.case.fire_tab,
                    },
                )
                self._emit({
                    "type": "classification",
                    "main": self.case.main_category,
                    "main_conf": self.case.main_conf,
                    "sub": self.case.sub_category,
                    "sub_conf": self.case.sub_conf,
                    "sub_source": "classifier",
                })
                self._notify_case_update()
                return None
            self._debug_print(
                "sub_reclassify_switch",
                {
                    "old": current,
                    "new": new_label,
                    "p_cur": 0.0,
                    "p_new": p_new,
                },
            )
            self._switch_subcategory(current, new_label, p_new)
            return (current, new_label)

        if current in all_probs:
            p_cur = float(all_probs[current])
        else:
            # 關鍵詞-only 子類不在 BERT 標籤中：全文仍命中則保留
            p_cur = 0.0
            if main_cat == "救護":
                kw_cat, _, _ = match_rescue_subcategory(text)
                if kw_cat == current:
                    self._debug_print(
                        "sub_reclassify_keep_keyword",
                        {"current": current, "top1": new_label, "p_new": p_new},
                    )
                    return None

        if new_label == current:
            return None
        if p_new <= p_cur:
            self._debug_print(
                "sub_reclassify_keep",
                {
                    "current": current,
                    "p_cur": p_cur,
                    "new": new_label,
                    "p_new": p_new,
                },
            )
            return None

        if main_cat == "火警":
            if p_new <= FIRE_BERT_CONF_THRESHOLD:
                self._debug_print(
                    "sub_reclassify_fire_below_threshold",
                    {"new": new_label, "p_new": p_new},
                )
                return None

        self._debug_print(
            "sub_reclassify_switch",
            {
                "old": current,
                "new": new_label,
                "p_cur": p_cur,
                "p_new": p_new,
            },
        )
        self._switch_subcategory(current, new_label, p_new)
        return (current, new_label)

    def _switch_subcategory(
        self,
        old_sub: Optional[str],
        new_sub: str,
        new_conf: float,
    ) -> None:
        """清空舊專屬槽、LLM 遷移 SOP、更新 sub_category。"""
        from fire_tab_map_119 import (
            FIELD_LABELS_ZH,
            FIRE_IDENTITY_CODE_FIELDS,
            apply_bert_subtype_to_case,
            sop_slots_for_tab,
            tab_for_subtype,
        )

        main_cat = self.case.main_category
        if main_cat == "火警":
            old_slots = set(sop_slots_for_tab(self.case.fire_tab))
            new_tab = tab_for_subtype(new_sub)
            new_slots = list(sop_slots_for_tab(new_tab))
            slot_meanings = dict(FIELD_LABELS_ZH)
        else:
            old_slots = set(sop_slots_for(old_sub))
            new_slots = list(sop_slots_for(new_sub))
            slot_meanings = dict(_RESCUE_SLOT_MEANINGS)

        snapshot: Dict[str, Any] = {}
        with self._case_lock:
            for field in set(old_slots) | set(new_slots):
                val = getattr(self.case, field, None)
                if val is not None:
                    snapshot[field] = val
            extra = self.case.filled_fields_for_summary()
            for key, val in extra.items():
                snapshot.setdefault(key, val)

            ambiguous = (old_slots & set(new_slots)) - SHARED_SEMANTIC_SLOTS
            if main_cat == "火警":
                # 同垂片切子類只清身份編號；has_flame 等 SOP 碼保留。
                ambiguous &= FIRE_IDENTITY_CODE_FIELDS
            exclusive_old = old_slots - set(new_slots)
            for field in exclusive_old | ambiguous:
                if hasattr(self.case, field):
                    setattr(self.case, field, None)

        remapped: Dict[str, Any] = {}
        if self._llm is not None and snapshot and new_slots:
            try:
                remapped = self._llm.remap_sop_fields_for_subcategory(
                    old_sub=old_sub,
                    new_sub=new_sub,
                    filled_fields=snapshot,
                    new_slots=new_slots,
                    slot_meanings=slot_meanings,
                ) or {}
            except Exception as e:
                self._debug_print("sop_remap_error", e)
                remapped = {}

        with self._case_lock:
            for field, val in remapped.items():
                if field in new_slots and val is not None:
                    setattr(self.case, field, val)
            if main_cat == "火警":
                apply_bert_subtype_to_case(
                    self.case, new_sub, new_conf, allow_tab_switch=True,
                )
            else:
                self.case.sub_category = new_sub
                self.case.sub_conf = new_conf

        self._debug_print(
            "sop_remap",
            {"old": old_sub, "new": new_sub, "remapped": remapped},
        )
        self._emit({
            "type": "classification",
            "main": self.case.main_category,
            "main_conf": self.case.main_conf,
            "sub": self.case.sub_category,
            "sub_conf": self.case.sub_conf,
            "sub_source": "classifier",
        })
        self._notify_case_update()

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

    def _revert_unconfirmed_district_guess(self) -> None:
        """地址沒走完覆誦就失敗時，把音近猜出來的行政區還原成原文。

        猜測未經報案人確認，不能當成已知資訊留給派遣或接手的真人
        （「不分區」曾被猜成「瑞芳區」，兩地相距甚遠）。
        """
        guess = self._district_guess
        if not guess:
            return
        original, guessed = guess
        if not self._district_guess_sampled:
            self._district_guess_sampled = True
            record_fuzzy_match(
                KIND_DISTRICT,
                spoken=original,
                matched=guessed,
                outcome=OUTCOME_UNCONFIRMED,
                score=self._district_guess_score,
                location_type=self.case.location_type,
                session=getattr(self, "_session_tag", None),
            )
        with self._case_lock:
            for field in self._LOCATION_MAP_FIELDS:
                value = getattr(self.case, field, None)
                if isinstance(value, str) and guessed in value:
                    setattr(self.case, field, value.replace(guessed, original, 1))
        self._district_guess = None
        self._debug_print("district_guess_reverted", guess)

    def _best_candidate_address(self) -> Optional[str]:
        """候選中資訊最完整的地址。

        hint 導向補問會清掉該重問的元件；若補問沒問到（報案人答不出來、
        預算用盡），case.address 會停在殘缺狀態（「土城區要走路1段2號」
        被削成「土城區」）。失敗時要回到最完整的候選，別把已知資訊丟掉。
        """
        candidates = [
            item for item in self._address_candidates
            if is_usable_address(item.get("text"))
            and item.get("api_status") not in _API_REJECTED_REASONS
        ]
        if not candidates:
            return None

        def rank(item):
            text = item["text"]
            return (
                1 if item.get("api_status") == "valid" else 0,
                len(re.sub(r"\s+", "", text)),
            )

        best = max(candidates, key=rank)
        if best.get("api_status") == "valid":
            return best["text"]
        merged = self._merge_candidate_components(candidates)
        return merged or best["text"]

    def _merge_candidate_components(
        self, candidates: List[Dict[str, Any]]
    ) -> Optional[str]:
        """把同一地址散在各候選的元件併回來。

        hint 導向補問一次只重問一格，報案人補的段和先前的門牌號會落在
        不同候選（「板橋區吳鳳路90號」+「板橋區吳鳳路2段」），
        merge_address 兩個方向都會丟一邊，得按元件各取最完整。

        只在「區相同、路名互為前綴」時合併——報案人改報別的地址時
        硬合併會拼出不存在的門牌。
        """
        parsed = []
        for item in candidates:
            parts = extract_street_address_components(item["text"])
            if parts.get("address_district") and parts.get("address_road"):
                parsed.append(parts)
        if len(parsed) < 2:
            return None

        districts = {p["address_district"] for p in parsed}
        if len(districts) != 1:
            return None
        roads = sorted(
            {p["address_road"] for p in parsed}, key=len, reverse=True
        )
        longest_road = roads[0]
        if not all(longest_road.startswith(r) or r.startswith(longest_road)
                   for r in roads):
            return None

        numbers = [p["address_number"] for p in parsed if p.get("address_number")]
        if not numbers:
            return None
        return build_street_address(
            districts.pop(), longest_road, numbers[-1], existing=None
        )

    def _restore_best_candidate(self) -> None:
        """最終失敗前，把 address 換成資訊最完整的候選（若更完整）。

        若採用的候選是 addrCheck 驗證通過的，驗證狀態要跟著回到 valid——
        否則會出現「地址正確但標成查無」：09-02 那通最後還原成有效的
        61巷地址，狀態卻停在中途那次二十六11巷的 invalid。
        """
        best = self._best_candidate_address()
        if not best:
            return
        current = re.sub(r"\s+", "", self.case.address or "")
        if len(re.sub(r"\s+", "", best)) <= len(current):
            return
        self._debug_print("address_restore_best", {"from": self.case.address, "to": best})
        with self._case_lock:
            self.case.address = best
        self._fill_components_from_address()
        verified = any(
            item.get("api_status") == "valid" and item["text"] == best
            for item in self._address_candidates
        )
        if verified:
            self._set_address_validation("valid")

    def _address_failure_report(self, reason: str) -> str:
        """第五步：給受理員的回報字串。

        受理員接手時最需要知道「報案人到底講了什麼」，而不只是一句失敗原因，
        所以把累積的候選與最後一次 API 提示一起帶上。
        """
        parts = [reason or "地址無法確認"]
        spoken = [
            item["text"] for item in self._address_candidates
            if item.get("source") != "api_suggested"
        ]
        if spoken:
            parts.append("報案人講過：" + "、".join(spoken[:4]))
        last_hint = next(
            (
                item["api_hint"] for item in reversed(self._address_candidates)
                if item.get("api_hint")
            ),
            None,
        )
        if last_hint:
            parts.append("系統提示：" + last_hint)
        return "｜".join(parts)

    def _mark_address_failure(self, reason: str) -> None:
        """发布地址错误标签，并让案件继续后续流程。"""
        self._revert_unconfirmed_district_guess()
        self._record_address_candidate(self.case.address, source="final")
        self._restore_best_candidate()
        reason = self._address_failure_report(reason)
        self._debug_print("address_failure", {
            "reason": reason,
            "candidates": self._address_candidates,
        })
        # 「API 查無」與「報案人沒明確確認」是兩件事，標籤要分開：
        # 2026-09-04 20:55 那通地址其實有效（API 回「地址有效：新北市三重區
        # 仁愛街283巷28號」），只是覆誦沒得到確認，卻被標成「地址搜尋失敗」，
        # 受理員會誤以為地址查不到。
        api_verified = self.case.address_validation_status == "valid"
        with self._case_lock:
            self.case.address_confirmed = False
            self.case.address_suspect_error = True
            self.case.address_error_reason = reason
            if not api_verified and self.case.address_validation_status not in {
                "invalid", "error"
            }:
                self.case.address_validation_status = "invalid"
            self.case.ImportantCase = 1
            self.case.ImportantTag = merge_important_tags(
                self.case.ImportantTag,
                ["地址未確認"] if api_verified else ["地址搜尋失敗"],
            )
        self._notify_case_update()

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

    # ── 一般門牌地址：五步流程的輔助 ──────────────────────────────────────

    def _record_address_candidate(
        self,
        text: Optional[str],
        *,
        source: str,
        api_status: Optional[str] = None,
        api_hint: Optional[str] = None,
    ) -> None:
        """累積地址候選；重問不清空，最後失敗時整包交給受理員。

        09-02 事故：報案人第一次講的地址其實有效，被整段重報清掉後就回不來。
        """
        value = (text or "").strip()
        if not value:
            return
        for item in self._address_candidates:
            if item["text"] == value:
                if api_status:
                    item["api_status"] = api_status
                    item["api_hint"] = api_hint
                return
        self._address_candidates.append({
            "text": value,
            "source": source,
            "turn": len(self.case.transcript or []),
            "api_status": api_status,
            "api_hint": api_hint,
        })

    _ADDRESS_ASK_BUDGET = 10

    def _address_budget_left(self) -> int:
        return max(0, self._ADDRESS_ASK_BUDGET - self._address_asks_used)

    def _address_ask(self, question: str) -> Optional[str]:
        """地址流程專用提問；總預算用完回 None，讓流程收斂到第五步。"""
        if self._address_budget_left() <= 0:
            self._debug_print("address_ask_budget_exhausted", self._address_asks_used)
            return None
        self._address_asks_used += 1
        return self._ask_and_extract(question)

    def _fill_components_from_address(self, *, overwrite: bool = False) -> None:
        """用目前 address 補齊區/路/號元件。

        預設「已有值不動」——元件多半是逐輪累積來的，比事後從字串回推可靠。
        `overwrite=True` 用在地址被**整個換掉**之後（addrCheck 讀音修正、
        LLM 整段重判）：舊元件是舊地址的殘骸，留著會讓受理員看到不存在的
        路名，也可能被 _rebuild_street_address 拿去把地址組回錯的。
        """
        existing = extract_street_address_components(self.case.address or "")
        with self._case_lock:
            for key in (
                "address_district", "address_road", "address_number",
            ):
                if not existing.get(key):
                    continue
                if overwrite or not getattr(self.case, key, None):
                    setattr(self.case, key, existing[key])

    def _should_ask_floor(self) -> bool:
        """是否還要追問樓層。規則表在 address_hint_119.FLOOR_SUPPRESS_RULES。"""
        reason = floor_suppress_reason(self.case)
        if reason:
            self._debug_print("floor_suppressed", reason)
            return False
        return address_ask_should_include_floor(self.case.full_caller_text())

    def _confirm_district_guess(self) -> bool:
        """核對臺語音近猜出來的行政區；同輪多個修正合併成一次問。

        回 True 表示可以繼續（已確認或本來就沒猜）；False 表示報案人否認，
        猜測已還原、需要重新問區。
        """
        guess = self._district_guess
        if not guess:
            return True
        _original, guessed = guess
        road = self.case.address_road
        spoken = f"{guessed}{road}" if road else guessed
        self._set_stage("location_guess_confirm")
        answer = self._address_ask(f"我聽到的是{spoken}，對嗎？")

        def _sample(outcome: str) -> None:
            if self._district_guess_sampled:
                return
            self._district_guess_sampled = True
            record_fuzzy_match(
                KIND_DISTRICT,
                spoken=_original,
                matched=guessed,
                outcome=outcome,
                score=self._district_guess_score,
                location_type=self.case.location_type,
                session=getattr(self, "_session_tag", None),
            )

        if answer is None:
            _sample(OUTCOME_UNCONFIRMED)
            return True
        if parse_yes_no(answer) is False or is_uncertain_answer(answer):
            _sample(OUTCOME_DENIED)
            self._revert_unconfirmed_district_guess()
            with self._case_lock:
                self.case.address_district = None
            return False
        # 沒有明確否認就當確認（急案不宜為了措辭再耗一輪）。
        _sample(OUTCOME_CONFIRMED)
        self._district_guess = None
        return True

    def _ask_dropped_address_details(self) -> None:
        """原話裡有「之N」或樓層、地址裡卻沒有 → 回頭問一次。

        STT 把「200之1號8樓」拆成「兩百。號之18樓」，規則只撿得到門牌號，
        覆誦就唸成「200號」，得等報案人自己發現、自己更正——那是把校對
        工作丟給正在急著求救的人。這兩個 token 在原話裡看得到，掉了就該問。
        """
        if self._dropped_details_asked:
            return
        texts = self.case.caller_texts()
        if not texts:
            return
        missing_sub, missing_floor = dropped_address_details(
            texts[-1], self.case.address
        )
        if missing_floor and not self._should_ask_floor():
            missing_floor = False
        if not (missing_sub or missing_floor):
            return
        self._dropped_details_asked = True
        if missing_sub and missing_floor:
            question = "剛剛沒聽清楚，是幾號之幾？幾樓？"
        elif missing_sub:
            number = (self.case.address_number or "").replace("號", "")
            question = (
                f"{number}號之幾呢？" if number else "是幾號之幾呢？"
            )
        else:
            question = ASK_FLOOR
        self._set_stage("location_detail_reask")
        answer = self._address_ask(question)
        if answer is None:
            return
        self._normalize_location_fields()
        self._fill_components_from_address()
        self._merge_lane_into_road(answer)
        self._rebuild_street_address()

    def _narrowed_reask(self, fallback: str) -> str:
        """第二輪重問時，已經確定的元件就不要再問一次。

        2026-09-06 04:44 實測：報案人說「救護車在那個鶯歌」，區已經明確，
        再問一次「請問事發地址在哪裡？」等於要他從頭講。示警級案子的節奏
        禁不起這種空轉——直接問缺的那一項。
        """
        district = (self.case.address_district or "").strip()
        road = (self.case.address_road or "").strip()
        if district and not road:
            return f"{district}的哪一條路呢？"
        if district and road and not (self.case.address_number or "").strip():
            return f"{district}{road}幾號呢？"
        return fallback

    def _ask_missing_component(self, kind: str) -> bool:
        """補問單一元件；回傳是否問到。kind: district / road / number / floor。"""
        question = {
            "district": ASK_DISTRICT,
            "road": ASK_ROAD,
            "number": ASK_NUMBER,
            "floor": ASK_FLOOR,
        }[kind]
        field = {
            "district": "address_district",
            "road": "address_road",
            "number": "address_number",
        }.get(kind)
        self._set_stage(f"location_{kind}_reask")
        answer = self._address_ask(question)
        if answer is None:
            return bool(getattr(self.case, field, None)) if field else False
        self._normalize_location_fields()
        self._fill_components_from_address()
        self._merge_lane_into_road(answer)
        if field is None:
            return True
        if not getattr(self.case, field, None):
            # 單獨回答「土城區」時 address 不一定被更新，直接從本輪原話補抽。
            extractor = {
                "district": extract_address_district,
                "road": extract_address_road,
                "number": extract_address_number,
            }[kind]
            value = extractor(answer or "")
            if value:
                with self._case_lock:
                    setattr(self.case, field, value)
        return bool(getattr(self.case, field, None))

    def _adopt_normalized_address(self, hint: Optional[str]) -> None:
        """驗證通過時改採 addrCheck 回傳的標準地址（樓層接回去）。

        報案人講「南亞南路」，API 回 valid 並說明「已依讀音修正為南雅南路」——
        存報案人的口語原文會讓受理員看到錯的路名。API 的修正比本地
        map_street.json 安全：它有把握（「本轄同音路名僅此一條」）才修。
        """
        normalized = normalized_address_from_hint(hint, spoken=self.case.address)
        if not normalized or normalized == self.case.address:
            return
        if not is_usable_address(normalized):
            return
        self._debug_print("adopt_normalized_address", {
            "spoken": self.case.address, "normalized": normalized,
        })
        note = phonetic_correction_note(hint)
        with self._case_lock:
            self.case.address = normalized
            if note:
                self.case.address_corrected_note = note
        if note:
            self._debug_print("phonetic_correction", note)
        # 舊元件屬於修正前的地址（永鎮路），一定要換掉
        self._fill_components_from_address(overwrite=True)

    def _merge_lane_into_road(self, text: Optional[str]) -> bool:
        """報案人單獨補「一段」「31巷」時併進路名；回傳是否有變動。

        路名 regex 需要「X路」開頭，報案人補一句「還有31巷」「一段22號」
        時抽不到，段和巷弄就此消失——實測三通因此覆誦時唸成「國光路11號」
        「仁愛街28號」「明德路22號」，報案人連續否認或 API 回「未提及段別」。

        段要接在巷之前（「中央路三段61巷」），所以先併段再併巷。
        """
        road = self.case.address_road
        if not road:
            return False
        changed = False

        if not road_has_section(road):
            section = extract_road_section(text or "")
            # 段必須緊接路名，若路名已有巷弄就不能再插段進去
            if section and section not in road and not road_has_lane(road):
                road = f"{road}{section}"
                changed = True

        if not road_has_lane(road):
            lane = extract_lane_alley(text or "")
            if lane and lane not in road:
                road = f"{road}{lane}"
                changed = True

        if not changed:
            return False
        self._debug_print("merge_into_road", {
            "from": self.case.address_road, "to": road,
        })
        with self._case_lock:
            self.case.address_road = road
        return True

    def _rebuild_street_address(self) -> Optional[str]:
        """由目前元件組回門牌地址（保留既有樓層與報案人講過的段/巷/弄）。"""
        # 路名開頭若重複了行政區（「中和區」＋「中和景平路」），先剝掉再組，
        # 並同步回欄位——否則 address 是「景平路」而 address_road 還是
        # 「中和景平路」，看板上兩個欄位對不起來。
        stripped = strip_district_prefix_from_road(
            self.case.address_road, self.case.address_district
        )
        if stripped and stripped != self.case.address_road:
            self._debug_print("strip_district_from_road", {
                "from": self.case.address_road, "to": stripped,
            })
            with self._case_lock:
                self.case.address_road = stripped
        if not has_complete_street_address(
            self.case.address_district,
            self.case.address_road,
            self.case.address_number,
        ):
            return None
        rebuilt = build_street_address(
            self.case.address_district,
            self.case.address_road,
            self.case.address_number,
            existing=self.case.address,
        )
        if rebuilt:
            with self._case_lock:
                self.case.address = rebuilt
        return rebuilt

    # 判斷字串裡有沒有樓層（含 B1 這類地下樓層）
    _FLOOR_IN_TEXT_RE = re.compile(
        r"(?:地下)?[零〇一二三四五六七八九十百千兩\d]+樓|[Bb][0-9]+"
    )

    _HINT_CLEAR_FIELDS = {
        # hint 類型 → 該重問而必須清掉的元件（其餘已驗證的元件一律保留）
        "nearby_numbers": ("address_number",),
        "need_number": ("address_number",),
        "need_section": ("address_road", "address_number"),
        "road_suggestions": ("address_road", "address_number"),
        "road_in_districts": ("address_district",),
        "road_unknown": ("address_road", "address_number"),
    }

    def _resolve_street_address(
        self, *, allow_reasks: bool
    ) -> tuple[bool, str, bool]:
        """一般門牌地址的第二～四步。

        第二步 缺什麼問什麼（模糊猜測先核對）
        第三步 addrCheck 驗證，失敗時用 hint 決定下一句問話，
               只清掉該重問的元件——不再整段推翻重來
        第四步 仍不成立就走引導式，逐級問到區→路→號
        """
        self._fill_components_from_address()

        # ── 第二步：補缺元件（模糊猜測先核對）────────────────────────────
        if allow_reasks:
            if not self._confirm_district_guess():
                self._ask_missing_component("district")
            for kind, field in (
                ("district", "address_district"),
                ("road", "address_road"),
                ("number", "address_number"),
            ):
                for _ in range(2):
                    if getattr(self.case, field, None):
                        break
                    if not self._ask_missing_component(kind):
                        continue

        for field, reason in (
            ("address_district", "地址缺少行政區"),
            ("address_road", "地址缺少道路"),
            ("address_number", "地址缺少門牌號"),
        ):
            if not getattr(self.case, field, None):
                # 補問已在上面做過，不必再讓外層整段清空重報。
                return False, reason, False

        rebuilt = self._rebuild_street_address()
        if not rebuilt:
            return False, "門牌地址資訊不完整", False
        self._record_address_candidate(rebuilt, source="component_merge")

        # ── 第三步：API 驗證 + hint 導向補問 ─────────────────────────────
        attempts = 3 if allow_reasks else 1
        last_reason = "地址驗測查無此地點"
        last_probe = None   # (送驗的地址, API reason)
        for attempt in range(attempts):
            self._set_stage("location_validating")
            # 用 query_jurisdiction（JurisdictionResult 已帶 hint 與 api_reason），
            # 資訊與 verify_address_detail 相同，但保持既有 mock / 呼叫點不變。
            result = query_jurisdiction(self.case.address or "")
            status, hint, api_reason = (
                result.valid, result.error, result.api_reason
            )
            self._record_address_candidate(
                self.case.address,
                source="component_merge",
                api_status=api_reason,
                api_hint=hint,
            )
            if status is True:
                self._adopt_normalized_address(hint)
                self._set_address_validation(
                    "valid", office_name=result.office_name
                )
                return True, "", False
            if status is None:
                self._set_address_validation(
                    "error", reason="地址驗測 API 無法使用"
                )
                return False, "地址驗測 API 無法使用", True

            last_reason = addrcheck_failure_reason(api_reason)
            self._set_address_validation("invalid", reason=last_reason)
            if not allow_reasks or attempt == attempts - 1:
                break

            # 第一次查無才啟用街路映射表重查——先拿報案人原話問 addrCheck，
            # 查得到就別讓表插手。map_street.json 是 vendor 用臺語音近生成的
            # （1707 個真實路名 × 平均 15 個變體），生成時沒排除「變體本身
            # 已是另一條真實路名」，實測 23 條會把講對的路改掉
            # （重陽路→三和路、中山北路→中正北路…）。
            if not self._street_mapping_enabled:
                before = self.case.address
                self._street_mapping_enabled = True
                self._normalize_location_fields()
                self._fill_components_from_address()
                self._rebuild_street_address()
                if self.case.address != before:
                    self._debug_print("street_mapping_after_miss", {
                        "before": before, "after": self.case.address,
                    })
                    continue

            # 送驗地址與失敗原因都沒變，表示上一輪的補問沒改變任何東西；
            # 再問同一句只會讓報案人覺得系統跳針（實測「這條路好像沒有12號欸」
            # 連問兩次）。直接進引導式。
            probe = (self.case.address, api_reason)
            if probe == last_probe:
                self._debug_print("hint_reask_no_progress", probe)
                break
            last_probe = probe

            advice = parse_address_hint(hint)
            self._last_hint_advice = advice
            self._debug_print(
                "hint_advice", {"kind": advice.kind, "hint": hint}
            )
            spoken_number = self.case.address_number
            with self._case_lock:
                for field in self._HINT_CLEAR_FIELDS.get(advice.kind, ()):
                    setattr(self.case, field, None)
            self._set_stage("location_hint_reask")
            if self._address_ask(
                build_hint_question(advice, spoken_number=spoken_number)
            ) is None:
                break
            self._normalize_location_fields()
            self._fill_components_from_address()
            _recent = self.case.caller_texts()
            self._merge_lane_into_road(_recent[-1] if _recent else "")
            for kind, field in (
                ("district", "address_district"),
                ("road", "address_road"),
                ("number", "address_number"),
            ):
                if not getattr(self.case, field, None):
                    self._ask_missing_component(kind)
            if not self._rebuild_street_address():
                break

        # ── 第三步半：規則走不通時，讓 LLM 讀整段對話重新判讀 ──────────
        # 不佔提問預算（不問報案人），通過 addrCheck 才採用。
        if allow_reasks and self._consolidate_with_llm():
            return True, "", False

        # ── 第四步：引導式逐級 ──────────────────────────────────────────
        if (
            allow_reasks
            and self._address_budget_left() >= 4
            and self._guided_address_collect()
        ):
            self._set_stage("location_validating")
            result = query_jurisdiction(self.case.address or "")
            status, hint, api_reason = (
                result.valid, result.error, result.api_reason
            )
            self._record_address_candidate(
                self.case.address,
                source="guided",
                api_status=api_reason,
                api_hint=hint,
            )
            if status is True:
                self._set_address_validation(
                    "valid", office_name=result.office_name
                )
                return True, "", False
            if status is False:
                last_reason = addrcheck_failure_reason(api_reason)
                self._set_address_validation("invalid", reason=last_reason)

        return False, last_reason, False

    # hint 種類 → addrCheck 已認可的元件（不必重問）
    _HINT_CONFIRMS = {
        "nearby_numbers": ("address_district", "address_road"),  # 路對、只有門牌號不對
        "need_number": ("address_district", "address_road"),     # 路名已確認，缺號
        "need_section": ("address_district",),                   # 路對但缺段
    }

    def _consolidate_with_llm(self) -> bool:
        """讓 LLM 讀**整段對話**重新判讀地址；回傳是否採用了新地址。

        規則抽取只看單輪，分多次補述的巷弄、口誤更正、STT 音近錯字都接不住。
        離線評測 14 通真實通話：規則命中 5、LLM 命中 13——錯的那幾通全是
        「國光路11號（缺31巷）」「橫科路31號（缺351巷）」這類漏掉補述的。

        LLM 不直接定案：輸出一律送 addrCheck，通過才採用，之後還要覆誦確認。
        因此不依賴 `confidence`（實測 14 通全回 high，包含判錯那通）。
        只在規則路徑已經失敗時才叫，延遲只花在失敗案例上。
        """
        if self._llm is None:
            return False
        texts = self.case.caller_texts()
        if not texts:
            return False
        last_hint = next(
            (
                item["api_hint"] for item in reversed(self._address_candidates)
                if item.get("api_hint")
            ),
            None,
        )
        try:
            out = self._llm.consolidate_address(
                texts,
                current_address=self.case.address,
                api_hint=last_hint,
            )
        except Exception as exc:
            self._debug_print("consolidate_address_error", exc)
            return False

        address = (out or {}).get("address")
        if not is_usable_address(address) or address == self.case.address:
            return False

        self._set_stage("location_llm_consolidate")
        self._debug_print("consolidate_address", {
            "from": self.case.address, "to": address,
            "confidence": out.get("confidence"),
        })
        self._record_address_candidate(address, source="llm_consolidated")

        result = query_jurisdiction(address)
        self._record_address_candidate(
            address, source="llm_consolidated",
            api_status=result.api_reason, api_hint=result.error,
        )
        if result.valid is not True:
            # 沒通過就不採用，讓流程照原本的引導式走
            self._debug_print("consolidate_rejected", result.api_reason)
            return False

        with self._case_lock:
            self.case.address = address
        self._fill_components_from_address(overwrite=True)
        self._adopt_normalized_address(result.error)
        self._set_address_validation("valid", office_name=result.office_name)
        return True

    def _guided_address_collect(self) -> bool:
        """第四步：引導式逐級詢問。

        必問只有 區→路→號 三級；段/巷/弄不主動問，但報案人主動講的
        會由 extract_address_road 一併收進路名，不會被丟掉。

        **已被 addrCheck 認可的元件不重問**：API 回 `road_only`（路對、
        門牌號不對）時，區和路是確定的，整組清掉重問只會拖長通話——
        實測 03:12 那通報案人明確講了「板橋區大觀路一段」，卻被要求
        從「請問是哪一區」重來。
        """
        self._set_stage("location_guided")
        previous_address = self.case.address
        advice = self._last_hint_advice
        keep = set(self._HINT_CONFIRMS.get(getattr(advice, "kind", ""), ()))
        kept = {f: getattr(self.case, f) for f in keep if getattr(self.case, f)}
        if kept:
            self._debug_print("guided_keep_confirmed", kept)
        with self._case_lock:
            # address 也要清掉，否則 _fill_components_from_address 會立刻
            # 從舊地址把元件補回來，引導式等於沒作用。
            self.case.address = None
            for field in ("address_district", "address_road", "address_number"):
                if field not in kept:
                    setattr(self.case, field, None)

        if kept:
            # 已知的部分直接跳過，只問缺的
            answer = ""
        else:
            answer = self._address_ask(GUIDED_OPENING)
            if answer is None:
                self._restore_address(previous_address)
                return False
        self._normalize_location_fields()
        district = extract_address_district(answer or "")
        if district:
            with self._case_lock:
                self.case.address_district = district
        if not self._confirm_district_guess():
            self._ask_missing_component("district")

        for kind, field in (
            ("district", "address_district"),
            ("road", "address_road"),
            ("number", "address_number"),
        ):
            if not getattr(self.case, field, None):
                self._ask_missing_component(kind)
            if not getattr(self.case, field, None):
                self._restore_address(previous_address)
                return False

        if self._should_ask_floor() and not re.search(r"樓", self.case.address or ""):
            self._ask_missing_component("floor")
        if self._rebuild_street_address():
            return True
        self._restore_address(previous_address)
        return False

    def _restore_address(self, previous_address: Optional[str]) -> None:
        """引導式收集失敗時還原地址，別讓受理員接到一片空白。"""
        if self.case.address or not previous_address:
            return
        with self._case_lock:
            self.case.address = previous_address
        self._fill_components_from_address()

    def _probe_location_type(self) -> Optional[str]:
        """規則判不出型態時，讓 addrCheck 自己判是哪一層。

        不帶 type 查詢，API 會選層並在 hint 開頭寫明結果。實測學校類地標
        在 House 層全數查無、在自動層全數命中並直接回門牌：
            板橋國小  House → 查無「國小」      Auto → 文化路一段23號
            南山高中  House → 是否為南山路？    Auto → 中和區南山高中
        查無時回退 address，讓門牌流程的 hint 導向去處理。

        ⚠️ 純區名／縣市名不送——自動層會硬配地標（五股區→五股區公所、
        新北市→樹林區肉品市場）且回 valid。
        """
        address = self.case.address or ""
        if not is_usable_address(address) or is_bare_district_or_city(address):
            return None
        try:
            status, hint, api_reason = verify_address_detail(address, None)
        except Exception as exc:
            self._debug_print("probe_location_type_error", exc)
            return "address"
        if status is not True:
            # 查無：型態仍然定為 address，交給門牌流程的 hint 導向處理。
            # 寫回 case 是刻意的——下一輪 _refresh_location_type 就不會再
            # 探測一次，同一個地址不重複打 API。
            self._debug_print("probe_location_type_miss", api_reason)
            with self._case_lock:
                self.case.location_type = "address"
            return "address"
        layer = landmark_layer_from_hint(hint) or "address"
        self._debug_print("probe_location_type", {
            "address": address, "layer": layer, "hint": (hint or "")[:80],
        })
        with self._case_lock:
            self.case.location_type = layer
        # 已經查過一次，結果直接交給下游，不要再打一次 API
        self._probed_result = (status, hint, api_reason)
        return layer

    def _validate_landmark_like(
        self, location_type: str
    ) -> tuple[bool, str, bool]:
        """地標／捷運驗測。

        addrCheck 的地標比對沒有相似度門檻，會把「捷運不存在站出口9」硬配成
        「捷運亞東醫院站2號出口」並回 status=true。API 的 hint 自己就寫著
        「若不確定請向報案人確認是否為此處」——所以模糊配出來的一律當猜測，
        必須讓報案人有機會否認，不得靜默採用。
        """
        error_reason = (
            "地標資料表無法讀取" if location_type == "landmark"
            else "捷運車站資料無法讀取"
        )
        invalid_reason = (
            "地標不在資料表中" if location_type == "landmark"
            else "查無捷運車站"
        )
        self._set_stage("location_validating")
        self._normalize_location_fields()
        spoken = self.case.address or ""
        # _probe_location_type 剛查過就沿用它的結果，別為了同一個地址
        # 再打一次 API——急案的每一次往返都是時間。
        probed = self._probed_result
        self._probed_result = None
        if probed is not None:
            status, hint, _api_reason = probed
        else:
            try:
                status, hint, _api_reason = verify_address_detail(
                    spoken, location_type
                )
            except Exception as exc:
                self._debug_print(f"{location_type}_validation_error", exc)
                self._set_address_validation("error", reason=error_reason)
                return False, error_reason, True

        if status is None:
            self._set_address_validation("error", reason=error_reason)
            return False, error_reason, True
        if status is not True:
            self._set_address_validation("invalid", reason=invalid_reason)
            return False, invalid_reason, True

        match = parse_landmark_hint(hint)
        if not match.is_fuzzy:
            self._set_address_validation("valid")
            return True, "", False

        # 模糊比對：先問報案人是不是這裡。
        self._debug_print("landmark_fuzzy_match", {
            "spoken": spoken,
            "matched": match.matched,
            "resolved": match.resolved,
        })
        def _sample(outcome: str) -> None:
            record_fuzzy_match(
                KIND_LANDMARK,
                spoken=spoken,
                matched=match.matched,
                resolved=match.resolved,
                outcome=outcome,
                alternatives=match.alternatives,
                api_hint=hint,
                location_type=location_type,
                session=getattr(self, "_session_tag", None),
            )

        answer = self._address_ask(build_landmark_confirm_question(match))
        if answer is None:
            # 預算用盡：不敢逕自採用猜測，標成疑義交給受理員。
            _sample(OUTCOME_UNCONFIRMED)
            self._set_address_validation(
                "invalid", reason=f"{invalid_reason}（地標為模糊比對，未經確認）"
            )
            return False, f"{invalid_reason}（未經確認）", False
        if parse_yes_no(answer) is False or is_uncertain_answer(answer):
            # 「不知道」不等於「對」——地址攸關派遣，模稜兩可不採用猜測。
            _sample(OUTCOME_DENIED)
            self._set_address_validation(
                "invalid", reason="報案人未能確認模糊比對到的地標"
            )
            return False, "地標比對未確認", True
        _sample(OUTCOME_CONFIRMED)

        # 報案人確認後才改寫成 API 解析出的地址。
        if match.resolved:
            with self._case_lock:
                self.case.address = match.resolved
        self._record_address_candidate(
            self.case.address, source="api_suggested", api_status="valid",
            api_hint=hint,
        )
        self._set_address_validation("valid")
        return True, "", False

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
        # 判型不受街路映射影響（看的是路/號/區的結構），所以先判型；
        # 門牌型態的街路映射延後到 addrCheck 查無才套用。
        self._normalize_location_fields()
        location_type = self._refresh_location_type()
        if not location_type:
            location_type = self._probe_location_type()
        if not location_type:
            return False, "無法判斷地址類別", False

        self._set_address_validation("pending")

        if location_type == "address":
            # 一般門牌地址走五步流程（補缺 → hint 導向 → 引導式），
            # 其餘型態維持原判斷邏輯。
            return self._resolve_street_address(
                allow_reasks=allow_component_reasks
            )

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
            self._normalize_location_fields()
            status, _hint, api_reason = verify_address_detail(
                self.case.address or "", "intersection"
            )
            if status is True:
                self._set_address_validation("valid")
                return True, "", False
            if status is False:
                reason = addrcheck_failure_reason(api_reason)
                self._set_address_validation("invalid", reason=reason)
                return False, reason, True
            self._set_address_validation("error", reason="地址驗測 API 無法使用")
            return False, "地址驗測 API 無法使用", True

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
            self._normalize_location_fields()
            status, _hint, api_reason = verify_address_detail(
                self.case.address or "", "highway"
            )
            if status is True:
                self._set_address_validation("valid")
                return True, "", False
            if status is False:
                reason = addrcheck_failure_reason(api_reason)
                self._set_address_validation("invalid", reason=reason)
                return False, reason, True
            self._set_address_validation("error", reason="地址驗測 API 無法使用")
            return False, "地址驗測 API 無法使用", True

        if location_type in {"landmark", "mrt"}:
            return self._validate_landmark_like(location_type)

        return False, "不支援的地址類別", False

    def _complete_and_validate_location(self) -> tuple[bool, str]:
        ok, reason, retryable = self._validate_location_once(
            allow_component_reasks=True
        )
        if ok or not retryable:
            return ok, reason

        # 一般門牌地址的重試（hint 導向補問 + 引導式）已在
        # _resolve_street_address 內完成，不再整段清空重報——那正是
        # 09-04「只有門牌號錯卻要報案人重講整個地址」的原因。
        if self.case.location_type == "address" and not retryable:
            return ok, reason

        self._set_stage("location_validation_reask")
        self._reset_location_for_correction()
        self._notify_case_update()
        self._ask_and_extract(GENERIC_ADDRESS_RETRY)
        if not is_usable_address(self.case.address):
            return False, "重新提供的地址仍無法抽取"
        ok, reason, _ = self._validate_location_once(
            allow_component_reasks=False
        )
        return ok, reason

    def _run_address_flow(
        self,
        *,
        stage_ask: str,
        stage_confirm: str,
        dispatch_line: str,
        ask_questions: tuple[str, ...],
    ) -> None:
        """地址流程外層：不論由哪個分支離開，結束後都把地點上鎖。

        內層有多個提前 return（抽取失敗／校驗失敗／確認成功…），統一在
        finally 上鎖，之後 _apply_location_rules 不再覆寫已成立的地點。
        """
        try:
            self._run_address_flow_inner(
                stage_ask=stage_ask,
                stage_confirm=stage_confirm,
                dispatch_line=dispatch_line,
                ask_questions=ask_questions,
            )
        finally:
            self._address_locked = True

    def _run_address_flow_inner(
        self,
        *,
        stage_ask: str,
        stage_confirm: str,
        dispatch_line: str,
        ask_questions: tuple[str, ...],
    ) -> None:
        """五步地址流程。

        1. 先從歷史對話補抽地址（每次進流程走一次，不是每輪）
        2. 仍無地址才開口問；模糊比對 → 判型 → 分型處理
        3. addrCheck 驗證，用 hint 決定下一句問話
        4. 仍不成立走引導式逐級詢問
        5. 還是不行就把候選與提示回報給受理員，流程繼續往下走
        """
        self._set_stage(stage_ask)

        # ── 第一步：歷史對話已講過的地址 ────────────────────────────────
        self._ensure_address_from_caller_history()
        self._record_address_candidate(self.case.address, source="history")
        self._notify_case_update()

        # ── 第二步：沒有地址才問。問句依樓層規則表決定要不要帶「幾樓」 ──
        addr_asks = 0
        ask_max = min(2, len(ask_questions))
        while not is_usable_address(self.case.address) and addr_asks < ask_max:
            addr_q = ask_questions[addr_asks]
            if addr_asks:
                addr_q = self._narrowed_reask(addr_q)
            if not self._should_ask_floor():
                addr_q = addr_q.replace("？幾樓？", "？").replace("幾樓？", "")
            addr_asks += 1
            self._debug_print("address_ask", {"n": addr_asks, "q": addr_q})
            answer = self._ask_and_extract(addr_q)
            self._clear_unusable_address()
            if not is_usable_address(self.case.address):
                self._try_extract_address(answer)
                self._clear_unusable_address()
            # 模糊比對在 _normalize_location_fields 內，會記下音近猜測供核對。
            self._normalize_location_fields()
            # 第一輪就要接住段/巷弄。報案人常講「新豐街。那個20巷6號1樓」，
            # 標點與贅詞把巷弄和路名隔開，路名 regex 抽不到，覆誦時就漏了
            #（實測 03:20 新豐街20巷、03:12 大觀路28巷 都中招）。
            if self._merge_lane_into_road(answer):
                self._rebuild_street_address()
            self._record_address_candidate(
                self.case.address, source="caller_stated"
            )
            self._notify_case_update()

        if not is_usable_address(self.case.address):
            self._debug_print("address_ask_exhausted", {"asks": addr_asks})
            self._mark_address_failure("地址抽取失敗")
            return

        self._ask_dropped_address_details()

        if addr_asks == 0:
            self._debug_print("skip_address_ask", self.case.address)

        valid, reason = self._complete_and_validate_location()
        if not valid:
            self._mark_address_failure(reason or "地址校驗失敗")
            return

        self._set_stage(stage_confirm)
        for _confirm_attempt in range(2):
            current_addr_display = self.case.display_address()
            if self._district_guess:
                # 行政區是音近猜的，覆誦時必須把區單獨點出來讓報案人否認。
                confirm_q = (
                    f"我聽到的地址是{current_addr_display}，"
                    f"請確認行政區是「{self._district_guess[1]}」對嗎？"
                )
            else:
                confirm_q = f"確定是{current_addr_display}這個地址嗎？"
            addr_before_confirm = self.case.address
            confirm_text = self._ask_and_extract(confirm_q)
            # 報案人常在覆誦時才補上巷弄（「還有31巷」）；先併進路名再判斷，
            # 地址因此變動時下面會走更正重驗。
            if self._merge_lane_into_road(confirm_text):
                self._rebuild_street_address()

            confirmed = parse_yes_no_for_question(confirm_q, confirm_text)
            # 覆誦當下報案人常一邊說「對」一邊補上新地址，那輪的抽取會把
            # case.address 就地改掉。若只看「對」就標成已確認，case 會顯示
            # 「已確認、有效」但存的其實是沒驗證過的地址（2026-09-02 那通
            # 驗的是 61巷、存的是二十六11巷）。地址變了就一律當更正重驗。
            if (
                is_usable_address(self.case.address)
                and self.case.address != addr_before_confirm
            ):
                self._debug_print("address_changed_during_confirm", {
                    "before": addr_before_confirm, "after": self.case.address,
                })
                confirmed = None
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
            if (
                not is_usable_address(corrected)
                and confirmed is None
                and self.case.address != addr_before_confirm
            ):
                # 本輪抽取已經把地址換掉，但 correction 沒抽出東西——
                # 直接拿改後的地址走重驗，別讓它未經驗證就留下。
                corrected = self.case.address
            if is_usable_address(corrected):
                with self._case_lock:
                    self.case.address = corrected
                    self.case.address_confirmed = None
                    self.case.location_type = None
                    self.case.address_district = None
                    self.case.address_road = None
                    self.case.address_number = None
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
                    return
                continue

            if confirmed is True:
                # 報案人確認過，音近猜測不再是未驗證資訊。
                self._district_guess = None
                with self._case_lock:
                    self.case.address_confirmed = True
                    self.case.address_suspect_error = False
                    self.case.address_error_reason = None
                self._notify_case_update()
                self._say(dispatch_line)
                self._dispatch_announced = True
                return

        self._mark_address_failure("報警人未能明確確認地址")
        return

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
            ask_questions=build_address_ask_questions(
                include_floor=address_ask_should_include_floor(
                    self.case.full_caller_text()
                ),
                flow="救護",
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
        # 重問時換句話問：觸發重問多半是 ASR 聽錯（例：「羊水」→「涼水」），
        # 一字不差地再問一次，報案人會以為系統沒聽到。
        _SUB_REASK_QUESTIONS = (
            "不好意思，請再說一次現場發生什麼狀況？",
            "麻煩您簡短描述一下傷病患目前的情形？",
        )
        candidates: List[tuple] = []
        if sub_cat is not None:
            candidates.append((sub_cat, sub_conf if sub_conf is not None else 0.0, sub_source))

        for _reask_i in range(_MAX_SUB_REASK):
            if sub_source == "keyword":
                break
            if sub_conf is not None and sub_conf >= _SUB_CONF_THRESHOLD:
                break

            self._ask_and_extract(_SUB_REASK_QUESTIONS[_reask_i])
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

        # ── 取得次類別 handler（可在對話中途因重分類切換並重入）──────────────
        self._sub_reclassify_enabled = True
        try:
            while True:
                try:
                    handler = get_handler(self.case.sub_category)
                    if hasattr(handler, "run_subtype_flow"):
                        handler.run_subtype_flow(self)
                    else:
                        self._run_救護_generic_handler(handler)
                    break
                except SubCategorySwitched as sw:
                    self._debug_print(
                        "sub_switched_restart",
                        {"old": sw.old, "new": sw.new},
                    )
                    continue
        finally:
            self._sub_reclassify_enabled = False

        # ════════════════════════════════════════════════════════
        # 階段 4：案情摘要回填（不對報案人複誦，僅更新欄位供 UI 顯示）
        # ════════════════════════════════════════════════════════
        self._set_stage("救護_summary_confirm")
        self._update_case_summary()
        self._notify_case_update()

        # ════════════════════════════════════════════════════════
        # 階段 5：報案人訊息 + 流程結束（委派給次類別 handler）
        # ════════════════════════════════════════════════════════
        handler = get_handler(self.case.sub_category)
        handler.collect_caller_info(self)

    def _run_救護_generic_handler(self, handler) -> None:
        """未登記子類的通用流程：前置問題 → 生命征象 → 後置問題 → 患者資訊。"""
        handler.run_pre_vital(self)

        # 階段 2：漸進確認生命征象（前一項為否才問下一項）
        self._ensure_known_fields_from_history()

        vital_questions = [
            ("救護_vital_1", "consciousness", "請問人是否還有意識？"),
            ("救護_vital_2", "breathing",     "請你看一下他是否有呼吸？"),
            ("救護_vital_3", "abdomen_rise",  "請看一下他肚子有沒有起伏？"),
        ]

        for question_i, (stage, slot, question) in enumerate(vital_questions):
            self._ensure_known_fields_from_history()

            if self._is_field_filled(slot):
                with self._case_lock:
                    vital_val = getattr(self.case, slot)
                self._debug_print(f"skip_{slot}", vital_val)
                self._set_stage(stage)
            else:
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

            # 任一項確認為有，即停止後續生命征象問題；只有明確為否才繼續。
            if vital_val is True:
                self._debug_print("vital_confirmed", slot)
                break
            if vital_val is None or question_i == len(vital_questions) - 1:
                self._check_ohca_and_transfer(vital_val, slot)

        # 生命征象後次類別額外問題（如：一般受傷的傷因/部位/TOCC）
        handler.run_post_vital(self)

        # 階段 3：詢問關鍵要素（已有值則跳過）
        self._ensure_known_fields_from_history()

        # 性別/年齡：語境感知（含受傷人數、報案人即患者等）
        handler._run_s6_gender_age(self, "救護_patient_1")

        patient_questions = [
            ("救護_patient_2", ("incident_description",), "剛剛發生甚麼事？"),
            (
                "救護_patient_3",
                ("current_condition",),
                handler.build_patient_condition_question(self),
            ),
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

    # ── 火警 handler ──────────────────────────────────────────────────────────

    def _run_火警(self) -> None:
        """火警地址確認後：Q1/Q2 分流 → 垂片 A/B1/B2/C → 安全提示 → 回撥確認。"""
        from handlers.火警通用 import HuoJingGenericHandler

        # ════════════════════════════════════════════════════════
        # 階段 1：詢問地址（首問同救護；不可用再追問建物/路燈）→ 覆頌 → 派車
        # ════════════════════════════════════════════════════════
        self._run_address_flow(
            stage_ask="火警_location",
            stage_confirm="火警_location_confirm",
            dispatch_line="已確認地址，消防車已派出了喔。",
            ask_questions=build_address_ask_questions(
                include_floor=address_ask_should_include_floor(
                    self.case.full_caller_text()
                ),
                flow="火警",
            ),
        )

        # ════════════════════════════════════════════════════════
        # 階段 2：建物 / 非建物分流 + 對應垂片細節
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
            ask_questions=build_address_ask_questions(
                include_floor=address_ask_should_include_floor(
                    self.case.full_caller_text()
                ),
                flow="緊急救援",
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
