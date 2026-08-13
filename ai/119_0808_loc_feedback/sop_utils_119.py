"""
sop_utils_119.py
━━━━━━━━━━━━━━━━━
119 報案受理 — 規則備援工具（LLM 不可用或抽取失敗時使用）
"""

from __future__ import annotations

import os
import re
from typing import Optional


# 報警人未報出縣市時預設套用的市級單位（可用環境變數覆蓋）
DEFAULT_CITY = os.environ.get("DEFAULT_CITY_119", "新北市")

# 縣市白名單：避免「士林夜市」「中央市場」等被誤判為已含市級單位
TAIWAN_CITIES = (
    "臺北市", "台北市", "新北市", "桃園市", "臺中市", "台中市",
    "臺南市", "台南市", "高雄市", "基隆市", "新竹市", "新竹縣",
    "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣",
    "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "台東縣",
    "澎湖縣", "金門縣", "連江縣",
)


# 明確在戶外、不會有樓層的地點說法（問「幾樓」不合理）
_OUTDOOR_LOCATION_KEYWORDS = (
    "巷口", "弄口", "路口", "街口", "圓環", "分隔島", "安全島",
    "路邊", "路旁", "路肩", "路中央", "馬路上", "馬路中間", "人行道", "騎樓",
    "天橋", "陸橋", "地下道", "橋上", "橋下", "橋墩", "涵洞", "隧道",
    "高速公路", "國道", "快速道路", "交流道", "產業道路", "省道",
    "公園", "廣場", "操場", "河堤", "堤防", "河邊", "溪邊", "海邊",
    "山上", "山區", "山路", "步道", "田裡", "田邊",
    "公車站", "站牌", "加油站",
)

_FLOOR_QUESTION_RE = re.compile(
    r"\s*(?:第幾樓|第幾層|幾樓|幾層|樓層)\s*[？?]?\s*$"
)


def has_outdoor_location_hint(text: str) -> bool:
    """報警人是否已表明在戶外地點（巷口/路邊/天橋等），此時不該再問幾樓。"""
    s = re.sub(r"\s+", "", str(text or ""))
    if not s:
        return False
    return any(k in s for k in _OUTDOOR_LOCATION_KEYWORDS)


def strip_floor_question(question: str) -> str:
    """移除問句尾端的樓層追問（「請先告訴我地址？幾樓？」→「請先告訴我地址？」）。"""
    q = str(question or "").strip()
    stripped = _FLOOR_QUESTION_RE.sub("", q)
    return stripped or q


def has_city_prefix(addr: str) -> bool:
    """地址是否已含縣市名（依白名單，不看單一「市」字）。"""
    if not addr:
        return False
    s = re.sub(r"\s+", "", str(addr))
    return any(city in s for city in TAIWAN_CITIES)


def ensure_city_prefix(addr: str, city: Optional[str] = None) -> str:
    """報警人未報縣市時補上預設市級單位（如「土城區中央路1號」→「新北市…」）。"""
    s = str(addr or "").strip()
    if not s or has_city_prefix(s):
        return s
    return f"{city or DEFAULT_CITY}{s}"


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


# 不可用於複讀確認的佔位／未知地址（LLM 偶發輸出）
_UNUSABLE_ADDRESS_MARKERS = frozenset({
    "未知", "（未知）", "(未知)", "不明", "不詳", "不详",
    "無", "无", "沒有", "没有", "不知道", "不清楚",
    "null", "none", "n/a", "na",
})


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
_HIGHWAY_NAME_RE = re.compile(
    r"((?:國道|国道)\s*[一二三四五六七八九十\d]+(?:號|号)?|"
    r"[\u4e00-\u9fff]{0,8}高速公路)"
)


def extract_address_district(text: str) -> Optional[str]:
    """抽取台灣行政區名稱（例如「板橋區」）。"""
    match = _DISTRICT_RE.search(text or "")
    return match.group(1) if match else None


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
    return any(
        k in addr
        for k in (
            "派出所", "分局", "警局", "學校", "車站", "捷運",
            "公園", "市場", "廟", "宮", "大樓", "大廈", "社區", "里辦",
            "機關", "公司", "工廠", "醫院", "診所",
        )
    )


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

    # 新片段只是路段/門牌延續（如「2段1號3樓」）→ 接在舊址後，勿丟失路名
    if road_cur and _is_address_continuation(n):
        merged = _join_address_continuation(cur, n)
        if "附近" in (new or "") and "附近" not in merged:
            merged += "附近"
        return merged

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
    if district and district not in n:
        if road_cur and road_new and (
            road_cur in road_new or road_new in road_cur or _same_road_base(road_cur, road_new)
        ):
            merged = district + n if not n.startswith(district) else n
            if "附近" in new and "附近" not in merged:
                merged += "附近"
            return merged
        if _has_more_address_detail(n, cur):
            merged = district + n if not n.startswith(district) else n
            if "附近" in (new or "") and "附近" not in merged:
                merged += "附近"
            return merged

    if re.search(r"[\u4e00-\u9fff]{1,8}區", n):
        return n if len(n_cmp) >= len(cur_cmp) else cur
    return n if len(n_cmp) > len(cur_cmp) else cur


def strip_admin_prefix(addr: str) -> str:
    """去掉開頭的縣市與行政區，只留路名之後的部分。"""
    s = str(addr or "").strip()
    for city in TAIWAN_CITIES:
        if s.startswith(city):
            s = s[len(city):]
            break
    return re.sub(r"^[一-鿿]{1,4}區", "", s)


def _extract_road_core(addr: str) -> str:
    # 先去縣市/區，否則貪婪匹配會把「新北市土城區中央路」整串當成路名，
    # 導致與只報路名的新址（「中央路2段1號」）比對不出是同一條路。
    addr = strip_admin_prefix(addr)
    m = re.search(
        r"([\u4e00-\u9fff0-9]+(?:路|街|大道)(?:\d+)?(?:巷|弄)?(?:\d+)?(?:弄)?(?:\d+)?號?)",
        addr,
    )
    return m.group(1) if m else ""


_CONTINUATION_RE = re.compile(
    r"^[一二三四五六七八九十百兩两\d]+\s*(?:段|巷|弄|號|号|樓|楼|F|f|之)"
)


def _is_address_continuation(addr: str) -> bool:
    """新片段是否僅為路段/門牌延續（如「2段1號3樓」「5號」），本身不含路名。"""
    if not addr:
        return False
    s = addr.strip()
    if re.search(r"(?:路|街|大道|區)", s):
        return False
    return bool(_CONTINUATION_RE.match(s))


_NUM = r"[一二三四五六七八九十百兩两\d]"

# 門牌成分的同義寫法，用於判斷新片段是否在更正舊址的同一層級
_UNIT_ALIASES = (
    ("段",),
    ("巷",),
    ("弄",),
    ("號", "号"),
    ("樓", "楼", "F", "f"),
)


def _component_count(addr: str) -> int:
    """片段含幾個門牌成分（段/巷/弄/號/樓）。"""
    return len(
        re.findall(rf"{_NUM}+\s*(?:段|巷|弄|號|号|樓|楼|F|f)", addr or "")
    )


def _join_address_continuation(cur: str, new: str) -> str:
    """
    把延續片段接在舊址後。

    - 新片段起始成分若舊址已有（如舊址已含「3樓」、新報「5樓」），
      從該成分起截斷舊址再接上，視為更正而非累加。
    - 其餘情況去除重疊字串後直接串接（如「2段」重報）。
    """
    cur_s = re.sub(r"\s+", "", cur)
    new_s = re.sub(r"\s+", "", new)

    head = re.match(rf"^{_NUM}+\s*(段|巷|弄|號|号|樓|楼|F|f)", new_s)
    if head:
        aliases = next(
            (a for a in _UNIT_ALIASES if head.group(1) in a), (head.group(1),)
        )
        matches = list(
            re.finditer(rf"{_NUM}+\s*(?:{'|'.join(aliases)})", cur_s)
        )
        if matches:
            hit = matches[-1]
            # 新片段只更正單一成分（如只報「3號」）→ 原地替換，保留後面的樓層
            if _component_count(new_s) == 1:
                return cur_s[: hit.start()] + new_s + cur_s[hit.end():]
            return cur_s[: hit.start()] + new_s

    for k in range(min(len(cur_s), len(new_s)), 0, -1):
        if cur_s[-k:] == new_s[:k]:
            return cur_s + new_s[k:]
    return cur_s + new_s


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
    # 路名後可接路段（「中央路2段1號3樓」「民權街二段87號」），數字含國字
    _num = r"[一二三四五六七八九十百兩两\d]"
    # 成分可帶「之N」（100之1號 / 148號2樓之3），結尾可帶地下樓層（50號B1）
    _addr_tail = (
        rf"(?:\s*{_num}+\s*段)?"
        rf"(?:\s*{_num}+(?:\s*之\s*{_num}+)?\s*(?:巷|弄|號|号|楼|樓|F|f)"
        rf"(?:\s*之\s*{_num}+)?)+"
        r"(?:\s*[Bb]\d+)?"
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
        rf"(?:{_num}+段)?"
        r"\d*"
        r"(?:巷|弄)?"
        r"\d*"
        r"(?:弄)?"
        rf"(?:{_num}+[號号])?"
        rf"(?:{_num}+[楼樓Ff])?"
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
