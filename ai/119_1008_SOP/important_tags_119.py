"""
119 全類型案件重要標籤。

IMPORTANT_TAGS 是所有允許出現的標籤（白名單），分成兩種：
- 案情標籤（CASE_CONTENT_TAGS）：報案人講到的案情，例如持刀、自殺。
  由 LLM 判斷，或從報案人原話直接比對。
- 系統狀態標籤（SYSTEM_STATUS_TAGS）：流程出狀況時由程式寫入，例如地址查不到、
  問兩次仍分不出火災類型。LLM 不可以選這些，否則流程其實正常時也會被誤標
  （例如聽到「我要報火災」就標上「火災類別無法確認」）。
擴充方式：新標籤追加至 IMPORTANT_TAGS；若是系統狀態標籤，也要加進 SYSTEM_STATUS_TAGS。
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple


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


def normalize_important_tags(
    value: Any, allowed_tags: Sequence[str] = IMPORTANT_TAGS,
) -> List[str]:
    """
    將字串或序列清洗為 allowed_tags 內、依輸入順序穩定去重的標籤。
    allowed_tags 預設是全部白名單；LLM 與原話比對的結果要傳 CASE_CONTENT_TAGS。
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
        for _, _, allowed in matches:
            if allowed not in normalized:
                normalized.append(allowed)
    return normalized


def match_important_tags(text: str) -> List[str]:
    """以本輪報警人原話直接比對案情標籤（系統狀態標籤不會從原話產生）。"""
    return normalize_important_tags(text, CASE_CONTENT_TAGS)


def merge_important_tags(current: Sequence[str], incoming: Any) -> List[str]:
    """保留既有合法標籤，並依本輪輸入順序追加新標籤。"""
    merged = normalize_important_tags(current)
    for tag in normalize_important_tags(incoming):
        if tag not in merged:
            merged.append(tag)
    return merged
