"""sop_element_id_119.py — 已填欄位 → SOP 要素編號。

編號格式是「次案類編號-題號」，例如救護-車禍的受傷原因是 ``202-1``。
對照表來自 scripts/CaseTypeQA.xlsx：用「主類別-次案類」加欄位中文名
對上「次案類 + 關鍵要素」。對不上的欄位不給編號。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Mapping, Optional, Tuple

from case_field_labels_119 import LABELS

_XLSX = Path(__file__).resolve().parent / "scripts" / "CaseTypeQA.xlsx"
_SHEET = "次案類問題"

# 代碼裡的次案類名稱 → Excel「次案類」橫線後面的名稱
_SUBCATEGORY_ALIASES = {
    "孕婦急產": "孕婦待產",
}

# 欄位中文名（LABELS）→ Excel「關鍵要素」。用字相同的不必寫在這裡。
_LABEL_TO_ELEMENT = {
    "是否有意識": "意識",
    "是否有呼吸": "呼吸",
    "傷病患人數": "患者人數",
    "過去病史": "病史",
    "發生了什麼事": "病徵",
    "延燒可能": "是否延燒",
    "應門狀況（起火戶或負責人）": "應門或聯絡狀況",
    "報案人是否即患者": "報案人與患者關係",
    "宮縮情況": "陣痛狀況",
    "預產期": "預產期與懷孕週數",
    "產檢異常史": "產檢狀況",
    # LABELS 寫「看到火還是煙」，表裡的關鍵要素是「火煙狀況」（透天厝第 4 題）。
    "看到火還是煙": "火煙狀況",
}


def case_type_key(main_category: Optional[str], sub_category: Optional[str]) -> Optional[str]:
    """拼出 Excel「次案類」欄的鍵。次案類未定、主類已是救護時用表裡的「救護」。"""
    main = (main_category or "").strip()
    sub = (sub_category or "").strip()
    if sub:
        sub = _SUBCATEGORY_ALIASES.get(sub, sub)
        if not main:
            return None
        return f"{main}-{sub}"
    if main == "救護":
        return "救護"
    return None


def _is_filled(field: str, value: Any) -> bool:
    """與 CaseInfo119.is_field_filled 同一套空值判斷。False 布林算已填。"""
    if value is None:
        return False
    if field == "ImportantCase" and value == 0:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _number_text(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value or "").strip()
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


@lru_cache(maxsize=1)
def load_element_index(path: str = str(_XLSX)) -> Dict[Tuple[str, str], str]:
    """(次案類, 關鍵要素) → 「編號-題號」。同一組重複時保留題號較小的那列。"""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("讀取 CaseTypeQA.xlsx 需要安裝 openpyxl") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if _SHEET not in workbook.sheetnames:
            raise ValueError(f"CaseTypeQA.xlsx 缺少工作表：{_SHEET}")
        sheet = workbook[_SHEET]
        rows = sheet.iter_rows(values_only=True)
        header = [str(cell or "").strip() for cell in next(rows, ())]
        required = ("次案類編號", "次案類", "題號", "關鍵要素")
        missing = [name for name in required if name not in header]
        if missing:
            raise ValueError(f"CaseTypeQA.xlsx 缺少欄位：{', '.join(missing)}")
        index = {name: header.index(name) for name in required}
        table: Dict[Tuple[str, str], str] = {}
        for row in rows:
            if not row or row[index["次案類編號"]] is None:
                continue
            subtype = str(row[index["次案類"]] or "").strip()
            element = str(row[index["關鍵要素"]] or "").strip()
            if not subtype or not element:
                continue
            code = (
                f"{_number_text(row[index['次案類編號']])}"
                f"-{_number_text(row[index['題號']])}"
            )
            key = (subtype, element)
            current = table.get(key)
            if current is None or _question_number(code) < _question_number(current):
                table[key] = code
        return table
    finally:
        workbook.close()


def _question_number(code: str) -> int:
    try:
        return int(code.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 10**9


def _answer_text(value: Any) -> str:
    """欄位值轉成看得懂的文字：是／否、清單用「、」串起來。"""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value)
    return _number_text(value)


# 不給編號的欄位：building_structure 是派遣卡的數字代碼（1 木造、2 鐵皮⋯），
# 跟文字的 building_construction 同樣叫「建物構造」，這一題用文字版。
_SKIP_FIELDS = {"building_structure"}

# 火警、照題目表問的救護次案類「還沒答、但要問」的題目放的內容。下游拿到的值一律是字串，用這兩個字判斷要問。
PENDING_ANSWER = "待問"


def sop_element_ids(case: Mapping[str, Any]) -> Dict[str, str]:
    """已填且對得上表的欄位 → {編號: 抽到的內容}。

    例如 {"102-5": "有火有煙"}。
    火警、照題目表問的救護次案類另外把「還沒答、但要問」的題目也列出來，
    內容是「待問」（見 _ordered_element_ids）。
    """
    subtype = case_type_key(case.get("main_category"), case.get("sub_category"))
    if not subtype:
        return {}
    table = load_element_index()
    ordered_ids = _ordered_element_ids(case, subtype, table)
    if ordered_ids is not None:
        return ordered_ids
    found: Dict[str, str] = {}
    for field, label in LABELS.items():
        if field in _SKIP_FIELDS:
            continue
        if field not in case or not _is_filled(field, case.get(field)):
            continue
        element = _LABEL_TO_ELEMENT.get(label, label)
        code = table.get((subtype, element))
        if code:
            found[code] = _answer_text(case.get(field))
    return found


def _ordered_element_ids(
    case: Mapping[str, Any], subtype: str, table: Mapping[Tuple[str, str], str],
) -> Optional[Dict[str, str]]:
    """火警、照題目表問的救護次案類：照題目的順序給編號，第 N 題就是「次案類編號-N」。

    題目表（火警 fire_tab_map_119.TAB_QUESTIONS、救護 ems_tab_map_119.EMS_QUESTIONS）
    跟 CaseTypeQA.xlsx 的題號一題一題對得上，所以直接用位置，不用名稱去對
    （同一個垂片有兩題都叫「建築物類型」）。
    - 有答案：放答案
    - 還沒答案，但要問（主動題、前置條件成立的條件題）：放「待問」，由下游判斷這題要問
    - 不用問（前置條件不成立、被動題還沒人講到）：不放
    要不要問，跟引擎追問用的是同一份前置條件。
    次案類沒有題目表（例如瓦斯漏氣、還沒照 xlsx 改寫的救護次案類）時回傳 None，
    交給原本用名稱對的做法。
    """
    from ems_tab_map_119 import questions_for_subtype
    from fire_tab_map_119 import (
        MODE_ACTIVE, MODE_CONDITIONAL, TAB_QUESTIONS, tab_for_subtype,
    )

    main = case.get("main_category")
    if main == "火警":
        questions = TAB_QUESTIONS.get(tab_for_subtype(case.get("sub_category")) or "")
    elif main == "救護":
        questions = questions_for_subtype(case.get("sub_category"))
    else:
        return None
    case_type_id = next(
        (code.rsplit("-", 1)[0] for (name, _), code in table.items() if name == subtype),
        None,
    )
    if not questions or not case_type_id:
        return None
    # 前置條件是用 case.欄位 的方式讀，把 dict 包成可以這樣讀的物件
    view = SimpleNamespace(**case)
    found: Dict[str, str] = {}
    for number, item in enumerate(questions, start=1):
        code = f"{case_type_id}-{number}"
        value = case.get(item.field)
        if _is_filled(item.field, value):
            if _answer_number(questions, item.field, view) == number:
                found[code] = _answer_text(value)
            continue
        if item.mode == MODE_ACTIVE or (
            item.mode == MODE_CONDITIONAL and item.condition(view)
        ):
            found[code] = PENDING_ANSWER
    return found


def _answer_number(questions: Tuple[Any, ...], field: str, view: Any) -> int:
    """同一個欄位出現在好幾題時（例如工廠、非工廠兩種建築物類型），答案放在哪一題。

    放在第一個前置條件成立（或沒有前置條件）的題目；都不成立就放第一題。
    """
    numbers = [n for n, item in enumerate(questions, start=1) if item.field == field]
    for number in numbers:
        condition = questions[number - 1].condition
        if condition is None or condition(view):
            return number
    return numbers[0]
