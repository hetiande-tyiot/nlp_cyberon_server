"""addrCheck hint 解析 + 地址詢問話術（119 客製，vendor 版沒有）。

換版時整檔複製即可，不需要逐行 port。引擎只需接三個入口：
`parse_address_hint()` / `build_hint_question()` / `should_ask_floor()`。

addrCheck /Verify 的 hint 是給人看的自然語言，格式由 API 端決定。
本模組把它解析成「下一步該問什麼」，解析失敗一律退回泛用問句，
不讓 API 改文案就弄壞整條地址流程。

2026-09-04 實測的五種 hint（reason 不足以區分，必須解析 hint）：
  road_only  「新北市板橋區大華街2號」查無此門牌；同路段鄰近門牌為
              新北市板橋區大華街1號、…、新北市板橋區大華街7號，請向報案人確認號碼。
  road_only  「土城區中央路」分成 一段、二段、三段、四段，請追問是哪一段以及門牌號碼。
  road_only  已確認路名「新北市板橋區大華街」，請追問門牌號碼。
  not_found  查無「中央路三段二十六」，是否為 新北市土城區中央路？
  not_found  查無「不存在路」這條路，請向報案人重新確認路名。
  ambiguous  「重陽路」的 一段、二段、四段 都有 1 號，是不同的地點，請追問報案人是哪一段。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

# ── hint 類型 ────────────────────────────────────────────────────────────────
# nearby_numbers  同路段有其他門牌 → 門牌號報錯了
# need_section    路名對但沒講第幾段
# need_number     路名已確認，缺門牌號
# road_suggestions 路名對不上，API 給了相近路名
# road_unknown    路名查無且無建議
# generic         解析不出來 → 泛用問句
HINT_KINDS = (
    "nearby_numbers",
    "need_section",
    "need_number",
    "road_suggestions",
    "road_in_districts",
    "road_unknown",
    "generic",
)

_NUMBER_TOKEN = r"[零〇一二三四五六七八九十百千兩\d]+(?:之[零〇一二三四五六七八九十百千兩\d]+)?"

# 「…同路段鄰近門牌為 A、B、C，請向報案人確認號碼。」
_NEARBY_RE = re.compile(r"同路段鄰近門牌為\s*([^，。]+)")
# 「「土城區中央路」分成 一段、二段、三段、四段，請追問…」
_SECTION_RE = re.compile(r"「([^」]+)」\s*分成\s*([^，。]+)")
# reason=ambiguous：「「重陽路」的 一段、二段、四段 都有 1 號，是不同的地點…」
# 同一門牌號在多個段都存在——不追問就會派錯段。
_AMBIGUOUS_SECTION_RE = re.compile(r"「([^」]+)」\s*的\s*([^，。]+?)\s*都有")
# 「已確認路名「新北市板橋區大華街」，請追問門牌號碼。」
_CONFIRMED_ROAD_RE = re.compile(r"已確認路名「([^」]+)」")
# 「查無「中央路三段二十六」，是否為 A、B？」
_SUGGEST_RE = re.compile(r"查無「([^」]+)」\s*，\s*是否為\s*([^？?。]+)")
# 「查無「不存在路」這條路，請向報案人重新確認路名。」
_ROAD_UNKNOWN_RE = re.compile(r"查無「([^」]+)」\s*這條路")
# 門牌尾段：從「…大華街1號」取出「1號」、「…6弄5號之1」取出「5號之1」
_TAIL_NUMBER_RE = re.compile(
    rf"([零〇一二三四五六七八九十百千兩\d]+號(?:之[零〇一二三四五六七八九十百千兩\d]+)?)$"
)
# 行政區前綴：把「新北市土城區中央路」縮成「中央路」，問話才不會又臭又長
_CITY_DISTRICT_PREFIX_RE = re.compile(
    r"^(?:[一-鿿]{2,3}[市縣])?([一-鿿]{1,4}區)"
)


@dataclass(frozen=True)
class AddressHintAdvice:
    """hint 解析結果：下一步該問什麼。"""

    kind: str = "generic"
    numbers: Tuple[str, ...] = ()       # nearby_numbers：可選門牌
    sections: Tuple[str, ...] = ()      # need_section：可選段別
    suggestions: Tuple[str, ...] = ()   # road_suggestions：建議路名
    road: Optional[str] = None          # need_number / need_section 的路名
    districts: Tuple[str, ...] = ()     # road_in_districts：同名路分佈的行政區
    unknown_text: Optional[str] = None  # 報案人講的、查不到的片段

    @property
    def is_parsed(self) -> bool:
        return self.kind != "generic"


def _split_items(text: str) -> List[str]:
    """拆「A、B、C」，順便去空白。"""
    return [item.strip() for item in re.split(r"[、,，]", text or "") if item.strip()]


def strip_district_prefix(value: str) -> str:
    """去掉「新北市土城區」這類前綴，只留路名部分。"""
    return _CITY_DISTRICT_PREFIX_RE.sub("", (value or "").strip()).strip() or value


def split_district_and_road(value: str) -> Tuple[Optional[str], str]:
    """拆成 (行政區, 路名)；沒有行政區時第一項為 None。"""
    text = (value or "").strip()
    match = _CITY_DISTRICT_PREFIX_RE.match(text)
    if not match:
        return None, text
    return match.group(1), text[match.end():].strip() or text


def parse_address_hint(hint: Optional[str]) -> AddressHintAdvice:
    """把 addrCheck 的 hint 解析成結構化建議。

    解析不出來時回 kind="generic"，呼叫端退回泛用問句。
    """
    text = (hint or "").strip()
    if not text:
        return AddressHintAdvice()

    match = _NEARBY_RE.search(text)
    if match:
        numbers: List[str] = []
        for item in _split_items(match.group(1)):
            tail = _TAIL_NUMBER_RE.search(item)
            if tail:
                numbers.append(tail.group(1))
        if numbers:
            return AddressHintAdvice(
                kind="nearby_numbers", numbers=tuple(dict.fromkeys(numbers))
            )

    match = _SECTION_RE.search(text)
    if match:
        sections = tuple(_split_items(match.group(2)))
        if sections:
            return AddressHintAdvice(
                kind="need_section",
                sections=sections,
                road=strip_district_prefix(match.group(1)),
            )

    match = _AMBIGUOUS_SECTION_RE.search(text)
    if match:
        sections = tuple(_split_items(match.group(2)))
        if sections:
            return AddressHintAdvice(
                kind="need_section",
                sections=sections,
                road=strip_district_prefix(match.group(1)),
            )

    match = _CONFIRMED_ROAD_RE.search(text)
    if match:
        return AddressHintAdvice(
            kind="need_number", road=strip_district_prefix(match.group(1))
        )

    match = _SUGGEST_RE.search(text)
    if match:
        items = _split_items(match.group(2))
        pairs = [split_district_and_road(item) for item in items]
        roads = [road for _district, road in pairs]
        districts = tuple(
            dict.fromkeys(d for d, _r in pairs if d)
        )
        # 同一條路名分佈在多個區：該問的是「哪一區」而不是「哪條路」。
        if len(items) > 1 and len(set(roads)) == 1 and len(districts) > 1:
            return AddressHintAdvice(
                kind="road_in_districts",
                districts=districts,
                road=roads[0],
                unknown_text=match.group(1).strip(),
            )
        if roads:
            return AddressHintAdvice(
                kind="road_suggestions",
                suggestions=tuple(dict.fromkeys(roads)),
                unknown_text=match.group(1).strip(),
            )

    match = _ROAD_UNKNOWN_RE.search(text)
    if match:
        return AddressHintAdvice(
            kind="road_unknown", unknown_text=match.group(1).strip()
        )

    return AddressHintAdvice()


# ── 地標／捷運的模糊比對 ─────────────────────────────────────────────────────
# addrCheck 的地標比對沒有相似度門檻：只要含「市場」「捷運」「站」這類通用詞
# 就會硬配一個最相近的地標並回 status=true。實測：
#   「捷運不存在站出口9」→ 捷運亞東醫院站2號出口
#   「未知市場旁邊」     → 市場 → 文山區景隆街2號附近（跨到臺北市）
# API 自己的 hint 就寫著「若不確定請向報案人確認是否為此處」，
# 所以模糊配出來的地標一律當猜測，必須覆誦確認，不得靜默採用。
_FUZZY_MARK = "（模糊比對）"
# 「地標：大觀市場 → 新北市板橋區大觀市場」
_LANDMARK_PAIR_RE = re.compile(r"地標：\s*([^→、。]+?)\s*→\s*([^。、]+)")
# 「其他可能：地標：大觀國中、地標：大觀國小。」
_LANDMARK_ALT_RE = re.compile(r"其他可能：\s*([^。]+)")
_LANDMARK_NAME_RE = re.compile(r"地標：\s*([^、。]+)")


@dataclass(frozen=True)
class LandmarkMatch:
    """地標比對結果；is_fuzzy=True 代表是猜的，必須向報案人確認。"""

    is_fuzzy: bool = False
    matched: Optional[str] = None       # 配到的地標名
    resolved: Optional[str] = None      # 對應到的地址
    alternatives: Tuple[str, ...] = ()  # API 提供的其他可能


def parse_landmark_hint(hint: Optional[str]) -> LandmarkMatch:
    """解析地標/捷運驗測的 hint，判斷是否為模糊比對。"""
    text = (hint or "").strip()
    if not text:
        return LandmarkMatch()
    is_fuzzy = _FUZZY_MARK in text
    matched = resolved = None
    pair = _LANDMARK_PAIR_RE.search(text)
    if pair:
        matched = pair.group(1).strip()
        resolved = pair.group(2).strip()
    alternatives: Tuple[str, ...] = ()
    alt = _LANDMARK_ALT_RE.search(text)
    if alt:
        alternatives = tuple(
            dict.fromkeys(
                name.strip()
                for name in _LANDMARK_NAME_RE.findall(alt.group(1))
                if name.strip() and name.strip() != matched
            )
        )
    return LandmarkMatch(
        is_fuzzy=is_fuzzy,
        matched=matched,
        resolved=resolved,
        alternatives=alternatives,
    )


def build_landmark_confirm_question(match: LandmarkMatch) -> str:
    """模糊配到的地標要讓報案人有機會否認。"""
    target = match.matched or match.resolved or "這個地點"
    if match.resolved and match.matched and match.resolved != match.matched:
        target = f"{match.matched}（{match.resolved}）"
    return f"我這邊找到的是{target}，是這裡嗎？"


# ── valid 時 API 回傳的正規化地址 ──────────────────────────────────────────
# addrCheck 驗證通過時，hint 會帶回它認可的標準地址；若做過讀音修正還會
# 明說修成什麼。採用它比留著報案人的口語原文更適合派遣，也比本地
# map_street.json 安全——API 有把握（「本轄同音路名僅此一條」）才修。
#   地址有效：新北市土城區中央路三段61巷2號
#   「南亞南路二段15號」查無此路名，已依讀音修正為「新北市板橋區南雅南路二段15號」（本轄同音路名僅此一條）
_NORMALIZED_RE = re.compile(r"已依讀音修正為「([^」]+)」")
_SPOKEN_IN_HINT_RE = re.compile(r"^「([^」]+)」查無此路名")


def phonetic_correction_note(hint: Optional[str]) -> Optional[str]:
    """addrCheck 依讀音改過地址時，給受理員的提示；沒改就回 None。

    API 的 hint 自己就寫著這個修正無法用複誦確認：
        「永鎮路128號」查無此路名，已依讀音修正為「新北市永和區永貞路128號」
        （本轄同音路名僅此一條）。注意：兩者讀音相同，向報案人複述路名
        無法分辨，如需確認請改問門牌號、樓層或附近路口。

    所以覆誦得到的「對」不具鑑別力——受理員要知道這個路名是系統改的。
    只在「本轄同音路名僅此一條」時 API 才會修，所以不必因此攔下流程，
    標記出來就好。
    """
    text = hint or ""
    normalized = _NORMALIZED_RE.search(text)
    if not normalized:
        return None
    spoken = _SPOKEN_IN_HINT_RE.search(text)
    said = spoken.group(1) if spoken else "報案人講的路名"
    note = f"系統依讀音將「{said}」修正為「{normalized.group(1)}」"
    if "讀音相同" in text:
        note += "；兩者讀音相同，覆誦無法分辨，如需確認請問門牌號或附近路口"
    return note
_VALID_ADDRESS_RE = re.compile(r"地址有效：\s*([^\s，。（(]+)")
# 樓層要自己接回去——addrCheck 不處理樓層
_FLOOR_TAIL_RE = re.compile(
    r"((?:地下)?[零〇一二三四五六七八九十百千兩\d]+樓"
    r"(?:之[零〇一二三四五六七八九十百千兩\d]+)?|[Bb][0-9]+(?:[Ff])?)"
)


def normalized_address_from_hint(
    hint: Optional[str], *, spoken: Optional[str] = None
) -> Optional[str]:
    """從 valid 的 hint 取出 API 認可的標準地址；接回原本講的樓層。

    解析不出來回 None（呼叫端保留原地址）。
    """
    text = (hint or "").strip()
    if not text:
        return None
    match = _NORMALIZED_RE.search(text) or _VALID_ADDRESS_RE.search(text)
    if not match:
        return None
    address = match.group(1).strip()
    if not address:
        return None
    floor = _FLOOR_TAIL_RE.search(spoken or "")
    if floor and floor.group(1) not in address:
        address += floor.group(1)
    return address


# ── 話術 ─────────────────────────────────────────────────────────────────────
# 原本三種失敗共用一句「地址無法確認，請重新提供完整正確的事發地點。」，
# 太僵硬也不像人講話；依 hint 拆成各自的說法。
GENERIC_ADDRESS_RETRY = "不好意思，地址我這邊對不起來，麻煩再說一次事發地點？"
ASK_DISTRICT = "請問是哪一區？"
ASK_ROAD = "請問是什麼路？"
ASK_NUMBER = "請問是幾號？"
ASK_FLOOR = "請問是幾樓？"
GUIDED_OPENING = "我們一項一項來，請問是哪一區？"


def _join_options(items: Sequence[str], limit: int = 3) -> str:
    return "、".join(items[:limit])


def build_hint_question(
    advice: AddressHintAdvice,
    *,
    spoken_number: Optional[str] = None,
) -> str:
    """依 hint 建議產生下一句問話；解析不出來時回泛用問句。

    spoken_number 是報案人講過的門牌號，用來說「好像沒有3號」。
    """
    if advice.kind == "nearby_numbers":
        if spoken_number:
            return f"這條路好像沒有{spoken_number}欸，麻煩再幫我看一下門牌？"
        return "這個門牌號碼我這邊查不到，麻煩再幫我看一下門牌？"

    if advice.kind == "need_section":
        road = advice.road or "這條路"
        if advice.sections:
            return f"{road}有分{_join_options(advice.sections, 4)}，請問是哪一段？"
        return f"{road}請問是哪一段？"

    if advice.kind == "need_number":
        return ASK_NUMBER

    if advice.kind == "road_suggestions":
        options = _join_options(advice.suggestions)
        unknown = advice.unknown_text
        if unknown:
            return f"這邊查不到{unknown}，是{options}嗎？"
        return f"請問是{options}嗎？"

    if advice.kind == "road_in_districts":
        road = advice.road or "這條路"
        return (
            f"{road}有好幾個區都有，"
            f"請問是{_join_options(advice.districts, 4)}？"
        )

    if advice.kind == "road_unknown":
        return "這條路我這邊查不到，麻煩再說一次路名？"

    return GENERIC_ADDRESS_RETRY


# ── 「不知道」不等於「對」 ────────────────────────────────────────────────
# parse_yes_no("不知道") 回 None（既非肯定也非否定）。猜測的確認若採用
# 「不是明確否認就當確認」，報案人一句「不知道」就會讓系統把猜測當成事實。
# 地址攸關派遣，這種模稜兩可一律不採用猜測。
_UNCERTAIN_TOKENS = (
    "不知道", "不知", "不清楚", "不確定", "不确定", "沒印象", "没印象",
    "不曉得", "不晓得", "不太確定", "不太清楚", "說不上來", "很難說",
)


def is_uncertain_answer(text: Optional[str]) -> bool:
    """報案人是否答不上來（有別於明確的是／否）。"""
    value = re.sub(r"\s+", "", text or "")
    return any(token in value for token in _UNCERTAIN_TOKENS)


# ── 是否追問樓層 ─────────────────────────────────────────────────────────────
# 之後要加情況（山區、工地、橋下…），在 FLOOR_SUPPRESS_RULES 加一列即可，
# 不必改流程碼。命中的規則名會回傳出去，方便從 log 看出為什麼沒問樓層。
FloorRule = Tuple[str, Callable[[object], bool]]


def _location_type_is_non_building(case: object) -> bool:
    return getattr(case, "location_type", None) in {"intersection", "highway", "mrt"}


def _fire_is_non_building(case: object) -> bool:
    return getattr(case, "non_building_fire", None) is not None


FLOOR_SUPPRESS_RULES: Tuple[FloorRule, ...] = (
    ("非建築地點型態", _location_type_is_non_building),
    ("火警非建築物", _fire_is_non_building),
)


def floor_suppress_reason(
    case: object,
    *,
    extra_rules: Sequence[FloorRule] = (),
) -> Optional[str]:
    """命中任一規則就回規則名（代表不問樓層），都沒命中回 None。

    landmark 刻意不列入：地標型態裡大樓、醫院佔多數，仍需要樓層。
    """
    for name, predicate in tuple(FLOOR_SUPPRESS_RULES) + tuple(extra_rules):
        try:
            if predicate(case):
                return name
        except Exception:
            continue
    return None
