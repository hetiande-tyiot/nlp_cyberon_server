"""
hard_subcategory_rules_119.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
次案類的硬規則。詞來自 scripts/案類關鍵字展開表1107_審核後.xlsx 的
「判斷案類絕對關鍵字_展開」表（已審核），表上有詞的次案類都會套用。
命中後由引擎同時寫入次案類與疑似次案類。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl

_SHEET = "判斷案類絕對關鍵字_展開"
_XLSX = Path(__file__).resolve().parent / "scripts" / "案類關鍵字展開表1107_審核後.xlsx"

# 表上的欄位：B 大案類、C 次案類、F 關鍵字（第一列是標題）。
_COL_MAIN = 1
_COL_SUB = 2
_COL_KEYWORD = 5

# 其他案類有幾個次案類在表上寫成「破門(緊急救援-破門)」，括號是對照用的說明，
# 程式裡的次案類名稱不含括號，所以讀進來時拿掉。
_OTHER_CASE_NOTE = re.compile(r"[（(]緊急救援-[^)）]*[)）]\s*$")

# 表上的「緊急救援／其他」都是卡住、夾住的說法，命中就走卡住夾住的題目。
_STUCK_LABEL = "其他(卡住夾住)"

# 使用者決定不收的詞：(大案類, 次案類, 關鍵字)。
_EXCLUDED = frozenset({
    # 這幾個是審核時加進集合住宅的相似詞，太通用，火警裡講到就會被定成集合住宅
    ("火警", "集合住宅", "失火"),
    ("火警", "集合住宅", "火災"),
    ("火警", "集合住宅", "著火"),
    ("火警", "集合住宅", "起火"),
    ("火警", "集合住宅", "燒起來"),
    ("火警", "集合住宅", "冒煙"),
    # 只描述煙、火的樣子，沒提到建築物；車子、山林、垃圾著火也會這樣講
    # （例如汽車火警回答「黑煙」就被改成集合住宅）
    ("火警", "集合住宅", "黑煙"),
    ("火警", "集合住宅", "白煙"),
    ("火警", "集合住宅", "濃煙"),
    ("火警", "集合住宅", "灰煙"),
    ("火警", "集合住宅", "煙很大"),
    ("火警", "集合住宅", "有濃煙"),
    ("火警", "集合住宅", "有火煙"),
    ("火警", "集合住宅", "有火"),
    ("火警", "集合住宅", "有火舌"),
    ("火警", "集合住宅", "火很大"),
    ("火警", "集合住宅", "燒很大"),
    ("火警", "集合住宅", "火燒出來"),
    ("火警", "集合住宅", "有爆炸聲"),
    ("火警", "集合住宅", "有人在呼救"),
    ("火警", "集合住宅", "有人在喊救命"),
    # 跌落山坡不是卡住夾住，不能走卡住夾住的題目；要歸哪個次案類還沒決定
    ("緊急救援", "其他", "走路跌落山坡"),
    ("緊急救援", "其他", "走路跌落山邊坡"),
    # 只講到橋太籠統，橋上的車禍、橋梁受損也會被定成跳水；「站在橋上」「從橋上跳下」這類較長的說法照常比對
    ("緊急救援", "跳水", "橋上"),
    ("緊急救援", "跳水", "橋梁"),
    ("緊急救援", "跳水", "橋中間"),
})

_Rule = Tuple[str, str, str, int]


def _compact(text: str) -> str:
    return "".join((text or "").split())


def _cell(row: tuple, idx: int) -> str:
    value = row[idx] if len(row) > idx else None
    return str(value or "").strip()


@lru_cache(maxsize=1)
def _load_rules() -> Dict[str, Tuple[_Rule, ...]]:
    by_main: Dict[str, List[_Rule]] = {}
    wb = openpyxl.load_workbook(_XLSX, data_only=True, read_only=True)
    try:
        ws = wb[_SHEET]
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row:
                continue
            main = _cell(row, _COL_MAIN)
            sub = _cell(row, _COL_SUB)
            keyword = _cell(row, _COL_KEYWORD)
            if not main or not sub or not keyword:
                continue
            if (main, sub, keyword) in _EXCLUDED:
                continue
            if main == "緊急救援" and sub == "其他":
                sub = _STUCK_LABEL
            elif main == "其他案類":
                sub = _OTHER_CASE_NOTE.sub("", sub).strip()
            by_main.setdefault(main, []).append((sub, keyword, _compact(keyword), row_idx))
    finally:
        wb.close()
    return {main: tuple(rules) for main, rules in by_main.items()}


def keywords_for(main_category: str, sub_category: str) -> Tuple[str, ...]:
    """該大案類、次案類載入到的關鍵詞。表上沒有則空。"""
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


_HERITAGE = "古蹟、文化財"
# 報案人關鍵詞標籤表上也有這些籠統的詞，不是古蹟的名字，地址裡的「○○寺路」才不會被當成古蹟
_HERITAGE_GENERIC = frozenset({"古蹟", "宮廟", "寺廟", "廟宇", "寺"})


def match_named_heritage(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    報案人回答地址的話裡，有沒有講到有名字的古蹟（例如「鶯歌美術館」）。

    只認「火警－古蹟、文化財」硬規則裡、同時也列在報案人關鍵詞標籤的名字，
    「寺」「宮廟」這類短詞不算，地址裡的「○○寺路」才不會被當成古蹟。
    回傳 (古蹟、文化財, 命中的名字)；未命中為 (None, None)。
    """
    from important_tags_119 import CALLER_KEYWORD_TAGS

    compact = _compact(text)
    if not compact:
        return None, None
    for keyword in keywords_for("火警", _HERITAGE):
        if keyword in _HERITAGE_GENERIC or keyword not in CALLER_KEYWORD_TAGS:
            continue
        if _compact(keyword) in compact:
            return _HERITAGE, keyword
    return None, None
