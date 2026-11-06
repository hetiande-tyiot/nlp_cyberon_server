"""
disaster_flow_119.py
━━━━━━━━━━━━━━━━━━━━
119 災害大類通用題目。所有子類走同一套題，只有火煙狀況那一題看子類。

規格：docs/(all)災害垂片規格_關鍵要素與問句_1106.xlsx（01-災害垂片），使用者 11/06 決定照這份改。
一個關鍵要素一個欄位：名稱跟別的垂片一字不差就共用欄位（11/04 使用者決定），所以
人員受困、火煙狀況共用火警的欄位，報案人位置、報案身分共用救護的欄位。
題目格式跟救護題目表（ems_tab_map_119）一樣：沒有問句的題目跟上一題同一句問，
只答到一半就用 handlers/base.py 的 SINGLE_MISSING_QUESTIONS 單問句再問一次。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from fire_tab_map_119 import (
    FIRE_SMOKE_FIRE_OR_SMOKE_VISIBLE,
    MODE_ACTIVE,
    MODE_CONDITIONAL,
    _people_trapped,
    FireQuestion as DisasterQuestion,
)

# 人員受傷（固定說法，照 xlsx 參考範圍）。人員受困的固定說法跟火警一樣，用火警的。
INJURY_UNKNOWN = "未知"
INJURY_NONE = "無人受傷"
INJURY_YES = "有人受傷"
# 交通影響
TRAFFIC_CLEAR = "未影響交通"
TRAFFIC_PARTIAL = "佔用部分車道"
TRAFFIC_BLOCKED = "完全無法通行"

# 火煙狀況的前置條件：災害類型是這三種才問。
SPARK_SUBTYPES: Tuple[str, ...] = ("電線掉落", "招牌掉落", "電線桿傾倒")
# 火煙狀況是這三種 → 改判火警（xlsx 備註「有可能災害要轉火警」，使用者 11/06 決定；
# 只有火花、無火無煙、不確定都不改判）
FIRE_SWITCH_SMOKE_STATES: Tuple[str, ...] = FIRE_SMOKE_FIRE_OR_SMOKE_VISIBLE

DISPATCH_LINE = "救護人員已經派出了歐。"
TRAPPED_COUNT_QUESTION = "有幾個人被困住？"
# 次案類判不出來時依序追問的兩句（使用者 11/07 決定），兩句問完還判不出來就轉真人
SUB_REASK_QUESTIONS: Tuple[str, ...] = (
    "請問發生什麼事呢？",
    "請再說明一次發生什麼事情呢？",
)

# 只能從固定說法裡選的欄位。選了清單以外的值就不記。
DISASTER_FIXED_ANSWERS: Dict[str, Tuple[str, ...]] = {
    "disaster_injury": (INJURY_UNKNOWN, INJURY_NONE, INJURY_YES),
    "traffic_impact": (TRAFFIC_CLEAR, TRAFFIC_PARTIAL, TRAFFIC_BLOCKED),
}


def _spark_subtype(case: Any) -> bool:
    """災害類型 = 電線掉落、招牌掉落、電線桿傾倒。子類還不知道就不算。"""
    return getattr(case, "sub_category", None) in SPARK_SUBTYPES


def should_switch_to_fire(case: Any) -> bool:
    """火煙狀況 = 有火有煙、有火無煙、無火有煙 → 改判火警。"""
    return getattr(case, "fire_or_smoke", None) in FIRE_SWITCH_SMOKE_STATES


# 順序就是 xlsx 的順序
DISASTER_QUESTIONS: Tuple[DisasterQuestion, ...] = (
    DisasterQuestion(
        "人員受傷", "disaster_injury", MODE_ACTIVE,
        "災害-人員受傷", "有沒有人受傷？還是有人被困住出不來嗎？",
    ),
    # 跟人員受傷同一句問
    DisasterQuestion(
        "人員受困", "trapped_status", MODE_ACTIVE, "災害-人員受困",
    ),
    DisasterQuestion(
        "受困人數", "disaster_trapped_count", MODE_CONDITIONAL,
        "災害-受困人數", TRAPPED_COUNT_QUESTION,
        _people_trapped, "人員受困＝有人受困",
    ),
    DisasterQuestion(
        "交通影響", "traffic_impact", MODE_ACTIVE,
        "災害-交通影響", "有擋到路嗎？車子還過得去嗎？",
    ),
    DisasterQuestion(
        "火煙狀況", "fire_or_smoke", MODE_CONDITIONAL,
        "災害-火煙狀況", "現場有沒有冒火花或冒煙？",
        _spark_subtype, "案類＝電線掉落、招牌掉落、電線桿傾倒",
    ),
    DisasterQuestion(
        "報案人位置", "caller_location", MODE_ACTIVE,
        "災害-報案人位置", "請問您還在現場嗎？是路過民眾嗎？",
    ),
    # 跟報案人位置同一句問
    DisasterQuestion(
        "報案身分", "caller_relation", MODE_ACTIVE, "災害-報案身分",
    ),
)


def disaster_schema_and_rules() -> tuple[Dict[str, str], str]:
    """災害欄位的 JSON Schema 與抽取規則。只在主類是災害時送給 LLM。
    火煙狀況沿用火警的抽取規則，在 llm_extractor_119 併進來。"""
    schema = {
        "disaster_injury": "未知|無人受傷|有人受傷|null",
        "trapped_status": "未知|無人受困|有人受困|null",
        "disaster_trapped_count": "string|null",
        "traffic_impact": "未影響交通|佔用部分車道|完全無法通行|null",
        "caller_location": "string|null",
        "caller_relation": "string|null",
    }
    rules = (
        "【災害欄位】只依報警人本輪實際回答抽取；未提及 → null，不得從受理員問題複製答案。"
        "固定說法的欄位只能從列出的說法選一個，依意思判斷，不是看有沒有出現那幾個字。"
        "「參考」只是常見說法，不是選擇題：回答符合某個參考說法就用那個說法；"
        "不符合但和這一欄有關，就用報案人的話簡短記下。\n"
        "- disaster_injury 人員受傷（固定說法）：只能填 未知、無人受傷、有人受傷。"
        "說沒有人受傷 → 無人受傷；有人受傷、流血、被壓到受傷 → 有人受傷；"
        "說不知道、沒看到、不清楚有沒有人受傷 → 未知。沒講到受傷 → null。\n"
        "- trapped_status 人員受困（固定說法）：只能填 未知、無人受困、有人受困。"
        "說沒有人被困、人都出來了 → 無人受困；"
        "有人被壓住、卡住、出不來、被困住 → 有人受困；"
        "說不知道、沒看到、不清楚有沒有人被困 → 未知。沒講到受困 → null。"
        "只回答「沒有」時，看受理員問的是受傷還是受困：同時問兩個就兩欄都填無。\n"
        "- disaster_trapped_count 受困人數：只在講到幾個人被困時填，"
        "照報案人的話記（例如兩個、大概三個人），不要換成數字代碼；沒講人數 → null。\n"
        "- traffic_impact 交通影響（固定說法）：只能填 未影響交通、佔用部分車道、完全無法通行。"
        "沒擋到、車子照過 → 未影響交通；"
        "擋到一部分、還過得去、佔用車道 → 佔用部分車道；"
        "車子過不去、路斷了、完全擋住 → 完全無法通行。"
        "只說不知道 → null。\n"
        "- caller_location 報案人位置：參考 在現場、在遠處、不敢靠近、不在現場。"
        "說還在這裡、在旁邊 → 在現場；已經離開、開車路過已經走了 → 不在現場。沒講到 → null。\n"
        "- caller_relation 報案身分：參考 本人、家人、朋友、同事、老闆、房東、110、里長、鄰居、"
        "工人、工地主任、路過、看護、管理室、警衛(保全)、不認識。"
        "路人、經過看到、開車經過 → 路過；警衛、保全 → 警衛(保全)。"
        "只回答在或不在現場、沒講身分 → null。"
    )
    return schema, rules
