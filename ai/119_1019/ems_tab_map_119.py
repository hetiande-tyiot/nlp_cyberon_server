"""ems_tab_map_119.py — 救護垂片題目表。

規格：docs/(all)救護垂片規格_關鍵要素與問句_1028.xlsx（只照標 OK 的工作表）
目前照題目表問的次案類：OK 表 7 類（墜落傷、燒燙傷、精神異常、吞食藥物、上吊、燒炭、割腕），
以及急病（01-急病）。其他救護次案類還是走原本的流程。
OK 表的案類不用觸發情境（廠商的機制：每題答完判斷情境、講固定的話），使用者 10/28 決定。
急病不是 OK 表，是之前另外改的，等承辦確認再處理。

寫法跟火警垂片表（fire_tab_map_119）一樣，每一題記下 xlsx 的「問法分類」與「前置條件」：
  主動：還不知道才問（報案人前面已經講過就跳過）
  條件：前置條件確定成立、而且還不知道才問；答案還不知道的條件一律當作不成立
  被動：AI 不主動問，報案人自己講到時由每一輪的欄位抽取記下來
題目的順序就是 xlsx 的題號，第 N 題送給下游的編號是「次案類編號-N」。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

# 題目的資料格式跟火警共用
from fire_tab_map_119 import (
    MODE_ACTIVE,
    MODE_CONDITIONAL,
    MODE_PASSIVE,
    FireQuestion as EmsQuestion,
)

# 條件會用到的固定說法。LLM 抽取規則（llm_extractor_119 的 rescue_ext_rules）
# 要求這幾個欄位遇到對應情況時一定記成這些字，條件才判斷得出來。
CONSCIOUSNESS_UNKNOWN = "未知"
CONSCIOUSNESS_AWAKE = ("意識清醒", "剛剛昏倒、現在已清醒")
# 前置條件「意識 = 對聲音有反應、對疼痛有反應、昏迷」
CONSCIOUSNESS_UNRESPONSIVE = ("對聲音有反應", "對疼痛有反應", "昏迷")
RELATION_SELF = "本人"
RELATION_STRANGER = ("不認識", "路過")
# 報案人位置 = 在現場（急病的「在患者旁邊」也算在現場）
LOCATION_ON_SCENE = ("在現場", "在患者旁邊")
# 燒炭：炭盆狀況、患者所在位置（回答這兩種時要講提醒，見 handlers/燒炭.py）
CHARCOAL_NOT_OUT = "尚未熄滅"
PATIENT_STILL_INSIDE = "還在裡面"
# 報案身分（OK 表參考範圍）：精神異常的病史、家屬陪同要看是不是家人、朋友
RELATION_FAMILY = "家人"
RELATION_FRIEND = "朋友"
# 墜落傷：尚未跳下、卡住 → 改判緊急救援（見 handlers/墜落傷.py）
FALL_NOT_YET = "尚未跳下"
FALL_JUMPED = "已跳下"
FALL_POSITION_STUCK = "卡住"
FALL_POSITION_UNKNOWN = "不清楚"
# 上吊
HANGING_UNTIED = "已解開繩子"
HANGING_NOT_UNTIED = "還沒解開"
BREAK_IN_NEEDED = "需要破門"
# 上吊患者位置在這些地方 → 改判緊急救援-其他（xlsx 備註：例如橋墩、山上電塔）
HANGING_REMOTE_PLACES = ("橋墩", "電塔")
# 精神異常
AGGRESSION_OTHERS = "攻擊他人"
FORCED_ADMISSION_NEEDED = "需要"
# 燒燙傷小兒：14 歲（含）以前轉真人
CHILD_MAX_AGE = 14


def fill_consciousness_from_level(case: Any) -> None:
    """
    意識程度抽到了、「是否有意識」還空著 → 補上，OHCA 判定用的是「是否有意識」。
    清醒的兩種補「是」，對聲音有反應、對疼痛有反應、昏迷補「否」，未知不補。
    """
    if case.consciousness is not None:
        return
    level = case.consciousness_level
    if level in CONSCIOUSNESS_AWAKE:
        case.consciousness = True
    elif level in CONSCIOUSNESS_UNRESPONSIVE:
        case.consciousness = False


def _consciousness_unknown(case: Any) -> bool:
    """意識 = 未知：報案人說不知道、看不到。還沒問到不算。"""
    return case.consciousness_level == CONSCIOUSNESS_UNKNOWN


def _consciousness_unresponsive(case: Any) -> bool:
    """
    意識 = 對聲音有反應、對疼痛有反應、昏迷。
    意識程度沒抽到、但「是否有意識」已經是「否」，也算成立：不能因為少了程度就不問呼吸。
    """
    level = case.consciousness_level
    if level:
        return level in CONSCIOUSNESS_UNRESPONSIVE
    return case.consciousness is False


def _caller_not_self(case: Any) -> bool:
    """報案身分 ≠ 本人：一定要已經問出報案身分，而且不是本人。"""
    relation = case.caller_relation
    return bool(relation) and relation != RELATION_SELF


def _caller_knows_patient(case: Any) -> bool:
    """報案身分 ≠ 不認識、路過：一定要已經問出報案身分。"""
    relation = case.caller_relation
    return bool(relation) and relation not in RELATION_STRANGER


def _caller_on_scene(case: Any) -> bool:
    """報案人位置 = 在現場。"""
    return case.caller_location in LOCATION_ON_SCENE


def _caller_on_scene_or_not_mentioned(case: Any) -> bool:
    """報案人位置 = 未提到、在現場。"""
    return not case.caller_location or _caller_on_scene(case)


def _caller_off_scene(case: Any) -> bool:
    """報案人位置 ≠ 在現場：一定要已經問出報案人位置，而且不在現場（在遠處、不敢靠近、不在現場）。"""
    return bool(case.caller_location) and not _caller_on_scene(case)


def _on_scene_or_knows_patient(case: Any) -> bool:
    """性別、年齡（燒燙傷、燒炭）：報案人位置 = 在現場，或報案身分 ≠ 不認識、路過。"""
    return _caller_on_scene(case) or _caller_knows_patient(case)


def _not_self_on_scene(case: Any) -> bool:
    """意識（燒炭、墜落傷）：報案身分 ≠ 本人，且報案人位置 = 在現場（燒燙傷等多了「未提到」）。"""
    return _caller_not_self(case) and _caller_on_scene(case)


def _not_self_on_scene_or_unmentioned(case: Any) -> bool:
    """意識（燒燙傷、割腕、吞食藥物）：報案身分 ≠ 本人，且報案人位置 = 未提到、在現場。"""
    return _caller_not_self(case) and _caller_on_scene_or_not_mentioned(case)


# ─── 墜落傷、上吊、精神異常的前置條件 ───────────────────────────────────────

def _fall_jumped(case: Any) -> bool:
    """墜落狀況 = 已跳下。"""
    return case.fall_status == FALL_JUMPED


def _fall_stuck(case: Any) -> bool:
    """患者位置 = 卡住（墜落傷）。"""
    return case.fall_position == FALL_POSITION_STUCK


def _fall_position_not_unknown(case: Any) -> bool:
    """患者位置 ≠ 不清楚（墜落傷）：一定要已經問出患者位置，而且不是不清楚。"""
    return bool(case.fall_position) and case.fall_position != FALL_POSITION_UNKNOWN


def _hanging_not_untied(case: Any) -> bool:
    """上吊狀況 = 還沒解開。"""
    return case.hanging_status == HANGING_NOT_UNTIED


def _hanging_untied_on_scene_or_unmentioned(case: Any) -> bool:
    """上吊意識：上吊狀況 = 已解開繩子，且報案人位置 = 未提到、在現場。"""
    return case.hanging_status == HANGING_UNTIED and _caller_on_scene_or_not_mentioned(case)


def _attacks_others(case: Any) -> bool:
    """攻擊傾向 = 攻擊他人。"""
    return case.aggression == AGGRESSION_OTHERS


def _forced_admission_needed(case: Any) -> bool:
    """強制送醫 = 需要。"""
    return case.forced_admission == FORCED_ADMISSION_NEEDED


def _caller_family_or_friend(case: Any) -> bool:
    """報案身分 = 家人、朋友。"""
    return case.caller_relation in (RELATION_FAMILY, RELATION_FRIEND)


def _caller_not_family(case: Any) -> bool:
    """報案身分 ≠ 家人：一定要已經問出報案身分，而且不是家人。"""
    relation = case.caller_relation
    return bool(relation) and relation != RELATION_FAMILY


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}


def _age_in_years(text: str) -> Optional[int]:
    """「8歲」「十二歲」「二十五歲」→ 歲數；看不出來回傳 None。"""
    match = re.search(r"\d+", text)
    if match:
        return int(match.group())
    match = re.search(r"([一二兩三四五六七八九]?)(十?)([一二三四五六七八九]?)\s*[歲岁]", text)
    if not match or not any(match.groups()):
        return None
    tens, ten, ones = match.groups()
    if ten:
        return _CN_DIGITS.get(tens, 1) * 10 + _CN_DIGITS.get(ones, 0)
    return _CN_DIGITS.get(tens or ones)


def is_child_age(age: Optional[str]) -> bool:
    """燒燙傷小兒（xlsx 備註：14 歲（含）以前）：講月份（未滿一歲）或 14 歲以下。看不出歲數就不算。"""
    text = str(age or "")
    if "個月" in text or "个月" in text:
        return True
    years = _age_in_years(text)
    return years is not None and years <= CHILD_MAX_AGE


_UNRESPONSIVE_TEXT = "意識 = 對聲音有反應、對疼痛有反應、昏迷"

# ─── 01-急病 ─────────────────────────────────────────────────────────────────
JI_BING_QUESTIONS: Tuple[EmsQuestion, ...] = (
    EmsQuestion("病徵", "incident_description", MODE_ACTIVE,
                "急病-病徵", "請問發生什麼事？"),
    EmsQuestion("報案人與患者關係", "caller_relation", MODE_ACTIVE,
                "急病-報案人與患者關係", "請問患者是您的什麼人？"),
    EmsQuestion("意識", "consciousness_level", MODE_ACTIVE,
                "急病-意識", "他現在人清醒嗎？叫他有沒有反應？"),
    EmsQuestion("報案人是否在場", "caller_location", MODE_CONDITIONAL,
                "急病-報案人是否在場", "您現在人在他旁邊嗎？可以靠近看看他嗎？",
                _consciousness_unknown, "意識 = 未知"),
    EmsQuestion("性別", "patient_gender", MODE_ACTIVE,
                "急病-性別", "他是男生還是女生？"),
    EmsQuestion("是否飲酒", "drinking_status", MODE_PASSIVE, "急病-是否飲酒"),
    EmsQuestion("平常行動能力", "mobility", MODE_PASSIVE, "急病-平常行動能力"),
    EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                "急病-呼吸", "他還有沒有呼吸？胸口、肚子有沒有一上一下起伏？",
                _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
    EmsQuestion("年齡", "patient_age", MODE_ACTIVE,
                "急病-年齡", "他大概幾歲？"),
    EmsQuestion("症狀發生時間", "symptom_onset", MODE_PASSIVE, "急病-症狀發生時間"),
    EmsQuestion("病史", "medical_history", MODE_PASSIVE, "急病-病史"),
    EmsQuestion("現場進入條件", "scene_access", MODE_PASSIVE, "急病-現場進入條件"),
    EmsQuestion("患者人數", "patient_count", MODE_PASSIVE, "急病-患者人數"),
)

# ─── 08-燒燙傷OK ─────────────────────────────────────────────────────────────
# 第 5 題年齡在 xlsx 沒有問句、前置條件也空白：第 4 題的問句同時問性別和年齡，
# 所以年齡跟第 4 題用同一個前置條件，不另外問。
_GENDER_AGE_TEXT = "報案人位置 = 在現場 或 報案身分 ≠ 不認識、路過"

SHAO_TANG_SHANG_QUESTIONS: Tuple[EmsQuestion, ...] = (
    EmsQuestion("燒燙傷原因", "injury_cause", MODE_ACTIVE,
                "燒燙傷-燒燙傷原因", "請問是被什麼東西燙到？或什麼原因燙傷？"),
    EmsQuestion("燙傷傷勢", "injury_severity", MODE_ACTIVE,
                "燒燙傷-燙傷傷勢", "有無起水泡，燒燙傷部位？大概範圍多大呢?"),
    EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                "燒燙傷-報案身分", "請問你認識患者嗎？"),
    EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                "燒燙傷-性別", "請問患者是男生還是女生？大概幾歲？",
                _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
    EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                "燒燙傷-年齡", "",
                _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
    EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                "燒燙傷-意識", "現在人清醒嗎？叫他有沒有反應？",
                _not_self_on_scene_or_unmentioned,
                "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
    EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                "燒燙傷-呼吸", "還有沒有呼吸？胸口、肚子有沒有一上一下起伏？",
                _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
    EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "燒燙傷-報案人位置"),
)

EMS_QUESTIONS: Dict[str, Tuple[EmsQuestion, ...]] = {
    "急病": JI_BING_QUESTIONS,
    "燒燙傷": SHAO_TANG_SHANG_QUESTIONS,
    # ─── 17-燒炭OK ───────────────────────────────────────────────────────────
    # 第 7 題年齡沒有問句：跟第 6 題性別同一句問。
    # 備註的提醒語、需要破門改判緊急救援，寫在 handlers/燒炭.py。
    "燒炭": (
        EmsQuestion("報案人位置", "caller_location", MODE_ACTIVE,
                    "燒炭-報案人位置", "您現在人還在現場嗎？"),
        EmsQuestion("炭盆狀況", "charcoal_status", MODE_CONDITIONAL,
                    "燒炭-炭盆狀況", "目前炭盆已熄滅了嗎？",
                    _caller_on_scene, "報案人位置 = 在現場"),
        EmsQuestion("現場進入條件", "scene_access", MODE_CONDITIONAL,
                    "燒炭-現場進入條件", "救護人員到場之後可以進去嗎？需不需要破門？",
                    _caller_off_scene, "報案人位置 ≠ 在現場"),
        EmsQuestion("患者所在位置", "patient_location", MODE_CONDITIONAL,
                    "燒炭-患者所在位置", "患者還在裡面嗎？還是已經出來了？",
                    _caller_on_scene, "報案人位置 = 在現場"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "燒炭-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "燒炭-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "燒炭-年齡", "",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "燒炭-意識", "患者現在清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene, "報案身分 ≠ 本人 且 報案人位置 = 在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "燒炭-呼吸", "他還有沒有呼吸？胸口、肚子有沒有一上一下起伏？",
                    _consciousness_unresponsive, "意識 ≠ 意識清醒、未知"),
    ),
    # ─── 06-墜落傷OK ─────────────────────────────────────────────────────────
    # 第 5 題年齡沒有問句：跟第 4 題性別同一句問，前置條件也跟第 4 題一樣。
    # 尚未跳下、卡住改判緊急救援，寫在 handlers/墜落傷.py。
    "墜落傷": (
        EmsQuestion("墜落狀況", "fall_status", MODE_ACTIVE,
                    "墜落傷-墜落狀況", "已經跳下來了嗎？還是還在上面？"),
        EmsQuestion("墜落高度", "fall_height", MODE_CONDITIONAL,
                    "墜落傷-墜落高度", "請問是從幾樓或多高的地方掉下來？",
                    _fall_jumped, "墜落狀況 = 已跳下"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "墜落傷-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "墜落傷-性別", "請問患者是男生還是女生？大概幾歲？",
                    _caller_knows_patient, "報案身分 ≠ 不認識、路過"),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "墜落傷-年齡", "",
                    _caller_knows_patient, "報案身分 ≠ 不認識、路過"),
        EmsQuestion("患者位置", "fall_position", MODE_CONDITIONAL,
                    "墜落傷-患者位置", "目前人掉在哪個地方？地面上還是哪裡？有卡住嗎？",
                    _fall_jumped, "墜落狀況 = 已跳下"),
        EmsQuestion("卡住位置", "stuck_location", MODE_CONDITIONAL,
                    "墜落傷-卡住位置", "目前是在遮雨棚上卡住還是女兒牆上？",
                    _fall_stuck, "患者位置 = 卡住"),
        EmsQuestion("報案人位置", "caller_location", MODE_CONDITIONAL,
                    "墜落傷-報案人位置", "你有在傷者旁邊嗎？可以靠近嗎？",
                    _fall_position_not_unknown, "患者位置 ≠ 不清楚"),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "墜落傷-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene, "報案身分 ≠ 本人 且 報案人位置 = 在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "墜落傷-呼吸", "他還有沒有呼吸？胸口、肚子有沒有一上一下起伏？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
    ),
    # ─── 16-上吊OK ───────────────────────────────────────────────────────────
    # 題號照 xlsx「列的位置」：患者位置排在第 3 列（順序欄寫 6，看起來是從墜落傷複製沒改到）。
    # 需要破門、患者在橋墩電塔改判緊急救援，寫在 handlers/上吊.py。
    "上吊": (
        EmsQuestion("上吊狀況", "hanging_status", MODE_ACTIVE,
                    "上吊-上吊狀況", "目前繩子解開了嗎？人在地上了嗎？"),
        EmsQuestion("破門需求", "break_in_need", MODE_CONDITIONAL,
                    "上吊-破門需求", "現場救護人員進得去嗎？需要破門嗎？",
                    _hanging_not_untied, "上吊狀況 = 還沒解開"),
        EmsQuestion("患者位置", "hanging_location", MODE_PASSIVE, "上吊-患者位置"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "上吊-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "上吊-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "上吊-年齡", "",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "上吊-意識", "現在人清醒嗎？叫他有沒有反應？",
                    _hanging_untied_on_scene_or_unmentioned,
                    "上吊狀況 = 已解開繩子 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "上吊-呼吸", "他還有沒有呼吸？胸口、肚子有沒有一上一下起伏？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "上吊-報案人位置"),
    ),
    # ─── 19-割腕OK ───────────────────────────────────────────────────────────
    # 第 2 題工具沒有問句：第 1 題「哪裡受傷？用什麼工具？」一起問。
    "割腕": (
        EmsQuestion("初步傷勢", "injury_severity", MODE_ACTIVE,
                    "割腕-初步傷勢", "請問是哪裡受傷？用什麼工具？"),
        EmsQuestion("工具", "cutting_tool", MODE_ACTIVE, "割腕-工具", ""),
        EmsQuestion("工具狀況", "tool_status", MODE_ACTIVE,
                    "割腕-工具狀況", "目前刀具移除了嗎？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "割腕-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "割腕-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "割腕-年齡", "",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "割腕-意識", "現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案人位置 = 未提到、在現場 且 報案身分 ≠ 本人"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "割腕-呼吸", "幫我看他有沒有正常呼吸，胸口、肚子有沒有一上一下起伏",
                    _consciousness_unresponsive, "意識 ≠ 意識清醒、未知"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "割腕-報案人位置"),
    ),
    # ─── 15-吞食藥物OK ───────────────────────────────────────────────────────
    # 第 2 題藥物數量沒有問句：第 1 題「吃了什麼藥物？大概幾顆？」一起問。
    # 藥袋備註的提醒（結束通話前講），寫在 handlers/吞食藥物.py。
    "吞食藥物": (
        EmsQuestion("服用藥物", "ingested_substance", MODE_ACTIVE,
                    "吞食藥物-服用藥物", "請問是吃了什麼藥物？大概幾顆？"),
        EmsQuestion("藥物數量", "drug_amount", MODE_ACTIVE, "吞食藥物-藥物數量", ""),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "吞食藥物-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "吞食藥物-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "吞食藥物-年齡", "",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "吞食藥物-意識", "現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "吞食藥物-呼吸", "他還有沒有呼吸？胸口、肚子有沒有一上一下起伏？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("病史", "medical_history", MODE_PASSIVE, "吞食藥物-病史"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "吞食藥物-報案人位置"),
        EmsQuestion("藥袋", "medicine_bag", MODE_PASSIVE, "吞食藥物-藥袋"),
    ),
    # ─── 13-精神異常OK ───────────────────────────────────────────────────────
    # 意識、呼吸是被動題（承辦：有動作行為就不用再問意識呼吸），所以不做 OHCA 判定。
    "精神異常": (
        EmsQuestion("攻擊傾向", "aggression", MODE_ACTIVE,
                    "精神異常-攻擊傾向", "請問目前有攻擊別人或傷害自己的動作嗎？"),
        EmsQuestion("受傷人數", "injured_count", MODE_CONDITIONAL,
                    "精神異常-受傷人數", "現場有沒有其他人受傷？幾個人受傷？",
                    _attacks_others, "攻擊傾向 = 攻擊他人"),
        EmsQuestion("強制送醫", "forced_admission", MODE_ACTIVE,
                    "精神異常-強制送醫", "需要強制送醫嗎？"),
        EmsQuestion("強制送醫原因", "forced_admission_reason", MODE_CONDITIONAL,
                    "精神異常-強制送醫原因", "請問是什麼狀況要強制送醫？",
                    _forced_admission_needed, "強制送醫 = 需要"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "精神異常-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "精神異常-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "精神異常-年齡", "",
                    _on_scene_or_knows_patient, _GENDER_AGE_TEXT),
        EmsQuestion("病史", "medical_history", MODE_CONDITIONAL,
                    "精神異常-病史", "請問患者有沒有過去病史？",
                    _caller_family_or_friend, "報案身分 = 家人、朋友"),
        EmsQuestion("家屬陪同", "family_accompany", MODE_CONDITIONAL,
                    "精神異常-家屬陪同", "身邊有家屬陪同嗎？",
                    _caller_not_family, "報案身分 ≠ 家人"),
        EmsQuestion("意識", "consciousness_level", MODE_PASSIVE, "精神異常-意識"),
        EmsQuestion("呼吸", "breathing", MODE_PASSIVE, "精神異常-呼吸"),
    ),
}


def questions_for_subtype(sub_category: Optional[str]) -> Tuple[EmsQuestion, ...]:
    """這個救護次案類的題目表；還沒照 xlsx 改寫的次案類回傳空的。"""
    return EMS_QUESTIONS.get(sub_category or "", ())
