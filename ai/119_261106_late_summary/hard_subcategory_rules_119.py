"""
hard_subcategory_rules_119.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
指定次案類的硬規則。詞來自 scripts/119keywords.xlsx 第一張表，
只收錄呼叫端點名的大案類／次案類。命中後由引擎同時寫入次案類與疑似次案類。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl

_SHEET = "民眾可能說的關鍵字(判斷次案類)"
_XLSX = Path(__file__).resolve().parent / "scripts" / "119keywords.xlsx"

# 詞尾的等級標記，例如 (D)、（B)、以及表裡的筆誤「路塌陷B)」。
_TRAILING_GRADE = re.compile(
    r"(?:[（(]\s*[ABCDabcd]\s*[)）]|[ABCDabcd]\s*[)）])\s*$"
)

# 只對這些次案類做硬規則。火警名稱與表內 C 列、垂片對照一致，不拆開。
HARD_RULE_TARGETS: Dict[str, Tuple[str, ...]] = {
    "救護": (
        "刀傷(切割傷)",
        "喝農藥",
        "電擊傷",
        "溺水",
        "槍傷",
        "吸入廢氣",
    ),
    "火警": (
        "旅館、百貨商場用途建築物",
        "古蹟、文化財",
        "地下建築物(如地下街)",
        "高層建築物(10層樓以上)",
        "船舶",
        "電影院用途建築物",
        "軌道型交通工具",
    ),
    "緊急救援": (
        "開瓦斯自殺",
        "氣爆",
        "緊急救援",
        "CO中毒",
        "溺水",
        "破門",
        "其他(卡住夾住)",
    ),
    "災害": (
        "道路坍方落石",
        "電線掉落",
        "積水",
        "鐵皮掉落",
        "道路受損",
        "招牌掉落",
        "自來水管線破裂",
        "淹水",
        "電線桿傾倒",
        "人員疏散及災民收容",
        "土石流及大規模崩塌災害",
        "災害",
        "交通號誌損壞",
        "山坡地社區災害",
        "電力停電",
        "道路中斷",
    ),
    "其他案類": (
        "破門",
        "動物救援",
        "其他案類",
        "剪除異物",
        "捕蜂",
        "捕捉動物",
        "送水",
        "電梯受困",
    ),
    "檢舉投訴": (
        "其它",
        "消防安全",
        "救護",
        "檢舉投訴",
        "危險物品",
        "服勤紀律",
        "救災",
    ),
}

# 表上的「緊急救援／其他」混了卡住和雜項。只有卡住這些詞才直通卡住的 SOP。
_STUCK_LABEL = "其他(卡住夾住)"
_STUCK_KEYWORDS = frozenset({
    "手指卡住",
    "手指頭卡住",
    "頭卡住",
    "腳卡住",
    "手被機器捲進去",
    "機器捲入",
    "腳卡在椅子",
})
_Rule = Tuple[str, str, str, int]


def normalize_hard_keyword(raw: object) -> str:
    """去掉空白與詞尾等級標記。等級被拿掉後沒有剩字就回空字串。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    return _TRAILING_GRADE.sub("", text).strip()


def _compact(text: str) -> str:
    return "".join((text or "").split())


@lru_cache(maxsize=1)
def _load_rules() -> Dict[str, Tuple[_Rule, ...]]:
    wanted = {
        main: set(subs) for main, subs in HARD_RULE_TARGETS.items()
    }
    found: Dict[Tuple[str, str], List[_Rule]] = {
        (main, sub): []
        for main, subs in HARD_RULE_TARGETS.items()
        for sub in subs
    }
    wb = openpyxl.load_workbook(_XLSX, data_only=True, read_only=True)
    try:
        ws = wb[_SHEET]
        current_main: Optional[str] = None
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row:
                continue
            main_cell = row[1] if len(row) > 1 else None
            sub_cell = row[2] if len(row) > 2 else None
            if main_cell is not None and str(main_cell).strip():
                current_main = str(main_cell).strip()
            if current_main not in wanted or sub_cell is None:
                continue
            sub = str(sub_cell).strip()
            if current_main == "緊急救援" and sub == "其他":
                bucket = found.get((current_main, _STUCK_LABEL))
                if bucket is None:
                    continue
                for cell in row[3:]:
                    keyword = normalize_hard_keyword(cell)
                    if keyword in _STUCK_KEYWORDS:
                        bucket.append((_STUCK_LABEL, keyword, _compact(keyword), row_idx))
                continue
            if sub not in wanted[current_main]:
                continue
            bucket = found[(current_main, sub)]
            for cell in row[3:]:
                keyword = normalize_hard_keyword(cell)
                if not keyword:
                    continue
                bucket.append((sub, keyword, _compact(keyword), row_idx))
    finally:
        wb.close()

    by_main: Dict[str, List[_Rule]] = {main: [] for main in HARD_RULE_TARGETS}
    for (main, _sub), rules in found.items():
        by_main[main].extend(rules)
    return {main: tuple(rules) for main, rules in by_main.items()}


def keywords_for(main_category: str, sub_category: str) -> Tuple[str, ...]:
    """該大案類、次案類載入到的關鍵詞（已去掉等級標記）。不在清單內則空。"""
    rules = _load_rules().get(main_category, ())
    return tuple(keyword for sub, keyword, _compact_kw, _row in rules if sub == sub_category)


def match_hard_subcategory(
    text: str,
    main_category: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    在目前大案類的硬規則裡做子串比對。

    多詞同時命中時取最長的詞；一樣長則取表中較前面的列。
    回傳 (次案類, 命中的關鍵詞)；未命中為 (None, None)。
    """
    compact = _compact(text)
    if not compact:
        return None, None
    rules = _load_rules().get(main_category)
    if not rules:
        return None, None

    best_sub: Optional[str] = None
    best_keyword: Optional[str] = None
    best_len = -1
    best_row = 10**9
    for sub, keyword, compact_kw, row in rules:
        if not compact_kw or compact_kw not in compact:
            continue
        if len(compact_kw) > best_len or (len(compact_kw) == best_len and row < best_row):
            best_len = len(compact_kw)
            best_row = row
            best_sub = sub
            best_keyword = keyword
    return best_sub, best_keyword
