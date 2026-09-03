"""
fire_tab_map_119.py
━━━━━━━━━━━━━━━━━━━━
119 火警垂片：27 案類 ↔ 代碼、BERT 標籤映射、問句、Q1/Q2 規則兜底。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple


FIRE_BERT_CONF_THRESHOLD = 0.5

ROUTE_Q1 = "請問是房子在燒嗎？還是其它東西燒起來？"
ROUTE_Q2 = "是車子在燒，還是山上、路邊的草木在燒呢？"
SAFETY_MESSAGE = (
    "消防車已經在路上了，請在安全的地方等候，看到車再幫我們引導消防隊。"
)

TAB_A = "A"
TAB_B1 = "B1"
TAB_B2 = "B2"
TAB_C = "C"


@dataclass(frozen=True)
class FireSubtype:
    name: str
    tab: str
    fire_incident_type: int
    building_type_code: Optional[str] = None
    non_building_fire: Optional[int] = None
    vehicle_wildfire_code: Optional[int] = None
    minor_fire_code: Optional[int] = None


FIRE_SUBTYPES: Tuple[FireSubtype, ...] = (
    FireSubtype("透天厝", TAB_A, 0, building_type_code="10"),
    FireSubtype("集合住宅", TAB_A, 0, building_type_code="11"),
    FireSubtype("倉庫", TAB_A, 0, building_type_code="12"),
    FireSubtype("旅館、百貨商場用途建築物", TAB_A, 0, building_type_code="20"),
    FireSubtype("運輸中樞用途建築物", TAB_A, 0, building_type_code="21"),
    FireSubtype("電影院用途建築物", TAB_A, 0, building_type_code="22"),
    FireSubtype("學校、醫院、老人院建築物", TAB_A, 0, building_type_code="23"),
    FireSubtype("毒災場所", TAB_A, 0, building_type_code="24"),
    FireSubtype("大型違章建築區與傳統市場(含工廠)", TAB_A, 0, building_type_code="25"),
    FireSubtype("石化廠建築物", TAB_A, 0, building_type_code="26"),
    FireSubtype("古蹟、文化財", TAB_A, 0, building_type_code="27"),
    FireSubtype("地下建築物(如地下街)", TAB_A, 0, building_type_code="28"),
    FireSubtype("高層建築物(10層樓以上)", TAB_A, 0, building_type_code="29"),
    FireSubtype("汽車", TAB_B1, 1, non_building_fire=0, vehicle_wildfire_code=0),
    FireSubtype("機車", TAB_B1, 1, non_building_fire=0, vehicle_wildfire_code=1),
    FireSubtype("隧道", TAB_B1, 1, non_building_fire=0, vehicle_wildfire_code=2),
    FireSubtype("軌道型交通工具", TAB_B1, 1, non_building_fire=0, vehicle_wildfire_code=3),
    FireSubtype("化學、毒劑交通工具", TAB_B1, 1, non_building_fire=0, vehicle_wildfire_code=4),
    FireSubtype("船舶", TAB_B1, 1, non_building_fire=0, vehicle_wildfire_code=5),
    FireSubtype("航空器", TAB_B1, 1, non_building_fire=0, vehicle_wildfire_code=6),
    FireSubtype("山林田野(平地)", TAB_B2, 1, non_building_fire=0, vehicle_wildfire_code=7),
    FireSubtype("山林田野(山地)", TAB_B2, 1, non_building_fire=0, vehicle_wildfire_code=8),
    FireSubtype("垃圾", TAB_C, 1, non_building_fire=1, minor_fire_code=0),
    FireSubtype("電線桿(電纜)", TAB_C, 1, non_building_fire=1, minor_fire_code=1),
    FireSubtype("瓦斯漏氣", TAB_C, 1, non_building_fire=1, minor_fire_code=2),
    FireSubtype("警報器作響", TAB_C, 1, non_building_fire=1, minor_fire_code=3),
    FireSubtype("查看案件", TAB_C, 1, non_building_fire=1, minor_fire_code=4),
)

FIRE_SUBTYPE_BY_NAME: Dict[str, FireSubtype] = {item.name: item for item in FIRE_SUBTYPES}

BERT_FIRE_LABELS = frozenset({
    "倉庫",
    "垃圾",
    "大型違章建築區與傳統市場(含工廠)",
    "山林田野(山地)",
    "山林田野(平地)",
    "旅館、百貨商場用途建築物",
    "查看案件",
    "機車",
    "汽車",
    "警報器作響",
    "透天厝",
    "集合住宅",
    "電線桿(電纜)",
})

# (field, stage, question)
TAB_A_QUESTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "building_type_code",
        "火警_A_building_type",
        "是哪一種建築物呢？透天厝、公寓大樓，還是其他的？",
    ),
    ("has_flame", "火警_A_flame", "現在有看到火苗竄出來嗎？還是只有看到煙？"),
    ("smoke_color_code", "火警_A_smoke", "那個煙是什麼顏色的？"),
    ("has_explosion", "火警_A_explosion", "剛剛有沒有聽到爆炸的聲音？"),
    ("spread_risk", "火警_A_spread", "火有沒有燒到旁邊的房子？看起來會不會燒過去？"),
    ("people_trapped_code", "火警_A_trapped", "裡面還有沒有人沒出來？"),
    ("building_floors_code", "火警_A_floors", "那棟房子總共幾層樓？"),
    ("fire_floor_code", "火警_A_fire_floor", "火是從幾樓開始燒的？"),
    ("building_structure", "火警_A_structure", "那棟房子是什麼蓋的呢？"),
    ("burn_area_code", "火警_A_area", "現在燒起來的範圍大概多大？"),
    ("access_water_info", "火警_A_access", "那邊消防車進得去嗎？附近有水源嗎？"),
)

TAB_B1_QUESTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "vehicle_wildfire_code",
        "火警_B1_subtype",
        "那是汽車還是機車呢？還是其它交通工具呢？",
    ),
)

TAB_B2_QUESTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "vehicle_wildfire_code",
        "火警_B2_subtype",
        "是燒在山上，還是路邊的平地呢？",
    ),
)

TAB_C_QUESTIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "minor_fire_code",
        "火警_C_subtype",
        "那您現在是看到有煙，還是聞到什麼味道？還是聽到警報聲呢？",
    ),
)

TAB_QUESTIONS: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    TAB_A: TAB_A_QUESTIONS,
    TAB_B1: TAB_B1_QUESTIONS,
    TAB_B2: TAB_B2_QUESTIONS,
    TAB_C: TAB_C_QUESTIONS,
}


def sop_slots_for_tab(tab: Optional[str]) -> Tuple[str, ...]:
    """返回該垂片會詢問的 SOP 槽位。"""
    questions = TAB_QUESTIONS.get(tab or "", ())
    return tuple(item[0] for item in questions)


def _clear_tab_exclusive_fields(case: Any, keep_tab: Optional[str]) -> None:
    """清空非目標垂片的專屬代碼欄，B1/B2 共用的 vehicle_wildfire_code 除外。"""
    for tab, questions in TAB_QUESTIONS.items():
        if tab == keep_tab:
            continue
        for field, _, _ in questions:
            if field == "vehicle_wildfire_code" and keep_tab in (TAB_B1, TAB_B2):
                continue
            if hasattr(case, field):
                setattr(case, field, None)


FIRE_IDENTITY_CODE_FIELDS = frozenset({
    "building_type_code",
    "vehicle_wildfire_code",
    "minor_fire_code",
})


def apply_subtype_identity_codes(
    case: Any,
    label: str,
    *,
    update_tab: bool = False,
) -> bool:
    """
    依子類名寫入身份編號欄，並清掉其他垂片的專屬碼。
    成功解析標籤則返回 True。
    """
    item = lookup_subtype(label)
    if item is None:
        return False
    _clear_tab_exclusive_fields(case, item.tab)
    if update_tab:
        case.fire_tab = item.tab
    case.fire_incident_type = item.fire_incident_type
    if item.tab == TAB_A:
        case.non_building_fire = None
    elif item.non_building_fire is not None:
        case.non_building_fire = item.non_building_fire
    case.building_type_code = item.building_type_code
    case.vehicle_wildfire_code = item.vehicle_wildfire_code
    case.minor_fire_code = item.minor_fire_code
    return True


def subtype_name_from_identity_codes(case: Any) -> Optional[str]:
    """由當前垂片上的身份編號反查唯一子類名。"""
    tab = getattr(case, "fire_tab", None)
    if tab not in TAB_QUESTIONS:
        tab = tab_for_codes(
            getattr(case, "fire_incident_type", None),
            getattr(case, "non_building_fire", None),
            getattr(case, "vehicle_wildfire_code", None),
            getattr(case, "minor_fire_code", None),
        )
    if tab == TAB_A:
        code = getattr(case, "building_type_code", None)
        if code is None or str(code).strip() == "":
            return None
        code_s = str(code).strip()
        for item in FIRE_SUBTYPES:
            if item.building_type_code == code_s:
                return item.name
        return None
    if tab in (TAB_B1, TAB_B2):
        code = getattr(case, "vehicle_wildfire_code", None)
        if code is None:
            return None
        try:
            code_i = int(code)
        except (TypeError, ValueError):
            return None
        for item in FIRE_SUBTYPES:
            if item.vehicle_wildfire_code == code_i:
                return item.name
        return None
    if tab == TAB_C:
        code = getattr(case, "minor_fire_code", None)
        if code is None:
            return None
        try:
            code_i = int(code)
        except (TypeError, ValueError):
            return None
        for item in FIRE_SUBTYPES:
            if item.minor_fire_code == code_i:
                return item.name
        return None
    return None

FIELD_LABELS_ZH: Dict[str, str] = {
    "fire_tab": "垂片",
    "fire_incident_type": "火災類型",
    "building_type_code": "建築物類型",
    "has_flame": "有無火焰",
    "smoke_color_code": "濃煙顏色",
    "has_explosion": "有無爆炸",
    "spread_risk": "延燒可能",
    "people_trapped_code": "有無受困",
    "building_floors_code": "建物樓層",
    "fire_floor_code": "起火樓層",
    "building_structure": "建物構造",
    "burn_area_code": "延燒面積",
    "access_water_info": "其他資訊",
    "non_building_fire": "非建築物火警",
    "vehicle_wildfire_code": "交通工具山林火警",
    "minor_fire_code": "輕微火警",
}

BUILDING_TYPE_ALIASES: Dict[str, str] = {
    "透天厝": "10", "透天": "10", "獨棟": "10", "独栋": "10",
    "集合住宅": "11", "公寓": "11", "大樓": "11", "大楼": "11", "住宅大樓": "11",
    "倉庫": "12", "仓库": "12",
    "旅館、百貨商場用途建築物": "20", "旅館": "20", "旅馆": "20",
    "百貨": "20", "商場": "20", "酒店": "20",
    "運輸中樞用途建築物": "21", "車站": "21", "機場": "21", "捷運站": "21",
    "電影院用途建築物": "22", "電影院": "22", "戲院": "22",
    "學校、醫院、老人院建築物": "23", "學校": "23", "学校": "23",
    "醫院": "23", "医院": "23", "老人院": "23", "安養": "23",
    "毒災場所": "24", "毒災": "24",
    "大型違章建築區與傳統市場(含工廠)": "25", "傳統市場": "25",
    "違章": "25", "工廠": "25", "工厂": "25",
    "石化廠建築物": "26", "石化": "26",
    "古蹟、文化財": "27", "古蹟": "27", "古迹": "27", "文化財": "27",
    "地下建築物(如地下街)": "28", "地下街": "28", "地下": "28",
    "高層建築物(10層樓以上)": "29", "高層": "29", "高层": "29",
    "未知": "00", "不知道": "00",
}

VEHICLE_WILDFIRE_ALIASES: Dict[str, int] = {
    "汽車": 0, "汽车": 0, "小客車": 0, "轎車": 0, "貨車": 0, "車子": 0, "车子": 0,
    "機車": 1, "机车": 1, "摩托車": 1,
    "隧道": 2,
    "軌道型交通工具": 3, "火車": 3, "高鐵": 3, "捷運": 3, "軌道": 3,
    "化學、毒劑交通工具": 4, "化學槽車": 4, "毒劑": 4,
    "船舶": 5, "船": 5,
    "航空器": 6, "飛機": 6, "飞机": 6, "航空": 6,
    "山林田野(平地)": 7, "平地": 7, "路邊": 7, "路边": 7,
    "山林田野(山地)": 8, "山上": 8, "山地": 8, "山林": 8,
}

MINOR_FIRE_ALIASES: Dict[str, int] = {
    "垃圾": 0,
    "電線桿(電纜)": 1, "電線桿": 1, "电线杆": 1, "電纜": 1, "电缆": 1,
    "瓦斯漏氣": 2, "瓦斯": 2,
    "警報器作響": 3, "警報": 3, "警报": 3,
    "查看案件": 4, "查看": 4,
}

SMOKE_COLOR_ALIASES: Dict[str, int] = {
    "無煙": 0, "无烟": 0, "沒有煙": 0, "没有烟": 0, "沒煙": 0,
    "黑色煙": 1, "黑煙": 1, "黑烟": 1, "黑": 1,
    "白色煙": 2, "白煙": 2, "白烟": 2, "白": 2,
    "其他色煙": 3, "其他": 3, "灰": 3, "黃": 3,
}

STRUCTURE_ALIASES: Dict[str, int] = {
    "其他": 0, "不知道": 0,
    "木造屋": 1, "木造": 1, "木頭": 1, "木头": 1,
    "鐵皮屋": 2, "铁皮屋": 2, "鐵皮": 2, "铁皮": 2,
    "連造式鐵皮屋": 3, "連造": 3,
    "磚造屋": 4, "磚造": 4, "磚": 4, "砖": 4,
    "RC": 5, "rc": 5, "鋼筋混凝土": 5,
    "SRC": 6, "src": 6,
}

FIRE_CODE_INT_RANGES: Dict[str, Tuple[int, int]] = {
    "fire_incident_type": (0, 1),
    "has_flame": (0, 1),
    "smoke_color_code": (0, 3),
    "has_explosion": (0, 1),
    "spread_risk": (0, 1),
    "people_trapped_code": (0, 1),
    "building_floors_code": (0, 4),
    "fire_floor_code": (0, 5),
    "building_structure": (0, 6),
    "burn_area_code": (0, 5),
    "access_water_info": (0, 3),
    "non_building_fire": (0, 1),
    "vehicle_wildfire_code": (0, 8),
    "minor_fire_code": (0, 4),
}

FIRE_CODE_FIELDS = frozenset(
    {"building_type_code"} | set(FIRE_CODE_INT_RANGES)
)

_Q1_BUILDING_KWS = (
    "房子", "房屋", "屋子", "住宅", "透天", "公寓", "大樓", "大楼",
    "建築", "建筑", "倉庫", "仓库", "工廠", "工厂", "廠房", "厂房",
    "旅館", "旅馆", "百貨", "商場", "學校", "学校", "醫院", "医院",
    "電影院", "电影院", "古蹟", "古迹", "地下街", "高層", "高层",
    "店面", "住家",
)
_Q1_OTHER_KWS = (
    "車子", "车子", "汽車", "汽车", "機車", "机车", "草木", "雜草", "杂草",
    "山林", "垃圾", "電線桿", "电线杆", "瓦斯", "警報", "警报",
    "其他東西", "其它東西", "其他东西", "其它东西",
)
_Q2_VEHICLE_KWS = (
    "車", "车", "汽車", "汽车", "機車", "机车", "隧道", "火車", "高铁",
    "軌道", "船舶", "船", "飛機", "飞机", "航空",
)
_Q2_VEG_KWS = ("山", "草", "林", "田", "樹", "树", "野外")
_Q2_MINOR_KWS = (
    "垃圾", "電線", "电缆", "電纜", "瓦斯", "警報", "警报",
    "查看", "都不是", "都沒", "都没",
)


def _strip_fire_prefix(label: str) -> str:
    text = (label or "").strip()
    for prefix in ("火警-", "火警－", "火警_"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def lookup_subtype(label: Optional[str]) -> Optional[FireSubtype]:
    if not label:
        return None
    name = _strip_fire_prefix(str(label))
    return FIRE_SUBTYPE_BY_NAME.get(name)


def codes_for_label(label: Optional[str]) -> Optional[Dict[str, Any]]:
    item = lookup_subtype(label)
    if item is None:
        return None
    out: Dict[str, Any] = {
        "fire_incident_type": item.fire_incident_type,
        "sub_category": item.name,
    }
    if item.building_type_code is not None:
        out["building_type_code"] = item.building_type_code
    if item.non_building_fire is not None:
        out["non_building_fire"] = item.non_building_fire
    if item.vehicle_wildfire_code is not None:
        out["vehicle_wildfire_code"] = item.vehicle_wildfire_code
    if item.minor_fire_code is not None:
        out["minor_fire_code"] = item.minor_fire_code
    return out


def tab_for_subtype(label: Optional[str]) -> Optional[str]:
    item = lookup_subtype(label)
    return item.tab if item else None


def tab_for_codes(
    fire_incident_type: Optional[int],
    non_building_fire: Optional[int] = None,
    vehicle_wildfire_code: Optional[int] = None,
    minor_fire_code: Optional[int] = None,
) -> Optional[str]:
    if fire_incident_type == 0:
        return TAB_A
    if fire_incident_type != 1:
        return None
    if non_building_fire == 1 or minor_fire_code is not None:
        return TAB_C
    if vehicle_wildfire_code is not None:
        if 0 <= vehicle_wildfire_code <= 6:
            return TAB_B1
        if vehicle_wildfire_code in (7, 8):
            return TAB_B2
    if non_building_fire == 0:
        return None
    return None


def infer_route_q1(text: str) -> Optional[str]:
    """報案人回答 Q1：building | other | None。"""
    t = (text or "").strip()
    if not t:
        return None
    if any(k in t for k in ("不是房子", "不是房屋", "不是屋", "其他東西", "其它東西", "其他东西", "其它东西")):
        return "other"
    if t in ("不是", "沒有", "没有", "否", "不對", "不对"):
        return "other"
    if t in ("是", "對", "对", "有", "嗯", "對啊", "对啊"):
        return "building"
    has_b = any(k in t for k in _Q1_BUILDING_KWS)
    has_o = any(k in t for k in _Q1_OTHER_KWS)
    if has_b and not has_o:
        return "building"
    if has_o and not has_b:
        return "other"
    return None


def infer_route_q2(text: str) -> Optional[str]:
    """報案人回答 Q2：vehicle | vegetation | minor | None。"""
    t = (text or "").strip()
    if not t:
        return None
    if any(k in t for k in ("都不是", "都沒", "都没", "都不是車子", "都不是草木")):
        return "minor"
    has_v = any(k in t for k in _Q2_VEHICLE_KWS)
    has_g = any(k in t for k in _Q2_VEG_KWS)
    has_m = any(k in t for k in _Q2_MINOR_KWS)
    if has_v and not has_g and not has_m:
        return "vehicle"
    if has_g and not has_v:
        return "vegetation"
    if has_m and not has_v and not has_g:
        return "minor"
    return None


def _as_int(val: Any) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    text = str(val).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _alias_lookup(aliases: Dict[str, Any], val: Any) -> Any:
    if val is None:
        return None
    text = str(val).strip()
    if text in aliases:
        return aliases[text]
    for key, mapped in aliases.items():
        if key and key in text:
            return mapped
    return None


def normalize_building_type_code(val: Any) -> Optional[str]:
    if val is None:
        return None
    text = str(val).strip()
    if text in {"00", "10", "11", "12", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29"}:
        return text
    as_int = _as_int(text)
    if as_int is not None:
        if as_int == 0:
            return "00"
        padded = f"{as_int:02d}" if as_int < 10 else str(as_int)
        if padded in {"10", "11", "12", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29"}:
            return padded
    aliased = _alias_lookup(BUILDING_TYPE_ALIASES, text)
    return aliased if isinstance(aliased, str) else None


def _parse_floor_number(text: str) -> Optional[int]:
    if any(k in text for k in ("地下", "B1", "b1", "地下室")):
        return -1
    match = re.search(r"(\d+)\s*層?", text)
    if match:
        return int(match.group(1))
    cn = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6,
          "七": 7, "八": 8, "九": 9, "十": 10}
    for word, num in cn.items():
        if word in text:
            return num
    return None


def _floors_code(n: int, *, fire_floor: bool) -> int:
    if n < 0:
        return 1 if fire_floor else 0
    if n <= 3:
        return 2 if fire_floor else 1
    if n <= 10:
        return 3 if fire_floor else 2
    if n <= 15:
        return 4 if fire_floor else 3
    return 5 if fire_floor else 4


def _burn_area_code(text: str) -> Optional[int]:
    match = re.search(r"(\d+(?:\.\d+)?)\s*坪", text)
    if not match:
        return None
    ping = float(match.group(1))
    if ping <= 50:
        return 1
    if ping <= 100:
        return 2
    if ping <= 300:
        return 3
    if ping <= 500:
        return 4
    return 5


def _access_water_code(text: str) -> Optional[int]:
    alley = any(k in text for k in ("小巷", "進不去", "进不去", "巷子"))
    water = any(k in text for k in ("缺水", "沒有水源", "没有水源", "沒水源", "沒消防栓"))
    has_water = any(k in text for k in ("有水源", "有消防栓", "有水"))
    can_enter = any(k in text for k in ("進得去", "进得去", "進得去", "可以進"))
    if alley and water:
        return 3
    if alley:
        return 1
    if water:
        return 2
    if can_enter and (has_water or "水源" in text or "消防栓" in text):
        return 0
    if can_enter and not water:
        return 0
    return None


def _yes_no_code(val: Any, yes_words: Iterable[str], no_words: Iterable[str]) -> Optional[int]:
    if isinstance(val, bool):
        return 1 if val else 0
    as_int = _as_int(val)
    if as_int in (0, 1):
        return as_int
    text = str(val or "")
    if any(k in text for k in no_words):
        return 0
    if any(k in text for k in yes_words):
        return 1
    return None


def normalize_fire_field(key: str, val: Any) -> Any:
    """將 LLM / 規則抽出的值正規成垂片代碼。無法判定則 None。"""
    if val is None:
        return None
    if key == "building_type_code":
        return normalize_building_type_code(val)
    if key == "fire_incident_type":
        as_int = _as_int(val)
        if as_int in (0, 1):
            return as_int
        text = str(val)
        if any(k in text for k in ("非建築", "非建筑", "不是房子", "其他")):
            return 1
        if any(k in text for k in ("建築", "建筑", "房子", "房屋")):
            return 0
        return None
    if key == "has_flame":
        return _yes_no_code(val, ("有火", "火苗", "火焰", "竄", "窜", "看到火"), ("沒有火", "没有火", "只有煙", "只有烟", "無火焰", "无火焰"))
    if key == "smoke_color_code":
        as_int = _as_int(val)
        if as_int is not None and 0 <= as_int <= 3:
            return as_int
        aliased = _alias_lookup(SMOKE_COLOR_ALIASES, val)
        return aliased if isinstance(aliased, int) else None
    if key == "has_explosion":
        return _yes_no_code(val, ("有爆炸", "爆炸", "轟", "轰"), ("沒有爆炸", "没有爆炸", "沒聽到", "没听到", "無爆炸"))
    if key == "spread_risk":
        return _yes_no_code(
            val,
            ("燒到旁邊", "烧到旁边", "延燒", "延烧", "會燒過去", "会烧过去", "已經燒"),
            ("沒有燒到", "没有烧到", "不會", "不会", "延燒可能性低"),
        )
    if key == "people_trapped_code":
        return _yes_no_code(
            val,
            ("有人受困", "還有人", "还有人", "沒出來", "没出来", "還在裡面", "还在里面"),
            ("沒有人", "没有人", "無人", "无人", "都出來", "都出来", "沒人",
             "沒有受困", "没有受困", "沒人受困"),
        )
    if key in ("building_floors_code", "fire_floor_code"):
        as_int = _as_int(val)
        lo, hi = FIRE_CODE_INT_RANGES[key]
        if as_int is not None and lo <= as_int <= hi:
            return as_int
        n = _parse_floor_number(str(val))
        if n is None:
            if "未知" in str(val) or "不知道" in str(val):
                return 0
            return None
        return _floors_code(n, fire_floor=(key == "fire_floor_code"))
    if key == "building_structure":
        as_int = _as_int(val)
        if as_int is not None and 0 <= as_int <= 6:
            return as_int
        aliased = _alias_lookup(STRUCTURE_ALIASES, val)
        return aliased if isinstance(aliased, int) else None
    if key == "burn_area_code":
        as_int = _as_int(val)
        if as_int is not None and 0 <= as_int <= 5:
            return as_int
        parsed = _burn_area_code(str(val))
        if parsed is not None:
            return parsed
        if "未知" in str(val) or "不知道" in str(val):
            return 0
        return None
    if key == "access_water_info":
        as_int = _as_int(val)
        if as_int is not None and 0 <= as_int <= 3:
            return as_int
        return _access_water_code(str(val))
    if key == "non_building_fire":
        as_int = _as_int(val)
        if as_int in (0, 1):
            return as_int
        text = str(val)
        if any(k in text for k in ("輕微", "轻微")):
            return 1
        if any(k in text for k in ("交通", "山林", "車子", "草木")):
            return 0
        return None
    if key == "vehicle_wildfire_code":
        as_int = _as_int(val)
        if as_int is not None and 0 <= as_int <= 8:
            return as_int
        aliased = _alias_lookup(VEHICLE_WILDFIRE_ALIASES, val)
        return aliased if isinstance(aliased, int) else None
    if key == "minor_fire_code":
        as_int = _as_int(val)
        if as_int is not None and 0 <= as_int <= 4:
            return as_int
        aliased = _alias_lookup(MINOR_FIRE_ALIASES, val)
        return aliased if isinstance(aliased, int) else None
    return val


def normalize_extracted_fire_fields(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """只保留成功正規化的火警代碼欄位，並同步布林別名。"""
    out: Dict[str, Any] = {}
    for key, val in extracted.items():
        if key not in FIRE_CODE_FIELDS:
            continue
        normalized = normalize_fire_field(key, val)
        if normalized is None:
            continue
        out[key] = normalized
    if "people_trapped_code" in out:
        out["people_trapped"] = out["people_trapped_code"] == 1
    if "spread_risk" in out:
        out["fire_spread"] = out["spread_risk"] == 1
    if "has_flame" in out:
        out["fire_or_smoke"] = "火" if out["has_flame"] == 1 else "煙"
    if "smoke_color_code" in out:
        out["smoke_color"] = {0: "無煙", 1: "黑煙", 2: "白煙", 3: "其他色煙"}.get(
            out["smoke_color_code"]
        )
    return out


def apply_bert_subtype_to_case(
    case: Any,
    label: str,
    conf: float,
    *,
    allow_tab_switch: bool = False,
) -> None:
    """
    將 BERT 細類寫入 case。
    fire_tab 已鎖定且 allow_tab_switch=False 時只更新該垂片內的細類碼，不改路由。
    allow_tab_switch=True 時可改 fire_tab 並寫入新垂片代碼。
    """
    codes = codes_for_label(label)
    if not codes:
        return
    predicted_tab = tab_for_subtype(label)
    locked_tab = getattr(case, "fire_tab", None)

    if allow_tab_switch and predicted_tab:
        case.sub_category = codes["sub_category"]
        case.sub_conf = conf
        apply_subtype_identity_codes(case, label, update_tab=True)
        return

    if locked_tab:
        if predicted_tab and predicted_tab != locked_tab:
            return
        case.sub_category = codes["sub_category"]
        case.sub_conf = conf
        apply_subtype_identity_codes(case, label, update_tab=False)
        return

    case.sub_category = codes["sub_category"]
    case.sub_conf = conf

    existing_type = getattr(case, "fire_incident_type", None)
    predicted_type = codes.get("fire_incident_type")
    if existing_type is not None and predicted_type is not None and existing_type != predicted_type:
        return

    apply_subtype_identity_codes(case, label, update_tab=False)


def apply_route_q1(case: Any, route: str) -> None:
    if route == "building":
        case.fire_incident_type = 0
        case.fire_tab = TAB_A
    elif route == "other":
        case.fire_incident_type = 1


def apply_route_q2(case: Any, route: str) -> None:
    case.fire_incident_type = 1
    if route == "vehicle":
        case.non_building_fire = 0
        case.fire_tab = TAB_B1
    elif route == "vegetation":
        case.non_building_fire = 0
        case.fire_tab = TAB_B2
    else:
        case.non_building_fire = 1
        case.fire_tab = TAB_C


def resolve_fire_tab(case: Any) -> Optional[str]:
    """依已填代碼推導垂片；成功則寫入 fire_tab。"""
    tab = getattr(case, "fire_tab", None)
    if tab in TAB_QUESTIONS:
        return tab
    tab = tab_for_codes(
        getattr(case, "fire_incident_type", None),
        getattr(case, "non_building_fire", None),
        getattr(case, "vehicle_wildfire_code", None),
        getattr(case, "minor_fire_code", None),
    )
    if tab:
        case.fire_tab = tab
    return tab
