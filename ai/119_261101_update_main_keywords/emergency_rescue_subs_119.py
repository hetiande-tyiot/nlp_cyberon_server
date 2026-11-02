"""
emergency_rescue_subs_119.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
緊急救援次案類：溺水、跳水、跳樓。
問法沿用車禍救助。被動題不問。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


DROWN = "溺水"
DIVE = "跳水"
FALL = "跳樓"

SIGHT_IN_WATER = "還在水裡"
SIGHT_GONE = "看不到人"
SIGHT_RESCUED = "已經救起"
SIGHTS: Tuple[str, ...] = (SIGHT_IN_WATER, SIGHT_GONE, SIGHT_RESCUED)

CONSCIOUSNESS: Tuple[str, ...] = (
    "意識清醒",
    "對聲音有反應",
    "對疼痛有反應",
    "昏迷",
)
GENDERS: Tuple[str, ...] = ("男性", "女性")

DROWN_CAUSES: Tuple[str, ...] = ("戲水", "釣魚", "失足", "其他")
FLOATATION: Tuple[str, ...] = ("有", "沒有")
DROWN_ROLES: Tuple[str, ...] = ("路人", "家屬", "海巡")
DIVE_ROLES: Tuple[str, ...] = ("路人", "家屬", "朋友")

DIVE_JUMPED = "已經跳下"
DIVE_NOT_YET = "還沒跳（還在橋上、欄杆外）"
DIVE_STATUSES: Tuple[str, ...] = (DIVE_JUMPED, DIVE_NOT_YET)

FALL_HIGH = "還在高處（頂樓、窗外、陽台等）"
FALL_DOWN = "已經掉下來"
FALL_STATUSES: Tuple[str, ...] = (FALL_HIGH, FALL_DOWN)
FALL_ROLES: Tuple[str, ...] = ("當事人(本人)", "家人", "鄰居或住戶", "路人")

MODE_ACTIVE = "主動"
MODE_CONDITIONAL = "條件"
MODE_PASSIVE = "被動"

DROWN_COUNT_QUESTION = "有幾個人落水？"
DIVE_COUNT_QUESTION = "有幾個人？"

COUNT_FIELD_QUESTIONS: Dict[str, str] = {
    "drown_count": DROWN_COUNT_QUESTION,
    "dive_count": DIVE_COUNT_QUESTION,
}


def normalize_mountain_cause(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "扭到", "跌倒", "受傷", "摔傷"):
        return "受傷"
    if "迷路" in text:
        return "迷路"
    if "不舒服" in text:
        return "身體不舒服"
    if _has_token(text, "失聯", "沒下山", "没下山"):
        return "失聯沒下山"
    return (raw or "").strip()


def normalize_mountain_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "同行", "家屬", "朋友", "代報", "代為"):
        return "代為報案"
    if "本人" in text and "不是本人" not in text:
        return "本人"
    return (raw or "").strip()


def normalize_trap_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if not _has_token(text, "不是本人", "不是當事人") and _has_token(text, "本人", "當事人"):
        return "當事人(本人)"
    if "同事" in text:
        return "同事"
    if _has_token(text, "家人", "家屬"):
        return "家人"
    if _has_token(text, "路人", "路過"):
        return "路人"
    return (raw or "").strip()


def normalize_gas_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if "管理員" in text:
        return "管理員"
    if _has_token(text, "住戶", "住家"):
        return "住戶"
    if "鄰居" in text:
        return "鄰居"
    if _has_token(text, "路人", "路過"):
        return "路人"
    return (raw or "").strip()


def normalize_gas_building(raw: str) -> str:
    text = "".join((raw or "").split())
    if text in GAS_BUILDINGS:
        return text
    aliases = (
        ("高層", "高層建築物(10層樓以上)"),
        ("十層", "高層建築物(10層樓以上)"),
        ("地下街", "地下建築物(如地下街)"),
        ("地下室", "地下建築物(如地下街)"),
        ("古蹟", "古蹟、文化財"),
        ("古迹", "古蹟、文化財"),
        ("文化財", "古蹟、文化財"),
        ("傳統市場", "大型違章建築區與傳統市場(含工廠)"),
        ("石化", "石化廠建築物"),
        ("毒災", "毒災場所"),
        ("老人院", "學校、醫院、老人院建築物"),
        ("醫院", "學校、醫院、老人院建築物"),
        ("医院", "學校、醫院、老人院建築物"),
        ("學校", "學校、醫院、老人院建築物"),
        ("学校", "學校、醫院、老人院建築物"),
        ("電影", "電影院用途建築物"),
        ("电影院", "電影院用途建築物"),
        ("車站", "運輸中樞用途建築物"),
        ("机场", "運輸中樞用途建築物"),
        ("機場", "運輸中樞用途建築物"),
        ("百貨", "旅館、百貨商場用途建築物"),
        ("商場", "旅館、百貨商場用途建築物"),
        ("旅館", "旅館、百貨商場用途建築物"),
        ("旅馆", "旅館、百貨商場用途建築物"),
        ("倉庫", "倉庫"),
        ("仓库", "倉庫"),
        ("公寓", "集合住宅"),
        ("集合住宅", "集合住宅"),
        ("透天", "透天厝"),
    )
    for token, label in aliases:
        if token in text:
            return label
    return (raw or "").strip()


def normalize_lift_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "管理員", "警衛", "保全"):
        return "管理員或警衛"
    if _has_token(text, "家人", "家屬", "同事"):
        return "其他"
    if "本人" in text and "不是本人" not in text:
        return "受困者本人"
    return (raw or "").strip()


def normalize_door_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "家人"):
        return "家人"
    if _has_token(text, "房客"):
        return "房客"
    if _has_token(text, "朋友"):
        return "朋友"
    if _has_token(text, "同事"):
        return "同事"
    if not _has_token(text, "不是本人", "不是當事人") and _has_token(text, "本人", "當事人"):
        return "本人"
    return (raw or "").strip()


def normalize_door_reason(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "自殺", "想不開"):
        return "說要自殺"
    if _has_token(text, "病史", "疾病"):
        return "有病史"
    if _has_token(text, "跌倒", "起不來", "起不来"):
        return "跌倒起不來"
    if _has_token(text, "獨居", "聯絡不上", "連絡不上", "失聯"):
        return "獨居聯絡不上"
    return (raw or "").strip()


def normalize_scene_gender(raw: str) -> str:
    text = "".join((raw or "").split())
    if "女" in text and "男" not in text:
        return "女性"
    if "男" in text:
        return "男性"
    return (raw or "").strip()


def normalize_infant_age(raw: str) -> str:
    """未滿一歲：一個月記成 .01。其餘照原話。"""
    text = "".join((raw or "").split())
    if not text:
        return (raw or "").strip()
    if re.fullmatch(r"\.\d{2}", text):
        return text
    words = (
        ("十二", 12), ("十一", 11), ("十", 10),
        ("九", 9), ("八", 8), ("七", 7), ("六", 6), ("五", 5),
        ("四", 4), ("三", 3), ("兩", 2), ("二", 2), ("一", 1),
    )
    for word, month in words:
        if text in {f"{word}個月", f"{word}月", f"{month}個月", f"{month}月"}:
            return f".{month:02d}"
    return (raw or "").strip()


def _has_token(text: str, *tokens: str) -> bool:
    return any(token in text for token in tokens)


def normalize_drown_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "海巡"):
        return "海巡"
    if _has_token(text, "家屬"):
        return "家屬"
    if _has_token(text, "路人", "路過"):
        return "路人"
    return (raw or "").strip()


def normalize_dive_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "家屬"):
        return "家屬"
    if _has_token(text, "朋友"):
        return "朋友"
    if _has_token(text, "路人", "路過"):
        return "路人"
    return (raw or "").strip()


def normalize_fall_role(raw: str) -> str:
    text = "".join((raw or "").split())
    if _has_token(text, "不是本人", "不是當事人"):
        text = text
    elif _has_token(text, "本人", "當事人"):
        return "當事人(本人)"
    if _has_token(text, "鄰居", "住戶"):
        return "鄰居或住戶"
    if _has_token(text, "家人", "家屬"):
        return "家人"
    if _has_token(text, "路人", "路過"):
        return "路人"
    return (raw or "").strip()


@dataclass(frozen=True)
class RescueSubQuestion:
    element: str
    field: str
    mode: str
    stage: str
    question: str
    condition: Optional[Callable[[Any], bool]] = None
    condition_text: str = ""


def _already_jumped(case: Any) -> bool:
    return getattr(case, "dive_status", None) == DIVE_JUMPED


def _visible_in_water(case: Any) -> bool:
    """在水面、看得到（載浮載沉）才問人數和意識。"""
    return getattr(case, "dive_sight", None) == SIGHT_IN_WATER


def _still_high(case: Any) -> bool:
    return getattr(case, "high_fall_status", None) == FALL_HIGH


def _mountain_injured(case: Any) -> bool:
    return getattr(case, "mountain_cause", None) == "受傷"


def _trap_not_self(case: Any) -> bool:
    """身分還沒記到就問；已經是本人才跳過。"""
    return getattr(case, "trap_caller_role", None) != "當事人(本人)"


def _door_not_self(case: Any) -> bool:
    """身分還沒記到就問；已經是本人才跳過。"""
    return getattr(case, "door_caller_role", None) != "本人"


MOUNTAIN = "山難"
TRAPPED_CASE = "其他"
TRAPPED_CASE_ALIAS = "其他(卡住夾住)"
GAS = "瓦斯漏氣(建築物)"

MOUNTAIN_INJURIES: Tuple[str, ...] = (
    "頭部外傷流血(含頸部)",
    "四肢明顯外傷",
    "胸腹背明顯外傷",
    "身軀多處部位明顯外傷",
    "頭部疼痛，無明顯外傷",
    "四肢疼痛，無明顯外傷",
    "胸腹腔背疼痛，無明顯外傷",
)
TRAP_FREED: Tuple[str, ...] = ("還卡著", "已經出來了")
YES_NO: Tuple[str, ...] = ("有", "沒有")
TRAP_ROLES: Tuple[str, ...] = ("當事人(本人)", "家人", "同事", "路人")
GAS_BUILDINGS: Tuple[str, ...] = (
    "透天厝",
    "集合住宅",
    "倉庫",
    "旅館、百貨商場用途建築物",
    "運輸中樞用途建築物",
    "電影院用途建築物",
    "學校、醫院、老人院建築物",
    "毒災場所",
    "石化廠建築物",
    "大型違章建築區與傳統市場(含工廠)",
    "古蹟、文化財",
    "地下建築物(如地下街)",
    "高層建築物(10層樓以上)",
    "其他",
)
GAS_STRENGTH: Tuple[str, ...] = ("很濃", "淡淡的", "一陣一陣")
GAS_TYPES: Tuple[str, ...] = ("天然氣", "瓦斯桶")
GAS_ROLES: Tuple[str, ...] = ("住戶", "鄰居", "管理員", "路人")

LIFT = "電梯受困"
DOOR = "破門"
LIFT_ROLES: Tuple[str, ...] = ("受困者本人", "管理員或警衛", "其他")
LIFT_COMPANY: Tuple[str, ...] = ("已經聯絡", "還沒聯絡")
LIFT_DISCOMFORT: Tuple[str, ...] = ("有", "沒有", "不知道")
DOOR_RESPONSES: Tuple[str, ...] = ("有回應", "沒有回應", "有聲音但叫不應")
DOOR_KINDS: Tuple[str, ...] = ("大門", "房門", "浴室門", "鐵門")
DOOR_KEYS: Tuple[str, ...] = ("有鑰匙但打不開", "沒有鑰匙", "已找鎖匠")
DOOR_CONSENT: Tuple[str, ...] = ("同意", "不同意", "家屬或屋主還沒到")
DOOR_REASONS: Tuple[str, ...] = ("獨居聯絡不上", "說要自殺", "有病史", "跌倒起不來")

LIFT_COUNT_QUESTION = "裡面有幾個人？"

MOUNTAIN_COUNT_QUESTION = "你們總共幾個人？"
COUNT_FIELD_QUESTIONS["mountain_count"] = MOUNTAIN_COUNT_QUESTION
COUNT_FIELD_QUESTIONS["lift_count"] = LIFT_COUNT_QUESTION


DROWN_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "報案身分", "drown_caller_role", MODE_ACTIVE,
        "緊急救援-溺水-報案身分", "請問是家屬朋友還是路人代報呢？",
    ),
    RescueSubQuestion(
        "溺水原因", "drown_cause", MODE_ACTIVE,
        "緊急救援-溺水-溺水原因", "是怎麼掉下去的？",
    ),
    RescueSubQuestion(
        "人數", "drown_count", MODE_ACTIVE,
        "緊急救援-溺水-人數", DROWN_COUNT_QUESTION,
    ),
    RescueSubQuestion(
        "目擊狀況", "drown_sight", MODE_ACTIVE,
        "緊急救援-溺水-目擊狀況", "還有看到人嗎？",
    ),
    RescueSubQuestion(
        "離岸距離", "drown_distance", MODE_ACTIVE,
        "緊急救援-溺水-離岸距離", "離岸邊大概多遠？",
    ),
    RescueSubQuestion(
        "救生裝備", "drown_flotation", MODE_ACTIVE,
        "緊急救援-溺水-救生裝備", "對方有穿救生衣或泳圈嗎？",
    ),
    RescueSubQuestion(
        "意識", "drown_consciousness", MODE_ACTIVE,
        "緊急救援-溺水-意識", "對方還會動嗎？",
    ),
    RescueSubQuestion(
        "性別", "drown_gender", MODE_ACTIVE,
        "緊急救援-溺水-性別", "是男生還是女生？",
    ),
    RescueSubQuestion(
        "年齡", "drown_age", MODE_ACTIVE,
        "緊急救援-溺水-年齡", "大概幾歲？",
    ),
    RescueSubQuestion(
        "衣著特徵", "drown_clothing", MODE_ACTIVE,
        "緊急救援-溺水-衣著特徵", "他穿什麼顏色的衣服？",
    ),
    RescueSubQuestion(
        "團體帶隊", "drown_group", MODE_PASSIVE,
        "緊急救援-溺水-團體帶隊", "是跟團體一起來的嗎？有帶隊的人嗎？",
    ),
)

DIVE_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "跳水狀況", "dive_status", MODE_ACTIVE,
        "緊急救援-跳水-跳水狀況", "對方已經跳下去了嗎？",
    ),
    RescueSubQuestion(
        "目擊狀況", "dive_sight", MODE_CONDITIONAL,
        "緊急救援-跳水-目擊狀況", "還有看到人嗎？",
        _already_jumped, "跳水狀況＝已經跳下",
    ),
    RescueSubQuestion(
        "報案身分", "dive_caller_role", MODE_ACTIVE,
        "緊急救援-跳水-報案身分", "請問是家屬朋友還是路人代報呢？",
    ),
    RescueSubQuestion(
        "性別", "dive_gender", MODE_ACTIVE,
        "緊急救援-跳水-性別", "是男生還是女生？",
    ),
    RescueSubQuestion(
        "年齡", "dive_age", MODE_ACTIVE,
        "緊急救援-跳水-年齡", "大概幾歲？",
    ),
    RescueSubQuestion(
        "衣著特徵", "dive_clothing", MODE_ACTIVE,
        "緊急救援-跳水-衣著特徵", "他穿什麼顏色的衣服？",
    ),
    RescueSubQuestion(
        "人數", "dive_count", MODE_CONDITIONAL,
        "緊急救援-跳水-人數", DIVE_COUNT_QUESTION,
        _visible_in_water, "目擊狀況＝還在水裡",
    ),
    RescueSubQuestion(
        "意識", "dive_consciousness", MODE_CONDITIONAL,
        "緊急救援-跳水-意識", "人還會動嗎？",
        _visible_in_water, "目擊狀況＝還在水裡",
    ),
)

FALL_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "報案身分", "fall_caller_role", MODE_ACTIVE,
        "緊急救援-跳樓-報案身分", "請問是家屬朋友還是路人代報呢？",
    ),
    RescueSubQuestion(
        "是否墜落", "high_fall_status", MODE_ACTIVE,
        "緊急救援-跳樓-是否墜落", "人還在上面嗎？還是跳下來了？",
    ),
    RescueSubQuestion(
        "輕生意圖", "fall_intent", MODE_CONDITIONAL,
        "緊急救援-跳樓-輕生意圖", "他是要自殺嗎？",
        _still_high, "是否墜落＝還在高處",
    ),
    RescueSubQuestion(
        "所在樓層", "fall_floor", MODE_ACTIVE,
        "緊急救援-跳樓-所在樓層", "現在在幾樓？",
    ),
    RescueSubQuestion(
        "性別", "fall_gender", MODE_ACTIVE,
        "緊急救援-跳樓-性別", "是男生還是女生？",
    ),
    RescueSubQuestion(
        "年齡", "fall_age", MODE_ACTIVE,
        "緊急救援-跳樓-年齡", "大概幾歲？",
    ),
)

MOUNTAIN_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "山難原因", "mountain_cause", MODE_ACTIVE,
        "緊急救援-山難-山難原因", "請問發生什麼事？是迷路還是受傷？",
    ),
    RescueSubQuestion(
        "受傷情形", "mountain_injury", MODE_CONDITIONAL,
        "緊急救援-山難-受傷情形", "哪裡受傷？",
        _mountain_injured, "山難原因＝受傷",
    ),
    RescueSubQuestion(
        "人數", "mountain_count", MODE_ACTIVE,
        "緊急救援-山難-人數", MOUNTAIN_COUNT_QUESTION,
    ),
    RescueSubQuestion(
        "位置座標", "mountain_location", MODE_ACTIVE,
        "緊急救援-山難-位置座標", "您現在在哪裡？手機可以看到座標嗎？",
    ),
    RescueSubQuestion(
        "報案身分", "mountain_caller_role", MODE_ACTIVE,
        "緊急救援-山難-報案身分", "請問是本人還是家屬朋友代報？",
    ),
    RescueSubQuestion(
        "性別", "mountain_gender", MODE_ACTIVE,
        "緊急救援-山難-性別", "是男生還是女生？",
    ),
    RescueSubQuestion(
        "年齡", "mountain_age", MODE_ACTIVE,
        "緊急救援-山難-年齡", "大概幾歲？",
    ),
    RescueSubQuestion(
        "意識", "mountain_consciousness", MODE_ACTIVE,
        "緊急救援-山難-意識", "現在人是清醒的嗎？",
    ),
    RescueSubQuestion(
        "入山資訊", "mountain_entry", MODE_ACTIVE,
        "緊急救援-山難-入山資訊", "幾點上山的？從哪裡上去的？",
    ),
    RescueSubQuestion(
        "登山路線", "mountain_route", MODE_ACTIVE,
        "緊急救援-山難-登山路線", "你們走哪一條路線？最後經過什麼地標？",
    ),
    RescueSubQuestion(
        "隨身物資", "mountain_supplies", MODE_ACTIVE,
        "緊急救援-山難-隨身物資", "身上的水、食物、保暖衣物夠嗎？有手電筒或哨子嗎？",
    ),
    RescueSubQuestion(
        "帶隊人員", "mountain_leader", MODE_PASSIVE,
        "緊急救援-山難-帶隊人員", "是自己來，還是跟團體一起？",
    ),
)

TRAP_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "卡住部位", "trap_body_part", MODE_ACTIVE,
        "緊急救援-卡住-卡住部位", "哪裡卡住了？",
    ),
    RescueSubQuestion(
        "卡住物品", "trap_object", MODE_ACTIVE,
        "緊急救援-卡住-卡住物品", "卡在什麼東西裡面？",
    ),
    RescueSubQuestion(
        "是否脫困", "trap_freed", MODE_ACTIVE,
        "緊急救援-卡住-是否脫困", "現在還卡著嗎？",
    ),
    RescueSubQuestion(
        "受傷情形", "trap_injury", MODE_ACTIVE,
        "緊急救援-卡住-受傷情形", "有流血或受傷嗎？",
    ),
    RescueSubQuestion(
        "場所", "trap_place", MODE_ACTIVE,
        "緊急救援-卡住-場所", "是在家裡還是工作的地方？",
    ),
    RescueSubQuestion(
        "性別", "trap_gender", MODE_ACTIVE,
        "緊急救援-卡住-性別", "是男生還是女生？",
    ),
    RescueSubQuestion(
        "年齡", "trap_age", MODE_ACTIVE,
        "緊急救援-卡住-年齡", "大概幾歲？",
    ),
    RescueSubQuestion(
        "報案身分", "trap_caller_role", MODE_ACTIVE,
        "緊急救援-卡住-報案身分", "請問是當事人還是家屬朋友代報？",
    ),
    RescueSubQuestion(
        "意識", "trap_consciousness", MODE_CONDITIONAL,
        "緊急救援-卡住-意識", "人是清醒的嗎？",
        _trap_not_self, "報案身分≠當事人(本人)",
    ),
)

GAS_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "建物用途", "gas_building_use", MODE_ACTIVE,
        "緊急救援-瓦斯-建物用途", "那裡是住家還是店家呢？",
    ),
    RescueSubQuestion(
        "報案身分", "gas_caller_role", MODE_ACTIVE,
        "緊急救援-瓦斯-報案身分", "請問您是住在附近，還是路人？",
    ),
    RescueSubQuestion(
        "有無火煙", "gas_flame", MODE_ACTIVE,
        "緊急救援-瓦斯-有無火煙", "有看到明顯的火或煙嗎？",
    ),
    RescueSubQuestion(
        "聞到位置", "gas_smell_place", MODE_ACTIVE,
        "緊急救援-瓦斯-聞到位置", "是在家裡面聞到，還是外面？",
    ),
    RescueSubQuestion(
        "味道濃淡", "gas_smell_strength", MODE_ACTIVE,
        "緊急救援-瓦斯-味道濃淡", "味道很濃嗎？",
    ),
    RescueSubQuestion(
        "瓦斯種類", "gas_type", MODE_ACTIVE,
        "緊急救援-瓦斯-瓦斯種類", "是用天然氣，還是瓦斯桶？",
    ),
    RescueSubQuestion(
        "鄰接建物", "gas_adjacent", MODE_PASSIVE,
        "緊急救援-瓦斯-鄰接建物", "旁邊有房子或車子嗎？",
    ),
    RescueSubQuestion(
        "身體不適", "gas_discomfort", MODE_PASSIVE,
        "緊急救援-瓦斯-身體不適", "有人身體不舒服嗎？",
    ),
)

LIFT_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "報案身分", "lift_caller_role", MODE_ACTIVE,
        "緊急救援-電梯-報案身分", "請問是本人嗎？還是管理員或警衛？",
    ),
    RescueSubQuestion(
        "社區棟別", "lift_building", MODE_ACTIVE,
        "緊急救援-電梯-社區棟別", "是哪個社區？哪一棟、哪一部電梯？",
    ),
    RescueSubQuestion(
        "受困樓層", "lift_floor", MODE_ACTIVE,
        "緊急救援-電梯-受困樓層", "電梯現在停在幾樓？",
    ),
    RescueSubQuestion(
        "受困人數", "lift_count", MODE_ACTIVE,
        "緊急救援-電梯-受困人數", LIFT_COUNT_QUESTION,
    ),
    RescueSubQuestion(
        "電梯公司", "lift_company", MODE_ACTIVE,
        "緊急救援-電梯-電梯公司", "有聯絡電梯公司了嗎？",
    ),
    RescueSubQuestion(
        "意識", "lift_consciousness", MODE_ACTIVE,
        "緊急救援-電梯-意識", "裡面的人都清醒嗎？",
    ),
    RescueSubQuestion(
        "身體不適", "lift_discomfort", MODE_PASSIVE,
        "緊急救援-電梯-身體不適", "裡面的人有沒有受傷或不舒服？",
    ),
)

DOOR_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    RescueSubQuestion(
        "報案身分", "door_caller_role", MODE_ACTIVE,
        "緊急救援-破門-報案身分", "請問是當事人還是家屬朋友代報？",
    ),
    RescueSubQuestion(
        "擔心原因", "door_reason", MODE_ACTIVE,
        "緊急救援-破門-擔心原因", "發生什麼事需要破門？",
    ),
    RescueSubQuestion(
        "有無回應", "knock_response", MODE_CONDITIONAL,
        "緊急救援-破門-有無回應", "敲門或打電話，會有回應嗎？",
        _door_not_self, "報案身分≠本人",
    ),
    RescueSubQuestion(
        "門的種類", "door_kind", MODE_ACTIVE,
        "緊急救援-破門-門的種類", "是大門還是房間的門？",
    ),
    RescueSubQuestion(
        "鑰匙鎖匠", "door_locksmith", MODE_ACTIVE,
        "緊急救援-破門-鑰匙鎖匠", "有沒有鑰匙？找過鎖匠嗎？",
    ),
    RescueSubQuestion(
        "同意破門", "door_consent", MODE_ACTIVE,
        "緊急救援-破門-同意破門", "我們破門會把門弄壞，家屬或屋主同意嗎？",
    ),
    RescueSubQuestion(
        "性別", "door_gender", MODE_CONDITIONAL,
        "緊急救援-破門-性別", "是男生還是女生？",
        _door_not_self, "報案身分≠本人",
    ),
    RescueSubQuestion(
        "年齡", "door_age", MODE_CONDITIONAL,
        "緊急救援-破門-年齡", "當事人大概幾歲？",
        _door_not_self, "報案身分≠本人",
    ),
)

SUB_QUESTIONS: Dict[str, Tuple[RescueSubQuestion, ...]] = {
    DROWN: DROWN_QUESTIONS,
    DIVE: DIVE_QUESTIONS,
    FALL: FALL_QUESTIONS,
    MOUNTAIN: MOUNTAIN_QUESTIONS,
    TRAPPED_CASE: TRAP_QUESTIONS,
    TRAPPED_CASE_ALIAS: TRAP_QUESTIONS,
    GAS: GAS_QUESTIONS,
    LIFT: LIFT_QUESTIONS,
    DOOR: DOOR_QUESTIONS,
}

# 自己問過性別、年齡的次案類，收尾不再問一次。瓦斯漏氣沒有這兩題。
GENDER_AGE_SUBS = frozenset({
    DROWN, DIVE, FALL, MOUNTAIN, TRAPPED_CASE, TRAPPED_CASE_ALIAS, DOOR,
})
# 自己問過意識的次案類，收尾不再問。跳樓、瓦斯漏氣、破門沒有單獨的意識題。
OWN_CONSCIOUSNESS_SUBS = frozenset({
    "車禍救助", DROWN, DIVE, MOUNTAIN, TRAPPED_CASE, TRAPPED_CASE_ALIAS, LIFT,
})


def asked_questions(questions: Tuple[RescueSubQuestion, ...]) -> Tuple[RescueSubQuestion, ...]:
    return tuple(item for item in questions if item.mode != MODE_PASSIVE)


# 換次案類時留著。講的是這個人，跟哪一個次案類無關。
EMERGENCY_KEEP_SLOTS: Tuple[str, ...] = (
    "incident_description",
    "caller_relation",
    "patient_gender",
    "patient_age",
    "breathing",
    "consciousness",
)


def emergency_slots_for(sub_category: Optional[str]) -> Tuple[str, ...]:
    """這個次案類會用到的欄位，含被動題，再加上換類時要留住的共用欄。"""
    from emergency_accident_119 import ACCIDENT_QUESTIONS, SUBCATEGORY

    if sub_category == SUBCATEGORY:
        fields = tuple(item.field for item in ACCIDENT_QUESTIONS)
    else:
        fields = tuple(
            item.field for item in SUB_QUESTIONS.get(sub_category or "", ())
        )
    return tuple(dict.fromkeys((*fields, *EMERGENCY_KEEP_SLOTS)))


ASKED_SUB_QUESTIONS: Tuple[RescueSubQuestion, ...] = (
    asked_questions(DROWN_QUESTIONS)
    + asked_questions(DIVE_QUESTIONS)
    + asked_questions(FALL_QUESTIONS)
    + asked_questions(MOUNTAIN_QUESTIONS)
    + asked_questions(TRAP_QUESTIONS)
    + asked_questions(GAS_QUESTIONS)
    + asked_questions(LIFT_QUESTIONS)
    + asked_questions(DOOR_QUESTIONS)
)

_UNIQUE_QUESTION_LISTS = (
    DROWN_QUESTIONS, DIVE_QUESTIONS, FALL_QUESTIONS,
    MOUNTAIN_QUESTIONS, TRAP_QUESTIONS, GAS_QUESTIONS,
    LIFT_QUESTIONS, DOOR_QUESTIONS,
)
SUB_FIELDS: Tuple[str, ...] = tuple(dict.fromkeys(
    item.field for questions in _UNIQUE_QUESTION_LISTS for item in questions
))

SUB_FIXED_ANSWERS: Dict[str, Tuple[str, ...]] = {
    "drown_cause": DROWN_CAUSES,
    "drown_sight": SIGHTS,
    "drown_flotation": FLOATATION,
    "drown_consciousness": CONSCIOUSNESS,
    "drown_gender": GENDERS,
    "dive_status": DIVE_STATUSES,
    "dive_sight": SIGHTS,
    "dive_consciousness": CONSCIOUSNESS,
    "dive_gender": GENDERS,
    "fall_caller_role": FALL_ROLES,
    "high_fall_status": FALL_STATUSES,
    "fall_gender": GENDERS,
    "mountain_injury": MOUNTAIN_INJURIES,
    "mountain_consciousness": CONSCIOUSNESS,
    "mountain_gender": GENDERS,
    "trap_freed": TRAP_FREED,
    "trap_injury": YES_NO,
    "trap_gender": GENDERS,
    "trap_caller_role": TRAP_ROLES,
    "trap_consciousness": CONSCIOUSNESS,
    "gas_building_use": GAS_BUILDINGS,
    "gas_flame": YES_NO,
    "gas_smell_strength": GAS_STRENGTH,
    "gas_type": GAS_TYPES,
    "gas_discomfort": YES_NO,
    "lift_caller_role": LIFT_ROLES,
    "lift_company": LIFT_COMPANY,
    "lift_consciousness": CONSCIOUSNESS,
    "lift_discomfort": LIFT_DISCOMFORT,
    "knock_response": DOOR_RESPONSES,
    "door_kind": DOOR_KINDS,
    "door_locksmith": DOOR_KEYS,
    "door_consent": DOOR_CONSENT,
    "door_gender": GENDERS,
}

ROLE_NORMALIZERS = {
    "drown_caller_role": normalize_drown_role,
    "dive_caller_role": normalize_dive_role,
    "fall_caller_role": normalize_fall_role,
    "mountain_caller_role": normalize_mountain_role,
    "trap_caller_role": normalize_trap_role,
    "gas_caller_role": normalize_gas_role,
    "lift_caller_role": normalize_lift_role,
    "door_caller_role": normalize_door_role,
}
AGE_FIELDS = frozenset({"drown_age", "dive_age", "fall_age", "mountain_age"})
GENDER_FIELDS = frozenset({
    "drown_gender", "dive_gender", "fall_gender",     "mountain_gender", "trap_gender", "door_gender",
})


def normalize_sub_field(key: str, raw: str) -> str:
    text = str(raw)
    if key in ROLE_NORMALIZERS:
        text = ROLE_NORMALIZERS[key](text)
    if key == "mountain_cause":
        text = normalize_mountain_cause(text)
    if key == "gas_building_use":
        text = normalize_gas_building(text)
    if key == "door_reason":
        text = normalize_door_reason(text)
    if key == "lift_discomfort":
        compact = "".join(text.split())
        if _has_token(compact, "不知道", "不確定", "不清楚"):
            text = "不知道"
        elif _has_token(compact, "沒有", "没有", "沒受傷", "沒不舒服"):
            text = "沒有"
        elif _has_token(compact, "有", "受傷", "不舒服"):
            text = "有"
    if key in AGE_FIELDS:
        text = normalize_infant_age(text)
    if key in GENDER_FIELDS:
        text = normalize_scene_gender(text)
    return text


def subs_schema_and_rules() -> tuple[Dict[str, str], str]:
    """三套次案類欄位。只在主類是緊急救援時送給 LLM。"""
    schema = {
        "drown_caller_role": "string|null",
        "drown_cause": "|".join(DROWN_CAUSES) + "|null",
        "drown_count": "string|null",
        "drown_sight": "|".join(SIGHTS) + "|null",
        "drown_distance": "string|null",
        "drown_flotation": "有|沒有|null",
        "drown_consciousness": "|".join(CONSCIOUSNESS) + "|null",
        "drown_gender": "男性|女性|null",
        "drown_age": "string|null",
        "drown_clothing": "string|null",
        "drown_group": "string|null",
        "dive_status": "|".join(DIVE_STATUSES) + "|null",
        "dive_sight": "|".join(SIGHTS) + "|null",
        "dive_caller_role": "string|null",
        "dive_gender": "男性|女性|null",
        "dive_age": "string|null",
        "dive_clothing": "string|null",
        "dive_count": "string|null",
        "dive_consciousness": "|".join(CONSCIOUSNESS) + "|null",
        "fall_caller_role": "|".join(FALL_ROLES) + "|null",
        "high_fall_status": "|".join(FALL_STATUSES) + "|null",
        "fall_intent": "string|null",
        "fall_floor": "string|null",
        "fall_gender": "男性|女性|null",
        "fall_age": "string|null",
        "mountain_cause": "string|null",
        "mountain_injury": "|".join(MOUNTAIN_INJURIES) + "|null",
        "mountain_count": "string|null",
        "mountain_location": "string|null",
        "mountain_caller_role": "string|null",
        "mountain_gender": "男性|女性|null",
        "mountain_age": "string|null",
        "mountain_consciousness": "|".join(CONSCIOUSNESS) + "|null",
        "mountain_entry": "string|null",
        "mountain_route": "string|null",
        "mountain_supplies": "string|null",
        "mountain_leader": "string|null",
        "trap_body_part": "string|null",
        "trap_object": "string|null",
        "trap_freed": "還卡著|已經出來了|null",
        "trap_injury": "有|沒有|null",
        "trap_place": "string|null",
        "trap_gender": "男性|女性|null",
        "trap_age": "string|null",
        "trap_caller_role": "|".join(TRAP_ROLES) + "|null",
        "trap_consciousness": "|".join(CONSCIOUSNESS) + "|null",
        "gas_building_use": "|".join(GAS_BUILDINGS) + "|null",
        "gas_caller_role": "string|null",
        "gas_flame": "有|沒有|null",
        "gas_smell_place": "string|null",
        "gas_smell_strength": "很濃|淡淡的|一陣一陣|null",
        "gas_type": "天然氣|瓦斯桶|null",
        "gas_adjacent": "string|null",
        "gas_discomfort": "有|沒有|null",
        "lift_caller_role": "受困者本人|管理員或警衛|其他|null",
        "lift_building": "string|null",
        "lift_floor": "string|null",
        "lift_count": "string|null",
        "lift_company": "已經聯絡|還沒聯絡|null",
        "lift_consciousness": "|".join(CONSCIOUSNESS) + "|null",
        "lift_discomfort": "有|沒有|不知道|null",
        "door_caller_role": "string|null",
        "door_reason": "string|null",
        "knock_response": "有回應|沒有回應|有聲音但叫不應|null",
        "door_kind": "大門|房門|浴室門|鐵門|null",
        "door_locksmith": "有鑰匙但打不開|沒有鑰匙|已找鎖匠|null",
        "door_consent": "同意|不同意|家屬或屋主還沒到|null",
        "door_gender": "男性|女性|null",
        "door_age": "string|null",
    }
    rules = (
        "【溺水、跳水、跳樓】只依報警人本輪實際回答抽取；未提及 → null，"
        "不得從受理員問題複製答案。固定說法只能從列出的字選一個。\n"
        "- drown_caller_role：路人、路過 → 路人；家屬 → 家屬；海巡 → 海巡；"
        "其他身分照原話。沒講身分 → null。\n"
        "- drown_cause 只能填 戲水、釣魚、失足、其他。"
        "玩水、游泳 → 戲水；釣魚 → 釣魚；不小心掉下去、失足 → 失足；"
        "講了別的原因 → 其他。沒講怎麼掉下去 → null。\n"
        "- drown_count、dive_count：照報案人的話記幾個人，不要換成數字代碼。沒講 → null。\n"
        "- drown_sight、dive_sight 只能填 還在水裡、看不到人、已經救起。"
        "還看得到、在水面、載浮載沉 → 還在水裡；人不見了、找不到 → 看不到人；"
        "已經拉上來 → 已經救起。沒講 → null。\n"
        "- drown_distance：離岸多遠，照原話。沒講 → null。\n"
        "- drown_flotation 只能填 有 或 沒有。有救生衣、有泳圈 → 有；沒有 → 沒有。沒講 → null。\n"
        "- drown_consciousness、dive_consciousness 只能填 "
        "意識清醒、對聲音有反應、對疼痛有反應、昏迷。"
        "還會動、清醒 → 意識清醒；會應聲 → 對聲音有反應；"
        "捏會動 → 對疼痛有反應；不會動、昏迷 → 昏迷。沒講 → null。\n"
        "- drown_gender、dive_gender、fall_gender 只能填 男性 或 女性。"
        "男生 → 男性；女生 → 女性。沒講 → null。\n"
        "- drown_age、dive_age、fall_age：照原話記幾歲。"
        "未滿一歲用小數，一個月記 .01、兩個月記 .02，以此類推。沒講 → null。\n"
        "- drown_clothing、dive_clothing：衣服或救生衣顏色，照原話。沒講 → null。\n"
        "- drown_group：公司、團體、成員或帶隊的人，照原話。這題不主動問，沒講 → null。\n"
        "- dive_status 只能填 已經跳下 或 還沒跳（還在橋上、欄杆外）。"
        "已經跳了 → 已經跳下；還在橋上、欄杆外、還沒跳 → 還沒跳（還在橋上、欄杆外）。沒講 → null。\n"
        "- dive_caller_role：路人、路過 → 路人；家屬 → 家屬；朋友 → 朋友；其他照原話。沒講 → null。\n"
        "- fall_caller_role 只能填 當事人(本人)、家人、鄰居或住戶、路人。"
        "本人、當事人 → 當事人(本人)；家人、家屬 → 家人；"
        "鄰居、住戶 → 鄰居或住戶；路人、路過 → 路人。對不上 → null。\n"
        "- high_fall_status 只能填 還在高處（頂樓、窗外、陽台等） 或 已經掉下來。"
        "人還在上面、窗台、陽台、頂樓 → 還在高處（頂樓、窗外、陽台等）；"
        "已經跳下來、掉在地上 → 已經掉下來。沒講 → null。\n"
        "- fall_intent：要不要自殺、有沒有說要跳，照原話。沒講 → null。\n"
        "- fall_floor：幾樓，照原話。沒講 → null。\n"
        "【山難、卡住、瓦斯漏氣】同樣只依本輪回答。\n"
        "- mountain_cause：迷路 → 迷路；身體不舒服 → 身體不舒服；"
        "失聯、沒下山 → 失聯沒下山；扭到、跌倒、受傷、摔傷 → 受傷；"
        "其他原因照原話。沒講 → null。\n"
        "- mountain_injury 只能填 "
        + "、".join(MOUNTAIN_INJURIES)
        + "。沒講傷在哪 → null。\n"
        "- mountain_count：照原話記幾個人。沒講 → null。\n"
        "- mountain_location：地點或座標、路燈電桿編號，照原話。沒講 → null。\n"
        "- mountain_caller_role：本人 → 本人；同行者、家屬、朋友、代報 → 代為報案；"
        "其他照原話。沒講 → null。\n"
        "- mountain_gender、trap_gender 只能填 男性 或 女性。男生 → 男性；女生 → 女性。\n"
        "- mountain_age：照原話。未滿一歲一個月記 .01。沒講 → null。\n"
        "- mountain_consciousness、trap_consciousness 只能填 "
        "意識清醒、對聲音有反應、對疼痛有反應、昏迷。清醒 → 意識清醒；"
        "不會動、昏迷 → 昏迷。沒講 → null。\n"
        "- mountain_entry：幾點上山、從哪裡入山、預計下山，照原話。沒講 → null。\n"
        "- mountain_route：路線和最後經過的地標，照原話。沒講 → null。\n"
        "- mountain_supplies：水、食物、保暖、手電筒、哨子夠不夠，照原話。沒講 → null。\n"
        "- mountain_leader：個人、公司或社團和帶隊的人，照原話。這題不主動問，沒講 → null。\n"
        "- trap_body_part、trap_object、trap_place：照原話。沒講 → null。\n"
        "- trap_freed 只能填 還卡著 或 已經出來了。還卡著 → 還卡著；已經出來 → 已經出來了。\n"
        "- trap_injury 只能填 有 或 沒有。有流血、有受傷 → 有；沒有 → 沒有。\n"
        "- trap_age：照原話記幾歲。沒講 → null。\n"
        "- trap_caller_role 只能填 當事人(本人)、家人、同事、路人。"
        "本人、當事人 → 當事人(本人)；家人、家屬 → 家人；同事 → 同事；路人 → 路人。\n"
        "- gas_building_use 只能填 "
        + "、".join(GAS_BUILDINGS)
        + "。透天 → 透天厝；公寓 → 集合住宅；十層以上 → 高層建築物(10層樓以上)；"
        "只說住家或店家、沒講更細 → 其他。對不上 → null。\n"
        "- gas_caller_role：住戶、住家 → 住戶；鄰居 → 鄰居；管理員 → 管理員；"
        "路人、路過 → 路人；其他照原話。沒講 → null。\n"
        "- gas_flame 只能填 有 或 沒有。看到火或煙 → 有；沒有 → 沒有。\n"
        "- gas_smell_place：家裡、廚房、樓梯、巷子，照原話。沒講 → null。\n"
        "- gas_smell_strength 只能填 很濃、淡淡的、一陣一陣。\n"
        "- gas_type 只能填 天然氣 或 瓦斯桶。\n"
        "- gas_adjacent：旁邊的房子或車子，照原話。這題不主動問，沒講 → null。\n"
        "- gas_discomfort 只能填 有 或 沒有。這題不主動問，沒講 → null。\n"
        "【電梯受困、破門】同樣只依本輪回答。\n"
        "- lift_caller_role 只能填 受困者本人、管理員或警衛、其他。"
        "本人 → 受困者本人；管理員、警衛 → 管理員或警衛；家人、同事 → 其他。\n"
        "- lift_building、lift_floor：社區、棟別、電梯、停在幾樓，照原話。沒講 → null。\n"
        "- lift_count：裡面幾個人，照原話。沒講 → null。\n"
        "- lift_company 只能填 已經聯絡 或 還沒聯絡。\n"
        "- lift_consciousness 只能填 意識清醒、對聲音有反應、對疼痛有反應、昏迷。"
        "都清醒 → 意識清醒；昏迷 → 昏迷。沒講 → null。\n"
        "- lift_discomfort 只能填 有、沒有、不知道。受傷或不舒服 → 有。"
        "這題不主動問，沒講 → null。\n"
        "- door_caller_role：本人、當事人 → 本人；家人、房客、朋友、同事收到對應字；"
        "其他照原話。沒講 → null。\n"
        "- door_reason：獨居聯絡不上、說要自殺、有病史、跌倒起不來收到這幾個字；"
        "其他原因照原話。沒講 → null。\n"
        "- knock_response 只能填 有回應、沒有回應、有聲音但叫不應。\n"
        "- door_kind 只能填 大門、房門、浴室門、鐵門。房間的門 → 房門。\n"
        "- door_locksmith 只能填 有鑰匙但打不開、沒有鑰匙、已找鎖匠。\n"
        "- door_consent 只能填 同意、不同意、家屬或屋主還沒到。\n"
        "- door_gender 只能填 男性 或 女性。男生 → 男性；女生 → 女性。\n"
        "- door_age：當事人大概幾歲，照原話。沒講 → null。"
    )
    return schema, rules
