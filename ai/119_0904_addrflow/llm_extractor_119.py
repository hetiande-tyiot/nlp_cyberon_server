"""
llm_extractor_119.py
━━━━━━━━━━━━━━━━━━━━
119 報案受理 — LLM 結構化抽取器

後端：llama-cpp-python (GGUF)，與 classifier_with_llm.py 使用同一模型。

對外介面
--------
LLMExtractor119
  .extract_slots(text, schema, rules, question=None) -> dict
      通用 JSON 結構化抽取（null 為首選）。
  .extract_address(caller_text) -> dict[address]
      抽取完整地址（含樓層）。
  .extract_address_components(caller_text, current_address) -> dict
      逐輪抽取門牌地址的區、路、號元件。
  .extract_confirmation(question, caller_text, current_address) -> dict
      判斷報警人是否確認地址，或提供新地址/補充。
  .extract_vital_sign(question, caller_text) -> bool | None
      抽取單一生命征象（True/False/None）。
  .extract_patient_info(question, caller_text) -> dict
      抽取患者性別/年齡/事件/現況（單輪問答上下文）。
  .extract_general_fields(caller_text) -> dict
      每輪通用欄位嘗試抽取（靜默降級）。
  .classify_fire_route(caller_text, question, which) -> str | None
      火警 Q1/Q2 分流（building/other 或 vehicle/vegetation/minor）。
  .check_trigger_scenarios(caller_text, already_triggered) -> list[int]
      急病觸發情境 1–10。
  .check_fire_trigger_scenarios(caller_text, already_triggered) -> list[int]
      火警觸發情境 2–14。
  .extract_summary_confirmation(question, caller_text) -> bool | None
      判斷報警人是否確認案情摘要。
  .remap_sop_fields_for_subcategory(old_sub, new_sub, filled, new_slots) -> dict
      切子類時從舊 SOP 要素抽取新子類相關要素。
  .generate_summary(transcript_texts, filled_fields) -> str
      案情摘要生成（每輪更新）。
  .generate_analysis_report(transcript, filled_fields) -> str
      AI 初報分析報告（固定「報告：(初報)」格式）。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Dict, List, Optional

import sys as _sys

import timing_119
from important_tags_119 import IMPORTANT_TAGS, normalize_important_tags
from sop_utils_119 import (
    clean_address_fragment,
    format_qa_for_llm,
    parse_yes_no,
    parse_yes_no_for_question,
)
from fire_tab_map_119 import (
    FIRE_CODE_FIELDS,
    infer_route_q1,
    infer_route_q2,
    normalize_extracted_fire_fields,
    normalize_fire_field,
)

# ─── 常量 ─────────────────────────────────────────────────────────────────────

DEFAULT_MODEL_PATH = (
    "/root/autodl-tmp/models/TW-119-Model/TW-119-Model.gguf"
)

# ── System Prompt：抽取任務 ───────────────────────────────────────────────────
_EXTRACT_SYSTEM_PROMPT = (
    "你是119報案受理系統的資訊抽取器。"
    "只能依據【文本】抽取，嚴禁常識推斷或編造。"
    "【文本】常為「受理員問題」+「報警人回答」；"
    "必須結合問題語義理解回答，尤其句末的「是/有/沒有」等短答。"
    "報警人可先描述病情再在句末回答問題（如「…是，清醒」），不得忽略。"
    "只輸出一個 JSON 物件，禁止輸出解釋、markdown、多餘文字或思考過程。"
    "禁止輸出 <think> 等思考標記。"
    "你的輸出第一個字元必須是 {，最後一個字元必須是 }。"
)

# ── 全局強約束尾部（附加於每個 rules 末尾）─────────────────────────────────
_STRICT_TAIL = (
    "\n\n【全局強約束（必須遵守）】\n"
    "- 你只能依據【文本】抽取，嚴禁常識推斷/聯想/補充\n"
    "- 相關性判定優先：若【文本】未明確涉及該欄位，必須輸出 null；"
    "寧可少填，不要亂填\n"
    "- 若【文本】包含「受理員問題」和「報警人回答」，"
    "欄位值必須來自報警人回答對該問題的語義回覆；問題只作為理解上下文\n"
    "- 對「沒有/沒有了/不知道」等簡短否定，需結合問題判斷其否定的欄位，"
    "輸出該欄位的明確否定狀態（false），不要只輸出「沒有」\n"
    "- 嚴禁照抄任何問題/選項/提示語；只允許使用【文本】裡的原始資訊\n"
    "- 對 string 欄位：只輸出最短關鍵資訊（建議 ≤ 40 字），不得整段複述\n"
    "- 對 true/false 欄位：只有【文本】明確表達肯定/否定才輸出 true/false；"
    "不確定/未提及 → null\n"
    "- 必須輸出 schema 中的所有 key（值為 null 也要輸出）\n"
    "- 輸出必須為單行 JSON，禁止換行或縮排\n"
)

# 是/否確認類抽取（地址確認、摘要確認、生命征象）使用較寬鬆尾部
_STRICT_TAIL_YESNO = (
    "\n\n【全局強約束（是/否確認）】\n"
    "- 【文本】=「受理員問題」+「報警人回答」，必須結合問題語義判斷\n"
    "- 報警人常先描述病情/經過，句末再回答「是，清醒」「有，還在呼吸」；"
    "不得因前半段病情描述就輸出 null\n"
    "- 只要回答中任何位置明確回答了該問題，就輸出 true/false\n"
    "- 短答「是/是的/对/有」→ true；「不是/沒有/沒」→ false\n"
    "- 禁止因回答過長就輸出 null\n"
    "- 必須輸出 schema 中的所有 key\n"
    "- 輸出必須為單行 JSON\n"
)

# ── System Prompt：摘要任務 ───────────────────────────────────────────────────
_SUMMARY_SYSTEM_PROMPT = (
    "你是119報案受理系統的案件摘要生成器。"
    "你的任務是根據報警人的原話和已確認的SOP欄位，生成一段簡潔、客觀的中文案情摘要。\n"
    "【核心原則】摘要必須且只能反映以下兩個來源中明確出現的事實：\n"
    "①報警人原話；②已確認欄位的正向內容。\n"
    "嚴禁根據案件類型標籤、常識、推斷或任何輸入以外的資訊補充任何細節。\n"
    "【地址】只有原話或欄位中明確出現地址時才可提及；嚴禁憑推斷填入任何地點。\n"
    "【傷情與救護】只有在報警人原話或欄位中存在明確的傷情描述或救護需求時，才可提及；\n"
    "否則嚴禁出現「受傷」「傷情」「需送醫」「需救護」等字眼。\n"
    "【格式】只輸出一段中文摘要正文；"
    "禁止輸出思考過程、<think>、標題、JSON、Markdown 或英文解釋。\n"
    "【個人資訊】不要輸出報警人姓名、電話號碼；"
    "嚴禁根據語氣推斷性別，嚴禁生成先生、小姐、女士等性別稱謂。\n"
    "摘要主語應直接描述案件事實，不要以報警人稱謂開頭。"
)

# ── System Prompt：AI 初報分析報告 ─────────────────────────────────────────────
_REPORT_SYSTEM_PROMPT = (
    "你是119報案受理系統的初報分析報告撰寫器。"
    "只能依據通話記錄與已抽取欄位撰寫，嚴禁編造。\n"
    "【重點欄位】事發地址、案件類別（主類/子類）、案情摘要。\n"
    "【語氣】参照消防/救護調度初報，客觀、簡潔、可執行。"
)

REPORT_HEADER = "報告：(初報)"
REPORT_COMMANDER_LABEL = "現場指揮官："

# 分析報告關注欄位（中文標籤 → case 欄位名）
REPORT_FIELD_MAP: Dict[str, str] = {
    "事發地址": "address",
    "主類別": "main_category",
    "子類別": "sub_category",
    "案情摘要": "case_summary",
    "事件描述": "incident_description",
    "目前狀況": "current_condition",
    "患者性別": "patient_gender",
    "患者年齡": "patient_age",
    "案件重要性": "ImportantCase",
    "重要標籤": "ImportantTag",
    "需要警察": "NeedPolice",
}

# ─── 工具函式 ─────────────────────────────────────────────────────────────────

_THINK_OPEN = "<" + "redacted_thinking>"
_THINK_CLOSE = "</" + "redacted_thinking>"
_THINK_ASSISTANT_PREFIX = f"{_THINK_OPEN}\n\n{_THINK_CLOSE}\n\n"
_THINK_JSON_PREFIX = f"{_THINK_OPEN}\n\n{_THINK_CLOSE}\n\n{{"


def _strip_think_and_fences(s: str) -> str:
    """移除思考鏈與 markdown 圍欄（對齊 110 llm_extractors）。"""
    if not s:
        return s
    s = re.sub(
        re.escape(_THINK_OPEN) + r".*?" + re.escape(_THINK_CLOSE),
        "",
        s,
        flags=re.S,
    )
    s = s.replace(_THINK_OPEN, "").replace(_THINK_CLOSE, "")
    # 未閉合的思考塊或英文思考開頭
    s = re.sub(r"(?is)^\s*here(?:'s| is) a thinking process:.*$", "", s).strip()
    s = re.sub(re.escape(_THINK_OPEN) + r".*$", "", s, flags=re.S).strip()
    s = re.sub(r"```[a-zA-Z0-9]*\s*", "", s)
    s = s.replace("```", "")
    return s.strip()


def _is_valid_summary(s: str) -> bool:
    """摘要是否為可用中文段落（排除思考鏈/英文殘留）。"""
    if not s:
        return False
    t = s.strip()
    if t.startswith("[LLM_ERROR"):
        return False
    bad = (
        "redacted_thinking",
        "thinking process",
        "here's a thinking",
        "here is a thinking",
        "```",
        "json schema",
    )
    low = t.lower()
    if any(b in low for b in bad):
        return False
    if re.search(r"[\u4e00-\u9fff]", t) is None:
        return False
    if len(re.findall(r"[\u4e00-\u9fff]", t)) < 8:
        return False
    return True


def format_transcript_for_report(transcript: List[Dict[str, str]]) -> str:
    """將通話記錄格式化為報告輸入文本。"""
    lines: List[str] = []
    for turn in transcript or []:
        role = turn.get("role")
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        if role == "assistant":
            lines.append(f"受理員：{text}")
        elif role == "caller":
            lines.append(f"報警人：{text}")
    return "\n".join(lines) if lines else "（無通話記錄）"


def case_dict_to_report_fields(case: Dict[str, Any]) -> Dict[str, Any]:
    """將 case dict 轉為分析報告用的中文欄位 dict（僅含非空值）。"""
    out: Dict[str, Any] = {}
    for label, key in REPORT_FIELD_MAP.items():
        val = case.get(key)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        out[label] = val
    return out


def _resolve_category_label(filled_fields: Dict[str, Any]) -> str:
    cat = (
        filled_fields.get("子類別")
        or filled_fields.get("sub_category")
        or filled_fields.get("主類別")
        or filled_fields.get("main_category")
        or "救護"
    )
    cat = str(cat).strip()
    return cat if cat.endswith("案") else f"{cat}案"


def _resolve_address_label(filled_fields: Dict[str, Any]) -> str:
    return str(
        filled_fields.get("事發地址")
        or filled_fields.get("address")
        or "（地址尚缺）"
    ).strip()


def _compose_summary_body(
    filled_fields: Dict[str, Any],
    transcript: List[Dict[str, str]],
) -> str:
    summary = filled_fields.get("案情摘要") or filled_fields.get("case_summary")
    if summary and str(summary).strip():
        return str(summary).strip()

    parts: List[str] = []
    incident = (
        filled_fields.get("事件描述")
        or filled_fields.get("incident_description")
    )
    condition = (
        filled_fields.get("目前狀況")
        or filled_fields.get("current_condition")
    )
    gender = filled_fields.get("患者性別") or filled_fields.get("patient_gender")
    age = filled_fields.get("患者年齡") or filled_fields.get("patient_age")

    if incident:
        parts.append(str(incident))
    if gender or age:
        parts.append(f"患者{gender or ''}{age or ''}")
    if condition:
        parts.append(f"目前狀況{condition}")

    if parts:
        text = "，".join(parts)
        return text if text.endswith("。") else f"{text}。"

    for turn in reversed(transcript or []):
        if turn.get("role") == "caller":
            t = (turn.get("text") or "").strip()
            if t:
                return t if t.endswith("。") else f"{t}。"
    return "（案情尚缺）"


def format_dispatch_report(location_category_line: str, summary_line: str) -> str:
    """
    組裝固定初報格式。

    報告：(初報)
           [地址+類別案]
           [案情摘要]
    現場指揮官：
    [留空]
    [留空]
    """
    line1 = f"       {location_category_line.strip()}"
    line2 = f"       {summary_line.strip()}"
    return (
        f"{REPORT_HEADER}\n"
        f"{line1}\n"
        f"{line2}\n"
        f"{REPORT_COMMANDER_LABEL}\n"
        "\n"
        "\n"
    )


def _is_valid_analysis_report(s: str) -> bool:
    if not s or s.startswith("[LLM_ERROR"):
        return False
    if "redacted_thinking" in s.lower() or "thinking process" in s.lower():
        return False
    return REPORT_HEADER in s and REPORT_COMMANDER_LABEL in s


def build_fallback_analysis_report(
    transcript: List[Dict[str, str]],
    filled_fields: Dict[str, Any],
) -> str:
    """規則版初報分析報告。"""
    line1 = f"{_resolve_address_label(filled_fields)}{_resolve_category_label(filled_fields)}"
    line2 = _compose_summary_body(filled_fields, transcript)
    return format_dispatch_report(line1, line2)


def build_fallback_summary(
    transcript_texts: List[str],
    filled_fields: Dict[str, Any],
) -> str:
    """LLM 摘要失敗時，依已填欄位與原話組裝規則摘要。"""
    parts: List[str] = []

    addr = filled_fields.get("address")
    if addr:
        parts.append(f"地點{addr}")

    incident = filled_fields.get("incident_description")
    if incident:
        parts.append(str(incident))

    condition = filled_fields.get("current_condition")
    if condition:
        parts.append(f"目前狀況{condition}")

    gender = filled_fields.get("patient_gender")
    age = filled_fields.get("patient_age")
    if gender or age:
        seg = "患者"
        if gender:
            seg += str(gender)
        if age:
            seg += str(age)
        parts.append(seg)

    sub = filled_fields.get("sub_category")
    if sub and not incident:
        parts.append(f"類型{sub}")

    if parts:
        return "，".join(parts) + "。"

    if transcript_texts:
        text = (transcript_texts[-1] or "").strip()
        if len(text) > 100:
            text = text[:100] + "…"
        return f"{text}。" if text else ""

    return ""


def _repair_truncated_json(fragment: str) -> Optional[dict]:
    """嘗試修復被 max_tokens 截斷的 JSON 物件。"""
    s = (fragment or "").strip()
    if not s.startswith("{"):
        return None
    # 若字串值未閉合，先補上引號
    in_str = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
    if in_str:
        s += '"'
    # 去掉尾端殘缺的 key/冒號/逗號
    s = re.sub(r",\s*$", "", s)
    s = re.sub(r",\s*\"[^\"]*$", "", s)
    s = re.sub(r":\s*$", ": null", s)
    open_b = s.count("{") - s.count("}")
    if open_b > 0:
        s += "}" * open_b
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_json_output(raw: str) -> dict:
    """從 LLM 原始輸出中提取第一個合法 JSON dict。"""
    raw = _strip_think_and_fences(raw.strip())
    # 嘗試直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 嘗試從 ``` 代碼塊中取出
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 嘗試從首個 { 到最後一個 } 提取
    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass
    # 截斷 JSON 修復（大 schema 常被 max_tokens 截斷）
    if start != -1:
        repaired = _repair_truncated_json(raw[start:])
        if repaired:
            return repaired
    return {}


def _coerce_bool(val: Any) -> Optional[bool]:
    """將字串/布林值轉換為 Python bool 或 None。"""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        parsed = parse_yes_no(val)
        if parsed is not None:
            return parsed
        # LLM 有時輸出「是，清醒」等片語而非 true
        if re.search(
            r"(?:是|對|对|有)[，,]?\s*(?:清醒|有意識|有意识|還在呼吸|有呼吸|有起伏)",
            val,
        ) and not re.search(r"(?:不|沒|无|無)", val[:6]):
            return True
        v = val.strip().lower()
        if v in ("true", "yes", "1"):
            return True
        if v in ("false", "no", "0"):
            return False
    return None


def _clean_str(val: Any) -> Optional[str]:
    """清理字串值，空字串/None 統一返回 None。"""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


# ─── 核心類 ───────────────────────────────────────────────────────────────────

_LLAMA_SERVER_ALIASES = {"llama-server", "llama_server", "llamaserver", "server"}

# 每輪的 schema group 彼此獨立（同一句話、不同欄位集），可同時打 llama-server。
# 池大小要 ≥ 單輪最多的 group 數（救護 5 組 + patient retry），留點餘裕給併發通話；
# 真正的節流在 llama-server 的 slot，這裡放寬沒關係。
_GROUP_POOL_SIZE = int(os.environ.get("LLM_GROUP_POOL_SIZE", "32"))
# 預設關閉。2026-09-16 在 5090 + TW-119-Model 實測：同一輪 6 組
#   依序 321/465/196/225/380/114ms → 合計 1701ms，牆鐘 1701ms
#   並行 634/787/956/762/1162/1707ms → 合計 6008ms，牆鐘 1707ms
# 每組都慢 3-5 倍，牆鐘一模一樣——GPU 在 batch=1 就已飽和，組間並行
# 換不到任何時間，只是把等待從「排隊」搬到「一起變慢」。
# 換更快的卡或更小的模型時可設 LLM_GROUP_PARALLEL=1 重測。
_GROUP_PARALLEL = os.environ.get("LLM_GROUP_PARALLEL", "0") != "0"
_group_pool: Optional[ThreadPoolExecutor] = None
_group_pool_lock = Lock()


# worker 執行緒的呼叫堆疊起點是 pool 的 run_one，_caller_op 往上走看不到
# extract_general_fields，op 會退化成內部函式名。派工前在父執行緒算好語意名，
# 由 worker 用 thread-local 覆寫。
_op_override = threading.local()


def _get_group_pool() -> ThreadPoolExecutor:
    global _group_pool
    if _group_pool is None:
        with _group_pool_lock:
            if _group_pool is None:
                _group_pool = ThreadPoolExecutor(
                    max_workers=_GROUP_POOL_SIZE,
                    thread_name_prefix="llmgroup",
                )
    return _group_pool


class LLMExtractor119:
    """
    119 報案受理 LLM 抽取器。

    參數
    ----
    model_path : str
        GGUF 模型路徑。
    n_ctx : int
        上下文視窗大小（token 數）。
    n_gpu_layers : int
        卸載到 GPU 的層數，-1 = 全部。
    temperature : float
        生成溫度，抽取任務建議 0.05~0.15。
    verbose : bool
        是否輸出 llama-cpp-python 原始日誌。
    """

    _MAX_TEXT_CHARS = 600  # 輸入截斷上限，避免超出 n_ctx

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,
        temperature: float = 0.1,
        verbose: bool = False,
        *,
        backend: Optional[str] = None,
        server_url: Optional[str] = None,
        server_model: Optional[str] = None,
        server_timeout: Optional[float] = None,
        server_max_connections: Optional[int] = None,
    ):
        self._temperature = temperature
        backend = (backend or os.environ.get("LLM_BACKEND", "gguf")).strip().lower()
        self.backend = "llama-server" if backend in _LLAMA_SERVER_ALIASES else "gguf"

        if self.backend == "llama-server":
            # ── 後端 B：llama-server 多 slot（真並發，不上 gen lock）────────
            try:
                import httpx
            except ImportError as e:
                raise RuntimeError(
                    "LLM_BACKEND=llama-server 需要 httpx：pip install httpx"
                ) from e

            self._llm = None
            self._lock = None  # 無 gen lock ＝ 並發由 llama-server slot 負責
            self._server_url = (
                server_url
                or os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8081")
            ).rstrip("/")
            self._server_model = (
                server_model or os.environ.get("LLAMA_SERVER_MODEL", "tw-119-model")
            )
            self._server_timeout = float(
                server_timeout
                if server_timeout is not None
                else os.environ.get("LLAMA_SERVER_TIMEOUT", "180")
            )
            _max_conn = int(
                server_max_connections
                if server_max_connections is not None
                else os.environ.get("LLAMA_SERVER_MAX_CONNECTIONS", "32")
            )
            # httpx.Client 本身 thread-safe；連線池要 ≥ 併發數，否則自己排隊
            self._http = httpx.Client(
                base_url=self._server_url,
                timeout=httpx.Timeout(self._server_timeout, connect=10.0),
                limits=httpx.Limits(
                    max_connections=_max_conn,
                    max_keepalive_connections=_max_conn,
                ),
            )
            return

        # ── 後端 A：in-process GGUF（原行為，單線序列化）──────────────────
        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise RuntimeError(
                "未安裝 llama-cpp-python。\n"
                "請安裝：CMAKE_ARGS='-DGGML_CUDA=on' "
                "pip install llama-cpp-python==0.3.23 --force-reinstall --no-cache-dir"
            ) from e

        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"GGUF 模型不存在: {model_path}")

        self._http = None
        self._llm = Llama(
            model_path=model_path,
            chat_format="qwen",
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            flash_attn=True,
        )
        self._lock = Lock()

    # ── 底層生成 ──────────────────────────────────────────────────────────────

    def _build_chatml_prompt(
        self,
        messages: list[dict],
        *,
        assistant_prefix: str = "",
    ) -> str:
        """構建 ChatML prompt（user 注入 /no_think，assistant 可預填空思考塊）。"""
        chunks = []
        for m in messages:
            role    = m.get("role", "user")
            content = m.get("content", "")
            if role == "user" and "/no_think" not in content:
                content = "/no_think\n\n" + content
            chunks.append(f"<|im_start|>{role}\n{content}")
        chunks.append(f"<|im_start|>assistant\n{assistant_prefix}")
        return "\n".join(chunks)

    def _complete(
        self,
        messages: list[dict],
        max_tokens: int = 256,
        stop: Optional[list[str]] = None,
        *,
        assistant_prefix: str = "",
    ) -> str:
        """調用 LLM 並返回清理後輸出。"""
        stop = stop or ["<|im_end|>", "<|endoftext|>"]
        prompt = self._build_chatml_prompt(
            messages,
            assistant_prefix=assistant_prefix,
        )
        # op = 語意層方法名（extract_address / classify_fire_route…）。
        # 不能只取 _getframe(1)：多數抽取都經由 extract_slots 這層內部共用
        # 函式呼叫 _complete，結果全部記成 extract_slots，分不出誰慢。
        # 往上找到最外層仍屬本類別的 frame 才是真正想看的那個。
        op = self._caller_op()
        t0 = time.perf_counter()
        try:
            if self.backend == "llama-server":
                raw = self._complete_via_server(prompt, max_tokens, stop)
            else:
                with self._lock:
                    result = self._llm.create_completion(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        stop=stop,
                        temperature=self._temperature,
                        top_p=0.9,
                        top_k=20,
                        repeat_penalty=1.0,
                    )
                raw = (result.get("choices") or [{}])[0].get("text", "").strip()
            out = _strip_think_and_fences(raw)
            timing_119.emit("llm", op, (time.perf_counter() - t0) * 1000.0,
                            in_size=len(prompt), out_size=len(out))
            return out
        except Exception as e:
            # 失敗也要記時間——逾時的那幾秒才是要查的
            timing_119.emit("llm", op, (time.perf_counter() - t0) * 1000.0,
                            in_size=len(prompt), extra="error=1")
            return f"[LLM_ERROR: {e}]"

    def _extract_groups(
        self,
        schema_groups: list,
        caller_text: str,
        *,
        question: Optional[str],
        tail: Optional[str],
    ) -> List[Dict[str, Any]]:
        """跑完所有 schema group，回傳與 schema_groups 同順序的結果。

        llama-server 後端沒有 gen lock，各組可真並發（實測一輪 6 組依序約
        4.5s，並行後等於最慢那一組）。gguf 後端有 _gen_lock，並行只是換個
        地方排隊還多付執行緒成本，所以維持依序。

        單組失敗回 {}（沿用原本的靜默降級），不影響其他組。
        """
        def run_one(group) -> Dict[str, Any]:
            schema, rules = group
            try:
                return self.extract_slots(
                    caller_text, schema, rules,
                    question=question,
                    strict_tail=tail,
                    max_tokens=512,
                )
            except Exception:  # noqa: BLE001
                return {}

        if (not _GROUP_PARALLEL
                or self.backend != "llama-server"
                or len(schema_groups) < 2):
            return [run_one(g) for g in schema_groups]

        # timing_119 的 sid 取自執行緒名稱；worker 不改名的話 TIMING 會記成
        # sid=-，併發時就歸不了戶。把呼叫端的執行緒名借給 worker 用。
        parent_name = threading.current_thread().name
        parent_op = self._caller_op()      # 在父執行緒算，堆疊才正確

        def run_named(group) -> Dict[str, Any]:
            worker = threading.current_thread()
            original_name = worker.name
            original_op = getattr(_op_override, "value", None)
            worker.name = parent_name
            _op_override.value = parent_op
            try:
                return run_one(group)
            finally:
                worker.name = original_name
                _op_override.value = original_op

        # map 保序，逐一取結果；例外已在 run_one 內吞掉
        return list(_get_group_pool().map(run_named, schema_groups))

    def _caller_op(self, max_depth: int = 8) -> str:
        """往上找呼叫堆疊中最外層、仍屬於本抽取器的方法名。"""
        override = getattr(_op_override, "value", None)
        if override:
            return override
        op = "_complete"
        for depth in range(1, max_depth + 1):
            try:
                frame = _sys._getframe(depth)
            except ValueError:
                break
            if frame.f_locals.get("self") is not self:
                break          # 已經離開本類別，上一個就是最外層
            name = frame.f_code.co_name
            if not name.startswith("_"):
                op = name
        return op

    def _complete_via_server(
        self,
        prompt: str,
        max_tokens: int,
        stop: list[str],
    ) -> str:
        """打 llama-server /completion（raw prompt，參數與 in-process 版 1:1）。

        不上 gen lock：併發由 llama-server 的 --parallel slot 負責，
        slot 滿了 llama-server 會自己排隊，不會回 503。
        """
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "stop": stop,
            "temperature": self._temperature,
            "top_p": 0.9,
            "top_k": 20,
            "repeat_penalty": 1.0,
            "cache_prompt": True,
            "stream": False,
        }
        resp = self._http.post("/completion", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("content") or "").strip()

    def close(self) -> None:
        """釋放 HTTP 連線池（llama-server 後端用；gguf 後端為 no-op）。"""
        if getattr(self, "_http", None) is not None:
            try:
                self._http.close()
            except Exception:  # noqa: BLE001
                pass

    # ── 通用 JSON 抽取 ────────────────────────────────────────────────────────

    def extract_slots(
        self,
        text: str,
        schema: Dict[str, str],
        rules: str,
        question: Optional[str] = None,
        *,
        strict_tail: Optional[str] = None,
        max_tokens: int = 512,
    ) -> Dict[str, Any]:
        """
        通用結構化 JSON 抽取。

        參數
        ----
        text     : 報警人輸入文本
        schema   : {"slot_name": "string|null" | "true|false|null"}
        rules    : 每個欄位的抽取規則（自由文字）
        question : 本輪受理員問題；與 text 一併打包為 Q&A 上下文
        strict_tail : 自訂全局尾部；預設 _STRICT_TAIL
        max_tokens  : 生成上限；大 schema 需 ≥512，避免 JSON 截斷

        返回
        ----
        解析後的 dict，解析失敗返回空 dict {}
        """
        text = text[: self._MAX_TEXT_CHARS]

        # 問答上下文包裝（本輪問題 + 報警人回答）
        context_text = format_qa_for_llm(question, text) if question else text

        tail = strict_tail if strict_tail is not None else _STRICT_TAIL

        # 構建 schema 展示（單行，方便模型解析）
        schema_items = ", ".join(f'"{k}": {v}' for k, v in schema.items())
        schema_str   = "{" + schema_items + "}"

        user_content = (
            f"請從【文本】中抽取欄位，只輸出一個 JSON。\n\n"
            f"【欄位規則】\n{rules.strip()}"
            f"{tail}\n"
            f"JSON Schema（必須完全一致）：{schema_str}\n\n"
            f"【文本】：\n{context_text}"
        )

        messages = [
            {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        # 勿用 "\n\n" 作 stop，否則單行 JSON 後偶發換行會被截斷
        raw = self._complete(
            messages,
            max_tokens=max_tokens,
            stop=["<|im_end|>", "<|endoftext|>"],
            assistant_prefix=_THINK_JSON_PREFIX,
        )
        if raw and not raw.lstrip().startswith("{"):
            raw = "{" + raw.lstrip()
        return _parse_json_output(raw)

    # ── 地址抽取 ──────────────────────────────────────────────────────────────

    def extract_address(
        self,
        caller_text: str,
        *,
        use_question: bool = True,
        include_floor: bool = True,
    ) -> Dict[str, Optional[str]]:
        """
        從報警人文本中抽取完整事發地址（含樓層）。

        use_question=False 時僅依原文抽取（適合第一輪混合陳述）。
        include_floor=False 時問題上下文不含樓層追問（車禍/路倒等戶外場景）。
        返回 {"address": str|None}
        """
        schema = {"address": "string|null"}
        rules = (
            "- address：抽取完整事發地址（區/路段/門牌/樓層；無門牌時可為地標），單一字串。\n"
            "  • 若出現「地址在/地址是/地點在」等，抽取其後的地址片段。\n"
            "  • 允許缺縣市：如「土城區裕民路142號」可直接輸出，勿因缺新北市而 null。\n"
            "  • 優先抽取含路/街/巷/弄/號的門牌地址；與機關地標同時出現時只取門牌。\n"
            "  • 例：「不是，民權街二段87號一樓」→「民權街二段87號一樓」\n"
            "  • 例：「這裡是汐止分局橫科派出所，儲藏室燒起來了」"
            "→ 僅「汐止分局橫科派出所」（勿併入儲藏室/燒起來等案情）。\n"
            "  • 嚴禁把否定/確認語併入地址：不是/不對/錯了/對/是/沒錯。\n"
            "  • 嚴禁把案件類別或事件描述併入：救護車/火災/消防/燒起來/起火/倒地等。\n"
            "  • 口語以頓號/逗號逐步細化的同一地址必須合併；勿整句複述。\n"
            "  • 未提及可定位地點 → null；嚴禁「未知」「不明」「不詳」等佔位字。"
        )
        if use_question:
            question = (
                "請先告訴我地址？幾樓？"
                if include_floor
                else "請先告訴我地址？"
            )
        else:
            question = None
        out = self.extract_slots(caller_text, schema, rules, question=question)
        addr = _clean_str(out.get("address"))
        if addr:
            addr = clean_address_fragment(addr) or None
        return {"address": addr}

    def consolidate_address(
        self,
        caller_texts: List[str],
        *,
        current_address: Optional[str] = None,
        api_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """整合**整段對話**的地址資訊，回傳最終判讀與待確認事項。

        與 `extract_address` 的差別：那個只看單輪，無法判斷
        「28號28巷」是口誤更正還是兩段資訊；本方法吃全部報案人發話，
        跟 `generate_summary` 一樣有完整脈絡。

        119 是分秒必爭的案件，prompt 的優先級明確寫入：
        **能定案就定案，只有真的不確定才回報 need_ask**，
        不要為了求全而多問。

        參數
        ----
        caller_texts    : 報警人各輪發言（依序）
        current_address : 目前流程已組出的地址（供對照，可為 None）
        api_hint        : addrCheck 最近一次的提示（含鄰近門牌等線索）

        回傳
        ----
        {
          "address": str|None,      # 整合後最完整的地址（含樓層）
          "district": str|None, "road": str|None,
          "number": str|None, "floor": str|None,
          "confidence": "high"|"low",
          "need_ask": str|None,     # 真的無法定案時，該問報案人的一句話
        }
        """
        if not caller_texts:
            return {}
        joined = "\n".join(f"{i+1}. {t}" for i, t in enumerate(caller_texts))
        schema = {
            "address": "string|null",
            "district": "string|null",
            "road": "string|null",
            "number": "string|null",
            "floor": "string|null",
            "confidence": "string|null",
            "need_ask": "string|null",
        }
        rules = (
            "你在協助 119 受理員從**整段通話**中確定事發地址。這是分秒必爭的案件。\n"
            "\n"
            "- address：整合所有輪次後最完整的門牌地址，含樓層。\n"
            "  • 報案人分多次補述同一地址時要合併："
            "「新豐街」+「還有20巷」→「新豐街20巷」。\n"
            "  • **口誤即時更正取後者**：「28號28巷」是先說錯再改口，該取「28巷」；"
            "「五十五號…不是551號」取「551號」。\n"
            "  • 報案人改報**另一個**地址時取最後一個完整的。\n"
            "  • 嚴禁併入案情、稱謂、確認語（救護車/失火/對/不是/我是路人）。\n"
            "  • 缺縣市可以，不要因此回 null。\n"
            "- district / road / number / floor：把 address 拆開；"
            "road 含段與巷弄（如「大觀路1段28巷6弄」），number 只有門牌號。\n"
            "- confidence：資訊足以定案填 \"high\"，否則 \"low\"。\n"
            "- need_ask：**只有 confidence 為 low 時**才填，寫一句要問報案人的話"
            "（20 字內、口語、直指缺的那一項）。\n"
            "  • 能定案就定案——多問一輪會延誤派遣，不要為了求全而問。\n"
            "  • 已知門牌不存在時，直接指出：「這條路好像沒有4號欸，"
            "麻煩再幫我看一下門牌？」\n"
            "  • 真有兩個都合理又互斥的候選才問二選一：「是28號還是4號？」"
        )
        context = []
        if current_address:
            context.append(f"目前流程組出的地址：{current_address}")
        if api_hint:
            context.append(f"地址查驗系統回覆：{api_hint}")
        text = joined if not context else joined + "\n\n【參考】" + "；".join(context)

        out = self.extract_slots(
            text, schema, rules, question=None, max_tokens=512
        )
        address = _clean_str(out.get("address"))
        if address:
            address = clean_address_fragment(address) or None
        confidence = (_clean_str(out.get("confidence")) or "").lower()
        return {
            "address": address,
            "district": _clean_str(out.get("district")),
            "road": _clean_str(out.get("road")),
            "number": _clean_str(out.get("number")),
            "floor": _clean_str(out.get("floor")),
            "confidence": "high" if confidence == "high" else "low",
            "need_ask": _clean_str(out.get("need_ask")),
        }

    def extract_address_components(
        self,
        caller_text: str,
        *,
        current_address: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """只依本輪原話抽取門牌地址片段及區、路、號元件。"""
        schema = {
            "address": "string|null",
            "address_district": "string|null",
            "address_road": "string|null",
            "address_number": "string|null",
        }
        rules = (
            f"目前已累積地址：{current_address or '無'}。此內容只供理解上下文，"
            "不可複製成本輪答案。\n"
            "- 每個欄位只可填報警人本輪明確說出的內容，未提及必須為 null。\n"
            "- address：本輪說出的純地址片段，可不完整；不得混入問題、確認語或案情。\n"
            "- address_district：行政區，例如「板橋區」。\n"
            "- address_road：道路名稱，包含段、巷、弄，例如「文化路二段」、"
            "「中央路133巷1弄」；不得包含門牌號。\n"
            "- address_number：門牌號，例如「32號」「100之2號」；"
            "不得把路段、巷或弄的數字當門牌。\n"
            "- 回答只有「板橋區」「文化路」「32號」时，仍需填入对应元件。"
        )
        out = self.extract_slots(
            caller_text,
            schema,
            rules,
        )
        address = _clean_str(out.get("address"))
        if address:
            address = clean_address_fragment(address) or None
        return {
            "address": address,
            "address_district": _clean_str(out.get("address_district")),
            "address_road": _clean_str(out.get("address_road")),
            "address_number": _clean_str(out.get("address_number")),
        }

    # ── 地址確認判斷 ──────────────────────────────────────────────────────────

    def extract_confirmation(
        self,
        question: str,
        caller_text: str,
        current_address: str,
    ) -> Dict[str, Any]:
        """
        判斷報警人是否確認地址，或提供了補充/修正地址。

        返回
        ----
        {
            "confirmed":   True | False | None,
            "new_address": str | None,
        }
        """
        schema = {
            "confirmed":   "true|false|null",
            "new_address": "string|null",
        }
        rules = (
            f"當前已記錄地址：{current_address}\n\n"
            "- confirmed：判斷報警人是否確認上述地址。\n"
            "  • 純肯定短答「是/是的/对/對/沒錯」→ true\n"
            "  • 純否定「不是/不對/錯了」→ false\n"
            "  • 「不是，[新地址]」或「不對，改成…」→ confirmed=false，"
            "並另填 new_address\n"
            "  • 僅補充門牌/弄/號、未明確否認舊址 → confirmed=null\n"
            "  • 長答句末肯定語仍視為 true\n"
            "- new_address：\n"
            "  • 報警人更正或補充地址時，只輸出純地址片段"
            "（路/街/巷/弄/號/樓或地標名）\n"
            "  • 例：「不是，民權街二段87號一樓」→ new_address="
            "「民權街二段87號一樓」（絕對不可含「不是」）\n"
            "  • 例：「連城路347巷1弄2號附近」→ 完整輸出該片段\n"
            "  • 嚴禁把不是/不對/錯了/對/是/沒錯併入 new_address\n"
            "  • 可省略區名；僅確認/否認且無新地址 → null"
        )
        out = self.extract_slots(
            caller_text, schema, rules,
            question=question,
            strict_tail=_STRICT_TAIL,
        )
        confirmed = _coerce_bool(out.get("confirmed"))
        if confirmed is None:
            confirmed = parse_yes_no_for_question(question, caller_text)
        new_addr = _clean_str(out.get("new_address"))
        if new_addr:
            new_addr = clean_address_fragment(new_addr) or None
        return {
            "confirmed":   confirmed,
            "new_address": new_addr,
        }

    # ── 生命征象抽取 ──────────────────────────────────────────────────────────

    def extract_vital_sign(
        self, question: str, caller_text: str
    ) -> Optional[bool]:
        """
        抽取單一生命征象（意識/呼吸/腹部起伏）。

        返回 True=有/是, False=沒有/否, None=不確定/未提及

        設計：配合「受理員問題 + 報警人回答」Q&A 上下文，
        確保「沒有」「沒」等簡短否定能正確對應到問題中的徵象。
        """
        schema = {"value": "true|false|null"}
        rules = (
            f"受理員本輪問題：{question}\n\n"
            "- value：只判斷報警人對**這一個問題**的回答，輸出 true/false/null。\n"
            "【長答處理（極重要）】\n"
            "- 報警人可能先描述病情（出血、頭暈、檢查…），句末再補「是，清醒」「有，還在呼吸」；\n"
            "  病情描述不影響判斷，只要句中有對問題的肯定/否定就必須輸出。\n"
            "【意識問題】（問題含「意識/清醒」時）\n"
            "  • true：清醒/有意識/是清醒/是，清醒/會回應/會睜眼/有反應\n"
            "  • false：沒有意識/昏迷/叫不醒/沒反應/無意識\n"
            "【呼吸問題】（問題含「呼吸」時）\n"
            "  • true：有呼吸/還在呼吸/是，有呼吸/會呼吸\n"
            "  • false：沒有呼吸/沒呼吸/無呼吸/不呼吸\n"
            "【腹部起伏問題】（問題含「起伏/肚子」時）\n"
            "  • true：有起伏/肚子有動/腹部有起伏\n"
            "  • false：沒有起伏/沒起伏/肚子不動\n"
            "- 只有完全未提及該徵象且無肯定/否定語句時才輸出 null"
        )
        out = self.extract_slots(
            caller_text, schema, rules,
            question=question,
            strict_tail=_STRICT_TAIL_YESNO,
        )
        val = _coerce_bool(out.get("value"))
        if val is None:
            val = parse_yes_no_for_question(question, caller_text)
        return val

    # ── 患者資訊單輪抽取 ──────────────────────────────────────────────────────

    def extract_patient_info(
        self,
        question: str,
        caller_text: str,
    ) -> Dict[str, Optional[str]]:
        """
        在問答上下文中批次抽取患者性別/年齡/事件描述/現在狀況。

        傳入問題以提供 Q&A 上下文，幫助模型理解短回答的語義。

        返回 {patient_gender, patient_age, incident_description, current_condition}
        """
        schema = {
            "patient_gender":       "string|null",
            "patient_age":          "string|null",
            "incident_description": "string|null",
            "current_condition":    "string|null",
        }
        rules = (
            "- patient_gender：患者性別（男/女）；「男生/男性」→男、「女生/女性」→女；"
            "描述他人時「一位先生/男士」→男、「一位女士/小姐」→女；"
            "「我是先生/小姐」為報案人稱呼，不得填 patient_gender；文本提及就抽取。\n"
            "- patient_age：患者年齡；「75歲左右」→「75歲」；文本提及就抽取。\n"
            "- incident_description：事件發生原因/經過/主要病情的最短描述；"
            "**不論本輪問題為何**，回答中描述事件或症狀經過就抽取。\n"
            "  例：「昨天做大腸鏡檢查，今天大便出血」→「大腸鏡檢查後便血」。\n"
            "  例：「說話口語含糊、腳沒力走不了」→「說話口語含糊、腳沒力走不了」。\n"
            "- current_condition：患者目前身體狀況/症狀；"
            "**不論本輪問題為何**，回答中描述現況就抽取。\n"
            "  例：「頭暈」「流血較多」「口語含糊」「腳沒力」「走不了」；未描述 → null。"
        )
        out = self.extract_slots(
            caller_text, schema, rules, question=question, max_tokens=384,
        )
        return {
            "patient_gender":       _clean_str(out.get("patient_gender")),
            "patient_age":          _clean_str(out.get("patient_age")),
            "incident_description": _clean_str(out.get("incident_description")),
            "current_condition":    _clean_str(out.get("current_condition")),
        }

    # ── 每輪通用欄位抽取 ──────────────────────────────────────────────────────

    def extract_general_fields(
        self,
        caller_text: str,
        question: Optional[str] = None,
        *,
        main_category: Optional[str] = None,
        call_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        每輪輸入後依案件類型跨欄位抽取業務欄位。

        設計原則：
        - 每一則報警人回答都抽取通用欄位
        - 僅抽取目前主類別的專屬欄位
        - 只有 call_type=局內回報時才抽取局內回報欄位
        - 救護患者欄位若仍空，再以 extract_patient_info 專項補強
        - 靜默降級：失敗返回 {}，不中斷主流程

        返回值只包含本次成功抽取的非 null 欄位。
        """
        # 分多輪抽取，降低大 JSON 截斷機率
        common_schema = {
            "address":              "string|null",
            "caller_name":          "string|null",
            "caller_contact":       "string|null",
            "caller_salutation":    "先生|小姐|null",
            "caller_address":       "string|null",
        }
        rescue_core_schema = {
            "consciousness":        "true|false|null",
            "breathing":            "true|false|null",
            "abdomen_rise":         "true|false|null",
            "patient_count":        "string|null",
            "patient_gender":       "string|null",
            "patient_age":          "string|null",
            "caller_is_patient":    "true|false|null",
            "incident_description": "string|null",
            "current_condition":    "string|null",
            "medical_history":      "string|null",
            "collapse_cause":       "string|null",
        }
        rescue_incident_schema = {
            "incident_description": "string|null",
        }
        location_schema = {
            "location_type":      "address|intersection|landmark|highway|mrt|null",
            "address_district":   "string|null",
            "address_road":       "string|null",
            "address_number":     "string|null",
            "intersection_road1": "string|null",
            "intersection_road2": "string|null",
            "highway_name":       "string|null",
            "highway_direction":  "南向|北向|null",
            "highway_kilometer":  "string|null",
        }
        rescue_ext_schema = {
            "injury_cause":          "string|null",
            "injury_location":       "string|null",
            "injury_severity":       "string|null",
            "tocc":                  "string|null",
            "ingested_substance":    "string|null",
            "blood_glucose":         "string|null",
            "blood_pressure":        "string|null",
            "seizure_info":          "string|null",
            "pregnancy_week":        "string|null",
            "due_date":              "string|null",
            "multiple_pregnancy":    "string|null",
            "water_broken_bleeding": "string|null",
            "contractions":          "string|null",
            "prenatal_history":      "string|null",
            "prenatal_clinic":       "string|null",
        }
        fire_schema = {
            "fire_or_smoke":          "string|null",
            "smoke_color":            "string|null",
            "burning_object":         "string|null",
            "fire_trend":             "string|null",
            "fire_extent":            "string|null",
            "fire_category":          "建築物|工廠|車輛|露天野外|null",
            "caller_position":        "string|null",
            "caller_role":            "string|null",
            "people_trapped":         "true|false|null",
            "trapped_count":          "string|null",
            "building_total_floors":  "string|null",
            "fire_floor":             "string|null",
            "fire_spread":            "true|false|null",
            "building_layout":        "string|null",
            "factory_scale_type":     "string|null",
            "factory_people_present": "true|false|null",
            "hazardous_materials":    "string|null",
            "vehicle_type":           "string|null",
            "vehicle_count":          "string|null",
            "vehicle_occupants":      "true|false|null",
            "vehicle_occupant_count": "string|null",
            "road_type":              "一般道路|高速公路|null",
            "outdoor_fire_type":      "string|null",
            "nearby_water_source":    "string|null",
            "affected_targets":       "string|null",
            "fire_incident_type":     "0|1|null",
            "building_type_code":     "00|10|11|12|20|21|22|23|24|25|26|27|28|29|null",
            "has_flame":              "0|1|null",
            "smoke_color_code":       "0|1|2|3|null",
            "has_explosion":          "0|1|null",
            "spread_risk":            "0|1|null",
            "people_trapped_code":    "0|1|null",
            "building_floors_code":   "0|1|2|3|4|null",
            "fire_floor_code":        "0|1|2|3|4|5|null",
            "building_structure":     "0|1|2|3|4|5|6|null",
            "burn_area_code":         "0|1|2|3|4|5|null",
            "access_water_info":      "0|1|2|3|null",
            "non_building_fire":      "0|1|null",
            "vehicle_wildfire_code":  "0|1|2|3|4|5|6|7|8|null",
            "minor_fire_code":        "0|1|2|3|4|null",
        }
        universal_schema = {
            "ImportantCase":  "0|1|2|null",
            "ImportantTag":   "string[]|null",
            "NeedPolice":     "true|false|null",
        }
        internal_report_schema = {
            "call_type":                    "局內回報|一般案件|null",
            "report_request_type":          "現場回報|支援請求|null",
            "field_report_content":         "string|null",
            "support_vehicle_type":         "string|null",
            "support_vehicle_count":        "integer|null",
            "support_request_confirmed":    "true|false|null",
            "has_additional_request":       "true|false|null",
        }
        common_rules = (
            "【通用欄位】只依報警人本輪實際回答抽取；未提及 → null。\n"
            "- address：可定位地址（優先門牌路街號）；"
            "「不是，民權街…」只取門牌；勿併入不是/救護車/火災/燒起來。\n"
            "- caller_name/caller_contact/caller_address：報案人姓名/電話/住址。\n"
            "- caller_salutation：只有報案人明確回答先生或小姐時才填；"
            "不可依姓名、聲音或語氣推測。"
        )
        rescue_core_rules = (
            "【抽取原則】結合問題語義，從報警人回答抽取；長答可同時填多欄；"
            "問題主題不同也不得漏抽。\n"
            "【示例】問「請問發生了什麼事？」"
            "答「男生 75 歲左右，說話口語含糊、腳沒力走不了」→\n"
            "patient_gender=男, patient_age=75歲, "
            "incident_description=說話口語含糊、腳沒力走不了, "
            "current_condition=口語含糊、腳沒力、走不了；其餘 null。\n"
            "- consciousness/breathing/abdomen_rise：僅明確提及時填 true/false。\n"
            "- patient_count/patient_gender/patient_age：提及就填；"
            "男生→男；75歲左右→75歲；"
            "描述他人「一位先生/女士」→ patient_gender；"
            "「我是先生/小姐」只填 caller_salutation，不填 patient_gender。\n"
            "- caller_is_patient：報案人描述自身症狀/自傷（我自己/我割腕/我頭痛）→ true；"
            "代他人報案（我媽媽/一位路人/我先生）→ false；未提及 → null。\n"
            "- incident_description：事件經過/主要病情；症狀描述也要填。\n"
            "- current_condition：目前症狀/狀況。\n"
            "- medical_history/collapse_cause：有才填，否則 null。"
        )
        rescue_incident_rules = (
            "【緊急救援案情】只依報警人本輪實際回答抽取；未提及 → null。\n"
            "- incident_description：發生的事件、現場狀況或需要救援的原因，"
            "使用最短且完整的描述。"
        )
        location_rules = (
            "【地點結構化抽取】每一欄只依報警人本輪實際說出的內容填寫，未提及 → null。\n"
            "- location_type：門牌地址=address；包含兩條道路交會、路口或巷口=intersection；"
            "可辨識建物/市場/公園等地標=landmark；國道或高速公路=highway；"
            "捷運站或捷運出口=mrt。\n"
            "- address_district：只抽取行政區，格式如「板橋區」。\n"
            "- address_road：門牌地址的道路名稱，可含段、巷、弄，不含門牌號。\n"
            "- address_number：只抽取帶「號」的門牌號，如「32號」「100之2號」；"
            "不得將段、巷、弄的數字當門牌號。\n"
            "- intersection_road1/intersection_road2：分別抽取交叉路口的兩條路、街或巷；"
            "只有一條時 road2 必須為 null。\n"
            "- highway_name：如「國道一號」「國道3號」；highway_direction 只可為南向或北向；"
            "highway_kilometer 只填公里數，可含小數，不含『公里處』。\n"
            "- 回答只是補充「板橋區」「文化路」「北向32.5公里」時，即使無法單獨判定"
            " location_type，也要抽取能確定的元件。"
        )
        rescue_ext_rules = (
            "【抽取原則】從報警人回答抽取下列欄位；未提及 → null。\n"
            "- injury_cause/location/severity：受傷原因/部位/傷勢。\n"
            "- tocc：旅遊/職業/接觸/群聚史。\n"
            "- ingested_substance：服藥種類數量。\n"
            "- blood_glucose/blood_pressure/seizure_info：血糖/血壓/抽搐。\n"
            "- pregnancy_week/due_date/multiple_pregnancy/"
            "water_broken_bleeding/contractions/prenatal_history/prenatal_clinic：孕產資訊。\n"
        )
        fire_rules = (
            "【火災欄位】只依報警人本輪實際回答抽取；可同時填多欄；"
            "未提及 → null，不得從受理員問題複製答案。"
            "代碼欄可填整數代碼或中文標籤。\n"
            "- fire_incident_type：房子/房屋/建築物正在燒=0；其他東西=1。\n"
            "- building_type_code：00未知；10透天厝；11集合住宅/公寓大樓；12倉庫；"
            "20旅館百貨商場；21運輸中樞；22電影院；23學校醫院老人院；24毒災場所；"
            "25大型違章建築區與傳統市場(含工廠)；26石化廠；27古蹟文化財；"
            "28地下建築物；29高層建築物(10層以上)。\n"
            "- has_flame：看到火苗/火焰=1；只有煙或無火焰=0。\n"
            "- smoke_color_code：0無煙；1黑色煙；2白色煙；3其他色煙。\n"
            "- has_explosion：聽到爆炸=1；明確沒有=0。\n"
            "- spread_risk：已燒到旁邊或極可能延燒=1；延燒可能性低=0。\n"
            "- people_trapped_code / people_trapped：有人沒出來或受困=1/true；"
            "明確無人受困=0/false。\n"
            "- building_floors_code：建物總樓層 0未知；1=1~3層；2=4~10層；"
            "3=11~15層；4=16層以上。可填層數或代碼。\n"
            "- fire_floor_code：起火樓層 0未知；1地下室；2=1~3層；3=4~10層；"
            "4=11~15層；5=16層以上。\n"
            "- building_structure：0其他；1木造屋；2鐵皮屋；3連造式鐵皮屋；"
            "4磚造屋；5RC；6SRC。\n"
            "- burn_area_code：0未知；1=0~50坪；2=50~100坪；3=100~300坪；"
            "4=300~500坪；5=500坪以上。\n"
            "- access_water_info：消防車能否進入、附近有無水源。"
            "0一般情況；1小巷；2缺水；3小巷且缺水。\n"
            "- non_building_fire：交通工具或山林草木=0；輕微火警=1。\n"
            "- vehicle_wildfire_code：0汽車；1機車；2隧道；3軌道型交通工具；"
            "4化學毒劑交通工具；5船舶；6航空器；7山林田野(平地)；8山林田野(山地)。\n"
            "- minor_fire_code：0垃圾；1電線桿(電纜)；2瓦斯漏氣；3警報器作響；"
            "4查看案件。\n"
            "- fire_or_smoke / smoke_color / burning_object / fire_trend / "
            "fire_extent：自由文本補充。\n"
            "- fire_category：若能判斷，住宅房子大樓=建築物；工廠廠房=工廠；"
            "汽機車=車輛；雜草垃圾山林=露天野外。\n"
            "- caller_position/caller_role、trapped_count、"
            "building_total_floors/fire_floor、factory_*、vehicle_*、"
            "outdoor_*：報案人有提到才填。"
        )
        allowed_tags = "、".join(IMPORTANT_TAGS)
        universal_rules = (
            "【全類型通用標記】只依報警人本輪回答中的明確新證據抽取；"
            "未提及或無法判斷必須輸出 null，不得沿用問題或先前內容。\n"
            "- ImportantCase：0=明確為預設/無需特別處理，1=一般處理，"
            "2=明確緊急處理；只可輸出整數 0、1、2 或 null。\n"
            f"- ImportantTag：只可從此白名單選擇：{allowed_tags}。"
            "可複選，輸出 JSON 字串陣列（例如 [\"持刀\",\"砍人\"]）；"
            "沒有符合項目則輸出 null，禁止創造其他標籤。\n"
            "- NeedPolice：報警人明確表示需要/要叫警察才輸出 true；"
            "明確表示不需要警察才輸出 false；僅提到119、救護車、消防車、火警、"
            "受傷或受理員詢問警察，不足以判定，輸出 null。"
        )
        internal_report_rules = (
            "【局內同仁回報】所有欄位只依本輪回答和受理員問題抽取；"
            "不得把問題中的車種、數量或需求當成回答內容，未能確定必須輸出 null。\n"
            "- call_type：回答明確表示「局內同仁、分隊、消防／救護單位回報、"
            "分隊回報、局內回報」才輸出「局內回報」；明確為一般民眾報案才輸出"
            "「一般案件」；僅說「回報火災」但無局內身分線索時不得猜測。\n"
            "- report_request_type：只是回報現場狀況／案情輸出「現場回報」；"
            "要求增派、支援、要車輸出「支援請求」。\n"
            "- field_report_content：只有問題正在詢問回報內容／案情，或回答明確說"
            "「回報內容是…」時，抽取完整但精簡的現場狀況；需求分類、地址、"
            "單純車輛需求或是非回答不得填入。\n"
            "- support_vehicle_type：抽取要求支援的車輛類型，如救護車、消防車、"
            "水箱車、雲梯車；沒有車種則 null。\n"
            "- support_vehicle_count：抽取要求支援的車輛數量並轉成正整數；"
            "沒有明確數量則 null。\n"
            "- support_request_confirmed：只有問題正在覆誦確認支援車種與數量時，"
            "回答確認正確輸出 true，否認或更正輸出 false；其他問題一律 null。\n"
            "- has_additional_request：只有問題在問「還有其他需要協助嗎」時，"
            "回答有其他需求輸出 true，明確沒有／不用／謝謝輸出 false；"
            "若回答直接描述另一項需求也輸出 true；其他問題一律 null。"
        )
        _aggressive_q = (
            "意識", "意识", "呼吸", "起伏", "是否", "確定", "對嗎",
            "發生", "发生", "什麼事", "什么事", "甚麼事", "甚么事", "狀況", "状况",
        )
        tail = _STRICT_TAIL_YESNO if question and any(
            k in question for k in _aggressive_q
        ) else _STRICT_TAIL

        schema_groups = [
            (common_schema, common_rules),
            (location_schema, location_rules),
            (universal_schema, universal_rules),
        ]
        if main_category == "救護":
            schema_groups.extend((
                (rescue_core_schema, rescue_core_rules),
                (rescue_ext_schema, rescue_ext_rules),
            ))
        if main_category == "緊急救援":
            schema_groups.append((rescue_incident_schema, rescue_incident_rules))
        if main_category == "火警":
            schema_groups.append((fire_schema, fire_rules))
        if call_type == "局內回報":
            schema_groups.append((internal_report_schema, internal_report_rules))

        merged: Dict[str, Any] = {}
        for out in self._extract_groups(
            schema_groups, caller_text, question=question, tail=tail,
        ):
            if out:
                merged.update(out)   # 合併順序仍依 schema_groups，後者覆蓋前者

        # 救護患者欄位缺漏 → 專項 LLM 再抽（小 schema，更穩）
        _need_patient_retry = (
            main_category == "救護"
            and
            len((caller_text or "").strip()) >= 6
            and (
                not _clean_str(merged.get("incident_description"))
                or not _clean_str(merged.get("patient_gender"))
                or not _clean_str(merged.get("patient_age"))
                or not _clean_str(merged.get("current_condition"))
            )
        )
        if _need_patient_retry:
            try:
                pi = self.extract_patient_info(question or "", caller_text)
                for k, v in pi.items():
                    if v and not _clean_str(merged.get(k)):
                        merged[k] = v
            except Exception:
                pass

        all_keys = [
            key
            for schema, _rules in schema_groups
            for key in schema
        ]
        result: Dict[str, Any] = {}
        for key in all_keys:
            val = merged.get(key)
            if val is None:
                continue
            if key in ("consciousness", "breathing", "abdomen_rise"):
                from sop_utils_119 import parse_vital_slot
                rule_val = parse_vital_slot(key, caller_text, question or "")
                bool_val = _coerce_bool(val)
                if rule_val is not None:
                    result[key] = rule_val
                elif bool_val is not None:
                    if (
                        key == "breathing"
                        and bool_val is True
                        and "呼吸" not in (caller_text or "")
                        and parse_vital_slot("consciousness", caller_text, "") is True
                    ):
                        continue
                    result[key] = bool_val
            elif key == "NeedPolice":
                bool_val = _coerce_bool(val)
                if bool_val is not None:
                    result[key] = bool_val
            elif key == "ImportantCase":
                try:
                    level = int(str(val).strip())
                except (TypeError, ValueError):
                    level = -1
                if not isinstance(val, bool) and level in (0, 1, 2):
                    result[key] = level
            elif key == "ImportantTag":
                tags = normalize_important_tags(val)
                if tags:
                    result[key] = tags
            elif key in (
                "people_trapped", "fire_spread", "factory_people_present",
                "vehicle_occupants",
                "support_request_confirmed", "has_additional_request",
                "caller_is_patient",
            ):
                bool_val = _coerce_bool(val)
                if bool_val is not None:
                    result[key] = bool_val
            elif key in FIRE_CODE_FIELDS:
                normalized = normalize_fire_field(key, val)
                if normalized is not None:
                    result[key] = normalized
            elif key == "support_vehicle_count":
                try:
                    count = int(str(val).strip())
                except (TypeError, ValueError):
                    count = 0
                if count > 0:
                    result[key] = count
            else:
                cleaned = _clean_str(val)
                if cleaned and key == "call_type" and cleaned not in {
                    "局內回報", "一般案件",
                }:
                    cleaned = None
                if cleaned and key == "report_request_type" and cleaned not in {
                    "現場回報", "支援請求",
                }:
                    cleaned = None
                if cleaned and key == "fire_category" and cleaned not in {
                    "建築物", "工廠", "車輛", "露天野外",
                }:
                    cleaned = None
                if cleaned and key == "road_type" and cleaned not in {
                    "一般道路", "高速公路",
                }:
                    cleaned = None
                if cleaned and key == "caller_salutation" and cleaned not in {
                    "先生", "小姐",
                }:
                    cleaned = None
                if cleaned and key == "location_type":
                    cleaned = cleaned.lower()
                    if cleaned not in {
                        "address", "intersection", "landmark", "highway", "mrt",
                    }:
                        cleaned = None
                if cleaned and key in ("address", "caller_address"):
                    cleaned = clean_address_fragment(cleaned) or None
                if cleaned:
                    result[key] = cleaned
        result.update(normalize_extracted_fire_fields(result))
        return result

    def classify_fire_route(
        self,
        caller_text: str,
        question: Optional[str] = None,
        *,
        which: str = "q1",
    ) -> Optional[str]:
        """
        判斷火警 Q1/Q2 分流。成功返回：
          q1 → building | other
          q2 → vehicle | vegetation | minor
        失敗返回 None（呼叫端再用規則兜底）。
        """
        text = (caller_text or "").strip()
        if not text:
            return None

        if which == "q1":
            schema = {"route": "building|other|null"}
            rules = (
                "判斷報警人是否在說「房子/房屋/建築物正在燃燒」。\n"
                "- building：房屋、住宅、公寓、大樓、倉庫、工廠、店面等建築物在燒。\n"
                "- other：明確不是房子，或在燒車子、草木、垃圾、電線等其他東西。\n"
                "- 無法判斷 → null。只輸出 JSON。"
            )
            allowed = {"building", "other"}
            fallback = infer_route_q1(text)
        else:
            schema = {"route": "vehicle|vegetation|minor|null"}
            rules = (
                "判斷非建築物火災的燃燒物。\n"
                "- vehicle：汽車、機車、隧道、火車、船舶、航空器等交通工具。\n"
                "- vegetation：山上、路邊草木、山林、田野。\n"
                "- minor：以上都不是（垃圾、電線桿、瓦斯、警報、查看等）。\n"
                "- 無法判斷 → null。只輸出 JSON。"
            )
            allowed = {"vehicle", "vegetation", "minor"}
            fallback = infer_route_q2(text)

        try:
            out = self.extract_slots(
                text, schema, rules,
                question=question,
                max_tokens=64,
            )
        except Exception:
            out = {}
        route = str(out.get("route") or "").strip().lower()
        if route in allowed:
            return route
        return fallback

    # ── 觸發情境偵測（急病專用）──────────────────────────────────────────────

    def check_trigger_scenarios(
        self,
        caller_text: str,
        already_triggered: List[int],
    ) -> List[int]:
        """
        根據報警人文本，偵測 10 個觸發情境中哪些被觸發。

        參數
        ----
        caller_text      : 本輪報警人輸入文本
        already_triggered: 已觸發過的情境編號，不重複觸發

        返回
        ----
        新觸發的情境編號列表（整數 1–10，僅含本輪新增）
        """
        schema = {f"s{i}": "true|false|null" for i in range(1, 11)}

        rules = (
            "從以下10個觸發情境中判斷哪些出現在【文本】裡，每項輸出 true/false/null。\n"
            "只要文本中出現對應描述（詞義相符即可，不必完全一致），該項輸出 true；\n"
            "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
            "情境定義：\n"
            "- s1：呼吸喘（喘不過氣、呼吸急促、呼吸困難）\n"
            "- s2：身體不適（頭暈、虛弱、全身無力、腹痛、腹瀉、嘔吐、發燒、"
            "全身發抖、心跳快、血壓高）\n"
            "- s3：胸悶、胸痛、心臟不適\n"
            "- s4：冒冷汗、抽搐\n"
            "- s5：昏迷（意識喪失、叫不醒、昏過去）\n"
            "- s6：低血糖（血糖低、低血糖發作）\n"
            "- s7：低血壓（血壓低、頭暈站不穩、低血壓）\n"
            "- s8：流鼻血\n"
            "- s9：有人噎到（喉嚨卡住、吞不下去、噎到）\n"
            "- s10：叫他沒反應或沒有呼吸（無反應、失去意識、停止呼吸）\n"
        )
        out = self.extract_slots(
            caller_text,
            schema=schema,
            rules=rules,
            strict_tail=_STRICT_TAIL,
        )

        already_set = set(already_triggered)
        new_triggers: List[int] = []
        for i in range(1, 11):
            key = f"s{i}"
            val = _coerce_bool(out.get(key))
            if val is True and i not in already_set:
                new_triggers.append(i)
        return new_triggers

    # ── 觸發情境偵測（火警通用）──────────────────────────────────────────────

    def check_fire_trigger_scenarios(
        self,
        caller_text: str,
        already_triggered: List[int],
    ) -> List[int]:
        """
        根據報警人文本，偵測火警觸發情境 2–14 中哪些被觸發。

        情境 1（說明地址）由地址覆頌流程處理，不在此偵測。

        返回本輪新觸發的情境編號列表（整數 2–14）。
        """
        schema = {f"s{i}": "true|false|null" for i in range(2, 15)}

        rules = (
            "從以下火警觸發情境中判斷哪些出現在【文本】裡，每項輸出 true/false/null。\n"
            "只要文本中出現對應描述（詞義相符即可，不必完全一致），該項輸出 true；\n"
            "文本明確否認 → false；未提及/不確定 → null（等同未觸發）。\n\n"
            "情境定義：\n"
            "- s2：無火無煙、燒焦味、警報聲（聞到燒焦味、警報響、沒看到火煙）\n"
            "- s3：聽別人說有火災（聽說、別人講、鄰居說有火災）\n"
            "- s4：聽到爆炸聲\n"
            "- s5：電線冒火花、燒電線、燒金紙、水溝冒煙\n"
            "- s6：山頭冒煙、整地冒煙\n"
            "- s7：瓦斯桶燒起來、瓦斯起火\n"
            "- s8：垃圾桶冒煙、行動電源冒煙\n"
            "- s9：掃墓起火、漁船起火\n"
            "- s10：有火、看到火、著火、起火\n"
            "- s11：有煙、冒煙、看到煙\n"
            "- s12：很大的火或煙（火很大、煙很大）\n"
            "- s13：一點點火或煙（小火、一點煙）\n"
            "- s14：爆炸聲（再確認爆炸相關描述）\n"
        )
        out = self.extract_slots(
            caller_text,
            schema=schema,
            rules=rules,
            strict_tail=_STRICT_TAIL,
        )

        already_set = set(already_triggered)
        new_triggers: List[int] = []
        for i in range(2, 15):
            key = f"s{i}"
            val = _coerce_bool(out.get(key))
            if val is True and i not in already_set:
                new_triggers.append(i)
        return new_triggers

    # ── 報案人訊息抽取 ────────────────────────────────────────────────────────

    def extract_caller_info(
        self,
        question: str,
        caller_text: str,
        *,
        include_address: bool = False,
    ) -> Dict[str, Optional[str]]:
        """
        從報警人回答中抽取報案人姓名與聯繫方式（電話/手機），
        以及可選的報案人住址。

        參數
        ----
        include_address : bool
            True 時額外抽取 caller_address（報案人本人住址，非事發地址）。
            用於急病等需要留存報案人住址的次類別。

        返回
        ----
        include_address=False：{"caller_name": ..., "caller_contact": ...,
                               "caller_salutation": ...}
        include_address=True ：另含 {"caller_address": ...}
        """
        schema: Dict[str, str] = {
            "caller_name":       "string|null",
            "caller_contact":    "string|null",
            "caller_salutation": "先生|小姐|null",
        }
        rules = (
            "- caller_name：報案人自述的姓名（可為全名/姓/稱謂）；未提及 → null。\n"
            "- caller_contact：報案人自述的電話號碼或手機號碼；抽取完整數字序列；"
            "未提及 → null。\n"
            "  • 若文本中含多個號碼，優先取報案人自報的聯繫電話。\n"
            "- caller_salutation：只有報案人明確回答「先生」或「小姐」時才填；"
            "不可依姓名、聲音或語氣推測。"
        )
        if include_address:
            schema["caller_address"] = "string|null"
            rules += (
                "\n- caller_address：報案人自述的本人住址（非事發現場地址）；"
                "抽取完整地址字串；未提及 → null。"
            )
        out = self.extract_slots(caller_text, schema, rules, question=question)
        result: Dict[str, Optional[str]] = {
            "caller_name":       _clean_str(out.get("caller_name")),
            "caller_contact":    _clean_str(out.get("caller_contact")),
            "caller_salutation": _clean_str(out.get("caller_salutation")),
        }
        if result["caller_salutation"] not in ("先生", "小姐"):
            result["caller_salutation"] = None
        if include_address:
            result["caller_address"] = _clean_str(out.get("caller_address"))
        return result

    # ── 摘要確認判斷 ──────────────────────────────────────────────────────────

    def extract_summary_confirmation(
        self, question: str, caller_text: str
    ) -> Optional[bool]:
        """
        判斷報警人是否確認案情摘要。

        返回 True=確認, False=不確認, None=不明確/有補充
        """
        schema = {"confirmed": "true|false|null"}
        rules = (
            "- confirmed：判斷報警人是否確認案情摘要。\n"
            "  • 回答「是/是的/对/對/沒錯/正確」→ true\n"
            "  • 回答「不是/不對/錯了/不完整」→ false\n"
            "  • 長答中若句末明確肯定摘要，仍輸出 true\n"
            "  • 若同時補充新資訊且未明確表態確認 → null"
        )
        out = self.extract_slots(
            caller_text, schema, rules,
            question=question,
            strict_tail=_STRICT_TAIL_YESNO,
        )
        confirmed = _coerce_bool(out.get("confirmed"))
        if confirmed is None:
            confirmed = parse_yes_no_for_question(question, caller_text)
        return confirmed

    # ── 子類切換：從舊 SOP 要素遷移到新子類 ───────────────────────────────────

    def remap_sop_fields_for_subcategory(
        self,
        *,
        old_sub: str,
        new_sub: str,
        filled_fields: Dict[str, Any],
        new_slots: List[str],
        slot_meanings: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        從已抽取的舊子類 SOP 要素中，抽取與新子類相關的欄位。

        只填能從舊要素合理對上的欄位；不能確定則省略。禁止臆造。
        失敗返回 {}。
        """
        if not new_slots or not filled_fields:
            return {}

        bool_slots = {
            "consciousness", "breathing", "abdomen_rise", "caller_is_patient",
        }
        schema: Dict[str, str] = {}
        for slot in new_slots:
            if slot in FIRE_CODE_FIELDS:
                schema[slot] = "string|int|null"
            elif slot in bool_slots:
                schema[slot] = "true|false|null"
            else:
                schema[slot] = "string|null"

        meaning_lines = []
        for slot in new_slots:
            zh = (slot_meanings or {}).get(slot, slot)
            meaning_lines.append(f"- {slot}（{zh}）")
        meaning_block = "\n".join(meaning_lines)

        try:
            filled_json = json.dumps(filled_fields, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            filled_json = str(filled_fields)

        rules = (
            f"舊子類「{old_sub}」已抽取的 SOP 要素見【文本】。\n"
            f"請只填寫新子類「{new_sub}」需要、且能從舊要素合理對上的欄位。\n"
            "【欄位含義】\n"
            f"{meaning_block}\n"
            "- 同名欄位若在新舊子類語義不同（例如 medical_history 可能是病史、"
            "家屬在場或是否在現場），不可原樣照抄，必須符合新子類含義才填。\n"
            "- 無法從舊要素確定的欄位必須輸出 null，禁止臆造。\n"
            "- 生命征象（consciousness/breathing/abdomen_rise）若舊要素已有明確"
            "是/否，可遷移。"
        )
        try:
            out = self.extract_slots(
                filled_json,
                schema,
                rules,
                max_tokens=512,
            )
        except Exception:
            return {}

        result: Dict[str, Any] = {}
        for slot in new_slots:
            val = out.get(slot)
            if val is None:
                continue
            if slot in bool_slots:
                coerced = _coerce_bool(val)
                if coerced is not None:
                    result[slot] = coerced
                continue
            if slot in FIRE_CODE_FIELDS:
                normalized = normalize_fire_field(slot, val)
                if normalized is not None:
                    result[slot] = normalized
                continue
            cleaned = _clean_str(val)
            if cleaned is not None:
                result[slot] = cleaned
        return result

    # ── 案情摘要生成 ──────────────────────────────────────────────────────────

    def generate_summary(
        self,
        transcript_texts: List[str],
        filled_fields: Dict[str, Any],
    ) -> str:
        """
        根據報警人逐字稿與已確認欄位生成案情摘要。

        設計（參照 110 sop_110_assistant.py _llm_generate_case_summary）：
        - 只反映①報警人原話 ②已確認欄位正向內容兩個來源
        - 排除 False 布林欄位（防止模型看欄位名腦補負向細節）
        - 60~150 字，不輸出標題/JSON/個人識別資訊

        參數
        ----
        transcript_texts : 報警人各輪發言文本列表
        filled_fields    : CaseInfo119.filled_fields_for_summary() 返回的 dict

        返回
        ----
        純文字摘要字串（失敗時返回空字串）
        """
        caller_text = "\n".join(transcript_texts) if transcript_texts else "（無）"

        # 排除技術欄位，只保留業務正向欄位
        _EXCLUDE_KEYS = {
            "case_summary", "transcript", "flow_stage", "result",
            "main_conf", "sub_conf",
        }
        display_fields: Dict[str, Any] = {
            k: v for k, v in filled_fields.items()
            if k not in _EXCLUDE_KEYS
        }

        fields_str = json.dumps(display_fields, ensure_ascii=False, indent=2)

        user_content = (
            "/no_think\n\n"
            "請嚴格根據以下「報警人原話」和「已確認欄位」生成摘要，"
            "禁止引入任何兩者之外的資訊。\n\n"
            "輸出要求：\n"
            "- 只輸出一段中文摘要正文，控制在 60~150 個中文字元。\n"
            "- 依序概括：案發地點（若有）、事件經過、已確認的關鍵事實"
            "（僅限輸入中出現的內容）。\n"
            "- 若某項資料缺失，直接略過，禁止猜測或推斷。\n"
            "- 禁止出現報警人姓名、電話或任何性別稱謂（先生/小姐/女士等）。\n"
            "- 禁止寫「根據資料」「系統顯示」「報警人表示」等元話語。\n"
            "- 禁止輸出思考過程、英文、JSON、標題或任何解釋，只輸出摘要正文。\n\n"
            f"【報警人原話】\n{caller_text}\n\n"
            f"【已確認欄位（JSON）】\n{fields_str}"
        )

        messages = [
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        raw = self._complete(
            messages,
            max_tokens=220,
            stop=[
                "<|im_end|>",
                "<|endoftext|>",
                _THINK_OPEN,
                _THINK_CLOSE,
                "\n\n",
            ],
            assistant_prefix=_THINK_ASSISTANT_PREFIX,
        )
        raw = _strip_think_and_fences(raw)
        if _is_valid_summary(raw):
            return raw
        return build_fallback_summary(transcript_texts, display_fields)

    # ── AI 分析報告生成 ────────────────────────────────────────────────────────

    def generate_analysis_report(
        self,
        transcript: List[Dict[str, str]],
        filled_fields: Dict[str, Any],
    ) -> str:
        """
        根據通話記錄與已抽取欄位生成「初報」格式 AI 分析報告。

        重點欄位：地址、案件類別、案情摘要。
        """
        dialog_text = format_transcript_for_report(transcript)
        fields_str = json.dumps(filled_fields, ensure_ascii=False, indent=2)
        context_text = (
            f"【通話記錄】\n{dialog_text}\n\n"
            f"【已抽取欄位】\n{fields_str}"
        )

        schema = {
            "location_category_line": "string|null",
            "summary_line":           "string|null",
        }
        rules = (
            "【任務】抽取初報報告兩行正文（系統會自動套上固定標題與現場指揮官欄）。\n"
            "【重點】事發地址、案件類別、案情摘要；可參考通話記錄補全。\n\n"
            "- location_category_line：第一行，格式為「[可選時間前缀][地址][案件類別]案」。\n"
            "  • 地址使用已抽取「事發地址」；類別優先「子類別」，其次「主類別」。\n"
            "  • 參考示例：今(5)日2049三峽區安坑69號之2火警案；"
            "救護可寫「土城區裕民路142號急病案」。\n"
            "  • 僅當通話中明確出現日期/時間才寫「今(X)日HHMM」前缀。\n"
            "- summary_line：第二行案情摘要正文，參照消防初報敘述風格，"
            "客觀描述事件經過、患者狀況、救護需求與已知處置；"
            "優先整合「案情摘要」欄位，可補充通話細節；禁止編造。"
        )

        try:
            out = self.extract_slots(context_text, schema, rules)
        except Exception:
            out = {}

        line1 = _clean_str(out.get("location_category_line"))
        line2 = _clean_str(out.get("summary_line"))

        if not line1:
            line1 = (
                f"{_resolve_address_label(filled_fields)}"
                f"{_resolve_category_label(filled_fields)}"
            )
        if not line2:
            line2 = _compose_summary_body(filled_fields, transcript)

        report = format_dispatch_report(line1, line2)
        if _is_valid_analysis_report(report):
            return report
        return build_fallback_analysis_report(transcript, filled_fields)
