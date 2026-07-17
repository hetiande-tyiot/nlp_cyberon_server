"""
sop_utils_119.py
━━━━━━━━━━━━━━━━━
119 報案受理 — 規則備援工具（LLM 不可用或抽取失敗時使用）
"""

from __future__ import annotations

import re
from typing import Optional


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
        if any(k in s for k in (
            "清醒", "有意識", "有意识", "還清醒", "是清醒", "會回應", "會睜眼",
            "睜得開", "有反應", "會動", "是，清醒", "對，清醒",
        )):
            if not any(k in s for k in (
                "沒有意識", "没有意识", "無意識", "无意识", "昏迷", "叫不醒",
                "沒反應", "没反应", "無反應",
            )):
                return True
        if any(k in s for k in ("沒有意識", "没有意识", "無意識", "昏迷", "叫不醒", "沒反應")):
            return False

    if any(k in q for k in ("呼吸",)):
        if any(k in s for k in ("有呼吸", "還在呼吸", "在呼吸", "會呼吸", "是，有呼吸", "有，在呼吸")):
            if "沒有呼吸" not in s and "沒呼吸" not in s and "無呼吸" not in s:
                return True
        if any(k in s for k in ("沒有呼吸", "沒呼吸", "无呼吸", "無呼吸", "不呼吸", "沒在呼吸")):
            return False

    if any(k in q for k in ("起伏", "肚子", "腹部")):
        if any(k in s for k in ("有起伏", "還在起伏", "肚子有動", "腹部有起伏", "有在動")):
            if not any(k in s for k in ("沒有起伏", "沒起伏", "無起伏", "不會動")):
                return True
        if any(k in s for k in ("沒有起伏", "沒起伏", "無起伏", "肚子不動", "不會動")):
            return False

    # 確認類問題（地址/摘要）
    if any(k in q for k in ("確定", "是否", "對嗎", "正確", "以上")):
        return parse_yes_no(clauses[-1] if clauses else s)

    return None


def extract_patient_info_hint(text: str) -> dict:
    """
    規則備援：從報警人原話抽取患者性別/年齡/事件/現況。
    適用於意識問答等長答中夾帶病情描述的情形。
    """
    s = (text or "").strip()
    if not s:
        return {}
    out: dict = {}

    if re.search(r"(男性|男生|男患者|是男|男的)", s):
        out["patient_gender"] = "男"
    elif re.search(r"(女性|女生|女患者|是女|女的)", s):
        out["patient_gender"] = "女"

    m_age = re.search(r"(\d{1,3})\s*歲", s)
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


def clean_address_fragment(text: str) -> str:
    """清理地址片段，去除事件描述等非地址尾綴。"""
    if not text:
        return ""
    s = text.strip()
    s = re.sub(r"[。\.，,；;！!？?]+$", "", s)
    for prefix in ("救護車，", "救護車,", "消防車，", "消防車,"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    s = re.split(
        r"(?:發生|有人|出(?:了)?車禍|車禍|受傷|倒地|昏倒|需要救護|要救護)",
        s,
        maxsplit=1,
    )[0].strip()
    return s


def merge_address(current: Optional[str], new: Optional[str]) -> Optional[str]:
    """
    合併兩段地址。確認環節報警人常只補門牌/弄，省略區名。

    例：中和區連城路347巷附近 + 連城路347巷1弄2號附近
        → 中和區連城路347巷1弄2號附近
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

    district_m = re.search(r"([\u4e00-\u9fff]{1,8}區)", cur)
    district = district_m.group(1) if district_m else ""

    # 新路名與舊路名有重疊 → 保留區名 + 較精確路段
    if district and district not in n:
        road_cur = _extract_road_core(cur)
        road_new = _extract_road_core(n)
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

    # 區 + 路/街 + 門牌 正則
    m = re.search(
        r"((?:[\u4e00-\u9fff]{1,8}區)"
        r"[\u4e00-\u9fff0-9]*"
        r"(?:路|街|大道)"
        r"\d*"
        r"(?:巷|弄)?"
        r"\d*"
        r"(?:弄)?"
        r"(?:\d+號)?"
        r"(?:附近)?)",
        s,
    )
    if m:
        loc = clean_address_fragment(m.group(1).strip())
        if _looks_like_address(loc):
            return loc

    # 無區名但有路+門牌（確認環節補充門牌）
    m2 = re.search(
        r"([\u4e00-\u9fff0-9]+(?:路|街|大道)\d*(?:巷|弄)?\d*(?:弄)?\d*號?(?:附近)?)",
        s,
    )
    if m2:
        loc = clean_address_fragment(m2.group(1).strip())
        if _looks_like_address(loc):
            return loc

    # 含關鍵地名字樣的較短片段
    keywords = ("區", "路", "街", "大道", "巷", "弄", "號", "樓", "F")
    if any(k in s for k in keywords) and len(s) <= 40:
        loc = clean_address_fragment(s)
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
