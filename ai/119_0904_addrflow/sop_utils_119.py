"""
sop_utils_119.py
━━━━━━━━━━━━━━━━━
119 報案受理 — 規則備援工具（LLM 不可用或抽取失敗時使用）
"""

from __future__ import annotations

import re
from typing import Dict, List, Literal, Optional, Tuple

from subcategory_keywords_119 import RESCUE_SUBCATEGORY_KEYWORDS


def format_qa_for_llm(question: str, answer: str) -> str:
    """將本輪受理員問題與報警人回答打包，供 LLM 抽取短答（是/对/没有）。"""
    q = (question or "").strip()
    a = (answer or "").strip()
    if q:
        return f"受理員問題：{q}\n報警人回答：{a}"
    return a


def parse_yes_no(text: str) -> Optional[bool]:
    """
    規則判斷是/否（LLM 備援）。
    適用短答：是、是的、对、對、沒錯、不是、不對 等。
    """
    s = (text or "").strip()
    if not s:
        return None
    # 否定優先（「沒有」含「有」）
    if any(x in s for x in ("沒有", "没有", "沒意識", "没意识", "無意識", "无意识",
                            "不是", "不對", "不对", "否", "不要", "不用", "昏迷", "叫不醒")):
        return False
    if s in {
        "是", "對", "对", "沒錯", "没错", "正確", "正确", "嗯", "好", "好的",
        "是的", "對的", "对的", "是啊", "對啊", "对啊", "可以", "沒問題", "没问题",
        "OK", "ok", "Ok", "有", "有的",
    }:
        return True
    if s in {"不是", "不對", "不对", "否", "不要", "不用", "無", "不需要", "沒有", "没有"}:
        return False
    if len(s) <= 8:
        if any(s.startswith(x) for x in ("是", "對", "对", "嗯", "好", "有")) and "不" not in s:
            return True
    # 「是，清醒」「对，有呼吸」等
    if re.search(r"^(?:是|對|对|有)[，,]?\s*\S+", s) and "不" not in s[:3]:
        return True
    return None


def parse_yes_no_for_question(question: str, answer: str) -> Optional[bool]:
    """
    結合本輪受理員問題語義，從報警人回答（可為長句）判斷是/否。

    報警人常見模式：先描述病情，句末再補「是，清醒」「有，還在呼吸」。
    注意：合問（意識+呼吸）時勿用此函式同時填兩個欄位，應改用 parse_vital_slot。
    """
    q = (question or "").strip()
    s = (answer or "").strip()
    if not s:
        return None

    # 短答
    if len(s) <= 10:
        v = parse_yes_no(s)
        if v is not None:
            return v

    # 取最後一個分句（句末常才是對問題的直接回答）
    clauses = re.split(r"[。！？!?；;]", s)
    clauses = [c.strip() for c in clauses if c.strip()]
    for clause in reversed(clauses[-3:]):  # 檢查最後 1~3 個分句
        v = parse_yes_no(clause)
        if v is not None:
            return v
        if re.search(r"(?:是|對|对|有)[，,]\s*\S+", clause) and "不" not in clause[:4]:
            return True

    # 依問題語義在全文搜尋（長答中夾雜病情描述時）
    if any(k in q for k in ("意識", "意识", "清醒")):
        slot_val = parse_vital_slot("consciousness", s, q)
        if slot_val is not None:
            return slot_val

    if any(k in q for k in ("呼吸",)):
        slot_val = parse_vital_slot("breathing", s, q)
        if slot_val is not None:
            return slot_val

    if any(k in q for k in ("起伏", "肚子", "腹部")):
        slot_val = parse_vital_slot("abdomen_rise", s, q)
        if slot_val is not None:
            return slot_val

    # 叫/捏反應類（S2 選項）
    if any(k in q for k in ("反應", "反应", "捏", "肩膀")):
        slot_val = parse_vital_slot("consciousness", s, q)
        if slot_val is not None:
            return slot_val

    # 確認類問題（地址/摘要）
    if any(k in q for k in ("確定", "是否", "對嗎", "正確", "以上")):
        return parse_yes_no(clauses[-1] if clauses else s)

    return None


def _has_negated_core(text: str, cores: tuple) -> bool:
    """
    是否出現對核心詞的否定，如「沒有清醒」「沒有正常呼吸」「不是清醒」。

    必須先於肯定匹配，避免「沒有清醒」因含「清醒」被誤判為 True。
    """
    s = text or ""
    neg_prefixes = (
        "沒有", "没有", "無", "无", "不", "沒", "没", "不是", "並非", "并非",
        "並無", "并无", "並未", "并未",
    )
    for core in cores:
        if not core:
            continue
        # 緊貼否定：沒有清醒 / 無呼吸
        for neg in neg_prefixes:
            if f"{neg}{core}" in s:
                return True
        # 中間可有簡短修飾：沒有正常呼吸、沒有在呼吸、不是很清醒
        for neg in ("沒有", "没有", "無", "无", "不", "沒", "没", "不是"):
            if re.search(re.escape(neg) + r".{0,6}" + re.escape(core), s):
                return True
    return False


def _has_unnegated_token(text: str, tokens: tuple) -> bool:
    """文本是否含未被否定前綴修飾的 token。"""
    s = text or ""
    neg_tails = ("沒有", "没有", "無", "无", "不", "沒", "没", "不是")
    for token in tokens:
        if not token:
            continue
        start = 0
        while True:
            i = s.find(token, start)
            if i < 0:
                break
            prefix = s[max(0, i - 4):i]
            if any(prefix.endswith(n) for n in neg_tails):
                start = i + 1
                continue
            # 再擋「沒有正常呼吸」這類：token 前 6 字內有否定
            window = s[max(0, i - 6):i]
            if any(n in window for n in ("沒有", "没有", "無", "无", "不是")):
                start = i + 1
                continue
            return True
    return False


def parse_vital_slot(
    slot: str,
    answer: str,
    question: str = "",
) -> Optional[bool]:
    """
    依單一生命征象欄位語義判斷是/否。

    避免合問時把「意識清醒」誤寫進 breathing，或把短答「有」同時灌進所有欄位。
    否定優先：沒有清醒 / 沒有正常呼吸 → False（不可因含「清醒」「正常呼吸」誤判 True）。
    """
    s = (answer or "").strip()
    q = (question or "").strip()
    if not s:
        return None

    if slot == "consciousness":
        if _has_negated_core(s, ("清醒", "意識", "意识", "反應", "反应")) or any(
            k in s for k in ("昏迷", "叫不醒", "無意識", "无意识")
        ):
            return False
        if _has_unnegated_token(s, (
            "意識清醒", "意识清醒", "清醒", "有意識", "有意识", "還清醒", "还清醒",
            "是清醒", "會回應", "会回应", "會睜眼", "会睁眼", "睜得開",
            "有反應", "有反应", "會動", "会动", "能動", "能动", "能打開", "能打开",
            "會發出聲音", "会发出声音", "是，清醒", "對，清醒",
        )):
            return True
        # 短答：反應題可接受「有/能」；意識+呼吸合問則需明確意識詞，避免誤填
        asks_reaction = any(k in q for k in ("反應", "反应", "捏", "肩膀"))
        asks_c = any(k in q for k in ("意識", "意识", "清醒"))
        only_breathing = ("呼吸" in s) and not any(
            k in s for k in ("清醒", "意識", "意识", "反應", "反应")
        )
        if only_breathing:
            return None
        if asks_reaction and len(s) <= 12:
            return parse_yes_no(s)
        if asks_c and "呼吸" not in q and len(s) <= 12:
            return parse_yes_no(s)
        return None

    if slot == "breathing":
        if _has_negated_core(s, ("呼吸", "正常呼吸")) or any(
            k in s for k in ("停止呼吸", "呼吸停止", "沒在呼吸", "没在呼吸")
        ):
            return False
        if _has_unnegated_token(s, (
            "有呼吸", "還在呼吸", "还在呼吸", "在呼吸", "會呼吸", "会呼吸",
            "正常呼吸", "是，有呼吸", "有，在呼吸", "有，還在呼吸",
        )):
            return True
        # 僅當本輪問題只問呼吸時，才接受短答；合問需明確呼吸詞
        asks_breathing = "呼吸" in q
        asks_consciousness = any(k in q for k in ("意識", "意识", "清醒"))
        if asks_breathing and not asks_consciousness and len(s) <= 12:
            return parse_yes_no(s)
        return None

    if slot == "abdomen_rise":
        if _has_negated_core(s, ("起伏", "動", "动")) or any(
            k in s for k in ("肚子不動", "不會動", "不会动")
        ):
            return False
        if _has_unnegated_token(s, (
            "有起伏", "還在起伏", "还在起伏", "肚子有動", "腹部有起伏", "有在動", "有在动",
        )):
            return True
        if any(k in q for k in ("起伏", "肚子", "腹部")) and len(s) <= 12:
            return parse_yes_no(s)
        # 叫/捏反應問題：有反應視為通過 S2（與腹部起伏同等之生命征象檢查點）
        if any(k in q for k in ("反應", "反应", "捏", "肩膀")):
            c = parse_vital_slot("consciousness", s, q)
            if c is not None:
                return c
        return None

    return None


def extract_vital_signs_hint(text: str) -> dict:
    """
    規則備援：從報警人原話抽取生命征象（不依賴受理員問題）。

    適用首輪長答已說明「意識清醒」「有呼吸」等，後續應對應跳過。
    """
    s = (text or "").strip()
    if not s:
        return {}
    out: dict = {}
    for slot in ("consciousness", "breathing", "abdomen_rise"):
        val = parse_vital_slot(slot, s, question="")
        if val is not None:
            out[slot] = val
    return out


def is_reaction_vital_question(question: str) -> bool:
    """是否為叫/捏反應類 S2 問題（非腹部起伏）。"""
    q = question or ""
    if any(k in q for k in ("起伏", "肚子", "腹部")):
        return False
    return any(k in q for k in ("反應", "反应", "捏", "肩膀"))


_CN_DIGIT = {
    "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
    "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
}


def extract_pregnancy_info_hint(text: str) -> dict:
    """
    規則備援：從報警人原話抽取孕婦急產相關欄位。

    適用長答一次帶多項，如：
    「39歲，第一胎，39週，預產期5月6日，單胞胎，產檢都正常」
    """
    s = (text or "").strip()
    if not s:
        return {}
    out: dict = {}

    m_age = re.search(r"(\d{1,3})\s*歲", s)
    if m_age:
        out["patient_age"] = f"{m_age.group(1)}歲"

    parity = None
    if any(k in s for k in ("初產", "頭胎", "第一胎", "第1胎")):
        parity = "第1胎"
    else:
        m_p = re.search(r"第\s*([一二三四五六七八九十\d]+)\s*胎", s)
        if m_p:
            raw = m_p.group(1).strip()
            num = _CN_DIGIT.get(raw, raw if raw.isdigit() else None)
            parity = f"第{num}胎" if num else f"第{raw}胎"

    week = None
    m_w = re.search(r"(\d{1,2})\s*週", s)
    if m_w:
        week = f"{m_w.group(1)}週"

    if parity and week:
        out["pregnancy_week"] = f"{parity}{week}"
    elif parity:
        out["pregnancy_week"] = parity
    elif week:
        out["pregnancy_week"] = week

    m_due = re.search(r"預產期\s*[是為：: ]*\s*([^，,。；;]+)", s)
    if m_due:
        due = re.sub(r"\s+", "", m_due.group(1).strip())
        if due and due not in {"不清楚", "不知道", "不確定", "不确定"}:
            out["due_date"] = due

    if any(k in s for k in ("單胞胎", "單胎")):
        out["multiple_pregnancy"] = "單胞胎"
    elif "多胞胎" in s:
        out["multiple_pregnancy"] = "多胞胎"
    elif any(k in s for k in ("雙胞胎", "雙胎")):
        out["multiple_pregnancy"] = "雙胞胎"

    if "產檢" in s:
        if any(k in s for k in ("都正常", "產檢正常", "無異常", "没異常", "沒異常", "没有异常")):
            out["prenatal_history"] = "產檢無異常"
        elif any(k in s for k in ("子癲", "妊娠糖尿病", "異常", "高危", "高危險")):
            # 取含「產檢」分句作簡述
            for part in re.split(r"[，,。；;]", s):
                if "產檢" in part and any(
                    k in part for k in ("異常", "子癲", "糖尿病", "高危")
                ):
                    out["prenatal_history"] = part.strip()[:40]
                    break

    if any(k in s for k in ("破水", "羊水破")) or "出血" in s or "流血" in s:
        has_water = any(k in s for k in ("破水", "羊水破")) and not _has_negated_core(
            s, ("破水", "羊水")
        )
        has_bleed = any(k in s for k in ("出血", "流血")) and not _has_negated_core(
            s, ("出血", "流血")
        )
        no_water = _has_negated_core(s, ("破水",)) or any(
            k in s for k in ("沒破水", "没有破水", "無破水")
        )
        no_bleed = _has_negated_core(s, ("出血", "流血")) or any(
            k in s for k in ("沒出血", "没有出血", "無出血")
        )
        if no_water and no_bleed:
            out["water_broken_bleeding"] = "無破水無出血"
        elif has_water or has_bleed or no_water or no_bleed:
            parts = []
            if has_water:
                parts.append("有破水")
            elif no_water:
                parts.append("無破水")
            if has_bleed:
                parts.append("有出血")
            elif no_bleed:
                parts.append("無出血")
            if parts:
                out["water_broken_bleeding"] = "，".join(parts)

    m_clinic = re.search(
        r"(?:在|於)?\s*([\u4e00-\u9fff]{2,12}(?:醫院|診所|婦產科|產檢所))\s*(?:產檢|看診)?",
        s,
    )
    if m_clinic and "產檢" in s:
        out["prenatal_clinic"] = m_clinic.group(1).strip()

    return out


# ── 患者語境推斷（規則備援，S6 前 deterministic 執行）────────────────────────

_SELF_SALUTATION_RE = re.compile(
    r"(?:我(?:是|叫)|稱呼(?:我|為)?|叫我)\s*(?:一位)?\s*(?:先生|小姐|女士)"
)
_THIRD_PARTY_MALE_RE = re.compile(
    r"(?:一位|有个|有個|有个|這位|这位|那位|路倒(?:的|了)?|倒(?:在|了)?(?:路(?:边|邊))?)"
    r"(?:的)?\s*(?:先生|男士|男性|男生|阿伯|大爷|大爺)"
)
_THIRD_PARTY_FEMALE_RE = re.compile(
    r"(?:一位|有个|有個|這位|这位|那位|路倒(?:的|了)?|倒(?:在|了)?(?:路(?:边|邊))?)"
    r"(?:的)?\s*(?:女士|小姐|女性|女生|阿姨|婆婆)"
)
# 簡化：句中「X先生/女士」且非自称
_HONORIFIC_MALE_RE = re.compile(
    r"(?<![是我叫])"
    r"(?:一位|有个|有個|這位|这位|那位|倒(?:在|了)?)\s*"
    r"(?:先生|男士)"
)
_HONORIFIC_FEMALE_RE = re.compile(
    r"(?<![是我叫])"
    r"(?:一位|有个|有個|這位|这位|那位|倒(?:在|了)?)\s*"
    r"(?:女士|小姐)"
)

_CALLER_IS_PATIENT_TRUE = re.compile(
    r"(?:"
    r"我(?:自己|本人)|是我(?:的|在)?|"
    r"我(?:割腕|吞(?:了)?藥|吞(?:了)?药|受傷|受伤|跌倒|昏倒)|"
    r"頭(?:很)?痛|头(?:很)?痛|胸口(?:很)?痛|胸(?:很)?痛|呼吸(?:很)?困難|"
    r"想(?:不開|不开)|上吊|燒炭|烧炭|喝(?:了)?藥|喝(?:了)?药"
    r")"
)
_CALLER_IS_PATIENT_FALSE = re.compile(
    r"(?:"
    r"我(?:媽|妈|爸|父|母|先生|老婆|丈夫|孩子|兒|儿|女|朋友|同事|鄰居|邻居)|"
    r"(?:一位|有个|有個|這位|这位|那位|帮我|幫我|幫朋友|帮朋友)|"
    r"(?:家屬|家属|路人|旁邊|旁边)(?:協助|协助)?(?:報案|报案)?"
    r")"
)

_PATIENT_COUNT_RE = re.compile(
    r"(\d+)\s*(?:位|个|個|名|人)|"
    r"(?:两|兩|三|四|五|六|七|八|九|十)\s*(?:位|个|個|名|人)|"
    r"(?:两|兩|三|四|五|六|七|八|九|十)(?:个人|個人)"
)
_CN_NUM = {"一": 1, "两": 2, "兩": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def infer_patient_gender_from_honorific(text: str) -> Optional[str]:
    """
    從報警人原話推斷患者性別（第三人称称谓）。
    「我是先生」等报案人自称不推断 patient_gender。
    """
    s = (text or "").strip()
    if not s:
        return None
    if _SELF_SALUTATION_RE.search(s):
        return None
    if (
        _THIRD_PARTY_MALE_RE.search(s)
        or _HONORIFIC_MALE_RE.search(s)
        or re.search(r"(?<![是我叫])一位先生", s)
    ):
        return "男"
    if (
        _THIRD_PARTY_FEMALE_RE.search(s)
        or _HONORIFIC_FEMALE_RE.search(s)
        or re.search(r"(?<![是我叫])一位女士", s)
    ):
        return "女"
    return None


def infer_caller_is_patient(text: str) -> Optional[bool]:
    """推断报案人是否即患者。不确定返回 None。"""
    s = (text or "").strip()
    if not s:
        return None
    if _CALLER_IS_PATIENT_FALSE.search(s):
        return False
    if _CALLER_IS_PATIENT_TRUE.search(s):
        return True
    return None


def parse_patient_count(value: Optional[str]) -> Optional[int]:
    """将 patient_count 字符串解析为整数。"""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"(\d+)", s)
    if m:
        n = int(m.group(1))
        return n if n > 0 else None
    m = _PATIENT_COUNT_RE.search(s)
    if m and m.group(1):
        return int(m.group(1))
    for cn, n in _CN_NUM.items():
        if cn in s and ("人" in s or "位" in s or "个" in s or "個" in s):
            return n
    if s in ("1", "一", "一个", "一個", "一位", "1位", "1人"):
        return 1
    return None


def extract_patient_info_hint(text: str) -> dict:
    """
    規則備援（僅在 LLM 不可用時使用）：從報警人原話抽取患者性別/年齡/事件/現況。
    正常流程以 LLM 跨欄位抽取為準，不應依賴本函式寫入業務欄位。
    """
    s = (text or "").strip()
    if not s:
        return {}
    out: dict = {}

    if re.search(r"(男性|男生|男患者|是男|男的)", s):
        out["patient_gender"] = "男"
    elif re.search(r"(女性|女生|女患者|是女|女的)", s):
        out["patient_gender"] = "女"
    else:
        honorific_gender = infer_patient_gender_from_honorific(s)
        if honorific_gender:
            out["patient_gender"] = honorific_gender

    m_age = re.search(r"(\d{1,3})\s*[歲岁]", s)
    if m_age:
        out["patient_age"] = f"{m_age.group(1)}歲"

    # 事件經過：醫療/意外描述
    incident = None
    for pat in (
        r"(?:昨天|今天|剛剛|方才)[^。！？]{0,40}(?:大腸鏡|車禍|跌倒|昏倒|受傷|出血|便血)",
        r"大腸鏡檢查[^。！？]{0,20}(?:出血|便血)",
        r"(?:車禍|意外|跌倒|昏倒|受傷)[^。！？]{0,30}",
    ):
        m = re.search(pat, s)
        if m:
            incident = re.split(r"[。！？]", m.group(0).strip())[0].strip()
            break
    if not incident and "大腸鏡" in s and ("出血" in s or "便血" in s):
        incident = "大腸鏡檢查後便血"
    if incident and len(incident) >= 4:
        out["incident_description"] = incident[:40]

    cond_kws = []
    for kw in (
        "頭暈", "胸悶", "呼吸困難", "昏迷", "意識不清", "虛弱",
        "流血較多", "出血不止", "疼痛", "噁心", "嘔吐",
    ):
        if kw in s:
            cond_kws.append(kw)
    if cond_kws:
        out["current_condition"] = "、".join(cond_kws[:4])

    return out


def _rescue_subcategory_keywords(*subcategories: str) -> Tuple[str, ...]:
    """從子類別關鍵詞表取出指定類別的全部關鍵詞。"""
    wanted = set(subcategories)
    out: List[str] = []
    for sub, keywords in RESCUE_SUBCATEGORY_KEYWORDS:
        if sub in wanted:
            out.extend(keywords)
    return tuple(out)


# 車禍、路倒等戶外場景：地址問句不追問樓層（這些詞不會是路名，直接比對）
OUTDOOR_ADDRESS_NO_FLOOR_KEYWORDS: Tuple[str, ...] = (
    _rescue_subcategory_keywords("車禍", "路倒")
    + ("倒臥路邊", "倒卧路边")
)

# 露天場所地標：夜市攤販等雖歸建物類（如集合住宅），但地點是露天的，問「幾樓」不合理。
# 報案人講到這些詞即不追問樓層（見 a2766f5f：南亞夜市攤販起火卻被問幾樓/從幾樓燒）。
OUTDOOR_LANDMARK_NO_FLOOR_KEYWORDS: Tuple[str, ...] = (
    "夜市", "菜市場", "市場", "市集", "攤販", "路邊攤", "攤位",
    "廣場", "公園", "園遊會", "夜市攤",
)

# 路名防呆：公園路／市場路／廣場路… 是常見路名，屬正常門牌地址、仍要問樓層。
# 露天地標詞後面若緊接這些路名尾綴，就不當成露天地標。
_STREET_SUFFIXES: Tuple[str, ...] = ("路", "街", "巷", "段", "大道", "道", "弄")


def _mentions_outdoor_landmark(s: str) -> bool:
    """文本是否提到露天地標（且不是路名的一部分，如公園路/市場路）。"""
    for kw in OUTDOOR_LANDMARK_NO_FLOOR_KEYWORDS:
        idx = s.find(kw)
        while idx != -1:
            rest = s[idx + len(kw):]
            if not rest.startswith(_STREET_SUFFIXES):
                return True
            idx = s.find(kw, idx + 1)
    return False


def address_ask_should_include_floor(text: str) -> bool:
    """是否應在地址詢問中附带「幾樓」。"""
    s = (text or "").strip()
    if not s:
        return True
    if any(kw in s for kw in OUTDOOR_ADDRESS_NO_FLOOR_KEYWORDS):
        return False
    if _mentions_outdoor_landmark(s):
        return False
    return True


def build_address_ask_questions(
    *,
    include_floor: bool = True,
    flow: Literal["救護", "火警", "緊急救援"] = "救護",
) -> Tuple[str, ...]:
    """依流程類型與是否追問樓層，生成地址詢問問題序列。"""
    if include_floor:
        first = "請先告訴我地址？幾樓？"
        rescue_second = "請問事發地址在哪裡？幾樓？"
    else:
        first = "請先告訴我地址？"
        rescue_second = "請問事發地址在哪裡？"

    if flow == "救護":
        return (first, rescue_second)

    return (
        first,
        "地址在哪裡呢？附近有明顯建物或標示嗎？",
        "有路燈或電線桿嗎？給我路燈或電線桿上面的編號、大約靠近哪邊呢？",
    )


# 不可用於複讀確認的佔位／未知地址（LLM 偶發輸出）
_UNUSABLE_ADDRESS_MARKERS = frozenset({
    "未知", "（未知）", "(未知)", "不明", "不詳", "不详",
    "無", "无", "沒有", "没有", "不知道", "不清楚",
    "null", "none", "n/a", "na",
})


# 可用地址的長度上限（去空白後字元數）。
MAX_USABLE_ADDRESS_LEN = 40


def is_usable_address(addr: Optional[str]) -> bool:
    """是否為可複讀確認的真實地址（非空、非「未知」等佔位）。"""
    if not addr:
        return False
    s = str(addr).strip()
    if not s:
        return False
    s_norm = re.sub(r"\s+", "", s).lower()
    if s_norm in {m.lower() for m in _UNUSABLE_ADDRESS_MARKERS}:
        return False
    # 整段對話不是地址。2026-09-04 實測：報案人一口氣講完案情與地址，
    # 因為句中有「醫院」被判成 landmark，59 字的整段話被存成 case.address
    # 並顯示給受理員。真實地址（含地標名）遠短於此。
    if len(s_norm) > MAX_USABLE_ADDRESS_LEN:
        return False
    # 僅括號內未知，如「（未知）」已覆蓋；再擋「地址未知」一類
    if s_norm in {"地址未知", "地址不明", "位置未知", "地點未知", "地点未知"}:
        return False
    return True


def clean_address_fragment(text: str) -> str:
    """清理地址片段，去除否定前綴、案件類別與事件描述等非地址內容。"""
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"[。\.，,；;！!？?]+$", "", s)
    # 確認更正：「不是，民權街…」「不對啊，改成…」
    s = re.sub(
        r"^(?:不是(?:這個)?|不對|不对|錯了|错了|不是的|不對啊|不对啊)"
        r"[，,、。\.；;！!？?\s]*"
        r"(?:改成|改為|改为|應該是|应该是|是)?[，,、\s]*",
        "",
        s,
    )
    # 「這裡是/我在」定位口語前綴
    s = re.sub(
        r"^(?:這裡是|这里是|這邊是|这边是|我在|在)"
        r"[，,、\s]*",
        "",
        s,
    )
    # 首輪常先答「救護車/火災」再報地址，如「救護車！景興街…」
    s = re.sub(
        r"^(?:救護車|救护车|救護|救护|火災|火灾|消防車|消防车|消防)"
        r"[，,、。\.；;！!？?\s]*",
        "",
        s,
    )
    # 「派出所，我們儲藏室燒起來」→ 截在「我們」或起火描述之前
    s = re.split(
        r"(?:發生|有人|出(?:了)?車禍|車禍|受傷|倒地|昏倒|需要救護|要救護|"
        r"燒起來|烧起来|起火|失火|著火|着火|冒煙|冒烟|"
        r"[，,、]\s*我們)",
        s,
        maxsplit=1,
    )[0].strip()
    s = re.sub(r"[，,、。\.；;！!？?\s]+$", "", s)
    # 地標後誤併的房間用途（無門牌時）：派出所儲藏室 → 派出所
    if s and not is_street_address(s):
        s2 = re.sub(
            r"(?:的)?(?:儲藏室|储藏室|倉庫|仓库)$",
            "",
            s,
        ).strip()
        if s2:
            s = s2
    if not is_usable_address(s):
        return ""
    return s


def is_street_address(addr: str) -> bool:
    """是否含路/街/大道 + 門牌數字（可派遣門牌地址）。"""
    if not addr:
        return False
    has_road = bool(re.search(r"(?:路|街|大道)", addr))
    has_number = bool(re.search(r"\d", addr)) or ("號" in addr)
    return has_road and has_number


_DISTRICT_RE = re.compile(
    r"(?:[\u4e00-\u9fff]{2,3}[市縣])?([\u4e00-\u9fff]{1,4}區)"
)
# 受理範圍內的行政區名單。純 regex 的 {1,4}區 會把口語贅詞吃進區名
#（「那個辦土城區」→「個辦土城區」），拼出的地址送 addrCheck 必然查無。
# 註：address_mapper_119 另有一份 _DISTRICT_CANDIDATES_FOR_NORM（僅新北、
# 供臺語模糊比對），用途不同；兩份都增修時要一起看。
# 受理轄區。裸區名（省略「區」）只認這 29 個，見 _BARE_DISTRICT_STEMS。
_NEW_TAIPEI_DISTRICTS = frozenset(
    "板橋區 三重區 中和區 永和區 新莊區 新店區 樹林區 鶯歌區 三峽區 淡水區 "
    "汐止區 瑞芳區 土城區 蘆洲區 五股區 泰山區 林口區 深坑區 石碇區 坪林區 "
    "三芝區 石門區 八里區 平溪區 雙溪區 貢寮區 金山區 萬里區 烏來區".split()
)
_KNOWN_DISTRICTS = frozenset(
    # 新北市
    "板橋區 三重區 中和區 永和區 新莊區 新店區 樹林區 鶯歌區 三峽區 淡水區 "
    "汐止區 瑞芳區 土城區 蘆洲區 五股區 泰山區 林口區 深坑區 石碇區 坪林區 "
    "三芝區 石門區 八里區 平溪區 雙溪區 貢寮區 金山區 萬里區 烏來區 "
    # 臺北市
    "中正區 大同區 中山區 松山區 大安區 萬華區 信義區 士林區 北投區 內湖區 "
    "南港區 文山區 "
    # 基隆市
    "仁愛區 安樂區 暖暖區 七堵區 "
    # 桃園市
    "桃園區 中壢區 大溪區 楊梅區 蘆竹區 大園區 龜山區 八德區 龍潭區 平鎮區 "
    "新屋區 觀音區 復興區".split()
)
_HIGHWAY_NAME_RE = re.compile(
    r"((?:國道|国道)\s*[一二三四五六七八九十\d]+(?:號|号)?|"
    r"[\u4e00-\u9fff]{0,8}高速公路)"
)


# 以「區」結尾但不是行政區的常見詞。regex 退路會把它們當區名抽出來
#（報案人答「不分區」→ 組成「不分區亞洲路3號」→ addrCheck 必然查無）。
# 縣市白名單。與行政區同病：regex 的 {2,3}[市縣] 會把口語贅詞吃進縣市名
#（「那個新北市」→「個新北市」），組出的地址 addrCheck 一律查無。
_KNOWN_CITIES = frozenset(
    "臺北市 台北市 新北市 桃園市 臺中市 台中市 臺南市 台南市 高雄市 "
    "基隆市 新竹市 新竹縣 苗栗縣 彰化縣 南投縣 雲林縣 嘉義市 嘉義縣 "
    "屏東縣 宜蘭縣 花蓮縣 臺東縣 台東縣 澎湖縣 金門縣 連江縣".split()
)

_NON_DISTRICT_WORDS = frozenset(
    "不分區 選區 學區 社區 園區 市區 郊區 地區 區域 行政區 工業區 住宅區 "
    "商業區 科學區 科技區 災區 山區 市轄區 管制區 警戒區 責任區 轄區".split()
)


def extract_address_city(text: str) -> str:
    """抽取縣市名；只認名單內的縣市，避免把「那個新北市」吃成「個新北市」。

    2026-09-04 實測：報案人說「嗯，在那個新北市五股區明德路12巷」，
    組出「個新北市五股區明德路12巷28號」送 addrCheck 查無，
    API 只認得出路名，回「明德路有好幾個區都有」，流程繞了三輪。
    """
    compact = re.sub(r"\s+", "", text or "")
    for index, char in enumerate(compact):
        if char not in "市縣":
            continue
        candidate = compact[max(0, index - 2):index + 1]
        if candidate in _KNOWN_CITIES:
            return candidate
    return ""


def is_known_district(name: Optional[str]) -> bool:
    """是否為受理範圍內已知的行政區名。

    供 address_mapper 判斷「這已經是合法區名，不要再拿去音近比對」——
    臺北市的信義區/文山區/中正區都會被誤配到新北市的區，且分數很高
    （文山區→金山區 0.769），光調門檻擋不掉。
    """
    return (name or "").strip() in _KNOWN_DISTRICTS


# 省略「區」的口語區名（「救護車在那個鶯歌」）。**只收新北市 29 區**：
# 臺北市的「中山」「信義」「大安」「文山」同時是常見路名前綴，
# 「中山北路」會被拆成「中山區」＋「北路」——與 2026-09-04 那個
# 「剝區名把中山北路剝成北路」是同一個坑，受理範圍外不值得冒這個險。
_BARE_DISTRICT_STEMS = {
    name[:-1]: name
    for name in _KNOWN_DISTRICTS
    if name in _NEW_TAIPEI_DISTRICTS
}
# 裸區名前面允許出現的字：句首、標點，或這幾個虛詞。
# 2026-09-06 04:46 實測「我要送台大金山。開刀」——「金山」前面是「大」，
# 不在名單內，才不會把台大金山醫院判成金山區。
_BARE_DISTRICT_LEAD = frozenset("在到於個是的那這來去往從")
_BARE_DISTRICT_TRAIL = ("區", "那邊", "這邊", "那裡", "这里", "這裡", "那兒", "這兒")
_BARE_DISTRICT_PUNCT = frozenset("。，、．·,.!?！？；;：:「」（）()")


def _bare_district(compact: str) -> Optional[str]:
    """在沒有「區」字的句子裡找口語區名。

    前後都要有線索才敢認，因為區名的兩個字常常是別的詞：
      前：句首／標點／虛詞（擋掉「台大金山」的「金山」）
      後：那邊之類的方位詞、標點、句尾，或緊接著一個路名
          （擋掉「三重點」「中和一下」；「鶯歌國慶街」則接受）
    「中和路」這種後面只有「路」字的不算路名（regex 要求路名有前綴字），
    所以不會把「中和路100號」判成中和區。
    """
    for index in range(len(compact) - 1):
        target = _BARE_DISTRICT_STEMS.get(compact[index:index + 2])
        if not target:
            continue
        if index and compact[index - 1] not in _BARE_DISTRICT_LEAD \
                and compact[index - 1] not in _BARE_DISTRICT_PUNCT:
            continue
        rest = compact[index + 2:]
        if not rest or rest[0] in _BARE_DISTRICT_PUNCT:
            return target
        if rest.startswith(_BARE_DISTRICT_TRAIL):
            return target
        if _ADDRESS_ROAD_RE.match(rest):
            return target
    return None


def extract_address_district(text: str) -> Optional[str]:
    """抽取台灣行政區名稱（例如「板橋區」）。

    先掃描名單內的區名，避免 regex 把「那個辦土城區」誤抽成「個辦土城區」；
    名單未收錄（例如受理範圍外的縣市）時才退回 regex，並濾掉「不分區」
    這類以「區」結尾但不是行政區的詞。
    """
    compact = re.sub(r"\s+", "", text or "")
    for index, char in enumerate(compact):
        if char != "區":
            continue
        for length in (3, 2):
            start = index - length + 1
            if start < 0:
                continue
            candidate = compact[start:index + 1]
            if candidate in _KNOWN_DISTRICTS:
                return candidate
    bare = _bare_district(compact)
    if bare:
        return bare
    match = _DISTRICT_RE.search(text or "")
    if not match:
        return None
    candidate = match.group(1)
    if candidate in _NON_DISTRICT_WORDS:
        return None
    return candidate


_ADDRESS_NUMBER_TOKEN = r"[零〇一二三四五六七八九十百千兩\d]+"
_ADDRESS_ROAD_RE = re.compile(
    rf"([\u4e00-\u9fff]{{1,12}}(?:大道|路|街)"
    rf"(?:{_ADDRESS_NUMBER_TOKEN}段)?"
    rf"(?:{_ADDRESS_NUMBER_TOKEN}巷)?"
    rf"(?:{_ADDRESS_NUMBER_TOKEN}弄)?)"
)
_ADDRESS_NUMBER_RE = re.compile(
    rf"({_ADDRESS_NUMBER_TOKEN}(?:之{_ADDRESS_NUMBER_TOKEN})?(?:號|号))"
)


# 路名前常見的口語贅詞；regex 的 {1,12}(路|街|大道) 會把它們吃進路名
#（「嗯，那個亞洲路3號」→「那個亞洲路」）。
_ROAD_PREFIX_FILLERS = (
    "那個", "那个", "這個", "这个", "就是", "在", "位於", "位于",
    "我家在", "我在", "地址是", "地址在", "呃", "嗯", "欸", "喔", "唉",
    "的", "就",
)

# 報案人常把區名黏在路名前面（「三重區的正義南路」），要能從路名前緣剝掉。
# ⚠️ 只剝完整區名，不剝省略「區」字的簡稱：簡稱和路名無法從結構區分——
# 「三重正義南路」的「三重」該剝，「中山北路二段」的「中山」不能剝，
# 而剝完「中山」剩下的「北路二段」照樣是合法路名，fullmatch 守衛擋不住。
# 少剝一個交給 addrCheck 的 hint 導向修正，好過把正確路名剝壞。
_ROAD_PREFIX_DISTRICTS = tuple(sorted(_KNOWN_DISTRICTS, key=len, reverse=True))


# 路名候選含這些字就不是路名。regex 的 {1,12}(路|街|大道) 會把任何以
# 「路」結尾的詞組當路名：實測「我是路人，所以我沒有開車」→「我是路人路」、
# 「不知道他躺在路邊」→「不知道他躺在路」，兩通都因此污染了已派遣的地址。
# 只收人稱與明顯的敘述詞——真實路名不含這些字（中山路／和平路／三民路皆安全）。
# 疑問詞：「什麼路」「哪一條路」是反問句的殘骸，永遠不是路名
_ROAD_REJECT_TOKENS = (
    "什麼", "甚麼", "什么", "哪", "怎", "路人", 
    "我", "你", "妳", "他", "她", "牠", "它",
    "是", "不", "沒", "躺", "倒", "知道", "看到", "聽到", "感覺",
)


# 泛稱而非路名。只擋完全相等的值——「馬路」是路的通稱，
# 但真的有路名含這兩個字時（若日後出現）不該被連坐。
_GENERIC_ROAD_WORDS = frozenset(
    "馬路 大馬路 路口 巷口 十字路口 產業道路 道路 這條路 那條路".split()
)


def looks_like_real_road(road: Optional[str]) -> bool:
    """路名候選是否像真的路名（排除從敘述句誤抽的片段）。"""
    value = re.sub(r"\s+", "", road or "")
    if not value:
        return False
    if value in _GENERIC_ROAD_WORDS:
        return False
    # 路名主體（「路／街／大道」之前那一段）全由口語贅詞字組成 → 不是路名。
    # 「就在那個路口」的 regex 候選是「就在那個路」，剝掉已知贅詞剩「那個路」，
    # 不含任何敘述詞就這樣過關了。比逐一列舉「那個路」「這個路」可靠。
    base = re.match(r"(.*?)(?:大道|路|街)", value)
    if base and base.group(1) and all(
        char in _ROAD_FILLER_CHARS for char in base.group(1)
    ):
        return False
    return not any(token in value for token in _ROAD_REJECT_TOKENS)


# 可以從路名前緣剝掉的口語用字。**刻意不收任何可能當路名開頭的字**
# （中民光忠仁信和大新長文復興南北東西三五永青自由成功明德福有…），
# 因為剝過頭就是「中山北路」→「北路」（⑩-6）。
_ROAD_FILLER_CHARS = frozenset(
    "我你妳他她牠它們這那個的了是不在到就跟幫請欸呃嗯喔啊哦嘿啦吧呢嗎邊裡裏"
)


def strip_road_fillers(road: Optional[str]) -> Optional[str]:
    """去掉路名前緣的口語贅詞，必要時逐字剝到剩合法路名。"""
    value = (road or "").strip()
    if not value:
        return road
    changed = True
    while changed:
        changed = False
        for filler in _ROAD_PREFIX_DISTRICTS + _ROAD_PREFIX_FILLERS:
            if value.startswith(filler) and len(value) > len(filler):
                remainder = value[len(filler):]
                if _ADDRESS_ROAD_RE.fullmatch(remainder):
                    value = remainder
                    changed = True
                    break
    # 清單外的贅詞：逐字往右剝，直到不再含敘述詞為止。
    # 2026-09-06 10:35 實測「我這邊是民生路2段」——句中沒有「區」也沒有縣市，
    # 沒有切點，regex 連前面的贅詞一起吃進去，含「我」「是」被
    # looks_like_real_road 整個否決，路名變成 None，之後倒退問「請問是什麼路？」。
    #
    # ⚠️ 只在**目前的值不合格時**才剝，而且一合格就停。這是不會剝成
    # 「中山北路」→「北路」的關鍵（⑩-6）：由左往右第一個合格的值就是
    # 最長的那個，永遠先碰到「中山北路」才輪得到「北路」。
    if not looks_like_real_road(value):
        index = 0
        while index < len(value) and value[index] in _ROAD_FILLER_CHARS:
            index += 1
        candidate = value[index:]
        if index and _ADDRESS_ROAD_RE.fullmatch(candidate):
            return candidate
    return value or road


# 報案人講地址常有停頓，STT 轉成標點：「光武街。136巷。8弄16號」。
# 路名 regex 的段/巷/弄必須緊接，遇標點就斷，巷弄要繞到覆誦才補得回來。
# ⚠️ 只去除「路/街/大道/段/巷/弄」與緊接的「N段/N巷/N弄」之間的標點——
# 全部去標點會把「蘆洲成功國小旁邊。長安街」連成一個路名候選。
_ROAD_SEGMENT_PUNCT_RE = re.compile(
    rf"(路|街|大道|段|巷|弄)[。，、．·,\.]+"
    rf"(?={_ADDRESS_NUMBER_TOKEN}(?:段|巷|弄))"
)


def strip_district_prefix_from_road(
    road: Optional[str], district: Optional[str]
) -> Optional[str]:
    """路名開頭若重複了已知的行政區名（含省略「區」的簡稱），剝掉。

    報案人常把區和路連著講：「中和景平路」「板橋國光路」「新莊的中港路」。
    組地址時會變成「中和區中和景平路」，addrCheck 查無，白繞一輪 hint 導向。

    ⚠️ 只在**與已知行政區重複**時才剝——這是與 `_ROAD_PREFIX_DISTRICTS`
    的關鍵差異。單看路名無法判斷「中山北路」的「中山」該不該剝，但若
    行政區是「淡水區」，「中山北路」並不以「淡水」開頭，自然不受影響。
    """
    if not road or not district:
        return road
    short = district[:-1] if district.endswith("區") else district
    for prefix in (district, short):
        if not prefix or not road.startswith(prefix) or len(road) <= len(prefix):
            continue
        rest = strip_road_fillers(road[len(prefix):])
        if rest and _ADDRESS_ROAD_RE.fullmatch(rest):
            return rest
    return road


def extract_address_road(text: str) -> Optional[str]:
    """抽取門牌地址道路，包含段、巷、弄，但不包含門牌號。"""
    compact = _ROAD_SEGMENT_PUNCT_RE.sub(
        r"\1", re.sub(r"\s+", "", text or "")
    )
    if "區" in compact:
        compact = re.sub(r"^.*?區", "", compact)
    else:
        # 報案人常只講「三重」不講「三重區」，切不到「區」；
        # 改用縣市當切點，免得路名吃進「新北市三重」。
        city = extract_address_city(compact)
        if city:
            compact = compact[compact.find(city) + len(city):]
    match = _ADDRESS_ROAD_RE.search(compact)
    if not match:
        return None
    road = strip_road_fillers(match.group(1))
    return road if looks_like_real_road(road) else None


# 巷／弄單獨出現時的抽取。路名 regex 需要「X路」開頭，報案人單獨補一句
# 「還有31巷」「648巷6號」時抽不到，巷弄就此消失——實測兩通因此覆誦時
# 唸成「國光路11號」「仁愛街28號」，報案人連續否認。
_LANE_ALLEY_RE = re.compile(
    rf"({_ADDRESS_NUMBER_TOKEN}巷(?:{_ADDRESS_NUMBER_TOKEN}弄)?)"
)
# 段也一樣：報案人補一句「一段22號」時抽不到「一段」。
# 2026-09-06 01:25 實測：最終存「明德路22號」，API 回「最接近的是
# 明德路一段22號（報案人未提及段別）」——段其實講了，只是沒被接住。
_SECTION_RE_UTIL = re.compile(rf"({_ADDRESS_NUMBER_TOKEN}段)")


def extract_lane_alley(text: str) -> Optional[str]:
    """抽取「N巷」「N巷N弄」；沒有則回 None。

    巷與弄之間的停頓標點也要去掉——實測「28巷。6弄。4號」只抽到「28巷」，
    6弄 就此消失，送驗地址少一層。
    """
    compact = _ROAD_SEGMENT_PUNCT_RE.sub(
        r"\1", re.sub(r"\s+", "", text or "")
    )
    match = _LANE_ALLEY_RE.search(compact)
    return match.group(1) if match else None


def extract_road_section(text: str) -> Optional[str]:
    """抽取「N段」；沒有則回 None。"""
    match = _SECTION_RE_UTIL.search(re.sub(r"\s+", "", text or ""))
    return match.group(1) if match else None


def road_has_lane(road: Optional[str]) -> bool:
    """路名是否已含巷弄。"""
    return bool(_LANE_ALLEY_RE.search(road or ""))


def road_has_section(road: Optional[str]) -> bool:
    """路名是否已含段。"""
    return bool(_SECTION_RE_UTIL.search(road or ""))


# 巷／弄的結尾位置：門牌號一定在它們之後（路→段→巷→弄→號→樓）
_LANE_ALLEY_END_RE = re.compile(rf"{_ADDRESS_NUMBER_TOKEN}[巷弄]")


# 「號」前面是年月日 → 這是日期不是門牌。
# 2026-09-06 04:46 實測：申訴案「我那個115年3月。23號叫救護車」，
# 「23號」被填成門牌，跟著把「馬偕」當路名，存成「馬偕23號」。
_DATE_TAIL_RE = re.compile(r"[年月日][。，、．·,\.\s]*$")


def _first_house_number(compact: str, start: int):
    """找第一個「不是日期」的門牌號。"""
    for match in _ADDRESS_NUMBER_RE.finditer(compact, start):
        if _DATE_TAIL_RE.search(compact[:match.start()]):
            continue
        return match
    return None


def extract_address_number(text: str) -> Optional[str]:
    """抽取門牌號並統一使用繁體「號」。

    句中若有巷／弄，只在它們**之後**找門牌號——地址結構是
    路→段→巷→弄→號→樓，號一定在巷弄後面。

    2026-09-06 03:12 實測：STT 把「28巷」聽成「28號28巷」，
    取第一個「N號」會抽到 28號，真正的門牌 4號 被跳過，
    之後 API 一直回「這條路沒有28號」，繞到引導式重來。
    """
    compact = re.sub(r"\s+", "", text or "")
    tail_start = 0
    for lane in _LANE_ALLEY_END_RE.finditer(compact):
        tail_start = lane.end()
    match = _first_house_number(compact, tail_start)
    if match is None and tail_start:
        # 巷弄後面沒有號（例如只講到「28巷」），退回全句搜尋
        match = _first_house_number(compact, 0)
    return match.group(1).replace("号", "號") if match else None


_SUB_NUMBER_RE = re.compile(rf"之{_ADDRESS_NUMBER_TOKEN}")
_FLOOR_TOKEN_RE = re.compile(rf"(?:地下)?{_ADDRESS_NUMBER_TOKEN}樓")


def dropped_address_details(spoken: str, address: Optional[str]) -> Tuple[bool, bool]:
    """報案人講了、但沒進到地址裡的細節；回 (缺「之N」, 缺樓層)。

    2026-09-06 10:35 實測：「兩百。號之18樓」被 STT 拆碎，只抽到門牌號，
    「之1」和「8樓」整個掉了，覆誦唸成「200號」，報案人得自己發現並更正。
    這兩個 token 在原話裡明明看得到——抽不出來就該回頭問，不要靜悄悄丟掉。
    """
    said = re.sub(r"\s+", "", spoken or "")
    have = re.sub(r"\s+", "", address or "")
    missing_sub = bool(_SUB_NUMBER_RE.search(said)) and not _SUB_NUMBER_RE.search(have)
    missing_floor = bool(_FLOOR_TOKEN_RE.search(said)) and not _FLOOR_TOKEN_RE.search(have)
    return missing_sub, missing_floor


def extract_street_address_components(text: str) -> Dict[str, str]:
    """從單輪文字抽取門牌地址的區、路、號元件。"""
    components = {
        "address_district": extract_address_district(text),
        "address_road": extract_address_road(text),
        "address_number": extract_address_number(text),
    }
    return {key: value for key, value in components.items() if value}


_PREGNANCY_COUNT_RE = re.compile(r"(胞胎|雙胎|双胎|龍鳳胎|龙凤胎)")


def looks_like_pregnancy_count(value: object) -> bool:
    """判斷傷患人數是否誤抽成胎數。

    孕婦急產案問「單胞胎還是雙胞胎？」，答「三胞胎」曾被填進 patient_count；
    胎數屬 multiple_pregnancy，傷病患仍是孕婦本人。
    """
    return bool(_PREGNANCY_COUNT_RE.search(str(value or "")))


def build_street_address(
    district: Optional[str],
    road: Optional[str],
    number: Optional[str],
    *,
    existing: Optional[str] = None,
) -> Optional[str]:
    """將完整區、路、號重建為門牌地址，並保留既有樓層資訊。"""
    if not district or not road or not number:
        return None
    road = strip_district_prefix_from_road(road, district)
    return compose_street_address(
        district,
        road,
        number,
        existing=existing,
    )


def compose_street_address(
    district: Optional[str],
    road: Optional[str],
    number: Optional[str],
    *,
    existing: Optional[str] = None,
) -> Optional[str]:
    """按區、路、號順序組合目前已知元件，供多輪增量更新。"""
    parts = [part for part in (district, road, number) if part]
    if not parts:
        return None
    city = extract_address_city(existing or "")
    if city and any(city in str(part or "") for part in parts):
        city = ""  # 元件裡已經帶了縣市，別組成「新北市新北市…」
    address = city + "".join(parts)
    # B1/B2 等地下樓層也要保留：地標驗測回的地址常寫成「…2號B1」，
    # 舊 regex 只認「樓」字，會把地下樓層整個丟掉。
    floor_match = re.search(
        rf"((?:地下)?{_ADDRESS_NUMBER_TOKEN}樓(?:之{_ADDRESS_NUMBER_TOKEN})?"
        rf"|[Bb][0-9]+(?:[Ff])?)",
        existing or "",
    )
    if number and floor_match and floor_match.group(1) not in address:
        address += floor_match.group(1)
    return address


def has_complete_street_address(
    district: Optional[str],
    road: Optional[str],
    number: Optional[str],
) -> bool:
    """門牌地址是否已具備行政區、道路及門牌號。"""
    return bool(district and road and number)


def extract_intersection_roads(text: str) -> List[str]:
    """抽取路口/巷口中的道路名稱，依出現順序去重。"""
    s = re.sub(r"\s+", "", text or "")
    s = re.sub(r"(?:路口|巷口)", "", s)
    roads: List[str] = []
    for segment in re.split(r"(?:與|与|和|及|交叉|、|,|，)", s):
        segment = re.sub(r"^.*?區", "", segment)
        match = re.search(
            r"([\u4e00-\u9fff0-9]{1,16}?(?:大道|路|街|巷))$",
            segment,
        )
        if match and match.group(1) not in roads:
            roads.append(match.group(1))
    return roads[:2]


def extract_highway_components(text: str) -> Dict[str, str]:
    """規則抽取高速公路名稱、方向及公里數。"""
    s = re.sub(r"\s+", "", text or "")
    out: Dict[str, str] = {}
    name_match = _HIGHWAY_NAME_RE.search(s)
    if name_match:
        out["highway_name"] = name_match.group(1)
    direction_match = re.search(r"(南向|北向)", s)
    if direction_match:
        out["highway_direction"] = direction_match.group(1)
    km_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:公里|K|k)", text or "")
    if km_match:
        out["highway_kilometer"] = km_match.group(1)
    return out


def build_intersection_address(
    district: Optional[str],
    road1: Optional[str],
    road2: Optional[str],
) -> Optional[str]:
    """将交叉路口组件组成统一显示地址。"""
    if not road1 or not road2:
        return None
    prefix = district or ""
    return f"{prefix}{road1}與{road2}路口"


def build_highway_address(
    name: Optional[str],
    direction: Optional[str],
    kilometer: Optional[str],
) -> Optional[str]:
    """将完整高速公路组件组成统一显示地址。"""
    if not name or not direction or not kilometer:
        return None
    km = re.sub(r"\s*(?:公里處|公里|K|k)\s*$", "", str(kilometer)).strip()
    return f"{name} {direction} {km}公里處" if km else None


def is_bare_district_or_city(text: Optional[str]) -> bool:
    """整串就只是行政區／縣市名（可含市+區），沒有任何路名門牌。

    這種字串**不可以**送去 addrCheck 的自動判斷層：API 會盡力配一個地標
    給你，而且回 valid——
        「五股區」→ 五股區公所
        「新北市」→ 樹林區「新北市肉品市場」
    報案人只講到區，正確反應是繼續問路，不是拿去查。
    """
    value = re.sub(r"[\s，、。]+", "", text or "")
    if not value:
        return False
    if value in _KNOWN_DISTRICTS or value in _KNOWN_CITIES:
        return True
    city = extract_address_city(value)
    if city and value[len(city):] in _KNOWN_DISTRICTS:
        return True
    return False


def landmark_layer_from_hint(hint: Optional[str]) -> Optional[str]:
    """從 addrCheck 自動判斷的 hint 反推它是在哪一層命中的。

    不帶 type 查詢時 API 會自己選層，hint 的開頭就寫著結果：
        地標比對成功…       → landmark
        地址有效：…          → address
        國道定位成功：…      → highway
        「A」與「B」…交會    → intersection
    查無時無從判斷，回 None 由呼叫端決定退路。
    """
    text = hint or ""
    if "地標比對成功" in text:
        return "landmark"
    if "國道定位" in text or "高速公路" in text:
        return "highway"
    if "交會" in text:
        return "intersection"
    if "地址有效" in text:
        return "address"
    return None


def classify_location_type(
    location: str,
    *,
    mrt_names: Optional[List[str]] = None,
    landmark_names: Optional[List[str]] = None,
) -> Optional[str]:
    """以确定性规则判断地点类别，供 LLM 结果校正与无模型备援。"""
    s = re.sub(r"\s+", "", location or "")
    if not s:
        return None
    if re.search(r"(?:國道|国道|高速公路)", s):
        return "highway"
    if ("路口" in s or "巷口" in s) or (
        len(extract_intersection_roads(s)) >= 2
        and re.search(r"(?:與|与|和|交叉)", s)
    ):
        return "intersection"
    if is_street_address(s):
        return "address"
    if any(name and name.replace(" ", "") in s for name in (mrt_names or [])):
        return "mrt"
    if ("捷運" in s or "捷运" in s) and ("站" in s or "出口" in s):
        return "mrt"
    if any(name and name.replace(" ", "") in s for name in (landmark_names or [])):
        return "landmark"
    if _is_landmark_only(s):
        return "landmark"
    if any(k in s for k in ("區", "路", "街", "大道", "巷", "弄", "號")):
        return "address"
    return None


def _is_landmark_only(addr: str) -> bool:
    """無可派遣門牌、偏機關/建物地標。"""
    if not addr or is_street_address(addr):
        return False
    if any(
        k in addr
        for k in (
            "派出所", "分局", "警局", "學校", "車站", "捷運",
            "公園", "市場", "廟", "宮", "大樓", "大廈", "社區", "里辦",
            "機關", "公司", "工廠", "醫院", "診所",
        )
    ):
        return True
    # 2026-09-11：補學校簡稱（五華國小/板橋國中/台灣大學…）。原本清單只有
    # 「學校」，具名學校未被認出，被「含區→address」接手降級成缺路缺號門牌。
    # 但這些字也可能是路名（大學路/國中路），故關鍵字後不可緊接路型字。
    if re.search(
        r"(?:國小|國中|高中|高職|大學|幼兒園|幼稚園|托兒所)(?![路街道段巷弄])",
        addr,
    ):
        return True
    return False


def _needs_prefix(district: str, new_text: str) -> bool:
    """新片段還需不需要補上區名。

    比對要用「板橋區」而不是「新北市板橋區」——報案人補述常只講區不講市，
    整串比對會判成「沒有區名」而重複前綴，組出「新北市板橋區板橋區民生路…」。
    """
    if not district:
        return False
    if district in new_text:
        return False
    core = district[-3:] if len(district) > 3 else district
    return core not in new_text


def _keep_road_prefix(
    current: str, district: str, road_cur: str, road_new: str
) -> str:
    """補述只給門牌／樓層時，前綴要保留到路名為止，不能只留區名。

    2026-09-06 10:35 實測：覆誦「民生路二段200號」後報案人更正
    「200之1號8樓」，逐輪 LLM 抽出的片段沒有路名，合併成
    「新北市板橋區200之1號8樓」——**路名整段消失**，
    下一句就變成「請問是什麼路？」，明明才剛唸過。
    """
    if road_cur and not road_new:
        # _extract_road_core 只回「民生路」，段／巷／弄會被切掉；
        # 前綴必須保留到完整路名，否則「二段」在這裡就丟了。
        full_road = extract_address_road(current) or road_cur
        index = current.find(full_road)
        if index >= 0:
            return current[:index + len(full_road)]
    return district


def merge_address(current: Optional[str], new: Optional[str]) -> Optional[str]:
    """
    合併兩段地址。確認環節報警人常只補門牌/弄，省略區名。

    例：中和區連城路347巷附近 + 連城路347巷1弄2號附近
        → 中和區連城路347巷1弄2號附近

    若新址為明確門牌、舊址僅地標（或不同路名），以新址替換，勿因字數較短而保留舊址。
    """
    cur = clean_address_fragment(current or "")
    n = clean_address_fragment(new or "")
    if not cur:
        return n or None
    if not n:
        return cur or None

    cur_cmp = re.sub(r"\s+", "", cur)
    n_cmp = re.sub(r"\s+", "", n)
    if cur_cmp == n_cmp:
        return cur
    if cur_cmp in n_cmp:
        return n
    if n_cmp in cur_cmp and not _has_more_address_detail(n, cur):
        return cur

    # 門牌地址更正地標，或換成另一條路 → 直接採用新址
    road_cur = _extract_road_core(cur)
    road_new = _extract_road_core(n)
    if is_street_address(n) and (
        _is_landmark_only(cur)
        or (road_new and road_cur and not _same_road_base(road_cur, road_new)
            and road_cur not in road_new and road_new not in road_cur)
        or (road_new and not road_cur)
    ):
        return n

    district_m = re.search(r"([\u4e00-\u9fff]{1,8}區)", cur)
    district = district_m.group(1) if district_m else ""

    # 新路名與舊路名有重疊 → 保留區名 + 較精確路段
    if district and _needs_prefix(district, n):
        if road_cur and road_new and (
            road_cur in road_new or road_new in road_cur or _same_road_base(road_cur, road_new)
        ):
            merged = district + n if not n.startswith(district) else n
            if "附近" in new and "附近" not in merged:
                merged += "附近"
            return merged
        if _has_more_address_detail(n, cur):
            merged = _keep_road_prefix(cur, district, road_cur, road_new) + n
            if "附近" in (new or "") and "附近" not in merged:
                merged += "附近"
            return merged

    if re.search(r"[\u4e00-\u9fff]{1,8}區", n):
        return n if len(n_cmp) >= len(cur_cmp) else cur
    return n if len(n_cmp) > len(cur_cmp) else cur


def _extract_road_core(addr: str) -> str:
    m = re.search(
        r"([\u4e00-\u9fff0-9]+(?:路|街|大道)(?:\d+)?(?:巷|弄)?(?:\d+)?(?:弄)?(?:\d+)?號?)",
        addr,
    )
    return m.group(1) if m else ""


def _same_road_base(a: str, b: str) -> bool:
    """兩段路名是否同一條路（如 連城路347巷 與 連城路347巷1弄）。"""
    base_a = re.sub(r"(弄|巷)\d+.*$", "", a)
    base_b = re.sub(r"(弄|巷)\d+.*$", "", b)
    return bool(base_a and base_b and (base_a in b or base_b in a))


def _has_more_address_detail(new: str, old: str) -> bool:
    """新地址是否比舊地址更精確（弄/號/樓層等）。"""
    detail_keys = ("弄", "號", "樓", "F", "之")
    new_score = sum(1 for k in detail_keys if k in new) + len(re.findall(r"\d+", new))
    old_score = sum(1 for k in detail_keys if k in old) + len(re.findall(r"\d+", old))
    return new_score > old_score


def looks_like_address_response(text: str) -> bool:
    """判斷回答是否主要在提供/修正地址（而非單純是/否）。"""
    s = (text or "").strip()
    if not s:
        return False
    if len(s) <= 6 and parse_yes_no(s) is not None:
        return False
    if extract_address_hint(s):
        return True
    return bool(
        any(k in s for k in ("路", "街", "巷", "弄", "號", "區", "大道"))
        and re.search(r"\d", s)
    )


def extract_address_hint(text: str) -> Optional[str]:
    """
    從報警人原話中規則抽取地址片段。

    適用：「地址在土城區裕民路142號」「我在永和區永平路148號」等口語表達。
    LLM 抽取失敗時作為備援，確保第一輪已含地址時可跳過地址詢問。
    """
    if not text:
        return None
    s = clean_address_fragment(text.strip())

    # 明確標記「地址在/地址是/地點在」
    for marker in ("地址在", "地址是", "地點在", "地點是", "位置在"):
        if marker in s:
            idx = s.find(marker)
            tail = s[idx + len(marker):].strip()
            tail = re.split(r"[，,。\.；;！!？?]", tail, maxsplit=1)[0].strip()
            tail = clean_address_fragment(tail)
            if _looks_like_address(tail):
                return tail

    # 區 + 路/街 + 門牌（允許口語空格：「景興街 210 巷 2 弄 33 號 4 樓」）
    _addr_tail = (
        r"(?:\s*\d+\s*(?:巷|弄|號|楼|樓|F|f))+"
        r"(?:\s*(?:附近))?"
    )
    m = re.search(
        r"((?:[\u4e00-\u9fff]{1,8}區)"
        r"[\u4e00-\u9fff0-9\s]*"
        r"(?:路|街|大道)"
        + _addr_tail
        + r")",
        s,
    )
    if m:
        loc = clean_address_fragment(m.group(1).strip())
        loc = re.sub(r"\s+", " ", loc)
        if _looks_like_address(loc):
            return loc

    # 無區名但有路+門牌（確認環節補充門牌）
    m2 = re.search(
        r"([\u4e00-\u9fff0-9]+(?:路|街|大道)" + _addr_tail + r")",
        s,
    )
    if m2:
        loc = clean_address_fragment(m2.group(1).strip())
        loc = re.sub(r"\s+", " ", loc)
        if _looks_like_address(loc):
            return loc

    # 緊湊寫法（無空格）：景興街210巷2弄33號4樓
    m3 = re.search(
        r"((?:[\u4e00-\u9fff]{1,8}區)?"
        r"[\u4e00-\u9fff0-9]*"
        r"(?:路|街|大道)"
        r"\d*"
        r"(?:巷|弄)?"
        r"\d*"
        r"(?:弄)?"
        r"(?:\d+號)?"
        r"(?:\d+[楼樓Ff])?"
        r"(?:附近)?)",
        s,
    )
    if m3:
        loc = clean_address_fragment(m3.group(1).strip())
        if _looks_like_address(loc):
            return loc

    # 含關鍵地名字樣的較短片段
    keywords = ("區", "路", "街", "大道", "巷", "弄", "號", "樓", "F")
    if any(k in s for k in keywords) and len(s) <= 40:
        loc = clean_address_fragment(s)
        loc = re.sub(r"\s+", " ", loc)
        if _looks_like_address(loc):
            return loc

    return None


def _looks_like_address(t: str) -> bool:
    """判斷片段是否像可派遣地址（非泛稱）。"""
    if not t or len(t) < 4:
        return False
    if t in {"這裡", "这里", "那邊", "那边", "附近", "路中央", "路口", "巷口"}:
        return False
    has_district = "區" in t
    has_road = any(k in t for k in ("路", "街", "大道", "巷", "弄"))
    has_number = bool(re.search(r"\d", t)) or "號" in t
    # 區+路，或 路+門牌，或 區+路+號
    if has_district and has_road:
        return True
    if has_road and has_number:
        return True
    if has_district and has_number and len(t) >= 6:
        return True
    return False
