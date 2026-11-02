"""
emergency_accident_119.py
━━━━━━━━━━━━━━━━━━━━━━━━
緊急救援次案類「車禍救助」的八題，以及大類收尾要問的題。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


SUBCATEGORY = "車禍救助"

INJURY_NONE = "無"
TRAPPED_NONE = "無人受困"
TRAPPED_YES = "有人受困"
ROLE_SELF = "當事人(本人)"
ROLE_PASSERBY = "路過"

VEHICLE_TYPES: Tuple[str, ...] = (
    "機車自撞(自摔)",
    "機車車禍",
    "自小客自撞",
    "自小客車車禍",
    "貨車卡車砂石車車禍",
    "大型巴士(遊覽車．公車)車禍",
    "中型巴士車禍",
    "特殊車輛車禍",
    "消防救護車輛車禍",
)
INJURY_TYPES: Tuple[str, ...] = (
    "頭部外傷流血(含頸部)",
    "四肢明顯外傷",
    "胸腹背明顯外傷",
    "身軀多處部位明顯外傷",
    "頭部疼痛，無明顯外傷",
    "四肢疼痛，無明顯外傷",
    "胸腹腔背疼痛",
    INJURY_NONE,
)
CONSCIOUSNESS_LEVELS: Tuple[str, ...] = (
    "意識清醒",
    "對聲音有反應",
    "對疼痛有反應",
    "昏迷",
)

MODE_ACTIVE = "主動"
MODE_CONDITIONAL = "條件"

COUNT_QUESTION = "有幾個人受傷？幾個人受困？"
RELATION_QUESTION = "你是他的誰？"
PATIENT_QUESTION = "患者是男生還是女生？幾歲？"
CONSCIOUSNESS_QUESTION = "請問人是否還有意識？"
BREATHING_QUESTION = "請你看一下他是否有呼吸？"
INCIDENT_QUESTION = "請問發生什麼事情？"
INCIDENT_REASK_QUESTION = "請問發生甚麼事？"
DISPATCH_LINE = "救援人員已派出了喔。"

ACCIDENT_FIXED_ANSWERS: Dict[str, Tuple[str, ...]] = {
    "accident_vehicle_type": VEHICLE_TYPES,
    "accident_injury": INJURY_TYPES,
    "accident_trapped": (TRAPPED_NONE, TRAPPED_YES),
    "accident_consciousness": CONSCIOUSNESS_LEVELS,
}

ACCIDENT_FIELDS: Tuple[str, ...] = (
    "accident_vehicle_type",
    "accident_injury",
    "accident_trapped",
    "accident_casualty_count",
    "accident_consciousness",
    "accident_burning",
    "accident_caller_role",
    "accident_traffic_impact",
)

TAIL_FIELDS: Tuple[str, ...] = (
    "caller_relation",
    "patient_gender",
    "patient_age",
    "breathing",
)


def normalize_accident_caller_role(raw: str) -> str:
    """本人、當事人收成當事人(本人)；路人、路過收成路過。其餘照原話。"""
    text = "".join((raw or "").split())
    if not text:
        return (raw or "").strip()
    negated = any(token in text for token in ("不是本人", "不是當事人"))
    if not negated and any(token in text for token in ("本人", "當事人")):
        return ROLE_SELF
    if any(token in text for token in ("路人", "路過")):
        return ROLE_PASSERBY
    return (raw or "").strip()


@dataclass(frozen=True)
class AccidentQuestion:
    element: str
    field: str
    mode: str
    stage: str
    question: str
    condition: Optional[Callable[[Any], bool]] = None
    condition_text: str = ""


def _need_casualty_count(case: Any) -> bool:
    """受傷情形不是「無」，或有人受困，才問人數。兩個都還沒出現就不算。"""
    injury = getattr(case, "accident_injury", None)
    trapped = getattr(case, "accident_trapped", None)
    if injury is not None and injury != INJURY_NONE:
        return True
    return trapped == TRAPPED_YES


def _ask_party_consciousness(case: Any) -> bool:
    """身分還沒出現就問；已經講明是本人才跳過。"""
    return getattr(case, "accident_caller_role", None) != ROLE_SELF


ACCIDENT_QUESTIONS: Tuple[AccidentQuestion, ...] = (
    AccidentQuestion(
        "事故車種", "accident_vehicle_type", MODE_ACTIVE,
        "緊急救援-事故車種", "是什麼車跟什麼車車禍？",
    ),
    AccidentQuestion(
        "受傷情形", "accident_injury", MODE_ACTIVE,
        "緊急救援-受傷情形", "有人受傷嗎？傷在哪裡？",
    ),
    AccidentQuestion(
        "有無受困", "accident_trapped", MODE_ACTIVE,
        "緊急救援-有無受困", "有沒有人被困在車裡出不來？",
    ),
    AccidentQuestion(
        "人數", "accident_casualty_count", MODE_CONDITIONAL,
        "緊急救援-人數", COUNT_QUESTION,
        _need_casualty_count, "受傷情形≠無，或有無受困＝有人受困",
    ),
    AccidentQuestion(
        "當事人意識", "accident_consciousness", MODE_CONDITIONAL,
        "緊急救援-當事人意識", "當事人有清醒嗎？",
        _ask_party_consciousness, "報案身分≠當事人(本人)",
    ),
    AccidentQuestion(
        "燃燒情形", "accident_burning", MODE_ACTIVE,
        "緊急救援-燃燒情形", "車子有沒有冒煙或起火？",
    ),
    AccidentQuestion(
        "報案身分", "accident_caller_role", MODE_ACTIVE,
        "緊急救援-報案身分", "請問是當事人還是路人代報？",
    ),
    AccidentQuestion(
        "影響範圍", "accident_traffic_impact", MODE_ACTIVE,
        "緊急救援-影響範圍", "有沒有擋到車道？路還過得去嗎？",
    ),
)


def accident_schema_and_rules() -> tuple[Dict[str, str], str]:
    """車禍救助與大類收尾的抽取。只在主類是緊急救援時送給 LLM。"""
    vehicles = "、".join(VEHICLE_TYPES)
    injuries = "、".join(INJURY_TYPES)
    minds = "、".join(CONSCIOUSNESS_LEVELS)
    schema = {
        "accident_vehicle_type": "|".join(VEHICLE_TYPES) + "|null",
        "accident_injury": "|".join(INJURY_TYPES) + "|null",
        "accident_trapped": f"{TRAPPED_NONE}|{TRAPPED_YES}|null",
        "accident_casualty_count": "string|null",
        "accident_consciousness": "|".join(CONSCIOUSNESS_LEVELS) + "|null",
        "accident_burning": "string|null",
        "accident_caller_role": "string|null",
        "accident_traffic_impact": "string|null",
        "caller_relation": "string|null",
        "patient_gender": "男|女|null",
        "patient_age": "string|null",
        "breathing": "true|false|null",
        "consciousness": "true|false|null",
    }
    rules = (
        "【車禍救助與緊急救援收尾】只依報警人本輪實際回答抽取；未提及 → null，"
        "不得從受理員問題複製答案。"
        "固定說法的欄位只能從列出的說法選一個，依意思判斷，不是看有沒有出現那幾個字。\n"
        f"- accident_vehicle_type 事故車種（固定說法）：只能填 {vehicles}。"
        "機車自己摔倒、自摔 → 機車自撞(自摔)；機車和別的車或人相撞 → 機車車禍；"
        "小客車自己撞到、自撞 → 自小客自撞；小客車和別的車相撞 → 自小客車車禍；"
        "貨車、卡車、砂石車 → 貨車卡車砂石車車禍；"
        "遊覽車、公車、大客車 → 大型巴士(遊覽車．公車)車禍；"
        "中巴 → 中型巴士車禍；救護車、消防車自己出事 → 消防救護車輛車禍；"
        "講了別種車 → 特殊車輛車禍。這輪沒講車種 → null。\n"
        f"- accident_injury 受傷情形（固定說法）：只能填 {injuries}。"
        "頭或脖子外傷、流血 → 頭部外傷流血(含頸部)；"
        "手腳有傷口 → 四肢明顯外傷；胸、腹、背有傷口 → 胸腹背明顯外傷；"
        "身上好幾處都有傷 → 身軀多處部位明顯外傷；"
        "頭或脖子只說痛、沒有傷口 → 頭部疼痛，無明顯外傷；"
        "手腳只說痛、沒有傷口 → 四肢疼痛，無明顯外傷；"
        "胸腹背只說痛、沒有傷口 → 胸腹腔背疼痛；"
        "明確說沒有人受傷 → 無。沒講到傷勢 → null。\n"
        f"- accident_trapped 有無受困（固定說法）：只能填 {TRAPPED_NONE} 或 {TRAPPED_YES}。"
        "人被困在車裡、出不來、卡在車內 → 有人受困；"
        "人都出來了、沒有被困 → 無人受困。沒講到有沒有被困 → null。\n"
        "- accident_casualty_count 人數：講到幾個人受傷或受困時，照報案人的話記"
        "（例如兩個受傷、一個人受困），不要換成數字代碼；沒講人數 → null。\n"
        f"- accident_consciousness 當事人意識（固定說法）：只能填 {minds}。"
        "清醒、有意識 → 意識清醒；會應聲 → 對聲音有反應；"
        "捏會動、對痛有反應 → 對疼痛有反應；叫不醒、昏迷 → 昏迷。"
        "這輪沒講意識 → null。\n"
        "- accident_burning 燃燒情形：照原話記有沒有冒煙、黑煙或白煙、火勢、有沒有延燒。"
        "沒講到煙或火 → null。\n"
        "- accident_caller_role 報案身分：照報案人的話記。"
        "本人、當事人、我就是傷者 → 當事人(本人)；路人、路過、路人代報 → 路過；"
        "講了別的關係就照原話。只回答在或不在、沒講身分 → null。\n"
        "- accident_traffic_impact 影響範圍：照原話記有沒有擋到車道、過不過得去、"
        "有沒有封閉。沒講到交通 → null。\n"
        "- caller_relation：你是他的誰。家人、朋友、不認識都照原話。"
        "「我是先生／小姐」是稱呼，不是關係，填 null。沒講關係 → null。\n"
        "- patient_gender：患者是男或女，只能填 男 或 女。"
        "這是患者，不是報案人；「我是先生／小姐」只是稱呼，填 null。"
        "他是男生、男性患者 → 男；女生、女性患者 → 女。沒講患者性別 → null。\n"
        "- patient_age：患者幾歲，照報案人的話記（例如 75歲）。"
        "沒講患者年齡 → null。\n"
        "- breathing：明確說有呼吸 → true；沒有呼吸、沒在喘 → false；沒講 → null。\n"
        "- consciousness：人是否還有意識。明確說有意識、清醒、還會動 → true；"
        "沒有意識、叫不醒、昏迷 → false；這輪沒講到意識 → null。"
    )
    return schema, rules
