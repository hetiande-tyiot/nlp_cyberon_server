"""
disaster_flow_119.py
━━━━━━━━━━━━━━━━━━━━
119 災害大類通用題目。所有子類走同一套題，只有火花那一題看子類。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


# 受傷受困。參考範圍只列了前兩個，但受困人數的前置條件是「有人受困」。
INJURY_NONE = "無人受傷"
INJURY_HURT = "有人受傷"
INJURY_TRAPPED = "有人受困"
# 交通影響
TRAFFIC_CLEAR = "未影響交通"
TRAFFIC_PARTIAL = "佔用部分車道"
TRAFFIC_BLOCKED = "完全無法通行"
# 有無火花冒煙或帶電。規格沒有單獨的「帶電」，帶電、漏電併入「有火花或冒煙」。
HAZARD_NONE = "沒有"
HAZARD_YES = "有火花或冒煙"
HAZARD_UNSURE = "不確定"
# 報案人身分
ROLE_OWNER = "屋主或住戶"
ROLE_NEIGHBOR = "鄰居或附近店家"
ROLE_PASSERBY = "路過"
ROLE_MANAGER = "里長或管理員"
ROLE_OTHER = "其他"

# 火花題的前置條件：災害類型是這三種才問。
SPARK_SUBTYPES: Tuple[str, ...] = ("電線掉落", "招牌掉落", "電線桿傾倒")

DISPATCH_LINE = "已確認地址，相關人員已派出了喔。"
TRAPPED_COUNT_QUESTION = "有幾個人被困住？"

MODE_ACTIVE = "主動"
MODE_CONDITIONAL = "條件"

# 只能從固定說法裡選的欄位。選了清單以外的值就不記。
DISASTER_FIXED_ANSWERS: Dict[str, Tuple[str, ...]] = {
    "disaster_injury_or_trapped": (INJURY_NONE, INJURY_HURT, INJURY_TRAPPED),
    "traffic_impact": (TRAFFIC_CLEAR, TRAFFIC_PARTIAL, TRAFFIC_BLOCKED),
    "electrical_hazard": (HAZARD_NONE, HAZARD_YES, HAZARD_UNSURE),
    "disaster_caller_role": (
        ROLE_OWNER, ROLE_NEIGHBOR, ROLE_PASSERBY, ROLE_MANAGER, ROLE_OTHER,
    ),
}

DISASTER_FIELDS: Tuple[str, ...] = (
    "disaster_injury_or_trapped",
    "disaster_trapped_count",
    "traffic_impact",
    "electrical_hazard",
    "disaster_caller_role",
)


@dataclass(frozen=True)
class DisasterQuestion:
    element: str
    field: str
    mode: str
    stage: str
    question: str
    condition: Optional[Callable[[Any], bool]] = None
    condition_text: str = ""


def _people_trapped(case: Any) -> bool:
    """受傷受困 = 有人受困。還沒問出來就不算。"""
    return getattr(case, "disaster_injury_or_trapped", None) == INJURY_TRAPPED


def _spark_subtype(case: Any) -> bool:
    """災害類型 = 電線掉落、招牌掉落、電線桿傾倒。子類還不知道就不算。"""
    return getattr(case, "sub_category", None) in SPARK_SUBTYPES


DISASTER_QUESTIONS: Tuple[DisasterQuestion, ...] = (
    DisasterQuestion(
        "受傷受困", "disaster_injury_or_trapped", MODE_ACTIVE,
        "災害-受傷受困", "有人被壓到受傷或受困嗎？",
    ),
    DisasterQuestion(
        "受困人數", "disaster_trapped_count", MODE_CONDITIONAL,
        "災害-受困人數", TRAPPED_COUNT_QUESTION,
        _people_trapped, "受傷受困＝有人受困",
    ),
    DisasterQuestion(
        "交通影響", "traffic_impact", MODE_ACTIVE,
        "災害-交通影響", "有擋到路嗎？車子還過得去嗎？",
    ),
    DisasterQuestion(
        "有無火花冒煙或帶電", "electrical_hazard", MODE_CONDITIONAL,
        "災害-有無火花冒煙或帶電", "電線有沒有冒火花或冒煙？",
        _spark_subtype, "災害類型＝電線掉落、招牌掉落、電線桿傾倒",
    ),
    DisasterQuestion(
        "報案人身分", "disaster_caller_role", MODE_ACTIVE,
        "災害-報案人身分", "請問您還在現場嗎？",
    ),
)


def disaster_schema_and_rules() -> tuple[Dict[str, str], str]:
    """災害欄位的 JSON Schema 與抽取規則。只在主類是災害時送給 LLM。"""
    schema = {
        "disaster_injury_or_trapped": "無人受傷|有人受傷|有人受困|null",
        "disaster_trapped_count": "string|null",
        "traffic_impact": "未影響交通|佔用部分車道|完全無法通行|null",
        "electrical_hazard": "沒有|有火花或冒煙|不確定|null",
        "disaster_caller_role": "屋主或住戶|鄰居或附近店家|路過|里長或管理員|其他|null",
    }
    rules = (
        "【災害欄位】只依報警人本輪實際回答抽取；未提及 → null，不得從受理員問題複製答案。"
        "固定說法的欄位只能從列出的說法選一個，依意思判斷，不是看有沒有出現那幾個字。\n"
        "- disaster_injury_or_trapped 受傷受困（固定說法）：只能填 無人受傷、有人受傷、有人受困。"
        "沒有人受傷、也沒有人被困 → 無人受傷；"
        "有人受傷但沒有被壓住、卡住、出不來 → 有人受傷；"
        "有人被壓住、卡住、出不來、被困住 → 有人受困（即使同時受傷也填有人受困）。"
        "只說不知道、沒看到 → null。\n"
        "- disaster_trapped_count 受困人數：只在講到幾個人被困時填，"
        "照報案人的話記（例如兩個、大概三個人），不要換成數字代碼；沒講人數 → null。\n"
        "- traffic_impact 交通影響（固定說法）：只能填 未影響交通、佔用部分車道、完全無法通行。"
        "沒擋到、車子照過 → 未影響交通；"
        "擋到一部分、還過得去、佔用車道 → 佔用部分車道；"
        "車子過不去、路斷了、完全擋住 → 完全無法通行。"
        "只說不知道 → null。\n"
        "- electrical_hazard 有無火花冒煙或帶電（固定說法）：只能填 沒有、有火花或冒煙、不確定。"
        "明確說沒有火花、沒有冒煙、沒有帶電 → 沒有；"
        "冒火花、冒煙、帶電、漏電、有電 → 有火花或冒煙；"
        "說不確定、沒看到、不清楚 → 不確定。"
        "這輪沒講到火花、煙或電 → null。\n"
        "- disaster_caller_role 報案人身分（固定說法）：只能填 "
        "屋主或住戶、鄰居或附近店家、路過、里長或管理員、其他。"
        "屋主、住戶、我家 → 屋主或住戶；"
        "鄰居、附近店家 → 鄰居或附近店家；"
        "路過、經過 → 路過；"
        "里長、管理員 → 里長或管理員；"
        "講了別的身分 → 其他。"
        "只回答在或不在、沒講身分 → null。"
    )
    return schema, rules
