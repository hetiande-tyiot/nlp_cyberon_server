"""
app_119.py
━━━━━━━━━━
119 報案受理 SOP — Streamlit 互動介面

版面配置
--------
左欄 (2/3)：對話氣泡 + 底部輸入框
右欄 (1/3)：分類結果徽章 + 案情欄位面板 + 案情摘要

線程架構
--------
  主線程  : Streamlit UI（display + user input）
  工作線程 : SopEngine119.run()（阻塞式 hear_text）

  input_q  : Queue[str]  — UI → worker
  output_q : Queue[dict] — worker → UI

啟動方式
--------
  cd /root/work/119
  streamlit run app_119.py
"""

from __future__ import annotations

import html
import queue
import sys
import threading
import time
from typing import Any, Dict, List, Optional

import streamlit as st

try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
except Exception:  # noqa: BLE001
    st_autorefresh = None  # type: ignore

# ─── 頁面配置（必須最先執行）────────────────────────────────────────────────
st.set_page_config(
    page_title="119 智能報案受理系統",
    page_icon="🚑",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── 工作目錄修正（確保相對 import 可找到同目錄模組）────────────────────────
import os
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# ─── 全域模型快取（跨 Streamlit rerun 保持模型實例）─────────────────────────
@st.cache_resource(show_spinner="正在載入模型，請稍候…")
def _load_models():
    """
    載入所有模型並返回 (main_clf, sub_clf, llm)。
    任一模型載入失敗時靜默降級為 None（對話流程仍可運行）。
    """
    main_clf = None
    sub_clf  = None
    llm      = None

    try:
        from inference_pipeline import HierarchicalClassifier
        main_clf = HierarchicalClassifier()
    except Exception as e:
        st.warning(f"主分類器未能載入（跳過）：{e}")

    try:
        from classifier_with_llm import build_classifiers
        sub_clf = build_classifiers(enable_llm=False)
    except Exception as e:
        st.warning(f"子分類器未能載入（跳過）：{e}")

    try:
        from llm_extractor_119 import LLMExtractor119
        llm = LLMExtractor119()
    except Exception as e:
        st.warning(f"LLM 未能載入（跳過）：{e}")

    return main_clf, sub_clf, llm


# ─── 樣式 ────────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* 整體背景 */
[data-testid="stAppViewContainer"] {
    background: #f0f4f8;
}

/* 左欄對話區 */
.chat-container {
    background: #ffffff;
    border-radius: 12px;
    padding: 16px 20px;
    min-height: 480px;
    max-height: 560px;
    overflow-y: auto;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    margin-bottom: 12px;
}

/* 助手氣泡 */
.bubble-assistant {
    background: #e8f4fd;
    border-left: 4px solid #1976d2;
    border-radius: 0 10px 10px 0;
    padding: 10px 14px;
    margin: 8px 0;
    max-width: 88%;
    font-size: 15px;
    line-height: 1.6;
    color: #1a1a2e;
}

/* 報警人氣泡 */
.bubble-caller {
    background: #fff3e0;
    border-right: 4px solid #e65100;
    border-radius: 10px 0 0 10px;
    padding: 10px 14px;
    margin: 8px 0 8px auto;
    max-width: 88%;
    font-size: 15px;
    line-height: 1.6;
    text-align: right;
    color: #1a1a2e;
}

/* 系統提示（OHCA / 結束等） */
.bubble-system {
    background: #fce4ec;
    border: 1.5px solid #e91e63;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 10px auto;
    max-width: 92%;
    font-size: 14px;
    color: #880e4f;
    text-align: center;
}

/* 右欄面板 */
.panel-card {
    background: #ffffff;
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    margin-bottom: 14px;
}

/* 欄位標籤 */
.field-label {
    font-size: 12px;
    color: #666;
    margin-bottom: 2px;
}

/* 欄位值 */
.field-value {
    font-size: 14px;
    font-weight: 600;
    color: #1a1a2e;
    padding: 4px 0;
    border-bottom: 1px solid #f0f0f0;
    margin-bottom: 6px;
    min-height: 22px;
}

/* 空值 */
.field-empty {
    font-size: 14px;
    color: #bbb;
    font-style: italic;
}

/* 徽章 */
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    margin: 2px 4px 2px 0;
}
.badge-main  { background:#e3f2fd; color:#0d47a1; }
.badge-sub   { background:#f3e5f5; color:#6a1b9a; }
.badge-ohca  { background:#ffebee; color:#b71c1c; }
.badge-ok    { background:#e8f5e9; color:#1b5e20; }
.badge-kw    { background:#fff8e1; color:#e65100; }

/* OHCA 警示橫幅 */
.ohca-banner {
    background: #b71c1c;
    color: white;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 15px;
    font-weight: 700;
    text-align: center;
    margin-bottom: 12px;
    animation: pulse 1.5s infinite;
}

@keyframes pulse {
    0%   { opacity: 1; }
    50%  { opacity: 0.75; }
    100% { opacity: 1; }
}

/* 進度步驟 */
.stage-step {
    display: flex;
    align-items: center;
    padding: 4px 0;
    font-size: 13px;
    color: #999;
}
.stage-step.active {
    color: #1976d2;
    font-weight: 600;
}
.stage-step.done {
    color: #388e3c;
}
.stage-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #ccc;
    margin-right: 8px;
    flex-shrink: 0;
}
.stage-dot.active { background: #1976d2; }
.stage-dot.done   { background: #388e3c; }

/* 輸入區 */
.input-area {
    background: #fff;
    border-radius: 10px;
    padding: 12px 16px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.07);
}

/* AI 分析報告 */
.report-panel {
    background: #fafafa;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 14px;
    line-height: 1.75;
    max-height: 420px;
    overflow-y: auto;
    white-space: pre-wrap;
    font-family: "Courier New", "Noto Sans TC", monospace;
    color: #222;
}
</style>
"""


# ─── 流程階段定義（用於右欄進度顯示）────────────────────────────────────────

_STAGE_LABELS: List[tuple[str, str]] = [
    ("initial",                  "詢問火災/救護"),
    ("main_classified",          "主類別分類完成"),
    ("location_district_reask",  "補問行政區"),
    ("location_road_reask",      "補問道路"),
    ("location_number_reask",    "補問門牌號"),
    ("location_intersection_reask", "補問交叉路口"),
    ("location_highway_reask",   "補問高速公路位置"),
    ("location_validating",      "地址資料校驗"),
    ("location_validation_reask", "重新確認完整地址"),
    ("救護_location",            "確認地址"),
    ("救護_location_confirm",    "地址確認中"),
    ("救護_sub_classified",      "子類別分類完成"),
    ("車禍_safety_reminder",     "車禍安全叮嚀"),
    ("急病_patient_count",       "詢問傷病患人數"),
    ("精神異常_patient_count",   "詢問傷病患人數"),
    ("打架受傷_patient_count",   "詢問傷病患人數"),
    ("救護_vital_1",             "確認意識"),
    ("救護_vital_2",             "確認呼吸"),
    ("救護_vital_3",             "確認腹部起伏"),
    ("一般受傷_injury_cause",    "詢問受傷原因"),
    ("一般受傷_injury_detail",   "詢問受傷部位/傷勢"),
    ("一般受傷_tocc",            "詢問 TOCC"),
    ("路倒_medical_history",     "詢問過去病史"),
    ("路倒_collapse_cause",      "詢問路倒原因"),
    ("路倒_tocc",                "詢問 TOCC"),
    ("救護_patient_1",           "詢問性別/年齡"),
    ("救護_patient_2",           "詢問事發原因"),
    ("救護_patient_3",           "詢問目前狀況"),
    ("救護_summary_confirm",     "案情摘要回填"),
    ("救護_caller_info",         "收集報案人訊息"),
    ("火警_location",            "確認地址"),
    ("火警_location_confirm",    "地址確認中"),
    ("火警_route_1",             "判斷是否建物火災"),
    ("火警_route_2",             "判斷燃燒物類型"),
    ("火警_A_building_type",     "建物：建築物類型"),
    ("火警_A_flame",             "建物：有無火焰"),
    ("火警_A_smoke",             "建物：濃煙顏色"),
    ("火警_A_explosion",         "建物：有無爆炸"),
    ("火警_A_spread",            "建物：延燒可能"),
    ("火警_A_trapped",           "建物：有無受困"),
    ("火警_A_floors",            "建物：建物樓層"),
    ("火警_A_fire_floor",        "建物：起火樓層"),
    ("火警_A_structure",         "建物：建物構造"),
    ("火警_A_area",              "建物：延燒面積"),
    ("火警_A_access",            "建物：巷道與水源"),
    ("火警_B1_subtype",          "交通工具細類"),
    ("火警_B2_subtype",          "山林田野細類"),
    ("火警_C_subtype",           "輕微火警細類"),
    ("火警_safety",              "安全提示"),
    ("火警_summary_confirm",     "案情摘要回填"),
    ("火警_caller_info",         "收集報案人訊息"),
    ("緊急救援_location",        "確認地址"),
    ("緊急救援_location_confirm", "地址確認中"),
    ("緊急救援_incident",        "詢問事發經過"),
    ("緊急救援_summary_confirm", "案情摘要回填"),
    ("緊急救援_caller_info",     "收集報案人訊息"),
    ("局內回報_need",            "確認回報需求"),
    ("局內回報_location",        "取得現場地址"),
    ("局內回報_location_reask",  "補問完整地址"),
    ("局內回報_field_content",   "登記現場回報"),
    ("局內回報_support_detail",  "確認支援車輛"),
    ("局內回報_support_confirm", "覆誦支援內容"),
    ("局內回報_more",            "確認其他需求"),
    ("completed",                "流程完成"),
    ("ohca_transfer",            "OHCA 轉人工"),
    ("human_transfer",           "轉接專人"),
    ("manual_end",               "操作員結束"),
]

_STAGE_ORDER = {s: i for i, (s, _) in enumerate(_STAGE_LABELS)}

_STAGE_LABELS_DICT: Dict[str, str] = dict(_STAGE_LABELS)

_RESCUE_PREFIX: List[str] = [
    "initial", "main_classified",
    "救護_location",
    "location_district_reask", "location_intersection_reask",
    "location_highway_reask", "location_validating",
    "location_validation_reask",
    "救護_location_confirm", "救護_sub_classified",
]
_RESCUE_VITALS: List[str] = ["救護_vital_1", "救護_vital_2", "救護_vital_3"]
_RESCUE_SUFFIX: List[str] = [
    "救護_patient_1", "救護_patient_2", "救護_patient_3",
    "救護_summary_confirm", "救護_caller_info", "completed",
    "ohca_transfer", "human_transfer",
]
_FIRE_PREFIX: List[str] = [
    "initial", "main_classified",
    "火警_location",
    "location_district_reask", "location_intersection_reask",
    "location_highway_reask", "location_validating",
    "location_validation_reask",
    "火警_location_confirm",
    "火警_route_1", "火警_route_2",
]
_FIRE_BRANCH_STAGES: Dict[str, List[str]] = {
    "A": [
        "火警_A_building_type", "火警_A_flame", "火警_A_smoke",
        "火警_A_explosion", "火警_A_spread", "火警_A_trapped",
        "火警_A_floors", "火警_A_fire_floor", "火警_A_structure",
        "火警_A_area", "火警_A_access",
    ],
    "B1": ["火警_B1_subtype"],
    "B2": ["火警_B2_subtype"],
    "C": ["火警_C_subtype"],
}
_FIRE_SUFFIX: List[str] = [
    "火警_safety", "火警_summary_confirm", "火警_caller_info",
    "completed", "human_transfer",
]
_EMERGENCY_STAGES: List[str] = [
    "initial", "main_classified",
    "緊急救援_location",
    "location_district_reask", "location_intersection_reask",
    "location_highway_reask", "location_validating",
    "location_validation_reask",
    "緊急救援_location_confirm",
    "緊急救援_incident",
    "緊急救援_summary_confirm", "緊急救援_caller_info",
    "completed", "human_transfer",
]
_INTERNAL_REPORT_STAGES: List[str] = [
    "initial", "main_classified", "局內回報_need",
    "局內回報_location", "局內回報_location_reask",
    "局內回報_field_content", "局內回報_support_detail",
    "局內回報_support_confirm", "局內回報_more", "completed",
]
_SUB_PRE_VITAL: Dict[str, List[str]] = {
    "車禍":    ["車禍_safety_reminder"],
    "急病":    ["急病_patient_count"],
    "精神異常": ["精神異常_patient_count"],
}
_SUB_POST_VITAL: Dict[str, List[str]] = {
    "一般受傷": ["一般受傷_injury_cause", "一般受傷_injury_detail", "一般受傷_tocc"],
    "路倒":    ["路倒_medical_history", "路倒_collapse_cause", "路倒_tocc"],
}


def _get_visible_stages(
    main_cat: Optional[str],
    sub_cat: Optional[str],
    fire_tab: Optional[str] = None,
) -> List[tuple[str, str]]:
    """根據主類別和次類別返回應顯示的流程階段列表。"""
    if main_cat is None:
        keys = [s for s, _ in _STAGE_LABELS]
    elif main_cat == "火警":
        prefix = list(_FIRE_PREFIX)
        if fire_tab == "A":
            prefix = [k for k in prefix if k != "火警_route_2"]
        keys = prefix + _FIRE_BRANCH_STAGES.get(fire_tab or "", []) + _FIRE_SUFFIX
    elif main_cat == "緊急救援":
        keys = _EMERGENCY_STAGES
    elif main_cat == "局內回報":
        keys = _INTERNAL_REPORT_STAGES
    elif main_cat != "救護":
        keys = ["initial", "main_classified", "completed"]
    else:
        pre  = _SUB_PRE_VITAL.get(sub_cat, [])  if sub_cat else []
        post = _SUB_POST_VITAL.get(sub_cat, []) if sub_cat else []
        keys = _RESCUE_PREFIX + pre + _RESCUE_VITALS + post + _RESCUE_SUFFIX
    return [(k, _STAGE_LABELS_DICT[k]) for k in keys if k in _STAGE_LABELS_DICT]


def _stage_status(
    current_stage: str,
    target_stage: str,
    stage_keys: Optional[List[str]] = None,
) -> str:
    """返回 'done' / 'active' / 'pending'。"""
    order = (
        {stage: index for index, stage in enumerate(stage_keys)}
        if stage_keys
        else _STAGE_ORDER
    )
    c = order.get(current_stage, -1)
    t = order.get(target_stage, -1)
    if c > t:
        return "done"
    if c == t:
        return "active"
    return "pending"


# ─── 輔助渲染函式 ────────────────────────────────────────────────────────────

def _val_html(val: Any, bool_map: Optional[Dict] = None) -> str:
    """將欄位值渲染成 HTML（空值顯示灰色佔位）。"""
    if val is None:
        return '<span class="field-empty">—</span>'
    if isinstance(val, bool):
        if bool_map:
            return bool_map.get(val, str(val))
        return "是" if val else "否"
    return str(val)


def _render_bubble(role: str, text: str) -> str:
    if role == "assistant":
        return f'<div class="bubble-assistant">🎙️ {text}</div>'
    elif role == "caller":
        return f'<div class="bubble-caller">{text} 📞</div>'
    else:
        return f'<div class="bubble-system">{text}</div>'


# ─── Session State 初始化 ─────────────────────────────────────────────────────

def _init_session():
    defaults = {
        "messages":           [],
        "case_data":          {},
        "flow_stage":         "initial",
        "classification":     {
            "main": None, "main_conf": None,
            "sub": None,  "sub_conf":  None,
            "sub_source": None,
        },
        "is_ohca":            False,
        "is_done":            False,
        "is_bridged":         False,
        "done_result":        None,
        "input_q":            None,
        "output_q":           None,
        "engine":             None,
        "worker_thread":      None,
        "worker_started":     False,
        "awaiting_engine":    False,
        "awaiting_started_at": None,
        "analysis_report":    None,
        "analysis_report_error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _apply_output_event(event: Dict[str, Any]) -> None:
    """將 worker 事件寫入 session_state。"""
    etype = event.get("type")

    if etype == "chat":
        st.session_state["messages"].append({
            "role": event["role"],
            "text": event["text"],
        })
        if event.get("role") == "assistant":
            st.session_state["awaiting_engine"] = False
            st.session_state["awaiting_started_at"] = None

    elif etype == "case_update":
        case_dict = event.get("case", {}) or {}
        st.session_state["case_data"]  = case_dict
        st.session_state["flow_stage"] = case_dict.get("flow_stage", "initial")
        st.session_state["is_ohca"]    = case_dict.get("is_ohca", False)

    elif etype == "classification":
        st.session_state["classification"] = {
            "main":       event.get("main"),
            "main_conf":  event.get("main_conf"),
            "sub":        event.get("sub"),
            "sub_conf":   event.get("sub_conf"),
            "sub_source": event.get("sub_source"),
        }

    elif etype == "stage_update":
        st.session_state["flow_stage"] = event.get("stage", "initial")

    elif etype == "stopped":
        result = event.get("result")
        st.session_state["done_result"] = result
        st.session_state["awaiting_engine"] = False
        st.session_state["awaiting_started_at"] = None
        if result in ("ohca_transfer", "human_transfer"):
            st.session_state["is_bridged"] = True
            st.session_state["is_done"] = False
        else:
            st.session_state["is_done"] = True

    elif etype == "error":
        st.session_state["messages"].append({
            "role": "system",
            "text": f"⚠️ 系統錯誤：{event.get('message', '')}",
        })
        st.session_state["is_done"] = True
        st.session_state["awaiting_engine"] = False
        st.session_state["awaiting_started_at"] = None


def _drain_output_q() -> int:
    output_q: Optional[queue.Queue] = st.session_state.get("output_q")
    if output_q is None:
        return 0
    drained = 0
    while True:
        try:
            event = output_q.get_nowait()
        except queue.Empty:
            break
        _apply_output_event(event)
        drained += 1
    return drained


def _wait_for_engine_events(
    *,
    reason: str,
    max_wait_s: float = 20.0,
    idle_grace_s: float = 0.45,
) -> int:
    """
    阻塞等待 worker 推送事件（參考 110 streamlit_app.py）。
    LLM 抽取/摘要生成可能需數秒，必須等到 case_update 等事件抵達。
    """
    worker = st.session_state.get("worker_thread")
    output_q: Optional[queue.Queue] = st.session_state.get("output_q")
    if output_q is None:
        return 0
    if not (worker and worker.is_alive()):
        return _drain_output_q()

    deadline = time.perf_counter() + max(0.0, float(max_wait_s))
    saw_event = False
    saw_assistant = False
    last_event_at = 0.0
    drained = 0

    while time.perf_counter() < deadline:
        remaining = deadline - time.perf_counter()
        timeout_s = min(0.10, max(0.01, remaining))
        try:
            event = output_q.get(timeout=timeout_s)
        except queue.Empty:
            if saw_event and last_event_at and (time.perf_counter() - last_event_at) >= idle_grace_s:
                break
            if reason == "user_turn" and saw_assistant and last_event_at:
                if (time.perf_counter() - last_event_at) >= idle_grace_s:
                    break
            continue

        _apply_output_event(event)
        drained += 1
        saw_event = True
        last_event_at = time.perf_counter()
        if event.get("type") == "chat" and event.get("role") == "assistant":
            saw_assistant = True
        if event.get("type") == "stopped" or st.session_state.get("is_done"):
            break

    drained += _drain_output_q()
    return drained


def _start_worker():
    """啟動工作線程（僅在尚未啟動時執行）。"""
    if st.session_state["worker_started"]:
        return

    main_clf, sub_clf, llm = _load_models()

    from sop_119_engine import SopEngine119, QueueDialogueIO

    input_q:  queue.Queue[str]         = queue.Queue()
    output_q: queue.Queue[Dict]        = queue.Queue()
    io = QueueDialogueIO(input_q, output_q)

    engine = SopEngine119(
        io=io,
        main_classifier=main_clf,
        sub_classifiers=sub_clf,
        llm_extractor=llm,
        debug=False,
    )

    t = threading.Thread(target=engine.run, daemon=True)
    t.start()

    st.session_state["engine"]            = engine
    st.session_state["input_q"]            = input_q
    st.session_state["output_q"]           = output_q
    st.session_state["worker_thread"]      = t
    st.session_state["worker_started"]     = True
    st.session_state["awaiting_engine"]    = True
    st.session_state["awaiting_started_at"] = time.perf_counter()


def _reset_session():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def _request_end_flow() -> None:
    """主動結束當前 SOP：向 worker 發送哨兵並等待 stopped。"""
    from sop_119_engine import END_FLOW_SENTINEL

    if st.session_state.get("is_bridged"):
        st.session_state["is_done"] = True
        st.session_state["is_bridged"] = False
        st.session_state["done_result"] = "manual_end"
        st.session_state["flow_stage"] = "manual_end"
        st.session_state["awaiting_engine"] = False
        st.session_state["awaiting_started_at"] = None
        st.session_state["messages"].append({
            "role": "system",
            "text": "流程已由操作員主動結束。",
        })
        return

    input_q: Optional[queue.Queue] = st.session_state.get("input_q")
    if input_q is not None:
        # 清空尚未處理的輸入，避免哨兵被排在後面
        while True:
            try:
                input_q.get_nowait()
            except queue.Empty:
                break
        input_q.put(END_FLOW_SENTINEL)

    st.session_state["awaiting_engine"] = True
    st.session_state["awaiting_started_at"] = time.perf_counter()
    with st.spinner("正在結束流程…"):
        _wait_for_engine_events(reason="end_flow", max_wait_s=20.0, idle_grace_s=0.3)

    if not st.session_state.get("is_done"):
        # worker 若卡在長耗時 LLM，仍先讓 UI 結束，避免按鈕無效
        st.session_state["is_done"] = True
        st.session_state["done_result"] = "manual_end"
        st.session_state["flow_stage"] = "manual_end"
        st.session_state["awaiting_engine"] = False
        st.session_state["awaiting_started_at"] = None
        st.session_state["messages"].append({
            "role": "system",
            "text": "流程已由操作員主動結束。",
        })
    st.rerun()


def _build_transcript_from_session() -> List[Dict[str, str]]:
    """優先使用 case 內 transcript，否則由 UI messages 組裝。"""
    case = st.session_state.get("case_data") or {}
    transcript = case.get("transcript") or []
    if transcript:
        return transcript
    out: List[Dict[str, str]] = []
    for m in st.session_state.get("messages") or []:
        role = m.get("role")
        text = (m.get("text") or "").strip()
        if not text or role == "system":
            continue
        if role in ("assistant", "caller"):
            out.append({"role": role, "text": text})
    return out


def _case_for_report() -> Dict[str, Any]:
    """合併 case_data 與 classification，供分析報告使用。"""
    case = dict(st.session_state.get("case_data") or {})
    clf = st.session_state.get("classification") or {}
    if clf.get("main") and not case.get("main_category"):
        case["main_category"] = clf["main"]
    if clf.get("sub") and not case.get("sub_category"):
        case["sub_category"] = clf["sub"]
    return case


def _generate_analysis_report() -> str:
    from llm_extractor_119 import (
        LLMExtractor119,
        build_fallback_analysis_report,
        case_dict_to_report_fields,
    )

    case = _case_for_report()
    transcript = _build_transcript_from_session()
    report_fields = case_dict_to_report_fields(case)

    if not transcript and not report_fields:
        raise ValueError("尚無通話內容或已抽取欄位，無法生成分析報告。")

    _, _, llm = _load_models()
    if llm is not None and isinstance(llm, LLMExtractor119):
        return llm.generate_analysis_report(transcript, report_fields)
    return build_fallback_analysis_report(transcript, report_fields)


def _render_analysis_report_panel():
    """分析報告：生成、展示、下載。"""
    has_data = bool(_build_transcript_from_session()) or bool(_case_for_report())

    if st.button(
        "📊 分析報告",
        use_container_width=True,
        disabled=not has_data,
        key="btn_analysis_report",
    ):
        st.session_state["analysis_report_error"] = None
        with st.spinner("正在生成 AI 分析報告…"):
            try:
                st.session_state["analysis_report"] = _generate_analysis_report()
            except Exception as e:
                st.session_state["analysis_report"] = None
                st.session_state["analysis_report_error"] = str(e)

    if not has_data:
        st.caption("需有通話內容後才可生成")

    err = st.session_state.get("analysis_report_error")
    if err:
        st.error(f"分析報告生成失敗：{err}")

    report = st.session_state.get("analysis_report")
    if report:
        st.markdown(
            f'<div class="report-panel">{html.escape(report)}</div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            label="⬇️ 下載報告（TXT）",
            data=report,
            file_name="119_analysis_report.txt",
            mime="text/plain",
            use_container_width=True,
            key="download_analysis_report",
        )


# ─── 主 UI ───────────────────────────────────────────────────────────────────

def main():
    _init_session()
    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown(
        '<h2 style="color:#1976d2;margin-bottom:4px;">🚑 119 智能報案受理系統</h2>'
        '<p style="color:#888;font-size:13px;margin-top:0;">'
        '台灣緊急救護 SOP 對話引擎 — 示範版</p>',
        unsafe_allow_html=True,
    )

    _start_worker()
    _drain_output_q()

    # 啟動後等待首句問候
    if (
        st.session_state.get("awaiting_engine")
        and not st.session_state.get("messages")
        and not st.session_state.get("is_done")
    ):
        _wait_for_engine_events(reason="bootstrap", max_wait_s=20.0, idle_grace_s=0.4)

    left_col, right_col = st.columns([2, 1], gap="medium")

    with left_col:
        if st.session_state["is_ohca"]:
            st.markdown(
                '<div class="ohca-banner">🚨 OHCA 警示 — 已轉接專人接線員</div>',
                unsafe_allow_html=True,
            )

        with st.container(height=520):
            for m in st.session_state["messages"]:
                if m["role"] == "system":
                    st.warning(m["text"])
                elif m["role"] == "assistant":
                    with st.chat_message("assistant"):
                        st.write(m["text"])
                else:
                    with st.chat_message("user"):
                        st.write(m["text"])

        awaiting = bool(st.session_state.get("awaiting_engine"))
        if awaiting and not st.session_state.get("is_done"):
            started = st.session_state.get("awaiting_started_at")
            waited = 0.0
            if started is not None:
                waited = max(0.0, time.perf_counter() - float(started))
            st.caption(f"本輪輸入處理中（LLM 抽取/摘要生成中）… 已等待 {waited:.1f}s")
            if st.button("同步最新狀態", use_container_width=True, key="sync_btn"):
                with st.spinner("正在同步最新案件要素…"):
                    _wait_for_engine_events(reason="manual_sync", max_wait_s=12.0, idle_grace_s=0.4)
                st.rerun()

        if not st.session_state["is_done"]:
            is_bridged = bool(st.session_state.get("is_bridged"))
            if is_bridged:
                result = st.session_state.get("done_result")
                if result == "ohca_transfer":
                    st.error("🚨 已判斷為 OHCA，轉接專人接線員。AI 不再提問，後續發言仍會更新 SOP 與摘要。")
                else:
                    st.warning("📞 已轉接專人接線員。AI 不再提問，後續發言仍會更新 SOP 與摘要。")

            ctrl_l, ctrl_r = st.columns([3, 1])
            with ctrl_r:
                if st.button(
                    "⏹ 結束流程",
                    use_container_width=True,
                    key="end_flow_btn",
                    help="主動終止當前報案 SOP，可重新開始新通話",
                ):
                    _request_end_flow()
            with ctrl_l:
                st.caption("測試中可隨時主動結束當前流程")

            user_text = st.chat_input(
                "旁聽輸入（報警人）" if is_bridged else "報警人：請輸入回答",
                disabled=awaiting,
            )
            if user_text and user_text.strip():
                user_text = user_text.strip()
                st.session_state["messages"].append({"role": "caller", "text": user_text})
                if is_bridged:
                    engine = st.session_state.get("engine")
                    if engine is not None:
                        with st.spinner("正在旁聽抽取並更新 SOP / 案件摘要…"):
                            engine.observe_utterance("caller", user_text)
                            _drain_output_q()
                    st.rerun()
                else:
                    st.session_state["awaiting_engine"] = True
                    st.session_state["awaiting_started_at"] = time.perf_counter()
                    input_q: queue.Queue = st.session_state["input_q"]
                    if input_q is not None:
                        input_q.put(user_text)
                    with st.spinner("119 正在處理本輪描述並回填案件要素…"):
                        _wait_for_engine_events(reason="user_turn", max_wait_s=30.0, idle_grace_s=0.5)
                    st.rerun()
        else:
            result = st.session_state["done_result"]
            if result == "dispatched":
                st.success("✅ 流程已完成 — 救護車已派出")
            elif result == "report_recorded":
                st.success("✅ 局內現場回報已記錄")
            elif result == "support_dispatched":
                st.success("✅ 支援請求已記錄，車輛已派遣")
            elif result == "ohca_transfer":
                st.error("🚨 已判斷為 OHCA，轉接專人接線員")
            elif result == "human_transfer":
                st.warning("📞 無法完成必要資訊確認，已轉接專人接線員")
            elif result == "manual_end":
                st.info("⏹ 流程已由操作員主動結束")
            else:
                st.warning("⚠️ 流程已結束")
            if st.button("🔄 重新開始新通話", use_container_width=True):
                _reset_session()

    # ════════════════════════════════════════════════════════════════════════
    # 右欄：分類結果 + 案情欄位 + 摘要
    # ════════════════════════════════════════════════════════════════════════
    with right_col:

        # ── 分類結果 ─────────────────────────────────────────────────────────
        clf = st.session_state["classification"]
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**📋 分類結果**")

            badges_html = ""
            if clf["main"]:
                conf_str = f" {clf['main_conf']:.0%}" if clf["main_conf"] else ""
                badges_html += f'<span class="badge badge-main">🔹 {clf["main"]}{conf_str}</span>'
            if clf["sub"]:
                conf_str = f" {clf['sub_conf']:.0%}" if clf["sub_conf"] else ""
                badges_html += f'<span class="badge badge-sub">🔸 {clf["sub"]}{conf_str}</span>'
            if clf.get("sub_source") == "keyword":
                badges_html += '<span class="badge badge-kw">🔑 關鍵詞直判</span>'
            if st.session_state["is_ohca"]:
                badges_html += '<span class="badge badge-ohca">⚡ OHCA</span>'
            elif clf["sub"] and not st.session_state["is_ohca"]:
                badges_html += '<span class="badge badge-ok">✅ 正常</span>'

            if badges_html:
                st.markdown(badges_html, unsafe_allow_html=True)
            else:
                st.markdown('<span style="color:#bbb;font-size:13px;">等待分類…</span>',
                            unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        case = st.session_state["case_data"]

        # ── 全類型通用標記 ───────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**🚨 通用標記**")

            important_case_labels = {
                0: "預設",
                1: "一般處理",
                2: "緊急處理",
            }
            important_tags = case.get("ImportantTag") or []
            tags_display = "、".join(important_tags) if important_tags else None
            universal_fields = [
                (
                    "案件重要性",
                    important_case_labels.get(
                        case.get("ImportantCase"),
                        case.get("ImportantCase"),
                    ),
                ),
                ("重要標籤", tags_display),
                ("需要警察", case.get("NeedPolice")),
            ]
            rows_html = ""
            for label, val in universal_fields:
                if label == "需要警察":
                    display = _val_html(
                        val,
                        {True: "✅ 需要", False: "❌ 不需要"},
                    )
                else:
                    display = _val_html(val)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 局內回報欄位 ─────────────────────────────────────────────────────
        if case.get("call_type") == "局內回報":
            with st.container():
                st.markdown('<div class="panel-card">', unsafe_allow_html=True)
                st.markdown("**📻 局內回報**")
                internal_fields = [
                    ("需求類型", case.get("report_request_type")),
                    ("回報內容", case.get("field_report_content")),
                    ("支援車種", case.get("support_vehicle_type")),
                    ("支援數量", case.get("support_vehicle_count")),
                    ("支援確認", case.get("support_request_confirmed")),
                ]
                rows_html = ""
                for label, val in internal_fields:
                    if label == "支援確認":
                        display = _val_html(
                            val,
                            {True: "✅ 已確認", False: "❌ 待修正"},
                        )
                    else:
                        display = _val_html(val)
                    rows_html += (
                        f'<div class="field-label">{label}</div>'
                        f'<div class="field-value">{display}</div>'
                    )
                st.markdown(rows_html, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

        # ── 地址欄位 ─────────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**📍 事發地址**")

            if case.get("address_suspect_error"):
                reason = case.get("address_error_reason") or "地址抽取或校驗錯誤"
                st.error(f"地址抽取或校驗錯誤，已標記並繼續後續流程：{reason}")

            type_labels = {
                "address": "門牌地址",
                "intersection": "交叉路口／巷口",
                "landmark": "特殊地標",
                "highway": "高速公路",
                "mrt": "捷運車站",
            }
            validation_labels = {
                "pending": "⏳ 校驗中",
                "valid": "✅ 有效",
                "invalid": "❌ 無效",
                "error": "⚠️ 校驗錯誤",
            }
            addr_fields = [
                ("地址",       case.get("address")),
                ("地址類別",   type_labels.get(
                    case.get("location_type"), case.get("location_type")
                )),
                ("行政區",     case.get("address_district")),
                ("路口道路一", case.get("intersection_road1")),
                ("路口道路二", case.get("intersection_road2")),
                ("高速公路",   case.get("highway_name")),
                ("方向",       case.get("highway_direction")),
                ("公里處",     case.get("highway_kilometer")),
                ("校驗狀態",   validation_labels.get(
                    case.get("address_validation_status"),
                    case.get("address_validation_status"),
                )),
                ("管轄單位",   case.get("jurisdiction_office")),
                ("已確認",     case.get("address_confirmed")),
            ]
            rows_html = ""
            for label, val in addr_fields:
                if label == "已確認":
                    display = _val_html(val, {True: "✅ 已確認", False: "❌ 未確認"})
                else:
                    display = _val_html(val)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 生命征象 ─────────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**❤️ 生命征象**")

            vital_fields = [
                ("意識",       case.get("consciousness")),
                ("呼吸",       case.get("breathing")),
                ("腹部起伏",   case.get("abdomen_rise")),
            ]
            bool_vital = {True: "✅ 有", False: "❌ 無"}
            rows_html = ""
            for label, val in vital_fields:
                display = _val_html(val, bool_vital)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 患者資訊 ─────────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**🧑 患者資訊**")

            patient_fields = [
                ("傷病患人數", case.get("patient_count")),
                ("性別",       case.get("patient_gender")),
                ("年齡",       case.get("patient_age")),
                ("事件描述",   case.get("incident_description")),
                ("目前狀況",   case.get("current_condition")),
                ("受傷原因",   case.get("injury_cause")),
                ("受傷部位",   case.get("injury_location")),
                ("傷勢",       case.get("injury_severity")),
                ("TOCC",       case.get("tocc")),
                ("過去病史",   case.get("medical_history")),
                ("路倒原因",   case.get("collapse_cause")),
                ("服藥種類",   case.get("ingested_substance")),
            ]
            rows_html = ""
            for label, val in patient_fields:
                display = _val_html(val)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 孕產資訊（孕婦急產）─────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**🤰 孕產資訊**")

            preg_fields = [
                ("胎次孕週",   case.get("pregnancy_week")),
                ("預產期",     case.get("due_date")),
                ("單/多胞胎",  case.get("multiple_pregnancy")),
                ("破水/出血",  case.get("water_broken_bleeding")),
                ("宮縮",       case.get("contractions")),
                ("產檢異常",   case.get("prenatal_history")),
                ("產檢醫院",   case.get("prenatal_clinic")),
            ]
            rows_html = ""
            for label, val in preg_fields:
                display = _val_html(val)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 火警 SOP 要素 ────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**🔥 火警要素**")

            from fire_tab_map_119 import FIELD_LABELS_ZH

            fire_fields = [
                (label, case.get(key)) for key, label in FIELD_LABELS_ZH.items()
            ] + [
                ("火/煙/氣味", case.get("fire_or_smoke")),
                ("煙色",       case.get("smoke_color")),
                ("燃燒物",     case.get("burning_object")),
                ("火勢趨勢",   case.get("fire_trend")),
                ("燃燒範圍",   case.get("fire_extent")),
            ]
            fire_tab = case.get("fire_tab")
            if fire_tab == "A":
                fire_fields += [
                    ("是否受困", case.get("people_trapped")),
                    ("受困人數", case.get("trapped_count")),
                ]
            elif fire_tab == "B1":
                fire_fields += [
                    ("車種", case.get("vehicle_type")),
                    ("車輛數", case.get("vehicle_count")),
                ]
            elif fire_tab in ("B2", "C"):
                fire_fields += [
                    ("燃燒場域", case.get("outdoor_fire_type")),
                    ("附近水源", case.get("nearby_water_source")),
                ]
            rows_html = ""
            for label, val in fire_fields:
                display = _val_html(val)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 急病補充（血糖/血壓/抽搐/觸發情境）─────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**🩺 急病補充**")

            scenarios = case.get("triggered_scenarios") or []
            scenarios_display = (
                "、".join(str(x) for x in scenarios) if scenarios else None
            )
            acute_fields = [
                ("血糖",       case.get("blood_glucose")),
                ("血壓",       case.get("blood_pressure")),
                ("抽搐資訊",   case.get("seizure_info")),
                ("觸發情境",   scenarios_display),
            ]
            rows_html = ""
            for label, val in acute_fields:
                display = _val_html(val)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 報案人訊息 ───────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**📞 報案人訊息**")

            caller_fields = [
                ("姓名",     case.get("caller_name")),
                ("聯繫方式", case.get("caller_contact")),
                ("稱呼",     case.get("caller_salutation")),
                ("住址",     case.get("caller_address")),
            ]
            rows_html = ""
            for label, val in caller_fields:
                display = _val_html(val)
                rows_html += (
                    f'<div class="field-label">{label}</div>'
                    f'<div class="field-value">{display}</div>'
                )
            st.markdown(rows_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 案情摘要 ─────────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**📝 案情摘要**")
            summary = case.get("case_summary") or ""
            if summary:
                st.markdown(
                    f'<div style="font-size:13px;line-height:1.7;color:#333;">'
                    f'{summary}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span style="color:#bbb;font-size:13px;">尚未生成摘要…</span>',
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)

        # ── AI 分析報告 ───────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**📊 AI 分析報告**")
            _render_analysis_report_panel()
            st.markdown("</div>", unsafe_allow_html=True)

        # ── 流程進度 ─────────────────────────────────────────────────────────
        with st.container():
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown("**🗺️ 流程進度**")
            current_stage = st.session_state["flow_stage"]
            main_cat = st.session_state["classification"].get("main")
            sub_cat  = st.session_state["classification"].get("sub")
            steps_html = ""
            visible_stages = _get_visible_stages(
                main_cat,
                sub_cat,
                fire_tab=case.get("fire_tab"),
            )
            visible_keys = [stage for stage, _ in visible_stages]
            for stage_key, stage_label in visible_stages:
                status = _stage_status(current_stage, stage_key, visible_keys)
                dot_cls = f"stage-dot {status}" if status != "pending" else "stage-dot"
                step_cls = f"stage-step {status}" if status != "pending" else "stage-step"
                icon = "✓ " if status == "done" else ("▶ " if status == "active" else "  ")
                steps_html += (
                    f'<div class="{step_cls}">'
                    f'<div class="{dot_cls}"></div>{icon}{stage_label}</div>'
                )
            st.markdown(steps_html, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # 處理中時自動輪詢（參考 110 streamlit_app.py）
    worker = st.session_state.get("worker_thread")
    if (
        st.session_state.get("awaiting_engine")
        and not st.session_state.get("is_done")
        and worker
        and worker.is_alive()
    ):
        if st_autorefresh is not None:
            st_autorefresh(interval=800, limit=200, key="await_engine_reply")
        else:
            time.sleep(0.8)
            _drain_output_q()
            st.rerun()


# ─── 入口 ────────────────────────────────────────────────────────────────────
# Streamlit 執行整個檔案，直接調用 main()
main()
