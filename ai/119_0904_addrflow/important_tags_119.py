"""
119 全類型案件重要標籤。

擴充方式：將新標籤追加至 IMPORTANT_TAGS；抽取結果只會保留此白名單中的值。
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
    "回撥電話無法確認",
    "報案人稱呼無法確認",
)


def normalize_important_tags(value: Any) -> List[str]:
    """將字串或序列清洗為白名單內、依輸入順序穩定去重的標籤。"""
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
                for order, allowed in enumerate(IMPORTANT_TAGS)
                if allowed in text
            ),
            key=lambda match: (match[0], match[1]),
        )
        for _, _, allowed in matches:
            if allowed not in normalized:
                normalized.append(allowed)
    return normalized


def match_important_tags(text: str) -> List[str]:
    """以本輪報警人原話直接匹配白名單標籤。"""
    return normalize_important_tags(text)


def merge_important_tags(current: Sequence[str], incoming: Any) -> List[str]:
    """保留既有合法標籤，並依本輪輸入順序追加新標籤。"""
    merged = normalize_important_tags(current)
    for tag in normalize_important_tags(incoming):
        if tag not in merged:
            merged.append(tag)
    return merged
