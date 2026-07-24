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
  .extract_confirmation(question, caller_text, current_address) -> dict
      判斷報警人是否確認地址，或提供新地址/補充。
  .extract_vital_sign(question, caller_text) -> bool | None
      抽取單一生命征象（True/False/None）。
  .extract_patient_info(question, caller_text) -> dict
      抽取患者性別/年齡/事件/現況（單輪問答上下文）。
  .extract_general_fields(caller_text) -> dict
      每輪通用欄位嘗試抽取（靜默降級）。
  .extract_summary_confirmation(question, caller_text) -> bool | None
      判斷報警人是否確認案情摘要。
  .generate_summary(transcript_texts, filled_fields) -> str
      案情摘要生成（每輪更新）。
  .generate_analysis_report(transcript, filled_fields) -> str
      AI 初報分析報告（固定「報告：(初報)」格式）。
"""

from __future__ import annotations

import json
import os
import re
from threading import Lock
from typing import Any, Dict, List, Optional

from sop_utils_119 import format_qa_for_llm, parse_yes_no, parse_yes_no_for_question

# ─── 常量 ─────────────────────────────────────────────────────────────────────

DEFAULT_MODEL_PATH = (
    "/home/cyberon2/nlp_cyberon_server/models/TW-119-Model.gguf"
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
    ):
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

        self._llm = Llama(
            model_path=model_path,
            chat_format="qwen",
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=verbose,
            flash_attn=True,
        )
        self._temperature = temperature
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
        try:
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
            return _strip_think_and_fences(raw)
        except Exception as e:
            return f"[LLM_ERROR: {e}]"

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
    ) -> Dict[str, Optional[str]]:
        """
        從報警人文本中抽取完整事發地址（含樓層）。

        use_question=False 時僅依原文抽取（適合第一輪混合陳述）。
        返回 {"address": str|None}
        """
        schema = {"address": "string|null"}
        rules = (
            "- address：抽取完整事發地址，合併區、路段、門牌、樓層、地標為一個字串。\n"
            "  • 若文本出現「地址在/地址是/地點在」等，抽取其後的地址片段。\n"
            "  • 允許缺縣市：如「土城區裕民路142號」可直接輸出，勿因缺新北市而輸出 null。\n"
            "  • 必須保留文本中所有可協助派遣定位的地點細節。\n"
            "  • 口語以頓號/逗號逐步細化的地點必須全部合併。\n"
            "  • 嚴禁把案件類別詞併入地址：救護車/救護/火災/消防/消防车等開頭回答。\n"
            "  • 若未提及任何可定位地點，輸出 null。\n"
            "  • 嚴禁輸出「未知」「不明」「不詳」等佔位字；無地址 → null。"
        )
        question = "請先告訴我地址？幾層？" if use_question else None
        out = self.extract_slots(caller_text, schema, rules, question=question)
        return {"address": _clean_str(out.get("address"))}

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
            "  • 若回答主要是提供新/更精確地址（補門牌、弄、號），confirmed → null\n"
            "  • 長答句末肯定語仍視為 true\n"
            "- new_address：\n"
            "  • 報警人提供不同或更精確地址時，抽取其提供的地址片段\n"
            "  • 例：「連城路347巷1弄2號附近」→ 完整輸出該片段\n"
            "  • 可省略區名，系統會與當前地址合併；僅確認/否認無新地址 → null"
        )
        out = self.extract_slots(
            caller_text, schema, rules,
            question=question,
            strict_tail=_STRICT_TAIL,
        )
        confirmed = _coerce_bool(out.get("confirmed"))
        if confirmed is None:
            confirmed = parse_yes_no_for_question(question, caller_text)
        return {
            "confirmed":   confirmed,
            "new_address": _clean_str(out.get("new_address")),
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
            "文本提及就抽取。\n"
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
    ) -> Dict[str, Any]:
        """
        每輪輸入後跨欄位嘗試抽取所有業務欄位。

        設計原則：
        - 每一則報警人回答都走 LLM，對全部業務欄位嘗試抽取
        - 拆成兩輪較小 schema（核心 + 擴展），避免單次 JSON 被截斷
        - 核心患者欄位若仍空，再以 extract_patient_info 專項補強（仍為 LLM）
        - 靜默降級：失敗返回 {}，不中斷主流程

        返回值只包含本次成功抽取的非 null 欄位。
        """
        # 分兩輪抽取，降低大 JSON 截斷機率
        core_schema = {
            "address":              "string|null",
            "consciousness":        "true|false|null",
            "breathing":            "true|false|null",
            "abdomen_rise":         "true|false|null",
            "patient_count":        "string|null",
            "patient_gender":       "string|null",
            "patient_age":          "string|null",
            "incident_description": "string|null",
            "current_condition":    "string|null",
            "medical_history":      "string|null",
            "collapse_cause":       "string|null",
        }
        ext_schema = {
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
            "caller_name":           "string|null",
            "caller_contact":        "string|null",
            "caller_address":        "string|null",
        }
        core_rules = (
            "【抽取原則】結合問題語義，從報警人回答抽取；長答可同時填多欄；"
            "問題主題不同也不得漏抽。\n"
            "【示例】問「發生了什麼事？」"
            "答「男生 75 歲左右，說話口語含糊、腳沒力走不了」→\n"
            "patient_gender=男, patient_age=75歲, "
            "incident_description=說話口語含糊、腳沒力走不了, "
            "current_condition=口語含糊、腳沒力、走不了；其餘 null。\n"
            "- address：可定位地址；勿併入救護車/火災等類別詞；無 → null。\n"
            "- consciousness/breathing/abdomen_rise：僅明確提及時填 true/false。\n"
            "- patient_count/patient_gender/patient_age：提及就填；"
            "男生→男；75歲左右→75歲。\n"
            "- incident_description：事件經過/主要病情；症狀描述也要填。\n"
            "- current_condition：目前症狀/狀況。\n"
            "- medical_history/collapse_cause：有才填，否則 null。"
        )
        ext_rules = (
            "【抽取原則】從報警人回答抽取下列欄位；未提及 → null。\n"
            "- injury_cause/location/severity：受傷原因/部位/傷勢。\n"
            "- tocc：旅遊/職業/接觸/群聚史。\n"
            "- ingested_substance：服藥種類數量。\n"
            "- blood_glucose/blood_pressure/seizure_info：血糖/血壓/抽搐。\n"
            "- pregnancy_week/due_date/multiple_pregnancy/"
            "water_broken_bleeding/contractions/prenatal_history/prenatal_clinic：孕產資訊。\n"
            "- caller_name/caller_contact/caller_address：報案人姓名/電話/住址。"
        )
        _aggressive_q = (
            "意識", "意识", "呼吸", "起伏", "是否", "確定", "對嗎",
            "發生", "发生", "什麼事", "什么事", "甚麼事", "甚么事", "狀況", "状况",
        )
        tail = _STRICT_TAIL_YESNO if question and any(
            k in question for k in _aggressive_q
        ) else _STRICT_TAIL

        merged: Dict[str, Any] = {}
        for schema, rules in (
            (core_schema, core_rules),
            (ext_schema, ext_rules),
        ):
            try:
                out = self.extract_slots(
                    caller_text, schema, rules,
                    question=question,
                    strict_tail=tail,
                    max_tokens=512,
                )
            except Exception:
                out = {}
            if out:
                merged.update(out)

        # 核心患者欄位缺漏 → 專項 LLM 再抽（小 schema，更穩）
        _need_patient_retry = (
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

        all_keys = list(core_schema) + list(ext_schema)
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
            else:
                cleaned = _clean_str(val)
                if cleaned:
                    result[key] = cleaned
        return result

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
        include_address=False：{"caller_name": ..., "caller_contact": ...}
        include_address=True ：{"caller_name": ..., "caller_contact": ..., "caller_address": ...}
        """
        schema: Dict[str, str] = {
            "caller_name":    "string|null",
            "caller_contact": "string|null",
        }
        rules = (
            "- caller_name：報案人自述的姓名（可為全名/姓/稱謂）；未提及 → null。\n"
            "- caller_contact：報案人自述的電話號碼或手機號碼；抽取完整數字序列；"
            "未提及 → null。\n"
            "  • 若文本中含多個號碼，優先取報案人自報的聯繫電話。"
        )
        if include_address:
            schema["caller_address"] = "string|null"
            rules += (
                "\n- caller_address：報案人自述的本人住址（非事發現場地址）；"
                "抽取完整地址字串；未提及 → null。"
            )
        out = self.extract_slots(caller_text, schema, rules, question=question)
        result: Dict[str, Optional[str]] = {
            "caller_name":    _clean_str(out.get("caller_name")),
            "caller_contact": _clean_str(out.get("caller_contact")),
        }
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
