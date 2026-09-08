"""
sop_api_server.py — HTTP API wrapper around SopEngine119 (119 救護報案)

部署（119_0904_addrflow）：
    cd /home/cyberon2/nlp_cyberon_server/ai/119_0904_addrflow
    /home/cyberon2/nlp_cyberon_server/llmenv/bin/uvicorn \
      sop_api_server:app --host 0.0.0.0 --port 8200

API 介面（與 119_0625_code 版相同 endpoint 設計）：
  - POST /session/new                    → 起新通話
  - POST /session/{id}/input             → 餵 caller 文字
  - POST /session/{id}/observe           → 轉真人後續聽對話，只更新 case_summary
  - POST /session/{id}/hangup            → 強制結束（送 END_FLOW 哨兵）
  - GET  /session/{id}/result            → 拿 case JSON
  - GET  /session/{id}/output            → 輪詢未消化 events
  - GET  /session/{id}/case/stream       → SSE 長連線，case 更新即推 case_updated，結束推 done
  - GET  /schema/case-fields/labels      → CaseInfo119 欄位中文對照
  - GET  /health

相對 119_0625_code 版的差異（119_0721_v2）：
  - 引擎升級為新版 SopEngine119（handlers/ 各案類處理器 + 子分類關鍵字比對）
  - 強制結束改用引擎原生哨兵 END_FLOW_SENTINEL（"__END_FLOW__"），
    引擎 _hear() 偵測後拋 FlowAbortedError → run() 收斂為 result="manual_end"
    （舊版是 input_q.put(None) + 自訂 _EngineEndCall，已移除）
  - case 序列化改用 CaseInfo119.to_dict()
  - 輸出 queue 是 typed events（chat / case_update / classification / stage_update / stopped / error）
    `/input` 回應同時給 `outputs: [string]`（過濾出 assistant chat）跟 `events: [dict]`（完整事件）
  - 模型使用 TW-119-Model GGUF（透過 GGUF_MODEL_PATH env 覆蓋）

相對 119_0721_v2 的差異（119_0724_add_2maincategory）：
  - 新增「火警」「緊急救援」兩個主類別的完整 SOP 流程（handlers/火警通用.py、緊急救援通用.py）
  - CaseInfo119 新增 6 個火警要素欄位（fire_or_smoke ... fire_floor）
  - REST API 契約與引擎介面（SopEngine119.__init__、END_FLOW_SENTINEL、to_dict）皆不變，本檔沿用

相對 119_0724_add_2maincategory 的差異（119_0808_loc_feedback）：
  - 地址流程升級：新增 location_validation_119.py，支援 address / intersection /
    landmark / highway / mrt 五種地點型態，並呼叫外部轄區 API 校驗地址真偽
    （env `JURISDICTION_API_URL`、`JURISDICTION_API_TIMEOUT`，預設 2.5 秒）
    → CaseInfo119 新增 11 個地址欄位（location_type ... address_error_reason）
  - 火警流程細分為建築物 / 工廠 / 車輛 / 露天野外四條分支（火警_category 分流）
    → 火警欄位由 6 個擴為 22 個；移除 flame_observation、smoke_trend
  - 新增「局內同仁回報」流程（現場回報 / 支援請求），case.result 多兩個終止值
    "report_recorded"、"support_dispatched"
  - 新增全類型通用標記 important_tags_119.py → ImportantCase / ImportantTag /
    NeedPolice 三欄位（ImportantTag 為 list，to_dict 空 list 會被濾掉）
  - CaseInfo119 欄位總數 46 → 87，case_field_labels_119.py 同步重建
  - 新依賴 openpyxl（讀 scripts/landmarks.xlsx 地標清單）
  - REST API 契約與引擎介面（SopEngine119.__init__、run()、DialogueIO 抽象方法、
    END_FLOW_SENTINEL、to_dict）皆不變，本檔沿用

相對 119_0808_loc_feedback 的差異（119_0813_adjustSOP）：
  - SOP 流程調整：引擎 343 行、handlers/base.py 239 行、sop_utils_119.py 414 行
  - CaseInfo119 新增 3 欄位 → 總數 87 → 90，labels 86 → 89
    address_road（道路含段巷弄）、address_number（門牌號）、
    caller_is_patient（報案人是否即患者）
  - 新增測試 tests/test_patient_context_119.py、tests/test_rescue_vital_flow_119.py
  - 廠商已吸收 0808 的本地修改：NeedPolice（轉介110）、「幾樓？」話術
  - ⚠️ 0808 的其餘本地修改 0813 尚未包含（自動補縣市 ensure_city_prefix、
    戶外不問樓層、地址片段合併、app_119 走 env、「還救護車」漏字），
    詳見 runbook §4，上線後需另行補回
  - REST API 契約與引擎介面皆不變，本檔沿用

本檔新增（/observe 轉真人後續聽，機器A 2026-08-28 需求）：
  - 新增 POST /session/{id}/observe，body {"text": str, "role": "caller"|"agent"}
    橋接給真人後，民眾與受理員每句話都送這裡。行為：append transcript →
    背景重算 case_summary → 照原路從 /case/stream 推 case_updated。
    不擋 done、不設 done、不產生 AI 回覆、不做欄位抽取
    （轉真人後結構化欄位改由受理員在前端手動填寫）。
  - transcript 多一個 role 值 "agent"（接手的真人受理員）。
  - ⚠️ SSE /case/stream 收線條件改變：原本引擎跑完（done）就推 done 並關閉，
    改為只在 /hangup 之後關閉。因為 AI 判斷轉真人時引擎就結束了，
    若照舊關閉，真人接手後的摘要就推不出去。對沒轉真人的一般通話而言，
    done 事件會從「引擎跑完」延後到「機器A 呼叫 /hangup」（相差數秒）。
    另有防呆逾時（OBSERVE_GRACE_S / OBSERVE_IDLE_CLOSE_S）避免連線洩漏。
  - 新增 env：OBSERVE_SUMMARY_MAX_TURNS / OBSERVE_DEBOUNCE_S /
    OBSERVE_MIN_INTERVAL_S / OBSERVE_GRACE_S / OBSERVE_IDLE_CLOSE_S
  - SopEngine119 與 /input /hangup /result /output 的既有行為皆未更動。
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import sys
import threading
import time
import uuid as uuidlib
from datetime import datetime
from typing import Any, Dict, List, Optional

# ── 確保可以 import 本目錄的模組 ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from case_field_labels_119 import LABELS as _CASE_FIELD_LABELS_119
from case_info_119 import CaseInfo119
from llm_extractor_119 import build_fallback_summary
from sop_119_engine import (
    END_FLOW_SENTINEL,
    DialogueIO,
    SopEngine119,
    TransferToHumanError,
)

# ── LLM extractor 使用 TW-119-Model GGUF（可用 GGUF_MODEL_PATH env 覆蓋）──
GGUF_MODEL_PATH = os.environ.get(
    "GGUF_MODEL_PATH",
    "/home/cyberon2/nlp_cyberon_server/models/TW-119-Model.gguf",
)
GGUF_N_CTX = int(os.environ.get("GGUF_N_CTX", "4096"))
GGUF_N_GPU_LAYERS = int(os.environ.get("GGUF_N_GPU_LAYERS", "-1"))
GGUF_TEMPERATURE = float(os.environ.get("GGUF_TEMPERATURE", "0.1"))

# 119 主/子 BERT 分類器
ENABLE_MAIN_CLASSIFIER = os.environ.get("ENABLE_MAIN_CLASSIFIER", "1") == "1"
ENABLE_SUB_CLASSIFIER = os.environ.get("ENABLE_SUB_CLASSIFIER", "1") == "1"
# 119 BERT 模型根目錄（vendor 預設 /root/autodl-tmp/models/，我們放在 ai/ 下）
BERT_MODELS_BASE = os.environ.get(
    "BERT_MODELS_BASE",
    "/home/cyberon2/nlp_cyberon_server/ai/",
)
# BERT 跑 CPU 還是 GPU；預設 CPU 把 VRAM 留給 LLM GGUF（跟 110 慣例一致）
BERT_DEVICE = os.environ.get("BERT_DEVICE", "cpu")

# 案件結構化 JSON log 寫出位置
LOG_DIR = os.environ.get("LOG_DIR", "/home/cyberon2/nlp_cyberon_server/log_119")

# ── /observe（轉真人後繼續更新摘要）調校參數 ─────────────────────────────
# 摘要輸入最多取最後幾輪對話（n_ctx 4096，長通話逐字稿塞不下）
OBSERVE_SUMMARY_MAX_TURNS = int(os.environ.get("OBSERVE_SUMMARY_MAX_TURNS", "40"))
# 收到句子後先等這麼久，把連續湧入的句子併成一次重算
OBSERVE_DEBOUNCE_S = float(os.environ.get("OBSERVE_DEBOUNCE_S", "2.0"))
# 兩次重算之間的最小間隔，避免真人連珠炮把 LLM 打爆
OBSERVE_MIN_INTERVAL_S = float(os.environ.get("OBSERVE_MIN_INTERVAL_S", "5.0"))
# 防呆：引擎已結束、還沒收到任何 /observe 時，SSE 最多再等這麼久（等橋接接通）
OBSERVE_GRACE_S = float(os.environ.get("OBSERVE_GRACE_S", "120"))
# 防呆：已在 observe 中，但久無新句子也無 /hangup 時，SSE 最多再撐這麼久
OBSERVE_IDLE_CLOSE_S = float(os.environ.get("OBSERVE_IDLE_CLOSE_S", "900"))


# ── 預載 LLM extractor ───────────────────────────────────────────────────
_shared_llm_extractor: Optional[Any] = None
if os.path.isfile(GGUF_MODEL_PATH):
    try:
        from llm_extractor_119 import LLMExtractor119
        print(f"⏳ 載入 LLMExtractor119 from {GGUF_MODEL_PATH} …", flush=True)
        _shared_llm_extractor = LLMExtractor119(
            model_path=GGUF_MODEL_PATH,
            n_ctx=GGUF_N_CTX,
            n_gpu_layers=GGUF_N_GPU_LAYERS,
            temperature=GGUF_TEMPERATURE,
        )
        print("✅ LLMExtractor119 就緒", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  LLMExtractor119 載入失敗：{exc}（純規則模式）", flush=True)
else:
    print(f"⚠️  GGUF_MODEL_PATH={GGUF_MODEL_PATH} 不存在，LLM 跳過", flush=True)

# ── 預載 119 主/子分類器（模型根目錄走 BERT_MODELS_BASE） ────────────────
_shared_main_classifier = None
_shared_sub_classifiers = None
if ENABLE_MAIN_CLASSIFIER:
    try:
        from inference_pipeline import HierarchicalClassifier
        print(f"⏳ 載入 119 主分類器 from {BERT_MODELS_BASE} (device={BERT_DEVICE})…", flush=True)
        _shared_main_classifier = HierarchicalClassifier(
            models_base=BERT_MODELS_BASE,
            device=BERT_DEVICE,
        )
        print("✅ 119 主分類器就緒", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  119 主分類器跳過：{exc}", flush=True)
if ENABLE_SUB_CLASSIFIER:
    try:
        from classifier_with_llm import build_classifiers, SubCategoryClassifier
        # vendor build_classifiers 只註冊「救護」+「火警」；緊急救援在下方補註冊。
        print(f"⏳ 載入 119 子分類器 from {BERT_MODELS_BASE} (device={BERT_DEVICE})…", flush=True)
        _shared_sub_classifiers = build_classifiers(
            models_base=BERT_MODELS_BASE,
            llm_model_path=None,   # 子分類器內建的 LLM reviewer 用不到，避免重複載 GGUF
            device=BERT_DEVICE,
            enable_llm=False,
        )
        # 補註冊「緊急救援」子分類器（vendor build_classifiers 未涵蓋）。
        # 2026-08-31 起三個子分類升級：救護 14 類 / 火警 13 類 / 緊急救援 8 類。
        _es_dir = os.path.join(BERT_MODELS_BASE, "TW-119-BERT-sub_緊急救援")
        if os.path.isdir(_es_dir):
            try:
                _shared_sub_classifiers.register(SubCategoryClassifier(
                    main_category="緊急救援",
                    model_dir=_es_dir,
                    llm_model_path=None,
                    device=BERT_DEVICE,
                ))
                print("✅ 補註冊 緊急救援 子分類器", flush=True)
            except Exception as exc2:  # noqa: BLE001
                print(f"⚠️  緊急救援 子分類器補註冊失敗：{exc2}", flush=True)
        print("✅ 119 子分類器就緒", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  119 子分類器跳過：{exc}", flush=True)

app = FastAPI(title="SopEngine119 API", version="4.0-119_0904_addrflow")


# ═══════════════════════════════════════════════════════════════════════════
# Session 狀態
# ═══════════════════════════════════════════════════════════════════════════

class Session:
    def __init__(self, sess_id: str) -> None:
        self.sess_id = sess_id
        # 機器 A（交換機/apiserver）的通話 UUID，由 /session/new 傳入。
        # 用來讓 case log 對回 A 側與測試回饋表；A 沒傳時為 None。
        self.call_uuid: Optional[str] = None
        # 119 input_q 只進字串（含 END_FLOW_SENTINEL 哨兵）
        self.input_q: "queue.Queue[str]" = queue.Queue()
        # 119 output_q 進 typed events: {"type": "chat"|"case_update"|...}
        self.output_q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        # engine 回到 hear_text 等下一句 caller 時 set（Issue #2 修法沿用）
        self._engine_ready = threading.Event()
        # CaseInfo119（engine 跑完才填）
        self.case: Optional[CaseInfo119] = None
        self.error: Optional[str] = None
        self.done = threading.Event()
        # 保留 engine 實例
        self.engine: Optional[SopEngine119] = None
        self.lock = threading.Lock()
        self.result_log_path: Optional[str] = None
        # ── /observe 轉真人後續聽 ───────────────────────────────────────
        # closed：只有 /hangup 會設。SSE 靠它決定何時收線，而不是靠 done
        # ——AI 判斷轉真人時引擎就結束（done=True），但真人接手後還要繼續
        # 用 /observe 餵對話、摘要要繼續往外推，所以不能一 done 就關。
        self.closed = threading.Event()
        # /observe 收到新句子就舉旗，背景 worker 看到就重算摘要
        self.summary_dirty = threading.Event()
        self.summary_worker: Optional[threading.Thread] = None
        # 同一 session 的摘要重算互斥（worker 與 /hangup 最後一次 flush）
        self.summary_lock = threading.Lock()
        # 最後一次收到 /observe 的時間（time.monotonic()），0 表示從未收到
        self.last_observe_at: float = 0.0


_sessions: Dict[str, Session] = {}
_sessions_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
# Queue-based DialogueIO（subclass 119 的 DialogueIO ABC）
# ═══════════════════════════════════════════════════════════════════════════

class QueuedIO119(DialogueIO):
    """
    把 say() 轉成 {"type": "chat", "role": "assistant", "text": ...} event。
    hear_text() 從 input_q 阻塞讀取；哨兵 END_FLOW_SENTINEL 直接回傳，
    由引擎 _hear() 偵測並拋 FlowAbortedError（收斂為 manual_end）。
    emit() 接 case_update / classification / stage_update / stopped 等 typed event。
    """

    def __init__(self, sess: Session) -> None:
        self._sess = sess

    def say(self, text: str) -> None:
        print(f"[SOP119 {self._sess.sess_id[:8]}] 受理員：{text}", flush=True)
        self._sess.output_q.put({"type": "chat", "role": "assistant", "text": text})

    def hear_text(self) -> str:
        self._sess._engine_ready.set()  # signal: engine ready for next caller text
        text = self._sess.input_q.get()
        self._sess._engine_ready.clear()
        if text != END_FLOW_SENTINEL:
            print(f"[SOP119 {self._sess.sess_id[:8]}] 報警人：{text}", flush=True)
        return text

    def emit(self, event: Dict[str, Any]) -> None:
        """非對話事件（case_update / classification / stage_update / stopped / error）。"""
        self._sess.output_q.put(event)


# ═══════════════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════════════

def _current_case_dict(sess: Session) -> Optional[Dict[str, Any]]:
    """
    取當下最新的 case dict（原始欄位名，與 /result 同一份）。
    engine 跑完後填 sess.case；跑的過程中 case 掛在 sess.engine.case 持續被更新。
    """
    case = sess.case
    if case is None and sess.engine is not None:
        case = getattr(sess.engine, "case", None)
    if case is None:
        return None
    try:
        return case.to_dict()
    except Exception:  # noqa: BLE001
        return None


def _inject_ids(sess: Session, case: Dict[str, Any]) -> Dict[str, Any]:
    """把 NLP session_id 與 A 側 call_uuid 併進 case dict，供對回 A/測試回饋。

    call_uuid 只在 A 有傳時才寫，避免舊資料多出一個 null 欄位。
    """
    case["session_id"] = sess.sess_id
    if sess.call_uuid:
        case["call_uuid"] = sess.call_uuid
    return case


def _rewrite_case_log(sess: Session) -> None:
    """把最新 case 蓋回 _run_engine 當初寫的那個 JSON 檔（含 /observe 期間的更新）。"""
    with sess.lock:
        path = sess.result_log_path
    if not path:
        return
    case = _current_case_dict(sess)
    if case is None:
        return
    _inject_ids(sess, case)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        print(f"[SOP119 {sess.sess_id[:8]}] ⚠️  重寫 case log 失敗：{exc}", flush=True)


# ── /observe：轉真人後繼續更新 case_summary ──────────────────────────────

# transcript 的 role → 摘要輸入的說話人標籤。
# "agent" 是 /observe 專用的新 role：橋接後接手的真人受理員。
_ROLE_LABELS_119 = {
    "assistant": "受理員",
    "caller":    "報警人",
    "agent":     "真人受理員",
}


def _transcript_lines_for_summary(
    case: CaseInfo119,
    max_turns: int,
) -> List[str]:
    """
    把 transcript 轉成標好說話人的字串 list，只取最後 max_turns 輪。

    不能直接用 case.caller_texts()：那個只撈 role == "caller"，
    真人受理員（role == "agent"）講的話會一句都進不到摘要裡。
    """
    lines: List[str] = []
    for turn in case.transcript or []:
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        label = _ROLE_LABELS_119.get(turn.get("role"))
        if label is None:
            continue
        lines.append(f"{label}：{text}")
    if max_turns > 0 and len(lines) > max_turns:
        lines = lines[-max_turns:]
    return lines


def _regenerate_summary(sess: Session) -> Optional[str]:
    """
    用「整段逐字稿（含真人受理員）＋轉接前已抽到的欄位」重算 case_summary。

    刻意不做欄位抽取：轉真人後結構化欄位改由受理員在前端手動填寫，
    這裡再跑 LLM 抽取只會跟人工輸入打架，也會多花一次 LLM 與地址 API。
    """
    engine = sess.engine
    if engine is None:
        return None
    case = getattr(engine, "case", None)
    if case is None:
        return None

    with engine._case_lock:
        lines = _transcript_lines_for_summary(case, OBSERVE_SUMMARY_MAX_TURNS)
        # 規則備援吃的是「未標註角色的報警人原話」：它沒欄位可用時會直接拿
        # 最後一句當摘要，餵標註過的全角色 lines 會抓到 AI 或受理員的問句。
        caller_texts = case.caller_texts()[-OBSERVE_SUMMARY_MAX_TURNS:]
        filled = case.filled_fields_for_summary()
    if not lines and not filled:
        return None

    summary = ""
    llm = getattr(engine, "_llm", None)
    if llm is not None:
        try:
            summary = llm.generate_summary(lines, filled)
        except Exception as exc:  # noqa: BLE001
            print(f"[SOP119 {sess.sess_id[:8]}] ⚠️  observe 摘要失敗：{exc}", flush=True)
            summary = ""
    if not summary:
        summary = build_fallback_summary(caller_texts, filled)
    return summary or None


def _apply_summary(sess: Session, summary: Optional[str]) -> bool:
    """寫回 case_summary 並同步 log 檔；有實際變動回 True。"""
    if not summary:
        return False
    engine = sess.engine
    case = getattr(engine, "case", None) if engine is not None else None
    if case is None:
        return False
    with engine._case_lock:
        if case.case_summary == summary:
            return False
        case.case_summary = summary
    _rewrite_case_log(sess)
    return True


def _flush_summary(sess: Session) -> bool:
    """重算並寫回摘要（同一 session 互斥）。"""
    with sess.summary_lock:
        return _apply_summary(sess, _regenerate_summary(sess))


def _summary_worker(sess: Session) -> None:
    """
    背景重算摘要，讓 /observe 本身能立刻回應、不被 LLM 卡住。

    節流：舉旗後先等 OBSERVE_DEBOUNCE_S 把連續句子併成一次，
    再確保與上次重算相隔至少 OBSERVE_MIN_INTERVAL_S。
    """
    last_run = 0.0
    while not sess.closed.is_set():
        if not sess.summary_dirty.wait(timeout=1.0):
            continue
        time.sleep(OBSERVE_DEBOUNCE_S)
        gap = OBSERVE_MIN_INTERVAL_S - (time.monotonic() - last_run)
        if gap > 0:
            time.sleep(gap)
        if sess.closed.is_set():
            break
        # 清旗要在取材之前：重算期間新進來的句子會再次舉旗、下一輪處理
        sess.summary_dirty.clear()
        try:
            changed = _flush_summary(sess)
        except Exception as exc:  # noqa: BLE001
            print(f"[SOP119 {sess.sess_id[:8]}] ⚠️  observe worker 例外：{exc}", flush=True)
            changed = False
        last_run = time.monotonic()
        if changed:
            print(f"[SOP119 {sess.sess_id[:8]}] 📝 observe 摘要已更新", flush=True)


def _ensure_summary_worker(sess: Session) -> None:
    """第一次 /observe 時才啟動背景 worker（沒轉真人的通話不會多開執行緒）。"""
    worker = sess.summary_worker
    if worker is not None and worker.is_alive():
        return
    with sess.lock:
        worker = sess.summary_worker
        if worker is not None and worker.is_alive():
            return
        worker = threading.Thread(
            target=_summary_worker,
            args=(sess,),
            daemon=True,
            name=f"sum119-{sess.sess_id[:8]}",
        )
        sess.summary_worker = worker
        worker.start()


def _stream_should_close(sess: Session, done_seen_at: Optional[float]) -> bool:
    """
    SSE 何時收線。

    - /hangup（sess.closed）→ 一律收線，這是機器A 唯一的收工訊號。
    - 引擎自己跑完（sess.done）不收線：AI 判斷轉真人時引擎就結束了，
      但真人接手後還會用 /observe 餵對話進來、摘要要繼續往外推。
    - 純防呆：引擎跑完後既沒 /observe 也沒 /hangup 就自己收掉，避免連線洩漏。
      首次 /observe 前給較短的 grace（等橋接接通），之後改用較長的閒置上限。
    """
    if sess.closed.is_set():
        return True
    if done_seen_at is None:
        return False
    if sess.last_observe_at > 0.0:
        return (time.monotonic() - sess.last_observe_at) > OBSERVE_IDLE_CLOSE_S
    return (time.monotonic() - done_seen_at) > OBSERVE_GRACE_S


def _drain_now(sess: Session) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    while True:
        try:
            out.append(sess.output_q.get_nowait())
        except queue.Empty:
            break
    return out


def _wait_for_turn_complete(sess: Session, timeout: float = 60.0) -> List[Dict[str, Any]]:
    """
    Block 直到 engine 回到下一個 hear_text 或 session done，再 drain output_q。
    取代固定 timeout，避免 LLM 慢時回空 outputs（沿用 110 Issue #2 修法）。
    """
    sess._engine_ready.wait(timeout=timeout)
    return _drain_now(sess)


def _events_to_outputs(events: List[Dict[str, Any]]) -> List[str]:
    """從事件列表抽出 assistant 對話字串（給 110-style outputs 欄位）。"""
    return [
        e.get("text", "")
        for e in events
        if e.get("type") == "chat" and e.get("role") == "assistant"
    ]


def _run_engine(sess: Session) -> None:
    io = QueuedIO119(sess)
    engine = SopEngine119(
        io,
        main_classifier=_shared_main_classifier,
        sub_classifiers=_shared_sub_classifiers,
        llm_extractor=_shared_llm_extractor,
        debug=False,
    )
    # 模糊比對取樣用；讓樣本能對回 case119_*.json 這通完整對話。
    engine._session_tag = sess.sess_id[:8]
    sess.engine = engine
    try:
        engine.run()  # 新版 run() 無參數；內部 try/except 收斂所有終止狀態
        sess.case = engine.case
        # 引擎已把終止狀態寫入 case.result（dispatched / ohca_transfer /
        # human_transfer / manual_end / error）；error 時同步反映到 sess.error
        if sess.case is not None and sess.case.result == "error":
            sess.error = "engine_error"
    except Exception as exc:  # noqa: BLE001
        # 走不到這（SopEngine119.run 內部已 catch），保留當保險
        sess.error = str(exc)
        sess.case = getattr(engine, "case", None)
        print(f"[SOP119 {sess.sess_id[:8]}] ⚠️  engine 例外：{exc}", flush=True)
    finally:
        sess.done.set()
        sess._engine_ready.set()  # 解開任何 _wait_for_turn_complete
        # case JSON log
        if sess.case is not None:
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_path = os.path.join(LOG_DIR, f"case119_{ts}_{sess.sess_id[:8]}.json")
                with sess.lock:
                    sess.result_log_path = log_path
                    with open(log_path, "w", encoding="utf-8") as f:
                        json.dump(_inject_ids(sess, sess.case.to_dict()), f,
                                  ensure_ascii=False, indent=2)
                print(f"[SOP119 {sess.sess_id[:8]}] 📝 case JSON → {log_path}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[SOP119 {sess.sess_id[:8]}] ⚠️  寫 case log 失敗：{exc}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class InputPayload(BaseModel):
    text: str


class ObservePayload(BaseModel):
    text: str
    role: str   # "caller"（民眾）或 "agent"（接手的真人受理員）


class SessionNewPayload(BaseModel):
    # 機器 A（交換機/apiserver）的通話 UUID，選填。傳了就會寫進 case log 的
    # call_uuid 欄，讓 log 對回 A 側與測試回饋表。不傳維持原行為。
    call_uuid: Optional[str] = None


@app.post("/session/new")
def new_session(payload: Optional[SessionNewPayload] = Body(default=None)):
    """新通話：開 engine 背景 thread，等到第一個 hear_text 出現再 return。

    payload 選填；機器 A 若帶入 call_uuid，會寫進 case log 供對回。
    無 body（舊呼叫方式）時 payload=None，行為不變。
    """
    sess_id = str(uuidlib.uuid4())
    sess = Session(sess_id)
    if payload is not None:
        sess.call_uuid = payload.call_uuid
    with _sessions_lock:
        _sessions[sess_id] = sess

    threading.Thread(
        target=_run_engine, args=(sess,), daemon=True, name=f"sop119-{sess_id[:8]}"
    ).start()

    events = _wait_for_turn_complete(sess, timeout=30.0)
    return {
        "session_id": sess_id,
        "call_uuid": sess.call_uuid,
        "outputs": _events_to_outputs(events),
        "events": events,
        "done": sess.done.is_set(),
    }


@app.post("/session/{sess_id}/input")
def push_input(sess_id: str, payload: InputPayload):
    """餵一句報警人文字。回到下一個 hear_text 或 done 才 return。"""
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    if sess.done.is_set():
        raise HTTPException(status_code=409, detail="session already done")

    sess._engine_ready.clear()  # 防 stale-ready race（Issue #2 修法）
    sess.input_q.put(payload.text)
    events = _wait_for_turn_complete(sess, timeout=60.0)

    return {
        "outputs": _events_to_outputs(events),
        "events": events,
        "done": sess.done.is_set(),
        "error": sess.error,
    }


@app.post("/session/{sess_id}/observe")
def observe_session(sess_id: str, payload: ObservePayload):
    """
    轉真人後的「只聽不說」管道：收下一句對話、繼續更新 case_summary。

    - 不看 done：AI 自己判斷轉真人時引擎已結束，受理員手動介入時引擎還活著，
      兩種情況都要能用，所以這裡不擋（110 舊版擋 done 的規矩不沿用）。
    - 不產生 AI 回覆、不設 done、不做欄位抽取（欄位轉真人後由前端人工填寫）。
    - LLM 丟到背景 worker 跑，本端點只寫 transcript 就回，不卡住通話。
    - 更新後的摘要照原路從 /session/{id}/case/stream 推出去，機器A 不必改。
    """
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    role = (payload.role or "").strip().lower()
    if role not in ("caller", "agent"):
        raise HTTPException(
            status_code=400, detail="role must be 'caller' or 'agent'"
        )

    engine = sess.engine
    if engine is None:
        raise HTTPException(status_code=500, detail="engine state lost")

    text = (payload.text or "").strip()
    if text:
        with engine._case_lock:
            engine.case.transcript.append({"role": role, "text": text})
        print(f"[SOP119 {sess.sess_id[:8]}] [轉接·{role}] {text}", flush=True)

    sess.last_observe_at = time.monotonic()
    _ensure_summary_worker(sess)
    if text:
        sess.summary_dirty.set()

    with engine._case_lock:
        transcript_size = len(engine.case.transcript)
    return {"accepted": True, "role": role, "transcript_size": transcript_size}


@app.post("/session/{sess_id}/hangup")
def hangup_session(sess_id: str):
    """強制結束：input_q.put(END_FLOW_SENTINEL) 讓引擎 _hear() 拋 FlowAbortedError。"""
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    sess.input_q.put(END_FLOW_SENTINEL)
    sess.done.wait(timeout=5.0)
    # 機器A 的收工訊號：停掉 observe worker、收掉 SSE
    sess.closed.set()
    sess.summary_dirty.set()  # 叫醒 worker 讓它看到 closed 後退出
    # observe 期間還有沒算完的摘要，這裡補算一次，讓緊接著的 /result 拿到最新版
    if sess.last_observe_at > 0.0:
        try:
            _flush_summary(sess)
        except Exception as exc:  # noqa: BLE001
            print(f"[SOP119 {sess.sess_id[:8]}] ⚠️  hangup 摘要 flush 失敗：{exc}", flush=True)
    return {"done": sess.done.is_set()}


@app.get("/session/{sess_id}/result")
def get_result(sess_id: str):
    """拿 CaseInfo119 完整案件 JSON。"""
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not sess.done.is_set():
        return {"done": False}
    return {
        "done": True,
        "error": sess.error,
        "case": sess.case.to_dict() if sess.case else None,
    }


@app.get("/session/{sess_id}/output")
def poll_output(sess_id: str):
    """輪詢未消化的 events（無等待）。"""
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    events = _drain_now(sess)
    return {
        "outputs": _events_to_outputs(events),
        "events": events,
        "done": sess.done.is_set(),
    }


@app.get("/session/{sess_id}/case/stream")
async def stream_case(sess_id: str):
    """
    SSE 長連線：case 一有更新推一筆 `case_updated`，案子結束推一筆 `done` 後關閉。

    - 回 HTTP 200 + Content-Type: text/event-stream
    - `data` 為壓成一行的完整 case JSON（原始欄位名，與 /result 同一份）
    - case 任一欄位變動即推一筆 `case_updated`（不 gate，首筆是否要 act_sub_class
      有值由機器A自行過濾；我方 gate 會把過程事件整串吞掉，故不做）
    - 每 ~15 秒送一行 `: keepalive` 防中間層斷線
    - 收線時機看 /hangup（sess.closed），不是看引擎是否跑完（sess.done）——
      轉真人後 /observe 還會繼續更新摘要，詳見 _stream_should_close()
    """
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    POLL_INTERVAL = 0.3      # 秒；輪詢 case 變動的間隔
    KEEPALIVE_INTERVAL = 15.0

    def _dumps(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    async def event_gen():
        # 以「全空 case」當基準，連上瞬間那份還沒抽任何欄位的空 case 不推，
        # 之後只要有實際變動（含 transcript）就推。
        last_serialized: Optional[str] = _dumps(CaseInfo119().to_dict())
        idle = 0.0
        done_seen_at: Optional[float] = None
        while True:
            case = _current_case_dict(sess)
            # case 任一欄位變動就推（不 gate，避免把過程事件整串吞掉）
            if case is not None:
                serialized = _dumps(case)
                if serialized != last_serialized:
                    last_serialized = serialized
                    yield f"event: case_updated\ndata: {serialized}\n\n"
                    idle = 0.0

            if sess.done.is_set() and done_seen_at is None:
                done_seen_at = time.monotonic()

            if _stream_should_close(sess, done_seen_at):
                final = _current_case_dict(sess)
                payload = {"done": True, "error": sess.error, "case": final}
                yield f"event: done\ndata: {_dumps(payload)}\n\n"
                return

            await asyncio.sleep(POLL_INTERVAL)
            idle += POLL_INTERVAL
            if idle >= KEEPALIVE_INTERVAL:
                idle = 0.0
                yield ": keepalive\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/schema/case-fields/labels")
def case_field_labels():
    """CaseInfo119 欄位 key → 中文 label（不含 transcript）。"""
    return _CASE_FIELD_LABELS_119


@app.get("/health")
def health():
    return {
        "status": "ok",
        "sessions": len(_sessions),
        "llm_loaded": _shared_llm_extractor is not None,
        "main_classifier_loaded": _shared_main_classifier is not None,
        "sub_classifier_loaded": _shared_sub_classifiers is not None,
    }
