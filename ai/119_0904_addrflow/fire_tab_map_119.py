"""
fire_tab_map_119.py
━━━━━━━━━━━━━━━━━━━━
119 火警垂片：27 案類 ↔ 代碼、BERT 標籤映射、問句；
案類分析時，LLM 判斷不出來改用這裡的關鍵詞判斷。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Tuple


FIRE_BERT_CONF_THRESHOLD = 0.5

# 案類分析：一句話直接分到 A / B1 / B2 / C 垂片（取代舊 Q1/Q2 兩段分流）
INCIDENT_STAGE = "火警-案類分析"
INCIDENT_Q = "請問發生什麼事？是什麼東西在燒？"
INCIDENT_REASK_Q = "不好意思，請您再說一次是什麼在燒？"
# 問兩次仍分不出是哪種火災、先當成輕微火警處理時，寫進 ImportantTag 的說明文字。
# 取代舊流程的「Q2 兩輪仍無法判斷」（意思相同，舊名稱裡的 Q2 已不存在）。
UNRESOLVED_TAB_TAG = "火災類型無法判斷，預設輕微火警"
SAFETY_MESSAGE = (
    "消防車已經在路上了，請在安全的地方等候，看到車再幫我們引導消防隊。"
)
# 報案人講出有人受困時，轉接專人前說的話（火警流程任何時候都適用）
TRAPPED_TRANSFER_MESSAGE = "消防車已經出發了，請不要掛電話，我馬上幫您轉給專人。"

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

# ─── 垂片題目 ────────────────────────────────────────────────────────────────
# 規格：docs/修改後_(all)火警垂片規格_關鍵要素與問句_0929.xlsx
# 每一題照 xlsx 記下「問法分類」與「前置條件」：
#   主動：還不知道才問（報案人前面已經講過就跳過）
#   條件：前置條件「確定成立」而且還不知道才問；報案人答不知道、人不在現場
#         等無法確定的情況，一律當作不成立、不問
#   被動：AI 不主動問，報案人自己講到時由每一輪的欄位抽取記下來
MODE_ACTIVE = "主動"
MODE_CONDITIONAL = "條件"
MODE_PASSIVE = "被動"


@dataclass(frozen=True)
class FireQuestion:
    element: str            # xlsx「關鍵要素」
    field: str              # 答案存在案件的哪個欄位
    mode: str               # 主動／條件／被動
    stage: str              # 問這一題時的流程階段名稱（log 與送給下游的 flow_stage）
    question: str = ""      # 受理員要問的話；被動題不問，可留空
    condition: Optional[Callable[[Any], bool]] = None  # 條件題才有
    condition_text: str = ""  # xlsx「前置條件」原文，供 log 與閱讀


# 條件會用到的固定說法。報案人的回答符合這些情況時，欄位一定要記成這幾個字，
# 條件才判斷得出來；其他情況照報案人說的內容記（參考範圍不是選擇題）。
# 火煙狀況（1005 xlsx 起分成 6 種）
FIRE_SMOKE_SPARK_ONLY = "只有火花"
FIRE_SMOKE_FIRE_AND_SMOKE = "有火有煙"
FIRE_SMOKE_FIRE_NO_SMOKE = "有火無煙"
FIRE_SMOKE_SMOKE_NO_FIRE = "無火有煙"
FIRE_SMOKE_NONE = "無火無煙"
FIRE_SMOKE_UNSURE = "不確定"
# 前置條件「看得到煙」「看得到火」各包含哪幾種火煙狀況（照 xlsx 的前置條件欄）
FIRE_SMOKE_SMOKE_VISIBLE = (FIRE_SMOKE_FIRE_AND_SMOKE, FIRE_SMOKE_SMOKE_NO_FIRE)
FIRE_SMOKE_FIRE_VISIBLE = (FIRE_SMOKE_FIRE_AND_SMOKE, FIRE_SMOKE_FIRE_NO_SMOKE)
TRAPPED_YES = "有人受困"
TRAPPED_NO = "無人受困"
TRAPPED_UNSURE = "不確定"
WAREHOUSE_OR_FACTORY = ("倉庫", "大型違章建築區與傳統市場(含工廠)")
# B1 乘客下車狀況：「仍有人在車上」跟有人受困一樣，立刻轉人工
OCCUPANTS_ALL_OUT = "人已全部下車"
OCCUPANTS_STILL_INSIDE = "仍有人在車上"
OCCUPANTS_UNSURE = "不確定"
# B1 車種：只有「貨車」會被前置條件用到（載運物），其他車種照報案人說的記
VEHICLE_KIND_TRUCK = "貨車"
# 氣味：沒聞到任何味道記「無」（C 來源確認的前置條件要用），其他照報案人說的記
ODOR_NONE = "無"

# 前置條件要用到、而且只能從固定說法裡選的欄位。
# 由 LLM 理解報案人的話後，從這些說法裡選一個；選了清單以外的值就不記（當作這一輪沒抽到）。
FIRE_FIXED_ANSWERS: Dict[str, Tuple[str, ...]] = {
    "fire_or_smoke": (
        FIRE_SMOKE_SPARK_ONLY, FIRE_SMOKE_FIRE_AND_SMOKE, FIRE_SMOKE_FIRE_NO_SMOKE,
        FIRE_SMOKE_SMOKE_NO_FIRE, FIRE_SMOKE_NONE, FIRE_SMOKE_UNSURE,
    ),
    "trapped_status": (TRAPPED_YES, TRAPPED_NO, TRAPPED_UNSURE),
    "occupants_status": (OCCUPANTS_ALL_OUT, OCCUPANTS_STILL_INSIDE, OCCUPANTS_UNSURE),
}


def _smoke_visible(case: Any) -> bool:
    """火煙狀況 = 有火有煙、無火有煙（報案人確定看得到煙）。"""
    return getattr(case, "fire_or_smoke", None) in FIRE_SMOKE_SMOKE_VISIBLE


def _fire_visible(case: Any) -> bool:
    """火煙狀況 = 有火有煙、有火無煙（報案人確定看得到火）。"""
    return getattr(case, "fire_or_smoke", None) in FIRE_SMOKE_FIRE_VISIBLE


def _no_fire_no_smoke(case: Any) -> bool:
    """火煙狀況 = 無火無煙。"""
    return getattr(case, "fire_or_smoke", None) == FIRE_SMOKE_NONE


_CN_FLOOR_ABOVE_ONE = "二兩三四五六七八九十"


def _building_more_than_one_floor(case: Any) -> bool:
    """
    建物樓層 > 1層樓。建物樓層還不知道（沒問到、報案人答未知）就不算。
    建物樓層存的是報案人說的文字，例如「5層樓」「2~3層樓」「三層」「1層樓」。
    有阿拉伯數字就看第一個數字；沒有的話看有沒有二到十的中文數字（「十一層」也算大於 1）。
    """
    text = (getattr(case, "building_total_floors", None) or "").strip()
    if not text:
        return False
    match = re.search(r"\d+", text)
    if match:
        return int(match.group()) > 1
    return any(ch in text for ch in _CN_FLOOR_ABOVE_ONE)


def _fire_visible_and_more_than_one_floor(case: Any) -> bool:
    """看得到火（有火有煙、有火無煙），而且建物樓層 > 1層樓（xlsx 的「＋」是「而且」）。"""
    return _fire_visible(case) and _building_more_than_one_floor(case)


# 地址裡的樓層寫法：「5樓」「十二樓」「5F」「B1」「地下室」
_ADDRESS_FLOOR_RE = re.compile(
    r"[0-9０-９一二兩三四五六七八九十]+\s*樓|\d+\s*[Ff](?![A-Za-z])|[Bb]\d|地下"
)
LOCATION_TYPE_LANDMARK = "landmark"  # 地點型態＝地標（學校、公園、市場這類可辨識的地點）


def _people_trapped(case: Any) -> bool:
    """有無受困 = 有人受困。"""
    return getattr(case, "trapped_status", None) == TRAPPED_YES


def _warehouse_or_factory(case: Any) -> bool:
    """建築物類型 = 倉庫、大型違章建築區與傳統市場(含工廠)。"""
    return getattr(case, "sub_category", None) in WAREHOUSE_OR_FACTORY


def _subtype_is(*names: str) -> Callable[[Any], bool]:
    """前置條件「次案類 = 某幾種」，例如「交通工具＝汽車、機車」。次案類還不知道就不成立。"""
    return lambda case: getattr(case, "sub_category", None) in names


def _address_has_floor(case: Any) -> bool:
    """完整地址（address）裡已經有樓層，例如「華興街16號5樓」。"""
    return bool(_ADDRESS_FLOOR_RE.search(getattr(case, "address", None) or ""))


def _source_location_unknown(case: Any) -> bool:
    """
    C 來源確認的前置條件：
    （氣味類型 ≠ 無　或　輕微火警＝警報器作響）＋ 地址沒有樓層 ＋ 地點型態 ≠ 地標
    「＋」是「而且」。氣味一定要已經問出來、而且不是「無」才算；還不知道就不算。
    地址已經講到幾樓、或地點是學校公園這類地標時，不用再問哪一戶哪一層（問卷抱怨）。
    """
    odor = (getattr(case, "odor", None) or "").strip()
    smell_or_alarm = (
        (bool(odor) and odor != ODOR_NONE)
        or getattr(case, "sub_category", None) == "警報器作響"
    )
    return (
        smell_or_alarm
        and not _address_has_floor(case)
        and getattr(case, "location_type", None) != LOCATION_TYPE_LANDMARK
    )


def _hazmat_vehicle_or_truck(case: Any) -> bool:
    """交通工具＝化學、毒劑交通工具，或 車種＝貨車（xlsx 前置條件的換行當作「或」）。"""
    return (
        getattr(case, "sub_category", None) == "化學、毒劑交通工具"
        or getattr(case, "vehicle_type", None) == VEHICLE_KIND_TRUCK
    )


TAB_A_QUESTIONS: Tuple[FireQuestion, ...] = (
    FireQuestion("建築物類型", "sub_category", MODE_ACTIVE,
                 "建築物火警-建築物類型", "是哪一種建築物呢？是公寓還是大樓？"),
    FireQuestion("場所用途", "place_usage", MODE_ACTIVE,
                 "建築物火警-場所用途", "現場是住家還是工廠呢？"),
    FireQuestion("建物樓層", "building_total_floors", MODE_ACTIVE,
                 "建築物火警-建物樓層", "那棟房子總共幾層樓？"),
    FireQuestion("火煙狀況", "fire_or_smoke", MODE_ACTIVE,
                 "建築物火警-火煙狀況", "現在有看到火嗎？還是只有看到煙？"),
    FireQuestion("濃煙顏色", "smoke_color", MODE_CONDITIONAL,
                 "建築物火警-濃煙顏色", "是黑煙還是白煙？",
                 _smoke_visible, "火煙狀況 = 有火有煙、無火有煙"),
    FireQuestion("起火樓層", "fire_floor", MODE_CONDITIONAL,
                 "建築物火警-起火樓層", "是幾樓在冒火呢？",
                 _fire_visible_and_more_than_one_floor,
                 "火煙狀況 = 有火有煙、有火無煙 ＋ 建物樓層 > 1層樓"),
    FireQuestion("延燒可能", "spread_status", MODE_CONDITIONAL,
                 "建築物火警-延燒可能", "火大概燒多大？會燒到旁邊的房子嗎？",
                 _fire_visible, "火煙狀況 = 有火有煙、有火無煙"),
    FireQuestion("有無受困", "trapped_status", MODE_ACTIVE,
                 "建築物火警-有無受困", "裡面還有沒有人沒出來？"),
    # 有人受困會立刻轉人工，所以 AI 實際上問不到這一題；
    # 轉人工後系統旁聽真人對話時，講到應門情況仍會記在這個欄位。
    FireQuestion("起火戶應門", "door_response", MODE_CONDITIONAL,
                 "建築物火警-起火戶應門", "有去敲過門嗎？裡面有人回應嗎？",
                 _people_trapped, "有無受困 = 有人受困"),
    FireQuestion("報案人身分", "caller_role", MODE_ACTIVE,
                 "建築物火警-報案人身分", "請問您是住在附近，還是路人？"),
    FireQuestion("建物構造", "building_construction", MODE_CONDITIONAL,
                 "建築物火警-建物構造", "請問是鐵皮工廠嗎？",
                 _warehouse_or_factory,
                 "建築物類型＝倉庫、大型違章建築區與傳統市場(含工廠)"),
    FireQuestion("危險物品", "hazardous_materials", MODE_CONDITIONAL,
                 "建築物火警-危險物品", "現場有沒有放瓦斯桶、化學藥品這類東西？",
                 _warehouse_or_factory,
                 "建築物類型＝倉庫、大型違章建築區與傳統市場(含工廠)"),
    FireQuestion("氣味", "odor", MODE_CONDITIONAL,
                 "建築物火警-氣味", "有聞到燒焦味嗎？",
                 _no_fire_no_smoke, "火煙狀況 = 無火無煙"),
    FireQuestion("有無爆炸", "explosion_status", MODE_PASSIVE, "建築物火警-有無爆炸"),
    FireQuestion("其他資訊", "access_info", MODE_PASSIVE, "建築物火警-其他資訊"),
    FireQuestion("延燒面積", "fire_extent", MODE_PASSIVE, "建築物火警-延燒面積"),
)

TAB_B1_QUESTIONS: Tuple[FireQuestion, ...] = (
    FireQuestion("交通工具", "sub_category", MODE_ACTIVE,
                 "交通工具火警-交通工具", "是什麼車在燒？汽車或機車嗎？"),
    FireQuestion("車種", "vehicle_type", MODE_CONDITIONAL,
                 "交通工具火警-車種", "是什麼車種呢？一般油車還是電動車？",
                 _subtype_is("汽車", "機車"), "交通工具＝汽車、機車"),
    FireQuestion("火煙狀況", "fire_or_smoke", MODE_ACTIVE,
                 "交通工具火警-火煙狀況", "現在有看到火嗎？還是只有看到煙？"),
    FireQuestion("濃煙顏色", "smoke_color", MODE_CONDITIONAL,
                 "交通工具火警-濃煙顏色", "請問是黑煙還是白煙？",
                 _smoke_visible, "火煙狀況 = 有火有煙、無火有煙"),
    FireQuestion("報案人身分", "caller_role", MODE_ACTIVE,
                 "交通工具火警-報案人身分", "請問您是車主或駕駛嗎？還是路人呢？"),
    FireQuestion("是否延燒", "spread_status", MODE_ACTIVE,
                 "交通工具火警-是否延燒", "火有沒有燒到旁邊的東西？"),
    FireQuestion("起火部位", "fire_origin_part", MODE_CONDITIONAL,
                 "交通工具火警-起火部位", "是車頭還是後車廂燒起來了呢？",
                 _subtype_is("汽車"), "交通工具＝汽車"),
    FireQuestion("起火車輛數量", "vehicle_count", MODE_CONDITIONAL,
                 "交通工具火警-起火車輛數量", "現場幾台在燒？",
                 _fire_visible, "火煙狀況 = 有火有煙、有火無煙"),
    FireQuestion("車輛是否已熄火", "engine_off_status", MODE_CONDITIONAL,
                 "交通工具火警-車輛是否已熄火", "車子熄火了嗎？",
                 _smoke_visible, "火煙狀況 = 有火有煙、無火有煙"),
    # 答「仍有人在車上」會立刻轉人工（跟有人受困一樣）
    FireQuestion("乘客下車狀況", "occupants_status", MODE_CONDITIONAL,
                 "交通工具火警-乘客下車狀況", "車上的人都下來了嗎？",
                 _subtype_is("汽車"), "交通工具＝汽車"),
    FireQuestion("有無人員受傷", "injury_status", MODE_CONDITIONAL,
                 "交通工具火警-有無人員受傷", "現場有沒有人受傷？",
                 _subtype_is("機車", "汽車"), "交通工具＝機車、汽車"),
    FireQuestion("載運物", "cargo", MODE_CONDITIONAL,
                 "交通工具火警-載運物", "車上有易燃物品之類的嗎？",
                 _hazmat_vehicle_or_truck, "交通工具＝化學、毒劑交通工具，或 車種=貨車"),
    FireQuestion("滅火狀況", "extinguish_status", MODE_CONDITIONAL,
                 "交通工具火警-滅火狀況", "現場有人在滅火嗎？",
                 _fire_visible, "火煙狀況 = 有火有煙、有火無煙"),
    FireQuestion("車輛停放或行駛中", "vehicle_motion", MODE_PASSIVE,
                 "交通工具火警-車輛停放或行駛中"),
    FireQuestion("車牌號碼", "plate_number", MODE_PASSIVE, "交通工具火警-車牌號碼"),
)

TAB_B2_QUESTIONS: Tuple[FireQuestion, ...] = (
    FireQuestion("山林火警", "sub_category", MODE_ACTIVE,
                 "山林田野火警-山林火警", "是山上還是路邊空地呢？"),
    FireQuestion("燃燒物", "burning_object", MODE_ACTIVE,
                 "山林田野火警-燃燒物", "是雜草、樹木，還是垃圾燒起來嗎？"),
    FireQuestion("火煙狀況", "fire_or_smoke", MODE_ACTIVE,
                 "山林田野火警-火煙狀況", "現在有看到火嗎？還是只有看到煙？"),
    FireQuestion("燃燒面積", "fire_extent", MODE_ACTIVE,
                 "山林田野火警-燃燒面積", "燒的範圍有一個籃球場那麼大嗎？"),
    FireQuestion("是否延燒", "spread_status", MODE_ACTIVE,
                 "山林田野火警-是否延燒", "火有沒有燒到旁邊的東西？"),
    FireQuestion("報案人身分", "caller_role", MODE_ACTIVE,
                 "山林田野火警-報案人身分", "請問您是住在附近，還是剛好經過？"),
    FireQuestion("滅火狀況", "extinguish_status", MODE_PASSIVE, "山林田野火警-滅火狀況"),
    FireQuestion("水源狀況", "nearby_water_source", MODE_PASSIVE, "山林田野火警-水源狀況"),
)

TAB_C_QUESTIONS: Tuple[FireQuestion, ...] = (
    FireQuestion("輕微火警", "sub_category", MODE_ACTIVE,
                 "輕微火警-輕微火警", "是警報器在響還是有人在燒垃圾？"),
    FireQuestion("警報器狀態", "alarm_status", MODE_CONDITIONAL,
                 "輕微火警-警報器狀態", "警報器現在還在響嗎？",
                 _subtype_is("警報器作響"), "輕微火警＝警報器作響"),
    FireQuestion("停電狀況", "power_outage", MODE_CONDITIONAL,
                 "輕微火警-停電狀況", "現在有停電嗎？",
                 _subtype_is("電線桿(電纜)"), "輕微火警＝電線桿(電纜)"),
    FireQuestion("火煙狀況", "fire_or_smoke", MODE_ACTIVE,
                 "輕微火警-火煙狀況", "現在有看到火嗎？還是只有看到煙？"),
    FireQuestion("氣味類型", "odor", MODE_CONDITIONAL,
                 "輕微火警-氣味類型", "現場有聞到燒焦味嗎？",
                 _no_fire_no_smoke, "火煙狀況 = 無火無煙"),
    FireQuestion("是否延燒", "spread_status", MODE_CONDITIONAL,
                 "輕微火警-是否延燒", "火有沒有燒到旁邊的東西？",
                 _fire_visible, "火煙狀況 = 有火有煙、有火無煙"),
    FireQuestion("報案人身分", "caller_role", MODE_ACTIVE,
                 "輕微火警-報案人身分", "請問您是住在附近，還是剛好經過？"),
    # 答「有人受困」會立刻轉人工（跟建築物火警一樣）
    FireQuestion("有無受困", "trapped_status", MODE_CONDITIONAL,
                 "輕微火警-有無受困", "有聽到有人在呼救嗎？",
                 _subtype_is("警報器作響", "查看案件"), "輕微火警＝警報器作響、查看案件"),
    FireQuestion("來源確認", "source_located", MODE_CONDITIONAL,
                 "輕微火警-來源確認", "知道是哪一戶、哪一層傳出來的嗎？",
                 _source_location_unknown,
                 "（氣味類型 ≠ 無　或　輕微火警＝警報器作響）＋ 地址沒有樓層 ＋ 地點型態 ≠ 地標"),
    FireQuestion("標的物", "target_object", MODE_PASSIVE, "輕微火警-標的物"),
    FireQuestion("無人應門或聯絡不上", "door_response", MODE_PASSIVE,
                 "輕微火警-無人應門或聯絡不上"),
    FireQuestion("燃燒範圍", "fire_extent", MODE_PASSIVE, "輕微火警-燃燒範圍"),
)

TAB_QUESTIONS: Dict[str, Tuple[FireQuestion, ...]] = {
    TAB_A: TAB_A_QUESTIONS,
    TAB_B1: TAB_B1_QUESTIONS,
    TAB_B2: TAB_B2_QUESTIONS,
    TAB_C: TAB_C_QUESTIONS,
}


# ─── 每一輪要請 LLM 抽取哪些火警欄位 ────────────────────────────────────────
# 只送這一輪用得到的欄位，避免把四張垂片的規則全部塞給 LLM（太長會超過模型上限）。
# 次案類代碼：報案人講出或更正次案類（例如「不是汽車，是機車」）時要抓得到。
# 舊流程「先分是不是建築物、再分交通山林或輕微」用的 fire_incident_type、non_building_fire
# 已不再抽取：現在由次案類決定垂片，不需要先分是不是建築物（欄位保留，不再填值）。
FIRE_IDENTITY_FIELDS: Tuple[str, ...] = (
    "building_type_code", "vehicle_wildfire_code", "minor_fire_code",
)
# 轉人工要看的欄位：不管在哪張垂片，報案人講出有人出不來都要立刻轉
FIRE_TRANSFER_FIELDS: Tuple[str, ...] = ("trapped_status", "occupants_status")
# 還不知道是哪張垂片時（報地址、案類分析），先抽四張垂片共用的欄位
FIRE_SHARED_FIELDS: Tuple[str, ...] = (
    "fire_or_smoke", "smoke_color", "spread_status", "caller_role", "odor", "fire_extent",
)


def fire_fields_to_extract(tab: Optional[str]) -> Tuple[str, ...]:
    """
    這一輪要請 LLM 抽取的火警欄位（依序、不重複）。
    - 已經知道垂片：次案類代碼 + 轉人工欄位 + 這張垂片 xlsx 上的所有欄位（含被動題）
    - 還不知道垂片：次案類代碼 + 轉人工欄位 + 四張垂片共用的欄位
    次案類名稱（sub_category）不請 LLM 直接填，由次案類代碼換算，所以不列入。
    """
    if tab in TAB_QUESTIONS:
        tab_fields = tuple(
            item.field for item in TAB_QUESTIONS[tab] if item.field != "sub_category"
        )
    else:
        tab_fields = FIRE_SHARED_FIELDS
    ordered = FIRE_IDENTITY_FIELDS + FIRE_TRANSFER_FIELDS + tab_fields
    return tuple(dict.fromkeys(ordered))


def sop_slots_for_tab(tab: Optional[str]) -> Tuple[str, ...]:
    """返回該垂片所有題目（含被動題）存答案的欄位。"""
    questions = TAB_QUESTIONS.get(tab or "", ())
    return tuple(item.field for item in questions)


def _clear_tab_exclusive_fields(case: Any, keep_tab: Optional[str]) -> None:
    """
    換垂片時只清掉「次案類代碼」，報案人已經回答過的內容全部保留、不重問。
    次案類代碼是用來決定走哪張垂片的（建築物類型、交通工具山林火警、輕微火警），
    換到新垂片後舊的次案類不再成立，所以要清掉；B1 / B2 共用同一個次案類代碼欄位，
    在 B1 與 B2 之間切換時不清。
    """
    for field in FIRE_IDENTITY_CODE_FIELDS:
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
    依次案類名稱寫入次案類代碼，並清掉其他垂片的次案類代碼。
    成功解析次案類則返回 True。
    （fire_incident_type、non_building_fire 已不再使用，不寫入。）
    """
    item = lookup_subtype(label)
    if item is None:
        return False
    _clear_tab_exclusive_fields(case, item.tab)
    if update_tab:
        case.fire_tab = item.tab
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
    "fire_incident_type": "建築物火警",  # 0＝是建築物火警、1＝不是
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
    # 垂片 A 照 0929 xlsx 重寫後使用的欄位（存文字）
    "sub_category": "次案類",  # 透天厝、機車、山林田野(平地)、垃圾…（決定走哪張垂片）
    "place_usage": "場所用途",
    "fire_or_smoke": "火煙狀況",
    "smoke_color": "濃煙顏色",
    "fire_floor": "起火樓層",
    "spread_status": "延燒可能",
    "trapped_status": "有無受困",
    "door_response": "應門狀況",  # A 起火戶應門、C 無人應門或聯絡不上共用
    "building_total_floors": "建物樓層",
    "caller_role": "報案人身分",
    "building_construction": "建物構造",
    "hazardous_materials": "危險物品",
    "odor": "氣味",
    "explosion_status": "有無爆炸",
    "access_info": "其他資訊",
    "fire_extent": "燃燒範圍",  # A 延燒面積、B2 燃燒面積、C 燃燒範圍共用
    # 垂片 B1（交通工具火警）
    "vehicle_type": "車種",
    "fire_origin_part": "起火部位",
    "vehicle_count": "起火車輛數量",
    "engine_off_status": "車輛是否已熄火",
    "occupants_status": "乘客下車狀況",
    "injury_status": "有無人員受傷",
    "cargo": "載運物",
    "extinguish_status": "滅火狀況",
    "vehicle_motion": "車輛停放或行駛中",
    "plate_number": "車牌號碼",
    # 垂片 B2（山林田野火警）
    "burning_object": "燃燒物",
    "nearby_water_source": "水源狀況",
    # 垂片 C（輕微火警）
    "alarm_status": "警報器狀態",
    "power_outage": "停電狀況",
    "source_located": "來源確認",
    "target_object": "標的物",
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

# 案類分析用的關鍵詞：報案人的回答只出現一種垂片的關鍵詞時，才決定是哪張垂片；
# 同時出現兩種以上（例如「房子旁邊的垃圾」）就不自己猜，交給 LLM 判斷。
# 不放單一個「車」字：「快叫消防車」「停車場」會被誤判成交通工具火警。
_TAB_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    TAB_A: (
        "房子", "房屋", "屋子", "住宅", "透天", "公寓", "大樓", "大楼",
        "建築", "建筑", "倉庫", "仓库", "工廠", "工厂", "廠房", "厂房",
        "旅館", "旅馆", "百貨", "商場", "學校", "学校", "醫院", "医院",
        "電影院", "电影院", "古蹟", "古迹", "地下街", "高層", "高层",
        "店面", "住家", "我家", "廚房", "厨房",
    ),
    TAB_B1: (
        "車子", "车子", "汽車", "汽车", "機車", "机车", "摩托車", "轎車",
        "貨車", "货车", "卡車", "公車", "小客車", "火車", "高鐵", "高铁",
        "槽車", "船", "飛機", "飞机", "航空器", "隧道",
    ),
    TAB_B2: (
        "山上", "山林", "山頭", "山坡", "山區", "雜草", "杂草", "草地",
        "草叢", "草皮", "芒草", "樹林", "树林", "竹林", "田裡", "田野",
        "農田", "空地", "荒地", "野外", "墳墓", "坟墓",
    ),
    TAB_C: (
        "垃圾", "電線桿", "电线杆", "電線", "电线", "電纜", "电缆", "瓦斯",
        "警報", "警报", "電箱", "變電箱", "電表", "水溝", "人孔",
    ),
}
# 報案人說「不是房子，是車子」時，要先把「不是房子」這一段拿掉再比對關鍵詞，
# 不然會同時比對到房子和車子。拿掉的範圍是從「不是／沒有」到下一個標點符號。
_NEGATED_SPAN_RE = re.compile(r"(不是|沒有|没有)[^，,。．！!？?\s]*")


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
    """次案類所屬的垂片，例如 機車 → B1。不是火警次案類就回傳 None。"""
    item = lookup_subtype(label)
    return item.tab if item else None


def subtype_name_for_code(field: str, value: Any) -> Optional[str]:
    """
    LLM 抽到的一個次案類代碼 → 次案類名稱，例如 vehicle_wildfire_code = 1 → 機車。
    代碼對不上任何次案類（例如建築物類型 00 未知）就回傳 None。
    """
    for item in FIRE_SUBTYPES:
        if field == "building_type_code":
            if item.building_type_code is not None and item.building_type_code == str(value).strip():
                return item.name
        elif field == "vehicle_wildfire_code":
            if item.vehicle_wildfire_code is not None and item.vehicle_wildfire_code == _as_int(value):
                return item.name
        elif field == "minor_fire_code":
            if item.minor_fire_code is not None and item.minor_fire_code == _as_int(value):
                return item.name
    return None


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


def infer_tab(text: str) -> Optional[str]:
    """
    用關鍵詞判斷報案人說的是哪張垂片，回傳 A、B1、B2 或 C。
    找不到任何關鍵詞，或同時出現兩種以上垂片的關鍵詞時，回傳 None（判斷不出來）。
    """
    t = _NEGATED_SPAN_RE.sub("", (text or "").strip())
    if not t:
        return None
    hits = [
        tab for tab, keywords in _TAB_KEYWORDS.items()
        if any(k in t for k in keywords)
    ]
    return hits[0] if len(hits) == 1 else None


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
    將 BERT 次案類寫入 case。
    fire_tab 已鎖定且 allow_tab_switch=False 時只更新該垂片內的次案類碼，不改路由。
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


def resolve_fire_tab(case: Any) -> Optional[str]:
    """
    目前應該走哪張垂片：已經決定就用已決定的；還沒決定但已知次案類，就用次案類所屬的垂片
    （次案類決定垂片）。都不知道就回傳 None。
    """
    tab = getattr(case, "fire_tab", None)
    if tab in TAB_QUESTIONS:
        return tab
    return tab_for_subtype(getattr(case, "sub_category", None))
