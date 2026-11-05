"""ems_tab_map_119.py — 救護垂片題目表。

規格：docs/(all)救護垂片規格_關鍵要素與問句_1104.xlsx
目前照題目表問的次案類：OK 表 7 類（墜落傷、燒燙傷、精神異常、吞食藥物、上吊、燒炭、割腕），
以及還沒標 OK、先照表問給承辦實測的急病、一般受傷、路倒、車禍、打架受傷、孕婦待產
（11/02 使用者決定），刀傷(切割傷)、槍傷、壓傷、電擊傷、溺水、喝農藥、吸入廢氣（11/03 使用者決定），
其它（11/04 使用者決定）。
照題目表問的案類不用觸發情境（廠商的機制：每題答完判斷情境、講固定的話），使用者 10/28 決定。
欄位、抽取規則、條件都以 xlsx 關鍵要素為準，不用廠商重複概念的舊欄位（是否有意識、報案人是否即患者等）。
一個關鍵要素一個欄位：垂片名稱一樣才共用欄位，欄位的中文名稱要跟垂片一字不差（11/04 使用者決定）。
呼吸 = 呼吸不正常、無呼吸 → 轉真人（使用者 11/02 決定，不再用 OHCA 判定，見 handlers/base.py）。

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
CONSCIOUSNESS_AWAKE = "清醒"
# 前置條件「意識 = 沒有反應」（1104 xlsx 11/05 版意識改成 未知／清醒／迷迷糊糊／沒有反應）
CONSCIOUSNESS_UNRESPONSIVE = ("沒有反應",)
# 呼吸是這兩種就轉真人（使用者 11/02 決定，不再用 OHCA 判定）
BREATHING_TRANSFER = ("呼吸不正常", "無呼吸")
RELATION_SELF = "本人"
# 報案人位置 = 在現場
LOCATION_ON_SCENE = ("在現場",)
# 燒炭：炭盆狀況、患者所在位置（回答這兩種時要講提醒，見 handlers/燒炭.py）
CHARCOAL_NOT_OUT = "尚未熄滅"
PATIENT_STILL_INSIDE = "還在裡面"
# 報案身分（OK 表參考範圍）：精神異常的病史、家屬陪同要看是不是家人、朋友
RELATION_FAMILY = "家人"
RELATION_FRIEND = "朋友"
# 墜落傷：墜落狀況是尚未跳下或卡住、患者位置是卡住 → 改判緊急救援（見 handlers/墜落傷.py）
FALL_NOT_YET = "尚未跳下"
FALL_JUMPED = "已跳下"
FALL_STATUS_STUCK = "卡住"
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
# 路倒：路倒狀況回答喝醉時，是否飲酒也記成有喝酒（xlsx 備註，見 handlers/路倒.py）
COLLAPSE_DRUNK = "喝醉"
DRINKING_YES = "有喝酒"
# 車禍：有人受困 → 改判緊急救援（xlsx 備註，見 handlers/車禍.py）
CRASH_TRAPPED_YES = "有人受困"
# 打架受傷：衝突還在進行才問持械
CONFLICT_ONGOING = "進行中"
# 孕婦待產：陣痛狀況是已經破水才講墊毛巾的提醒語（見 handlers/孕婦急產.py）
CONTRACTIONS_WATER_BROKEN = "已經破水"
# 燒燙傷小兒：14 歲（含）以前轉真人
CHILD_MAX_AGE = 14
# 溺水：還在水裡（xlsx 備註）、看不到人（使用者 11/05 決定）→ 改判緊急救援（見 handlers/溺水.py）
DROWNING_NOT_RESCUED = ("還在水裡", "看不到人")


def _consciousness_unresponsive(case: Any) -> bool:
    """意識 = 沒有反應。"""
    return case.consciousness_level in CONSCIOUSNESS_UNRESPONSIVE


def _caller_not_self(case: Any) -> bool:
    """報案身分 ≠ 本人：一定要已經問出報案身分，而且不是本人。"""
    relation = case.caller_relation
    return bool(relation) and relation != RELATION_SELF


def _caller_on_scene(case: Any) -> bool:
    """報案人位置 = 在現場。"""
    return case.caller_location in LOCATION_ON_SCENE


def _caller_on_scene_or_not_mentioned(case: Any) -> bool:
    """報案人位置 = 未提到、在現場。"""
    return not case.caller_location or _caller_on_scene(case)


def _caller_off_scene(case: Any) -> bool:
    """報案人位置 ≠ 在現場：一定要已經問出報案人位置，而且不在現場（在遠處、不敢靠近、不在現場）。"""
    return bool(case.caller_location) and not _caller_on_scene(case)


def _on_scene_or_family_friend(case: Any) -> bool:
    """性別、年齡：報案人位置 = 未提到、在現場，或報案身分 = 家人、朋友。"""
    return _caller_on_scene_or_not_mentioned(case) or _caller_family_or_friend(case)


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


def _caller_self_family_or_friend(case: Any) -> bool:
    """報案身分 = 本人、家人、朋友（孕婦待產）。"""
    return case.caller_relation in (RELATION_SELF, RELATION_FAMILY, RELATION_FRIEND)


def _conflict_ongoing(case: Any) -> bool:
    """衝突狀況 = 進行中（打架受傷）。"""
    return case.conflict_status == CONFLICT_ONGOING


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


_UNRESPONSIVE_TEXT = "意識 = 沒有反應"

# ─── 01-急病 ─────────────────────────────────────────────────────────────────
# 性別、年齡共用的前置條件（各案類第幾題不同，條件一樣）
_GENDER_AGE_TEXT = "報案人位置 = 未提到、在現場 或 報案身分 = 家人、朋友"

# 第 5 題年齡沒有問句：跟第 4 題性別同一句問，前置條件也跟第 4 題一樣。
JI_BING_QUESTIONS: Tuple[EmsQuestion, ...] = (
    EmsQuestion("病徵", "symptoms", MODE_ACTIVE,
                "急病-病徵", "請問患者是哪裡不舒服？"),
    EmsQuestion("患者人數", "patient_count", MODE_PASSIVE, "急病-患者人數"),
    EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                "急病-報案身分", "請問你認識患者嗎？"),
    EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                "急病-性別", "請問患者是男生還是女生？大概幾歲？",
                _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                "急病-年齡", "",
                _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                "急病-意識", "他現在人清醒嗎？叫他有沒有反應？",
                _not_self_on_scene_or_unmentioned,
                "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
    EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                "急病-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
    EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "急病-報案人位置"),
)

# ─── 08-燒燙傷OK ─────────────────────────────────────────────────────────────
# 第 5 題年齡在 xlsx 沒有問句、前置條件也空白：第 4 題的問句同時問性別和年齡，
# 所以年齡跟第 4 題用同一個前置條件，不另外問。

SHAO_TANG_SHANG_QUESTIONS: Tuple[EmsQuestion, ...] = (
    EmsQuestion("燒燙傷原因", "burn_cause", MODE_ACTIVE,
                "燒燙傷-燒燙傷原因", "請問是被什麼東西燙到？或什麼原因燙傷？"),
    EmsQuestion("燙傷傷勢", "burn_severity", MODE_ACTIVE,
                "燒燙傷-燙傷傷勢", "有無起水泡，燒燙傷部位？大概範圍多大呢?"),
    EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                "燒燙傷-報案身分", "請問你認識患者嗎？"),
    EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                "燒燙傷-性別", "請問患者是男生還是女生？大概幾歲？",
                _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                "燒燙傷-年齡", "",
                _on_scene_or_family_friend, _GENDER_AGE_TEXT),
    EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                "燒燙傷-意識", "現在人清醒嗎？叫他有沒有反應？",
                _not_self_on_scene_or_unmentioned,
                "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
    EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                "燒燙傷-呼吸", "還有沒有呼吸？胸部有沒有一上一下起伏呢？",
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
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "燒炭-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "燒炭-意識", "患者現在清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene, "報案身分 ≠ 本人 且 報案人位置 = 在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "燒炭-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
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
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "墜落傷-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
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
                    "墜落傷-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
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
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "上吊-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "上吊-意識", "現在人清醒嗎？叫他有沒有反應？",
                    _hanging_untied_on_scene_or_unmentioned,
                    "上吊狀況 = 已解開繩子 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "上吊-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "上吊-報案人位置"),
    ),
    # ─── 19-割腕OK ───────────────────────────────────────────────────────────
    # 第 2 題工具沒有問句：第 1 題「哪裡受傷？用什麼工具？」一起問。
    "割腕": (
        EmsQuestion("傷勢", "injury_severity", MODE_ACTIVE,
                    "割腕-傷勢", "請問是哪裡受傷？用什麼工具？"),
        EmsQuestion("工具", "cutting_tool", MODE_ACTIVE, "割腕-工具", ""),
        EmsQuestion("工具移除", "tool_status", MODE_ACTIVE,
                    "割腕-工具移除", "目前刀具還在患者身邊嗎？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "割腕-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "割腕-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "割腕-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "割腕-意識", "現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案人位置 = 未提到、在現場 且 報案身分 ≠ 本人"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "割腕-呼吸", "幫我看他有沒有正常呼吸，胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
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
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "吞食藥物-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "吞食藥物-意識", "現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "吞食藥物-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
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
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "精神異常-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("病史", "medical_history", MODE_CONDITIONAL,
                    "精神異常-病史", "請問患者有沒有過去病史？",
                    _caller_family_or_friend, "報案身分 = 家人、朋友"),
        EmsQuestion("家屬陪同", "family_accompany", MODE_CONDITIONAL,
                    "精神異常-家屬陪同", "身邊有家屬陪同嗎？",
                    _caller_not_family, "報案身分 ≠ 家人"),
        EmsQuestion("意識", "consciousness_level", MODE_PASSIVE, "精神異常-意識"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "精神異常-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "精神異常-報案人位置"),
    ),
    # ─── 10-一般受傷（還沒標 OK）────────────────────────────────────────────
    # 第 7 題年齡沒有問句：跟第 6 題性別同一句問，前置條件也跟第 6 題一樣。
    # 提醒語（止血、斷指時講斷指保存）寫在 handlers/一般受傷.py。
    "一般受傷": (
        EmsQuestion("受傷原因", "injury_cause", MODE_ACTIVE,
                    "一般受傷-受傷原因", "請問是怎麼受傷的？是跌倒嗎？"),
        EmsQuestion("發生場所", "injury_place", MODE_PASSIVE, "一般受傷-發生場所"),
        EmsQuestion("受傷部位", "injury_location", MODE_ACTIVE,
                    "一般受傷-受傷部位", "傷到哪裡？"),
        EmsQuestion("傷勢", "injury_severity", MODE_ACTIVE,
                    "一般受傷-傷勢", "傷得嚴不嚴重？有沒有一直流血？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "一般受傷-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "一般受傷-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "一般受傷-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "一般受傷-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "一般受傷-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "一般受傷-報案人位置"),
    ),
    # ─── 14-路倒（還沒標 OK）────────────────────────────────────────────────
    # 第 8 題年齡沒有問句：跟第 7 題性別同一句問，前置條件也跟第 7 題一樣。
    # 路倒狀況回答喝醉時是否飲酒也記成有喝酒，寫在 handlers/路倒.py。
    "路倒": (
        EmsQuestion("路倒狀況", "collapse_status", MODE_ACTIVE,
                    "路倒-路倒狀況", "他看起來是喝醉、睡著，還是身體不舒服？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "路倒-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("是否飲酒", "drinking_status", MODE_PASSIVE, "路倒-是否飲酒"),
        EmsQuestion("外觀特徵", "patient_appearance", MODE_ACTIVE,
                    "路倒-外觀特徵", "他身上穿什麼顏色的衣服？我請救護人員好認一點。"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "路倒-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("身旁親友", "companion_present", MODE_PASSIVE, "路倒-身旁親友"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "路倒-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "路倒-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "路倒-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "路倒-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "路倒-報案人位置"),
    ),
    # ─── 02-車禍（還沒標 OK）────────────────────────────────────────────────
    # 第 8 題年齡沒有問句：跟第 7 題性別同一句問，前置條件也跟第 7 題一樣。
    # 有人受困改判緊急救援，寫在 handlers/車禍.py。
    "車禍": (
        EmsQuestion("事故車種", "crash_vehicles", MODE_ACTIVE,
                    "車禍-事故車種", "請問是什麼車跟什麼車的車禍？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "車禍-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("人員受困", "crash_trapped", MODE_ACTIVE,
                    "車禍-人員受困", "有沒有人被卡在車子裡面，或是車子底下？"),
        EmsQuestion("受傷部位", "injury_location", MODE_PASSIVE, "車禍-受傷部位"),
        EmsQuestion("傷勢", "injury_severity", MODE_PASSIVE, "車禍-傷勢"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "車禍-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "車禍-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "車禍-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "車禍-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "車禍-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "車禍-報案人位置"),
    ),
    # ─── 09-打架受傷（還沒標 OK）────────────────────────────────────────────
    # 第 7 題年齡沒有問句：跟第 6 題性別同一句問，前置條件也跟第 6 題一樣。
    # 提醒語表的句子還沒定，不講提醒語。
    "打架受傷": (
        EmsQuestion("衝突狀況", "conflict_status", MODE_ACTIVE,
                    "打架受傷-衝突狀況", "現在還有在打嗎？您那邊安全嗎？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "打架受傷-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("是否飲酒", "drinking_status", MODE_PASSIVE, "打架受傷-是否飲酒"),
        EmsQuestion("持械", "weapon_held", MODE_CONDITIONAL,
                    "打架受傷-持械", "請問他們手上有沒有拿刀、棍子之類的東西？",
                    _conflict_ongoing, "衝突狀況 = 進行中"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "打架受傷-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "打架受傷-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "打架受傷-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "打架受傷-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "打架受傷-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("病徵", "symptoms", MODE_PASSIVE, "打架受傷-病徵"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "打架受傷-報案人位置"),
    ),
    # ─── 12-孕婦待產（還沒標 OK）────────────────────────────────────────────
    # 第 4 題懷孕週數沒有問句：跟第 3 題預產期同一句問（只缺一個時的補問句見 handlers/base.py）。
    # 報案身分排第 1 題：第 3～6 題的條件要看報案身分。提醒語寫在 handlers/孕婦急產.py。
    "孕婦待產": (
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "孕婦待產-報案身分", "請問是孕婦本人，還是家人朋友？"),
        EmsQuestion("陣痛狀況", "contractions", MODE_ACTIVE,
                    "孕婦待產-陣痛狀況", "現在有規則陣痛嗎？"),
        EmsQuestion("預產期", "due_date", MODE_CONDITIONAL,
                    "孕婦待產-預產期", "預產期是什麼時候？現在懷孕幾週了？",
                    _caller_self_family_or_friend, "報案身分 = 本人、家人、朋友"),
        EmsQuestion("懷孕週數", "pregnancy_week", MODE_CONDITIONAL, "孕婦待產-懷孕週數", "",
                    _caller_self_family_or_friend, "報案身分 = 本人、家人、朋友"),
        EmsQuestion("胎次與胎數", "multiple_pregnancy", MODE_CONDITIONAL,
                    "孕婦待產-胎次與胎數", "這是第幾胎？是單胞胎還是雙胞胎？",
                    _caller_self_family_or_friend, "報案身分 = 本人、家人、朋友"),
        EmsQuestion("產檢狀況", "prenatal_history", MODE_CONDITIONAL,
                    "孕婦待產-產檢狀況", "之前產檢都正常嗎？",
                    _caller_self_family_or_friend, "報案身分 = 本人、家人、朋友"),
        EmsQuestion("性別", "patient_gender", MODE_PASSIVE, "孕婦待產-性別"),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "孕婦待產-年齡", "請問大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "孕婦待產-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "孕婦待產-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("病徵", "symptoms", MODE_PASSIVE, "孕婦待產-病徵"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "孕婦待產-報案人位置"),
    ),
    # ─── 03-刀傷(切割傷)（還沒標 OK）────────────────────────────────────────
    # 第 7 題年齡沒有問句：跟第 6 題性別同一句問，前置條件也跟第 6 題一樣。
    # 受傷原因跟一般受傷同一個欄位，刀傷只能記四個選項之一（見 llm_extractor_119）。
    "刀傷(切割傷)": (
        EmsQuestion("受傷原因", "injury_cause", MODE_ACTIVE,
                    "刀傷(切割傷)-受傷原因", "請問是自己不小心割到，還是被別人弄傷的？"),
        EmsQuestion("工具", "cutting_tool", MODE_PASSIVE, "刀傷(切割傷)-工具"),
        EmsQuestion("受傷部位", "injury_location", MODE_ACTIVE,
                    "刀傷(切割傷)-受傷部位", "傷到哪裡？"),
        EmsQuestion("傷勢", "injury_severity", MODE_ACTIVE,
                    "刀傷(切割傷)-傷勢", "傷得嚴不嚴重？有沒有一直流血？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "刀傷(切割傷)-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "刀傷(切割傷)-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "刀傷(切割傷)-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "刀傷(切割傷)-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "刀傷(切割傷)-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("患者人數", "patient_count", MODE_PASSIVE, "刀傷(切割傷)-患者人數"),
        EmsQuestion("是否飲酒", "drinking_status", MODE_PASSIVE, "刀傷(切割傷)-是否飲酒"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "刀傷(切割傷)-報案人位置"),
    ),
    # ─── 04-槍傷（還沒標 OK）────────────────────────────────────────────────
    # 第 6 題年齡沒有問句：跟第 5 題性別同一句問，前置條件也跟第 5 題一樣。
    "槍傷": (
        EmsQuestion("受傷部位", "injury_location", MODE_ACTIVE,
                    "槍傷-受傷部位", "傷到哪裡？"),
        EmsQuestion("傷勢", "injury_severity", MODE_ACTIVE,
                    "槍傷-傷勢", "傷得嚴不嚴重？有沒有一直流血？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "槍傷-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "槍傷-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "槍傷-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "槍傷-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "槍傷-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "槍傷-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("受傷原因", "injury_cause", MODE_PASSIVE, "槍傷-受傷原因"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "槍傷-報案人位置"),
    ),
    # ─── 05-壓傷（還沒標 OK）────────────────────────────────────────────────
    # 題目跟槍傷一樣。第 6 題年齡沒有問句：跟第 5 題性別同一句問，前置條件也跟第 5 題一樣。
    "壓傷": (
        EmsQuestion("受傷部位", "injury_location", MODE_ACTIVE,
                    "壓傷-受傷部位", "傷到哪裡？"),
        EmsQuestion("傷勢", "injury_severity", MODE_ACTIVE,
                    "壓傷-傷勢", "傷得嚴不嚴重？有沒有一直流血？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "壓傷-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "壓傷-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "壓傷-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "壓傷-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "壓傷-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "壓傷-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("受傷原因", "injury_cause", MODE_PASSIVE, "壓傷-受傷原因"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "壓傷-報案人位置"),
    ),
    # ─── 07-電擊傷（還沒標 OK）──────────────────────────────────────────────
    # 第 7 題年齡沒有問句：跟第 6 題性別同一句問，前置條件也跟第 6 題一樣。
    "電擊傷": (
        EmsQuestion("電擊種類", "electric_type", MODE_ACTIVE,
                    "電擊傷-電擊種類", "請問是被什麼電到? 高壓電還是雷電?"),
        EmsQuestion("現場是否已斷電", "power_off", MODE_ACTIVE,
                    "電擊傷-現場是否已斷電", "那邊的電源有沒有先關掉？現在斷電了嗎？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "電擊傷-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("傷患身分", "patient_identity", MODE_ACTIVE,
                    "電擊傷-傷患身分", "患者是工地工人嗎？還是外籍移工呢？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "電擊傷-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "電擊傷-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "電擊傷-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "電擊傷-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "電擊傷-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "電擊傷-報案人位置"),
    ),
    # ─── 11-溺水（還沒標 OK）────────────────────────────────────────────────
    # 第 6 題年齡沒有問句：跟第 5 題性別同一句問，前置條件也跟第 5 題一樣。
    # 未拉上岸改判緊急救援，寫在 handlers/溺水.py。
    "溺水": (
        EmsQuestion("溺水狀況", "drowning_status", MODE_ACTIVE,
                    "溺水-溺水狀況", "人拉上岸了嗎? 還是還在水裡?"),
        EmsQuestion("溺水原因", "drowning_cause", MODE_ACTIVE,
                    "溺水-溺水原因", "請問是怎麼落水的？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "溺水-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "溺水-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "溺水-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "溺水-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "溺水-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "溺水-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "溺水-報案人位置"),
    ),
    # ─── 18-喝農藥（還沒標 OK）──────────────────────────────────────────────
    # 第 6 題年齡沒有問句：跟第 5 題性別同一句問，前置條件也跟第 5 題一樣。
    "喝農藥": (
        EmsQuestion("農藥種類", "pesticide_type", MODE_ACTIVE,
                    "喝農藥-農藥種類", "知道他喝的是什麼農藥嗎？瓶子還在嗎？"),
        EmsQuestion("農藥劑量", "pesticide_amount", MODE_ACTIVE,
                    "喝農藥-農藥劑量", "大概喝了多少？"),
        EmsQuestion("患者人數", "patient_count", MODE_PASSIVE, "喝農藥-患者人數"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "喝農藥-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "喝農藥-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "喝農藥-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "喝農藥-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "喝農藥-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("病徵", "symptoms", MODE_PASSIVE, "喝農藥-病徵"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "喝農藥-報案人位置"),
    ),
    # ─── 20-吸入廢氣（還沒標 OK）────────────────────────────────────────────
    # 第 5 題年齡沒有問句：跟第 4 題性別同一句問，前置條件也跟第 4 題一樣。
    "吸入廢氣": (
        EmsQuestion("病徵", "symptoms", MODE_ACTIVE,
                    "吸入廢氣-病徵", "請問患者是哪裡不舒服？"),
        EmsQuestion("患者人數", "patient_count", MODE_ACTIVE,
                    "吸入廢氣-患者人數", "現場有幾個人需要救護？"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "吸入廢氣-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "吸入廢氣-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "吸入廢氣-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "吸入廢氣-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "吸入廢氣-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "吸入廢氣-報案人位置"),
    ),
    # ─── 21-其它（還沒標 OK）────────────────────────────────────────────────
    # 第 5 題年齡沒有問句：跟第 4 題性別同一句問，前置條件也跟第 4 題一樣。
    "其它": (
        EmsQuestion("主訴", "chief_complaint", MODE_ACTIVE,
                    "其它-主訴", "請問患者是身體不舒服，還是受傷？"),
        EmsQuestion("患者人數", "patient_count", MODE_PASSIVE, "其它-患者人數"),
        EmsQuestion("報案身分", "caller_relation", MODE_ACTIVE,
                    "其它-報案身分", "請問你認識患者嗎？"),
        EmsQuestion("性別", "patient_gender", MODE_CONDITIONAL,
                    "其它-性別", "請問患者是男生還是女生？大概幾歲？",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("年齡", "patient_age", MODE_CONDITIONAL,
                    "其它-年齡", "",
                    _on_scene_or_family_friend, _GENDER_AGE_TEXT),
        EmsQuestion("意識", "consciousness_level", MODE_CONDITIONAL,
                    "其它-意識", "他現在人清醒嗎？叫他有沒有反應？",
                    _not_self_on_scene_or_unmentioned,
                    "報案身分 ≠ 本人 且 報案人位置 = 未提到、在現場"),
        EmsQuestion("呼吸", "breathing", MODE_CONDITIONAL,
                    "其它-呼吸", "他還有沒有呼吸？胸部有沒有一上一下起伏呢？",
                    _consciousness_unresponsive, _UNRESPONSIVE_TEXT),
        EmsQuestion("病史", "medical_history", MODE_PASSIVE, "其它-病史"),
        EmsQuestion("現場進入條件", "scene_access", MODE_PASSIVE, "其它-現場進入條件"),
        EmsQuestion("是否飲酒", "drinking_status", MODE_PASSIVE, "其它-是否飲酒"),
        EmsQuestion("平常行動能力", "mobility", MODE_PASSIVE, "其它-平常行動能力"),
        EmsQuestion("報案人位置", "caller_location", MODE_PASSIVE, "其它-報案人位置"),
    ),
}


def questions_for_subtype(sub_category: Optional[str]) -> Tuple[EmsQuestion, ...]:
    """這個救護次案類的題目表；還沒照 xlsx 改寫的次案類回傳空的。"""
    return EMS_QUESTIONS.get(sub_category or "", ())
