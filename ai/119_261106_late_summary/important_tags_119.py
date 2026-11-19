"""
119 全類型案件重要標籤。

IMPORTANT_TAGS 是所有允許出現的標籤（白名單），分成兩種：
- 案情標籤（CASE_CONTENT_TAGS）：報案人講到的案情，例如持刀、自殺。
  由 LLM 判斷，或從報案人原話直接比對。
- 系統狀態標籤（SYSTEM_STATUS_TAGS）：流程出狀況時由程式寫入，例如地址查不到、
  問兩次仍分不出火災類型。LLM 不可以選這些，否則流程其實正常時也會被誤標
  （例如聽到「我要報火災」就標上「火災類別無法確認」）。
擴充方式：新標籤追加至 IMPORTANT_TAGS；若是系統狀態標籤，也要加進 SYSTEM_STATUS_TAGS。

另有報案人關鍵字（CALLER_KEYWORD_TAGS）：報案人原話講到就把那個詞本身加進標籤，
提醒受理員。只做原話比對，不給 LLM 選（詞太多，放進提示會拖慢推論）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Sequence, Tuple

import openpyxl


IMPORTANT_TAGS: Tuple[str, ...] = (
    "槍聲",
    "殺人",
    "跳樓",
    "賭博",
    "自殺",
    "上吊",
    "槍枝",
    "毒品",
    "持械",
    "持刀",
    "持槍",
    "擄人",
    "砍人",
    "屍體",
    "毒駕",
    "性侵",
    "非法拘禁",
    "救命",
    "強盜",
    "OHCA",
    "地址搜尋失敗",
    "地址未確認",
    "Q1 兩輪仍無法判斷",
    "Q2 兩輪仍無法判斷",
    "火災類別無法確認",
    "火災類型無法判斷，預設輕微火警",
    "回撥電話無法確認",
    "報案人稱呼無法確認",
)

# 系統狀態標籤：只由程式寫入，LLM 與原話比對都不會產生
SYSTEM_STATUS_TAGS: Tuple[str, ...] = (
    "地址搜尋失敗",
    "地址未確認",
    "Q1 兩輪仍無法判斷",
    "Q2 兩輪仍無法判斷",
    "火災類別無法確認",
    "火災類型無法判斷，預設輕微火警",
    "回撥電話無法確認",
    "報案人稱呼無法確認",
)

# 案情標籤：給 LLM 選、以及從報案人原話比對時，只用這一份
CASE_CONTENT_TAGS: Tuple[str, ...] = tuple(
    tag for tag in IMPORTANT_TAGS if tag not in SYSTEM_STATUS_TAGS
)

# 報案人關鍵字：讀 scripts/案類關鍵字展開表1107_審核後.xlsx 的「都應反色字_展開」頁，
# 表上 F 欄每一個關鍵字都收（已含審核採用的相似詞）。
# 「產生方式」寫「待補名稱」的列（廠辦大樓、工業區）是等使用者補具體名稱的佔位，不收。
_KEYWORD_XLSX = Path(__file__).resolve().parent / "scripts" / "案類關鍵字展開表1107_審核後.xlsx"
_KEYWORD_SHEET = "都應反色字_展開"


def _load_caller_keywords() -> Tuple[str, ...]:
    wb = openpyxl.load_workbook(_KEYWORD_XLSX, data_only=True, read_only=True)
    try:
        keywords: List[str] = []
        for row in wb[_KEYWORD_SHEET].iter_rows(min_row=2, values_only=True):
            keyword = str(row[5] or "").strip() if len(row) > 5 else ""
            method = str(row[6] or "").strip() if len(row) > 6 else ""
            if keyword and method != "待補名稱" and keyword not in keywords:
                keywords.append(keyword)
        return tuple(keywords)
    finally:
        wb.close()


CALLER_KEYWORD_TAGS: Tuple[str, ...] = _load_caller_keywords()

# 報案人講到這些詞就標上「OHCA」（使用者 11/17 決定，先放這兩個）
OHCA_TAG = "OHCA"
OHCA_KEYWORDS: Tuple[str, ...] = ("OHCA", "ohca")

# 全部合法標籤：合併既有標籤時用這一份，報案人關鍵字才不會被濾掉
ALL_TAGS: Tuple[str, ...] = IMPORTANT_TAGS + CALLER_KEYWORD_TAGS


def normalize_important_tags(
    value: Any, allowed_tags: Sequence[str] = ALL_TAGS,
) -> List[str]:
    """
    將字串或序列清洗為 allowed_tags 內、依輸入順序穩定去重的標籤。
    allowed_tags 預設是全部合法標籤；LLM 的結果要傳 CASE_CONTENT_TAGS。
    同一段話裡，短的詞若是包在比較長的詞裡面，只留長的
    （例如「有人燒炭」只標「有人燒炭」，不會再多標一個「燒炭」）。
    """
    if value is None:
        return []
    if isinstance(value, str):
        values: Sequence[Any] = (value,)
    elif isinstance(value, (list, tuple, set)):
        values = tuple(value)
    else:
        return []

    normalized: List[str] = []
    for item in values:
        text = str(item) if item is not None else ""
        matches = sorted(
            (
                (text.find(allowed), order, allowed)
                for order, allowed in enumerate(allowed_tags)
                if allowed in text
            ),
            key=lambda match: (match[0], match[1]),
        )
        for start, _, allowed in matches:
            end = start + len(allowed)
            inside_longer_word = any(
                other_start <= start and end <= other_start + len(other)
                and len(other) > len(allowed)
                for other_start, _, other in matches
            )
            if inside_longer_word:
                continue
            if allowed not in normalized:
                normalized.append(allowed)
    return normalized


def match_important_tags(text: str) -> List[str]:
    """以本輪報警人原話直接比對案情標籤與報案人關鍵字（系統狀態標籤不會從原話產生）。"""
    tags = normalize_important_tags(text, CASE_CONTENT_TAGS + CALLER_KEYWORD_TAGS)
    if OHCA_TAG not in tags and any(word in text for word in OHCA_KEYWORDS):
        tags.append(OHCA_TAG)
    return tags


def important_case_level(tags: Sequence[str], level: int) -> int:
    """有 OHCA 標籤的案件，重要程度一律是 2（緊急處理），不會被後面的判斷降下來。"""
    return 2 if OHCA_TAG in tags else level


def merge_important_tags(current: Sequence[str], incoming: Any) -> List[str]:
    """保留既有合法標籤，並依本輪輸入順序追加新標籤。"""
    merged = normalize_important_tags(current)
    for tag in normalize_important_tags(incoming):
        if tag not in merged:
            merged.append(tag)
    return merged
