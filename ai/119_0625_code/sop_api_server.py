"""
sop_api_server_119.py — HTTP API wrapper around SopEngine119 (119 救護報案)

部署：
    cd /home/aitop4/nlp_cyberon_server/ai/119_0625_code
    /home/aitop4/project/110llm/110LLM_0526_TW-110-Model_V3.0/venv/bin/uvicorn \
      sop_api_server_119:app --host 0.0.0.0 --port 8200

API 介面：跟 110LLM 的 sop_api_server.py 一樣的 endpoint 設計：
  - POST /session/new                    → 起新通話
  - POST /session/{id}/input             → 餵 caller 文字
  - POST /session/{id}/hangup            → 強制結束（送 None EOF）
  - GET  /session/{id}/result            → 拿 case JSON
  - GET  /session/{id}/output            → 輪詢未消化 events
  - GET  /schema/case-fields/labels      → CaseInfo119 欄位中文對照
  - GET  /health

對比 110LLM 版（差異）：
  - 引擎換成 SopEngine119（救護 SOP，OHCA 自動轉人工）
  - DialogueIO `hear_text()` 沒 prompt 參數
  - 沒 EndOfInput；本檔自定 `_EngineEndCall` 透過 input_q.put(None) 觸發
  - 輸出 queue 是 typed events（chat / case_update / classification / stage_update / stopped / error），不是純字串
    `/input` 回應同時給 `outputs: [string]`（過濾出 assistant chat）跟 `events: [dict]`（完整事件）
  - 沒 /observe（119 沒對應 _llm_post_extract）
  - 沒 /case/stream
  - 模型暫用 110 的 Qwen3.6-35B GGUF（透過 GGUF_MODEL_PATH env）；主/子分類器無 TW-119 模型 → None 降級
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import uuid as uuidlib
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

# ── 確保可以 import 本目錄的模組 ──────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from case_field_labels_119 import LABELS as _CASE_FIELD_LABELS_119
from case_info_119 import CaseInfo119
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

# ── LLM extractor 暫用 110 的 Qwen3.6-35B GGUF ──────────────────────────
GGUF_MODEL_PATH = os.environ.get(
    "GGUF_MODEL_PATH",
    "/home/aitop4/project/110llm/110LLM_Qwen3.6-35B/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_S.gguf",
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
    "/home/aitop4/nlp_cyberon_server/ai/",
)
# BERT 跑 CPU 還是 GPU；預設 CPU 把 VRAM 留給 Qwen3.6-35B GGUF（跟 110 慣例一致）
BERT_DEVICE = os.environ.get("BERT_DEVICE", "cpu")

# 案件結構化 JSON log 寫出位置
LOG_DIR = os.environ.get("LOG_DIR", "/home/aitop4/nlp_cyberon_server/log_119")


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
        from classifier_with_llm import build_classifiers
        # vendor build_classifiers 只註冊「救護」+「火警」兩個子分類器，
        # 緊急救援/其他案類即使有 BERT 也不會自動 register（vendor 行為，未改）。
        print(f"⏳ 載入 119 子分類器 from {BERT_MODELS_BASE} (device={BERT_DEVICE})…", flush=True)
        _shared_sub_classifiers = build_classifiers(
            models_base=BERT_MODELS_BASE,
            llm_model_path=None,   # 子分類器內建的 LLM reviewer 用不到，避免重複載 GGUF
            device=BERT_DEVICE,
            enable_llm=False,
        )
        print("✅ 119 子分類器就緒", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  119 子分類器跳過：{exc}", flush=True)

app = FastAPI(title="SopEngine119 API", version="1.0-119")


# ═══════════════════════════════════════════════════════════════════════════
# 自定義 EndOfCall（119 引擎沒這個 exception；用 input_q.put(None) + 此例外觸發）
# ═══════════════════════════════════════════════════════════════════════════

class _EngineEndCall(Exception):
    """報警人主動掛斷（POST /hangup）時注入。"""


# ═══════════════════════════════════════════════════════════════════════════
# Session 狀態
# ═══════════════════════════════════════════════════════════════════════════

class Session:
    def __init__(self, sess_id: str) -> None:
        self.sess_id = sess_id
        # 119 input_q 只進字串（或 None EOF）
        self.input_q: "queue.Queue[Optional[str]]" = queue.Queue()
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
        # SopEngine119.run() 內部會把 _EngineEndCall 當一般 Exception → result="error"。
        # 用旗標讓 _run_engine 在 run() 跑完後覆寫成 "caller_hangup"。
        self._hangup_triggered = False


_sessions: Dict[str, Session] = {}
_sessions_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
# Queue-based DialogueIO（subclass 119 的 DialogueIO ABC）
# ═══════════════════════════════════════════════════════════════════════════

class QueuedIO119(DialogueIO):
    """
    把 say() 轉成 {"type": "chat", "role": "assistant", "text": ...} event。
    hear_text() 從 input_q 阻塞讀取；遇到 None 拋 _EngineEndCall。
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
        if text is None:
            self._sess._hangup_triggered = True
            raise _EngineEndCall
        print(f"[SOP119 {self._sess.sess_id[:8]}] 報警人：{text}", flush=True)
        return text

    def emit(self, event: Dict[str, Any]) -> None:
        """非對話事件（case_update / classification / stage_update / stopped / error）。"""
        self._sess.output_q.put(event)


# ═══════════════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════════════

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
    sess.engine = engine
    try:
        engine.run()  # 119 run() 沒參數；內部 try/except Exception 吞光所有例外
        sess.case = engine.case
        # SopEngine119 把所有 Exception（含我們的 _EngineEndCall）標成 result="error"，覆寫
        if sess._hangup_triggered:
            sess.error = "caller_hangup"
            if sess.case is not None:
                sess.case.result = "caller_hangup"
    except Exception as exc:  # noqa: BLE001
        # 走不到這（SopEngine119 內部已 catch），保留當保險
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
                        json.dump(asdict(sess.case), f, ensure_ascii=False, indent=2)
                print(f"[SOP119 {sess.sess_id[:8]}] 📝 case JSON → {log_path}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[SOP119 {sess.sess_id[:8]}] ⚠️  寫 case log 失敗：{exc}", flush=True)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

class InputPayload(BaseModel):
    text: str


@app.post("/session/new")
def new_session():
    """新通話：開 engine 背景 thread，等到第一個 hear_text 出現再 return。"""
    sess_id = str(uuidlib.uuid4())
    sess = Session(sess_id)
    with _sessions_lock:
        _sessions[sess_id] = sess

    threading.Thread(
        target=_run_engine, args=(sess,), daemon=True, name=f"sop119-{sess_id[:8]}"
    ).start()

    events = _wait_for_turn_complete(sess, timeout=30.0)
    return {
        "session_id": sess_id,
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


@app.post("/session/{sess_id}/hangup")
def hangup_session(sess_id: str):
    """強制結束：input_q.put(None) 讓 QueuedIO119.hear_text 拋 _EngineEndCall。"""
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    sess.input_q.put(None)
    sess.done.wait(timeout=5.0)
    return {"done": sess.done.is_set()}


@app.get("/session/{sess_id}/result")
def get_result(sess_id: str):
    """拿 CaseInfo119 (16 + transcript 欄位)。"""
    with _sessions_lock:
        sess = _sessions.get(sess_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not sess.done.is_set():
        return {"done": False}
    return {
        "done": True,
        "error": sess.error,
        "case": asdict(sess.case) if sess.case else None,
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


@app.get("/schema/case-fields/labels")
def case_field_labels():
    """CaseInfo119 欄位 key → 中文 label（17 條，不含 transcript）。"""
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
