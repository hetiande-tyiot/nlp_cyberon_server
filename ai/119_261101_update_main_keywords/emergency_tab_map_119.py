"""emergency_tab_map_119.py — 緊急救援垂片題目表。

規格：docs/(all)緊急救援垂片規格_關鍵要素與問句_1106.xlsx，使用者 11/06 決定照這份改。
九張表都照表問，包括還沒標 OK 的 310 瓦斯漏氣(建築物)。

寫法跟救護題目表（ems_tab_map_119）、災害題目表（disaster_flow_119）一樣，每一題記下 xlsx 的
「問法分類」與「前置條件」：
  主動：還不知道才問（報案人前面已經講過就跳過）
  條件：前置條件確定成立、而且還不知道才問；答案還不知道的條件一律當作不成立
  被動：AI 不主動問，報案人自己講到時由每一輪的欄位抽取記下來
題目的順序就是 xlsx 的順序。年齡在 xlsx 沒有問句、前置條件空白：上一題性別的問句同時問性別和年齡，
所以年齡跟性別同一句問、用同一個前置條件（跟救護一樣）。

一個關鍵要素一個欄位：名稱跟別的垂片一字不差、參考範圍也一樣，就共用欄位（11/04、11/06 使用者決定），
共用哪些見下面的 EMERGENCY_SHARED_FIELDS。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from fire_tab_map_119 import (
    FIRE_SMOKE_FIRE_OR_SMOKE_VISIBLE,
    MODE_ACTIVE,
    MODE_CONDITIONAL,
    MODE_PASSIVE,
    TAB_A,
    TAB_B1,
    TRAPPED_YES,
    FireQuestion as EmergencyQuestion,
)

# 次案類名稱（照系統案類）
CRASH = "車禍救助"
DROWN = "溺水"
DIVE = "跳水"
FALL = "跳樓"
MOUNTAIN = "山難"
TRAPPED = "其他"            # 309-其他：xlsx 只分析了內容是卡住、夾住的通話
TRAPPED_ALIAS = "其他(卡住夾住)"
GAS = "瓦斯漏氣(建築物)"
LIFT = "電梯受困"
DOOR = "破門"

DISPATCH_LINE = "救護人員已經派出了歐。"
# 次案類還判不出來時，分兩次問（使用者 11/05 給的句子）。兩句都問完還是判不出來，就直接問姓名電話。
INCIDENT_QUESTION = "請描述發生什麼事需要救援？"
INCIDENT_REASK_QUESTION = "是有人受傷，還是有人困住出不來嗎？"

# 條件會用到的固定說法。抽取規則（見下面的 EMERGENCY_FIELD_RULES）要求遇到對應情況時一定記成這幾個字。
RELATION_SELF = "本人"
RELATION_FAMILY = "家人"
RELATION_FRIEND = "朋友"
LOCATION_ON_SCENE = "在現場"
CONSCIOUSNESS_UNRESPONSIVE = "沒有反應"
INJURY_NONE = "無"
DROWNING_IN_WATER = "還在水裡"
DROWNING_NOT_VISIBLE = "看不到人"
DIVE_JUMPED = "已跳下"
FALL_NOT_YET = "尚未跳下"
MOUNTAIN_INJURED = "受傷"

# 火煙狀況是有火有煙、有火無煙、無火有煙 → 改判火警（xlsx 備註，使用者 11/05 決定；只有火花、不確定都不改判）。
# 車禍救助轉交通工具火警（垂片 B1），瓦斯漏氣轉建築物火警（垂片 A）。
FIRE_SWITCH_TABS: Dict[str, str] = {CRASH: TAB_B1, GAS: TAB_A}

# 性別、年齡只答到一個時的補問句（使用者 11/05 決定）。整句用「患者」的表沿用救護的單問句
#（handlers/base.py 的 SINGLE_MISSING_QUESTIONS）；整句用「當事人」的表用下面這兩句。
PARTY_SINGLE_MISSING_QUESTIONS = {
    "patient_gender": "請問當事人是男生還是女生？",
    "patient_age": "請問當事人大概幾歲？",
}
PARTY_SUBS = frozenset({MOUNTAIN, TRAPPED, TRAPPED_ALIAS, DOOR})


# ─── 前置條件 ─────────────────────────────────────────────────────────────────

def _on_scene_or_not_mentioned(case: Any) -> bool:
    """報案人位置 = 未提到、在現場。"""
    return not case.caller_location or case.caller_location == LOCATION_ON_SCENE


def _not_self(case: Any) -> bool:
    """報案身分 ≠ 本人：一定要已經問出報案身分，而且不是本人。"""
    return bool(case.caller_relation) and case.caller_relation != RELATION_SELF


def _on_scene_or_family_friend(case: Any) -> bool:
    """報案人位置 = 未提到、在現場，或報案身分 = 家人、朋友。"""
    return _on_scene_or_not_mentioned(case) or case.caller_relation in (RELATION_FAMILY, RELATION_FRIEND)


def _not_self_on_scene_or_not_mentioned(case: Any) -> bool:
    """報案身分 ≠ 本人，且報案人位置 = 未提到、在現場。"""
    return _not_self(case) and _on_scene_or_not_mentioned(case)


def _unresponsive(case: Any) -> bool:
    """意識 = 沒有反應。"""
    return case.consciousness_level == CONSCIOUSNESS_UNRESPONSIVE


def _injured_or_trapped(case: Any) -> bool:
    """受傷部位 ≠ 無，或人員受困 = 有人受困。受傷部位要已經問出來而且不是無。"""
    injured = bool(case.injury_location) and case.injury_location != INJURY_NONE
    return injured or case.trapped_status == TRAPPED_YES


def _person_visible(case: Any) -> bool:
    """（報案身分 ≠ 本人，或報案人位置 = 未提到、在現場），且溺水狀況 ≠ 看不到人。
    溺水狀況要已經問出來而且不是看不到人。"""
    status = case.drowning_status
    return (
        (_not_self(case) or _on_scene_or_not_mentioned(case))
        and bool(status) and status != DROWNING_NOT_VISIBLE
    )


def _dive_jumped_on_scene(case: Any) -> bool:
    """跳水狀況 = 已跳下，且報案人位置 = 未提到、在現場。"""
    return case.dive_status == DIVE_JUMPED and _on_scene_or_not_mentioned(case)


def _in_water(case: Any) -> bool:
    """溺水狀況 = 還在水裡。"""
    return case.drowning_status == DROWNING_IN_WATER


def _fall_not_yet(case: Any) -> bool:
    """墜落狀況 = 尚未跳下。"""
    return case.fall_status == FALL_NOT_YET


def _mountain_injured(case: Any) -> bool:
    """山難原因 = 受傷。"""
    return case.mountain_cause == MOUNTAIN_INJURED


def _self_or_on_scene(case: Any) -> bool:
    """報案身分 = 本人，或報案人位置 = 在現場。"""
    return case.caller_relation == RELATION_SELF or case.caller_location == LOCATION_ON_SCENE


_ON_SCENE_TEXT = "報案人位置 = 未提到、在現場"
_GENDER_AGE_TEXT = "報案人位置 = 未提到、在現場 或 報案身分 = 家人、朋友"
_CONSCIOUSNESS_TEXT = "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"
_VISIBLE_TEXT = "(報案身分 ≠ 本人 或 報案人位置 = 未提到、在現場) 且 溺水狀況 ≠ 看不到人"
_UNRESPONSIVE_TEXT = "意識 = 沒有反應"
_BREATHING_QUESTION = "他還有沒有呼吸？胸部有沒有一上一下起伏呢？"


def _gender_age(sub: str, question: str) -> Tuple[EmergencyQuestion, ...]:
    """性別、年齡兩題：年齡沒有問句，跟性別同一句問、用同一個前置條件。"""
    return (
        EmergencyQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                          f"緊急救援-{sub}-性別", question,
                          _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmergencyQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                          f"緊急救援-{sub}-年齡", "",
                          _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    )


def _breathing(sub: str) -> EmergencyQuestion:
    return EmergencyQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                             f"緊急救援-{sub}-呼吸", _BREATHING_QUESTION,
                             _unresponsive, _UNRESPONSIVE_TEXT)


def _caller_location(sub: str) -> EmergencyQuestion:
    return EmergencyQuestion("報案人位置", "caller_location", MODE_PASSIVE, f"緊急救援-{sub}-報案人位置")


# ─── 題目表（順序照 xlsx）──────────────────────────────────────────────────────
# 301-車禍救助：意識的前置條件要看報案身分，但報案身分排在第 9 題；報案人前面沒講到身分時，
# 輪到意識那一題條件還不成立，就不問（照 xlsx 順序，使用者沒決定前不調換）。

CRASH_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("事故車種", "crash_vehicles", MODE_ACTIVE,
                      "緊急救援-車禍救助-事故車種", "請問是什麼車跟什麼車的車禍？"),
    EmergencyQuestion("受傷部位", "injury_location", MODE_CONDITIONAL,
                      "緊急救援-車禍救助-受傷部位", "傷到哪裡？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("傷勢", "injury_severity", MODE_CONDITIONAL,
                      "緊急救援-車禍救助-傷勢", "傷得嚴不嚴重？有沒有一直流血？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("人員受困", "trapped_status", MODE_CONDITIONAL,
                      "緊急救援-車禍救助-人員受困", "有沒有人被困在車裡出不來？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("患者人數", "patient_count", MODE_CONDITIONAL,
                      "緊急救援-車禍救助-患者人數", "有幾個人受傷？幾個人受困？",
                      _injured_or_trapped, "受傷部位 ≠ 無 或 人員受困 = 有人受困"),
    EmergencyQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                      "緊急救援-車禍救助-意識", "當事人有清醒嗎？",
                      _not_self_on_scene_or_not_mentioned, _CONSCIOUSNESS_TEXT),
    _breathing(CRASH),
    EmergencyQuestion("火煙狀況", "fire_or_smoke", MODE_CONDITIONAL,
                      "緊急救援-車禍救助-火煙狀況", "車子有沒有冒煙或起火？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-車禍救助-報案身分", "請問是當事人還是路人代報？"),
    EmergencyQuestion("交通影響", "traffic_impact", MODE_ACTIVE,
                      "緊急救援-車禍救助-交通影響", "有擋到路嗎？車子還過得去嗎？"),
    _caller_location(CRASH),
)

DROWN_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("溺水原因", "drowning_cause", MODE_ACTIVE,
                      "緊急救援-溺水-溺水原因", "請問是怎麼落水的？"),
    EmergencyQuestion("患者人數", "patient_count", MODE_ACTIVE,
                      "緊急救援-溺水-患者人數", "有幾個人落水？"),
    EmergencyQuestion("溺水狀況", "drowning_status", MODE_CONDITIONAL,
                      "緊急救援-溺水-溺水狀況", "還有看到人嗎？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("離岸距離", "drown_distance", MODE_CONDITIONAL,
                      "緊急救援-溺水-離岸距離", "離岸邊大概多遠？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("救生裝備", "drown_flotation", MODE_CONDITIONAL,
                      "緊急救援-溺水-救生裝備", "對方有穿救生衣或泳圈嗎？",
                      _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-溺水-報案身分", "請問是家屬朋友還是路人代報呢？"),
    *_gender_age(DROWN, "請問患者是男生還是女生？大概幾歲？"),
    EmergencyQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                      "緊急救援-溺水-意識", "對方還會動嗎？",
                      _person_visible, _VISIBLE_TEXT),
    _breathing(DROWN),
    EmergencyQuestion("外觀特徵", "patient_appearance", MODE_CONDITIONAL,
                      "緊急救援-溺水-外觀特徵", "他穿什麼顏色的衣服？",
                      _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    EmergencyQuestion("團體帶隊", "drown_group", MODE_PASSIVE, "緊急救援-溺水-團體帶隊"),
    _caller_location(DROWN),
)

DIVE_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("跳水狀況", "dive_status", MODE_ACTIVE,
                      "緊急救援-跳水-跳水狀況", "對方已經跳下去了嗎？"),
    EmergencyQuestion("溺水狀況", "drowning_status", MODE_CONDITIONAL,
                      "緊急救援-跳水-溺水狀況", "還看得到患者嗎？",
                      _dive_jumped_on_scene, "跳水狀況 = 已跳下 且 報案人位置 = 未提到、在現場"),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-跳水-報案身分", "請問是家屬朋友還是路人代報呢？"),
    *_gender_age(DIVE, "請問患者是男生還是女生？大概幾歲？"),
    EmergencyQuestion("外觀特徵", "patient_appearance", MODE_CONDITIONAL,
                      "緊急救援-跳水-外觀特徵", "他穿什麼顏色的衣服？",
                      _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    EmergencyQuestion("患者人數", "patient_count", MODE_CONDITIONAL,
                      "緊急救援-跳水-患者人數", "有幾個人呢？",
                      _in_water, "溺水狀況 = 還在水裡"),
    EmergencyQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                      "緊急救援-跳水-意識", "人還會動嗎？",
                      _person_visible, _VISIBLE_TEXT),
    _breathing(DIVE),
    _caller_location(DIVE),
)

FALL_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("墜落狀況", "fall_status", MODE_ACTIVE,
                      "緊急救援-跳樓-墜落狀況", "人還在上面嗎？還是跳下來了？"),
    EmergencyQuestion("輕生意圖", "fall_intent", MODE_CONDITIONAL,
                      "緊急救援-跳樓-輕生意圖", "他是要自殺嗎？",
                      _fall_not_yet, "墜落狀況 = 尚未跳下"),
    EmergencyQuestion("所在樓層", "fall_floor", MODE_ACTIVE,
                      "緊急救援-跳樓-所在樓層", "現在在幾樓？"),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-跳樓-報案身分", "請問是家屬朋友還是路人代報呢？"),
    *_gender_age(FALL, "請問患者是男生還是女生？大概幾歲？"),
    _caller_location(FALL),
)

MOUNTAIN_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("山難原因", "mountain_cause", MODE_ACTIVE,
                      "緊急救援-山難-山難原因", "請問發生什麼事？是迷路還是受傷？"),
    EmergencyQuestion("受傷部位", "injury_location", MODE_CONDITIONAL,
                      "緊急救援-山難-受傷部位", "傷到哪裡？",
                      _mountain_injured, "山難原因 = 受傷"),
    EmergencyQuestion("傷勢", "injury_severity", MODE_CONDITIONAL,
                      "緊急救援-山難-傷勢", "傷得嚴不嚴重？有沒有一直流血？",
                      _mountain_injured, "山難原因 = 受傷"),
    EmergencyQuestion("患者人數", "patient_count", MODE_ACTIVE,
                      "緊急救援-山難-患者人數", "你們總共幾個人？"),
    EmergencyQuestion("位置座標", "mountain_location", MODE_ACTIVE,
                      "緊急救援-山難-位置座標", "您現在在哪裡？手機可以看到座標嗎？"),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-山難-報案身分", "請問是本人還是家屬朋友代報？"),
    *_gender_age(MOUNTAIN, "請問當事人是男生還是女生？大概幾歲？"),
    EmergencyQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                      "緊急救援-山難-意識", "現在人是清醒的嗎？",
                      _not_self_on_scene_or_not_mentioned, _CONSCIOUSNESS_TEXT),
    _breathing(MOUNTAIN),
    EmergencyQuestion("入山資訊", "mountain_entry", MODE_ACTIVE,
                      "緊急救援-山難-入山資訊", "幾點上山的？從哪裡上去的？"),
    EmergencyQuestion("登山路線", "mountain_route", MODE_ACTIVE,
                      "緊急救援-山難-登山路線", "你們走哪一條路線？最後經過什麼地標？"),
    EmergencyQuestion("隨身物資", "mountain_supplies", MODE_CONDITIONAL,
                      "緊急救援-山難-隨身物資", "身上的水、食物、保暖衣物夠嗎？有手電筒或哨子嗎？",
                      _self_or_on_scene, "報案身分 = 本人 或 報案人位置 = 在現場"),
    EmergencyQuestion("團體帶隊", "drown_group", MODE_PASSIVE, "緊急救援-山難-團體帶隊"),
    _caller_location(MOUNTAIN),
)

TRAPPED_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("卡住部位", "trap_body_part", MODE_CONDITIONAL,
                      "緊急救援-卡住夾住-卡住部位", "哪裡卡住了？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("卡住物品", "trap_object", MODE_CONDITIONAL,
                      "緊急救援-卡住夾住-卡住物品", "卡在什麼東西裡面？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("是否脫困", "trap_freed", MODE_CONDITIONAL,
                      "緊急救援-卡住夾住-是否脫困", "現在還卡著嗎？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("受傷部位", "injury_location", MODE_CONDITIONAL,
                      "緊急救援-卡住夾住-受傷部位", "傷到哪裡？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("傷勢", "injury_severity", MODE_CONDITIONAL,
                      "緊急救援-卡住夾住-傷勢", "傷得嚴不嚴重？有沒有一直流血？",
                      _on_scene_or_not_mentioned, _ON_SCENE_TEXT),
    EmergencyQuestion("發生場所", "injury_place", MODE_ACTIVE,
                      "緊急救援-卡住夾住-發生場所", "是在家裡還是工作的地方？"),
    *_gender_age("卡住夾住", "請問當事人是男生還是女生？大概幾歲？"),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-卡住夾住-報案身分", "請問是當事人還是家屬朋友代報？"),
    EmergencyQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                      "緊急救援-卡住夾住-意識", "人是清醒的嗎？",
                      _not_self_on_scene_or_not_mentioned, _CONSCIOUSNESS_TEXT),
    _breathing("卡住夾住"),
    _caller_location("卡住夾住"),
)

# 310 還沒標 OK，使用者 11/05 決定一樣照表問。身體不適跟電梯受困共用一格（名稱一樣）。
GAS_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("場所用途", "place_usage", MODE_ACTIVE,
                      "緊急救援-瓦斯漏氣-場所用途", "那裡是住家還是店家呢？"),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-瓦斯漏氣-報案身分", "請問您是住在附近，還是路人？"),
    EmergencyQuestion("火煙狀況", "fire_or_smoke", MODE_ACTIVE,
                      "緊急救援-瓦斯漏氣-火煙狀況", "有看到明顯的火或煙嗎？"),
    EmergencyQuestion("聞到位置", "gas_smell_place", MODE_ACTIVE,
                      "緊急救援-瓦斯漏氣-聞到位置", "是在家裡面聞到，還是外面？"),
    EmergencyQuestion("味道濃淡", "gas_smell_strength", MODE_ACTIVE,
                      "緊急救援-瓦斯漏氣-味道濃淡", "味道很濃嗎？"),
    EmergencyQuestion("瓦斯種類", "gas_type", MODE_ACTIVE,
                      "緊急救援-瓦斯漏氣-瓦斯種類", "是用天然氣，還是瓦斯桶？"),
    EmergencyQuestion("鄰接建物", "gas_adjacent", MODE_PASSIVE, "緊急救援-瓦斯漏氣-鄰接建物"),
    EmergencyQuestion("身體不適", "gas_discomfort", MODE_PASSIVE, "緊急救援-瓦斯漏氣-身體不適"),
    _caller_location("瓦斯漏氣"),
)

# 意識的前置條件要看報案身分，但報案身分排在第 8 題（同車禍救助的說明）。
LIFT_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("社區棟別", "lift_building", MODE_ACTIVE,
                      "緊急救援-電梯受困-社區棟別", "是哪個社區？哪一棟、哪一部電梯？"),
    EmergencyQuestion("受困樓層", "lift_floor", MODE_ACTIVE,
                      "緊急救援-電梯受困-受困樓層", "電梯現在停在幾樓？"),
    EmergencyQuestion("受困人數", "lift_count", MODE_ACTIVE,
                      "緊急救援-電梯受困-受困人數", "裡面有幾個人？"),
    EmergencyQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                      "緊急救援-電梯受困-意識", "裡面的人都清醒嗎？",
                      _not_self_on_scene_or_not_mentioned, _CONSCIOUSNESS_TEXT),
    _breathing(LIFT),
    EmergencyQuestion("身體不適", "gas_discomfort", MODE_PASSIVE, "緊急救援-電梯受困-身體不適"),
    EmergencyQuestion("電梯公司", "lift_company", MODE_ACTIVE,
                      "緊急救援-電梯受困-電梯公司", "有聯絡電梯公司了嗎？"),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-電梯受困-報案身分", "請問是本人嗎？還是管理員或警衛？"),
    _caller_location(LIFT),
)

# 有無回應的前置條件要看報案身分，但報案身分排在第 3 題（同車禍救助的說明）。
DOOR_QUESTIONS: Tuple[EmergencyQuestion, ...] = (
    EmergencyQuestion("擔心原因", "door_reason", MODE_ACTIVE,
                      "緊急救援-破門-擔心原因", "發生什麼事需要破門？"),
    EmergencyQuestion("有無回應", "knock_response", MODE_CONDITIONAL,
                      "緊急救援-破門-有無回應", "敲門或打電話，會有回應嗎？",
                      _not_self, "報案身分 ≠ 本人"),
    EmergencyQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                      "緊急救援-破門-報案身分", "請問是當事人還是家屬朋友代報？"),
    *_gender_age(DOOR, "請問當事人是男生還是女生？大概幾歲？"),
    EmergencyQuestion("門的種類", "door_kind", MODE_ACTIVE,
                      "緊急救援-破門-門的種類", "是大門還是房間的門？"),
    EmergencyQuestion("鑰匙鎖匠", "door_locksmith", MODE_ACTIVE,
                      "緊急救援-破門-鑰匙鎖匠", "有沒有鑰匙？找過鎖匠嗎？"),
    EmergencyQuestion("同意破門", "door_consent", MODE_ACTIVE,
                      "緊急救援-破門-同意破門", "我們破門會把門弄壞，家屬或屋主同意嗎？"),
    _caller_location(DOOR),
)

EMERGENCY_QUESTIONS: Dict[str, Tuple[EmergencyQuestion, ...]] = {
    CRASH: CRASH_QUESTIONS,
    DROWN: DROWN_QUESTIONS,
    DIVE: DIVE_QUESTIONS,
    FALL: FALL_QUESTIONS,
    MOUNTAIN: MOUNTAIN_QUESTIONS,
    TRAPPED: TRAPPED_QUESTIONS,
    TRAPPED_ALIAS: TRAPPED_QUESTIONS,
    GAS: GAS_QUESTIONS,
    LIFT: LIFT_QUESTIONS,
    DOOR: DOOR_QUESTIONS,
}


def questions_for_subtype(sub_category: Optional[str]) -> Tuple[EmergencyQuestion, ...]:
    """這個緊急救援次案類的題目表；判不出次案類或沒有表的回傳空的。"""
    return EMERGENCY_QUESTIONS.get(sub_category or "", ())


def should_switch_to_fire(case: Any) -> Optional[str]:
    """車禍救助、瓦斯漏氣的火煙狀況看得到火或煙時，回傳要轉去的火警垂片；不用轉回傳 None。"""
    tab = FIRE_SWITCH_TABS.get(case.sub_category or "")
    if tab and case.fire_or_smoke in FIRE_SMOKE_FIRE_OR_SMOKE_VISIBLE:
        return tab
    return None


# ─── 欄位 ─────────────────────────────────────────────────────────────────────

# 跟別的垂片名稱一字不差、參考範圍也一樣，共用的欄位。主類是緊急救援時也可以寫入；
# 切大類時新大類也用到就保留（例如救護改判緊急救援，前面問到的報案身分不用重問）。
EMERGENCY_SHARED_FIELDS = frozenset({
    # 救護
    "caller_relation", "caller_location", "patient_gender", "patient_age", "patient_count",
    "injury_location", "injury_severity", "crash_vehicles", "injury_place",
    "consciousness_level", "breathing", "drowning_cause", "drowning_status", "fall_status",
    "patient_appearance",
    # 火警
    "trapped_status", "fire_or_smoke", "place_usage",
    # 災害
    "traffic_impact",
})

# 題目表用到的欄位，加上判次案類用的「發生什麼事」
_ALL_FIELDS: Tuple[str, ...] = tuple(dict.fromkeys(
    item.field for questions in EMERGENCY_QUESTIONS.values() for item in questions
))
# 緊急救援自己的欄位。切離緊急救援時清空。
EMERGENCY_OWN_FIELDS = frozenset(_ALL_FIELDS) - EMERGENCY_SHARED_FIELDS

# 呼吸的參考範圍（救護、緊急救援 xlsx 一樣，共用 breathing 這一格）。抽取後只收這四種文字。
BREATHING_OPTIONS: Tuple[str, ...] = ("未知", "有呼吸", "呼吸不正常", "無呼吸")

# xlsx 寫「只能填」的欄位：抽到選項以外的說法就不記（見 llm_extractor_119），
# 不然前置條件比對不到（例如寫成「已經跳下」，「跳水狀況 = 已跳下」就不成立，後面該問的題都不問）。
# 意識、性別、溺水狀況、墜落狀況跟救護共用，救護 xlsx 的參考範圍一樣。
EMERGENCY_FIXED_ANSWERS: Dict[str, Tuple[str, ...]] = {
    "consciousness_level": ("清醒", "迷迷糊糊", "沒有反應", "未知"),
    "patient_gender": ("男性", "女性"),
    "drowning_status": (DROWNING_IN_WATER, DROWNING_NOT_VISIBLE, "已拉上岸"),
    "fall_status": (FALL_NOT_YET, "已跳下", "卡住", "已勸導離開"),
    "dive_status": (FALL_NOT_YET, DIVE_JUMPED, "已勸導離開"),
    "drown_flotation": ("有", "沒有"),
    "trap_freed": ("還卡著", "已經出來了"),
    "gas_smell_strength": ("很濃", "淡淡的", "一陣一陣"),
    "gas_type": ("天然氣", "瓦斯桶"),
    "gas_discomfort": ("有", "沒有", "不知道"),
    "lift_company": ("已經聯絡", "還沒聯絡"),
    "knock_response": ("有回應", "沒有回應", "有聲音但叫不應"),
    "door_kind": ("大門", "房門", "浴室門", "鐵門"),
    "door_locksmith": ("有鑰匙但打不開", "沒有鑰匙", "已找鎖匠"),
    "door_consent": ("同意", "不同意", "家屬或屋主還沒到"),
}

# 換次案類時留著：講的是同一個人、同一通電話，跟哪一個次案類無關。
EMERGENCY_KEEP_SLOTS: Tuple[str, ...] = (
    "incident_description", "caller_relation", "caller_location",
    "patient_gender", "patient_age", "consciousness_level", "breathing",
)


def emergency_slots_for(sub_category: Optional[str]) -> Tuple[str, ...]:
    """這個次案類會用到的欄位（含被動題），再加上換次案類時要留住的欄位。"""
    fields = tuple(item.field for item in questions_for_subtype(sub_category))
    return tuple(dict.fromkeys((*fields, *EMERGENCY_KEEP_SLOTS)))


# ─── 抽取規則 ─────────────────────────────────────────────────────────────────
# 照 1106 xlsx 的參考範圍。寫「只能填」的會拿來判斷要不要問下一題或改判，只能記成固定說法；
# 跟救護共用的欄位用救護同樣的說法，同一格才不會出現兩套說法。
# 火煙狀況、人員受困、場所用途用火警的抽取規則，在 llm_extractor_119 併進來。

EMERGENCY_FIRE_RULE_FIELDS = ("fire_or_smoke", "trapped_status", "place_usage")

EMERGENCY_FIELD_RULES: Dict[str, Tuple[str, str]] = {
    "incident_description": (
        "string|null",
        "- incident_description：發生的事件、現場狀況或需要救援的原因，使用最短且完整的描述。",
    ),
    "caller_relation": (
        "string|null",
        "- caller_relation 報案身分：報案人和當事人的關係，只能填這幾種之一："
        "本人、家人、朋友、同事、老闆、房東、110、里長、鄰居、工人、工地主任、路過、看護、管理室、"
        "警衛(保全)、不認識。"
        "報案人講自己的狀況就是本人（我受傷、我被困住、我卡住了、我們迷路了、我遇到山難）；"
        "爸媽、兄弟姊妹、先生太太、老公老婆、子女等親屬 → 家人（我媽、我爸、我妹妹）；"
        "我朋友 → 朋友；我同事 → 同事；我鄰居 → 鄰居；警衛、保全 → 警衛(保全)；"
        "路人、經過看到 → 路過。沒講到 → null。",
    ),
    "caller_location": (
        "string|null",
        "- caller_location 報案人位置：報案人現在在哪裡，只能填這幾種之一："
        "在現場、在遠處、不敢靠近、不在現場。在當事人身邊也算在現場。"
        "地址、路名不是報案人位置，不要填在這裡。沒講到 → null。",
    ),
    "patient_gender": (
        "男性|女性|null",
        "- patient_gender 性別：當事人性別，只能填 男性 或 女性"
        "（男生、男的、一位先生、阿公 → 男性；女生、女的、一位小姐、阿嬤 → 女性）。"
        "「我是先生／小姐」講的是報案人自己，報案人不是當事人時不填。沒講到 → null。",
    ),
    "patient_age": (
        "string|null",
        "- patient_age 年齡：當事人年齡（例：75歲左右 → 75歲）；未滿一歲記月份（例：3個月）。沒講到 → null。",
    ),
    "consciousness_level": (
        "string|null",
        "- consciousness_level 意識：當事人意識，只能填這幾種之一："
        "清醒（清醒、醒著、會講話、會回答、會動）；"
        "迷迷糊糊（意識不清、昏昏沉沉、講話不清楚、叫了才有反應、要捏才有反應）；"
        "沒有反應（沒反應、叫不醒、叫不起來、昏迷、不省人事）；"
        "未知（不知道、看不到、不敢靠近）。"
        "「人不清楚」記迷迷糊糊，「我不清楚」記未知。沒講到意識 → null。",
    ),
    "breathing": (
        "未知|有呼吸|呼吸不正常|無呼吸|null",
        "- breathing 呼吸：當事人呼吸，只能填這幾種之一："
        "未知（不知道、看不到）；"
        "有呼吸（有呼吸、還在呼吸、會呼吸、正常呼吸、胸口或肚子有起伏）；"
        "呼吸不正常；"
        "無呼吸（沒有呼吸、停止呼吸、呼吸停止、沒在呼吸、胸口肚子沒有起伏）。沒講到 → null。",
    ),
    "crash_vehicles": (
        "string|null",
        "- crash_vehicles 事故車種：車禍是什麼車跟什麼車，照報案人說的記（例：汽車撞機車、機車自摔、車撞行人）；"
        "沒講到 → null。",
    ),
    "injury_location": (
        "string|null",
        "- injury_location 受傷部位：只填身體受傷的位置，照報案人說的記（例：頭、臉、手、腳、腰、背）；"
        "明確說沒有人受傷 → 無。「在右邊那一棟／那邊／對面」是事發地點，必須 null。沒講到 → null。",
    ),
    "injury_severity": (
        "string|null",
        "- injury_severity 傷勢：照報案人說的記（例：流血、骨折、擦傷、傷得重不重）。沒講到 → null。",
    ),
    "drowning_cause": (
        "string|null",
        "- drowning_cause 溺水原因：怎麼落水的，照報案人說的記（例：戲水、釣魚、失足落水、游泳抽筋、翻船）。"
        "沒講到 → null。",
    ),
    "drowning_status": (
        "還在水裡|看不到人|已拉上岸|null",
        "- drowning_status 溺水狀況：落水的人現在怎樣，只能填：還在水裡、看不到人、已拉上岸。沒講到 → null。",
    ),
    "fall_status": (
        "尚未跳下|已跳下|卡住|已勸導離開|null",
        "- fall_status 墜落狀況：要跳樓的人是不是已經掉下來，只能填：尚未跳下、已跳下、卡住、已勸導離開。"
        "還在高處是尚未跳下；已經掉下來也算已跳下；跳下來卡住記卡住。沒講到 → null。",
    ),
    "patient_appearance": (
        "string|null",
        "- patient_appearance 外觀特徵：當事人的外觀，讓救援人員到現場認得出來，照報案人說的記"
        "（常見：衣服顏色、救生衣顏色）。沒講到 → null。",
    ),
    "injury_place": (
        "string|null",
        "- injury_place 發生場所：在什麼地方發生，照報案人說的記（常見：住家、工廠、店家）。沒講到 → null。",
    ),
    "traffic_impact": (
        "未影響交通|佔用部分車道|完全無法通行|null",
        "- traffic_impact 交通影響（固定說法）：只能填 未影響交通、佔用部分車道、完全無法通行。"
        "沒擋到、車子照過 → 未影響交通；擋到一部分、還過得去、佔用車道 → 佔用部分車道；"
        "車子過不去、路斷了、完全擋住 → 完全無法通行。只說不知道 → null。",
    ),
    "drown_distance": (
        "string|null",
        "- drown_distance 離岸距離：落水的人離岸邊多遠，照報案人說的記。沒講到 → null。",
    ),
    "drown_flotation": (
        "有|沒有|null",
        "- drown_flotation 救生裝備：落水的人有沒有穿救生衣或泳圈，只能填：有、沒有。沒講到 → null。",
    ),
    "drown_group": (
        "string|null",
        "- drown_group 團體帶隊：是自己來還是跟團體一起、有沒有帶隊的人，"
        "參考 個人、公司、社團（記下名稱、帶隊者資料）。沒講到 → null。",
    ),
    "dive_status": (
        "尚未跳下|已跳下|已勸導離開|null",
        "- dive_status 跳水狀況：要跳水的人跳下去了沒，只能填：尚未跳下、已跳下、已勸導離開。"
        "還在橋上、在欄杆外是尚未跳下。沒講到 → null。",
    ),
    "fall_intent": (
        "string|null",
        "- fall_intent 輕生意圖：照報案人說的記（常見：說要跳、說要自殺）。沒講到 → null。",
    ),
    "fall_floor": (
        "string|null",
        "- fall_floor 所在樓層：要跳樓的人現在在幾樓，照報案人說的記（例：5樓、頂樓）。沒講到 → null。",
    ),
    "mountain_cause": (
        "string|null",
        "- mountain_cause 山難原因：照報案人說的記，常見：迷路、受傷、身體不舒服、失聯沒下山；"
        "扭到、跌倒、摔傷都記「受傷」。沒講到 → null。",
    ),
    "mountain_location": (
        "string|null",
        "- mountain_location 位置座標：現場正確地點、GPS 座標、路燈、電桿、電塔等編號，照報案人說的記。"
        "沒講到 → null。",
    ),
    "mountain_entry": (
        "string|null",
        "- mountain_entry 入山資訊：幾點幾分上山、從哪裡入山、預計幾點下山、從哪裡下山，照報案人說的記。"
        "沒講到 → null。",
    ),
    "mountain_route": (
        "string|null",
        "- mountain_route 登山路線：登山目的、入山多久、路上有什麼標示、經過什麼地標多久，照報案人說的記。"
        "沒講到 → null。",
    ),
    "mountain_supplies": (
        "string|null",
        "- mountain_supplies 隨身物資：食物、飲水、保暖衣物夠不夠，有沒有手電筒或哨子，照報案人說的記。"
        "沒講到 → null。",
    ),
    "trap_body_part": (
        "string|null",
        "- trap_body_part 卡住部位：身體哪裡卡住，照報案人說的記（常見：手指、手、腳）。沒講到 → null。",
    ),
    "trap_object": (
        "string|null",
        "- trap_object 卡住物品：卡在什麼東西裡面，照報案人說的記"
        "（常見：椅子、門、機器、夾娃娃機、嬰兒床、戒指）。沒講到 → null。",
    ),
    "trap_freed": (
        "還卡著|已經出來了|null",
        "- trap_freed 是否脫困：只能填：還卡著、已經出來了。沒講到 → null。",
    ),
    "gas_smell_place": (
        "string|null",
        "- gas_smell_place 聞到位置：在哪裡聞到瓦斯味，照報案人說的記（常見：家裡、廚房、樓梯間、外面巷子）。"
        "沒講到 → null。",
    ),
    "gas_smell_strength": (
        "很濃|淡淡的|一陣一陣|null",
        "- gas_smell_strength 味道濃淡：只能填：很濃、淡淡的、一陣一陣。沒講到 → null。",
    ),
    "gas_type": (
        "天然氣|瓦斯桶|null",
        "- gas_type 瓦斯種類：只能填：天然氣、瓦斯桶。沒講到 → null。",
    ),
    "gas_adjacent": (
        "string|null",
        "- gas_adjacent 鄰接建物：旁邊有沒有房子或車子，照報案人說的記。沒講到 → null。",
    ),
    "lift_building": (
        "string|null",
        "- lift_building 社區棟別：哪個社區、哪一棟、哪一部電梯，照報案人說的記。沒講到 → null。",
    ),
    "lift_floor": (
        "string|null",
        "- lift_floor 受困樓層：電梯停在幾樓，照報案人說的記（常見：停在某一樓、卡在兩層樓中間）。"
        "沒講到 → null。",
    ),
    "lift_count": (
        "string|null",
        "- lift_count 受困人數：電梯裡有幾個人，照報案人說的記（例：1人、2人）。沒講到 → null。",
    ),
    "lift_company": (
        "已經聯絡|還沒聯絡|null",
        "- lift_company 電梯公司：有沒有聯絡電梯公司，只能填：已經聯絡、還沒聯絡。沒講到 → null。",
    ),
    "door_reason": (
        "string|null",
        "- door_reason 擔心原因：為什麼需要破門，照報案人說的記"
        "（常見：獨居聯絡不上、說要自殺、有病史、跌倒起不來）。沒講到 → null。",
    ),
    "knock_response": (
        "有回應|沒有回應|有聲音但叫不應|null",
        "- knock_response 有無回應：敲門或打電話、叫裡面的人有沒有反應，"
        "只能填：有回應、沒有回應、有聲音但叫不應。沒講到 → null。",
    ),
    "door_kind": (
        "大門|房門|浴室門|鐵門|null",
        "- door_kind 門的種類：只能填：大門、房門、浴室門、鐵門。沒講到 → null。",
    ),
    "door_locksmith": (
        "有鑰匙但打不開|沒有鑰匙|已找鎖匠|null",
        "- door_locksmith 鑰匙鎖匠：只能填：有鑰匙但打不開、沒有鑰匙、已找鎖匠。沒講到 → null。",
    ),
    "door_consent": (
        "同意|不同意|家屬或屋主還沒到|null",
        "- door_consent 同意破門：家屬或屋主同不同意破門，只能填：同意、不同意、家屬或屋主還沒到。"
        "沒講到 → null。",
    ),
}


def _count_rule(sub_category: Optional[str]) -> Tuple[str, str]:
    """患者人數：車禍救助記受傷幾人、受困幾人；其他次案類記人數。"""
    if sub_category == CRASH:
        rule = "- patient_count 患者人數：照報案人說的記受傷幾人、受困幾人（例：受傷2人、受困1人）。沒講到 → null。"
    else:
        rule = "- patient_count 患者人數：有幾個人，記人數（例：1人、2人）。沒講到 → null。"
    return "string|null", rule


def _discomfort_rule(sub_category: Optional[str]) -> Tuple[str, str]:
    """身體不適：電梯受困多了「不知道」，受傷也算；瓦斯漏氣只有有、沒有。"""
    if sub_category == LIFT:
        return "有|沒有|不知道|null", (
            "- gas_discomfort 身體不適：裡面的人有沒有受傷或不舒服，只能填：有、沒有、不知道；受傷也算有。"
            "沒講到 → null。"
        )
    return "有|沒有|null", "- gas_discomfort 身體不適：有沒有人身體不舒服，只能填：有、沒有。沒講到 → null。"


def emergency_fields_to_extract(sub_category: Optional[str]) -> Tuple[str, ...]:
    """這一輪要抽的欄位：次案類已經知道就只抽那張表的欄位，還不知道就抽全部的表。"""
    questions = questions_for_subtype(sub_category)
    fields = (item.field for item in questions) if questions else _ALL_FIELDS
    return tuple(dict.fromkeys(("incident_description", *fields)))


def emergency_schema_and_rules(sub_category: Optional[str]) -> Tuple[Dict[str, str], str]:
    """緊急救援欄位的 JSON Schema 與抽取規則（不含火警規則的三個欄位）。只在主類是緊急救援時送給 LLM。"""
    special = {"patient_count": _count_rule(sub_category), "gas_discomfort": _discomfort_rule(sub_category)}
    schema: Dict[str, str] = {}
    lines = []
    for field in emergency_fields_to_extract(sub_category):
        if field in EMERGENCY_FIRE_RULE_FIELDS:
            continue
        type_text, rule = special.get(field) or EMERGENCY_FIELD_RULES[field]
        schema[field] = type_text
        lines.append(rule)
    rules = (
        "【緊急救援欄位】只依報警人本輪實際回答抽取；未提及 → null，不得從受理員問題複製答案。"
        "報案人只回「有」「沒有」「對」時，看問題問的是哪一項才填那一項。"
        "寫「只能填」的欄位只能從列出的說法選一個，依意思判斷，不是看有沒有出現那幾個字。"
        "「參考」「常見」只是常見說法，不是選擇題：回答符合某個說法就用那個說法；"
        "不符合但和這一欄有關，就用報案人的話簡短記下。\n"
        + "\n".join(lines)
    )
    return schema, rules
