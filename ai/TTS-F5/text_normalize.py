"""TTS 文字正規化：阿拉伯數字 → 中文，讓 F5-TTS 用中文唸數字。

規則（針對 110 受理情境）:
  1. 長數字串（>=4 碼，電話/案件編號/車牌數字）→ 逐位唸：0912 → 零九一二
  2. 「110」「119」「113」等三碼專線 → 逐位唸：110 → 一一零
  3. 數字+量詞（分鐘/位/個/歲/樓/公尺…）→ 數量唸法：3分鐘 → 三分鐘、25歲 → 二十五歲
  4. 其他 1-3 碼數字 → 數量唸法：12 → 十二
  5. 警用/無線電情境（車牌、呼號、代碼…關鍵字後的數字）→ 報讀式逐位：
     1709 → 么拐洞勾（洞么兩三四五六拐八勾）
"""

from __future__ import annotations

import re

_DIGITS = "零一二三四五六七八九"
# 警用/無線電報讀式（0-9）。1 用「幺」不用「么」：實測 F5 把破音字「么」
# 唸成 ㄇㄜ˙，「幺」才穩定唸 ㄧㄠ（ASR 反向驗證 2026-07-07）。
_DIGITS_RADIO = "洞幺兩三四五六拐八勾"

# 這些關鍵字之後（10 字內）出現的數字 → 報讀式逐位唸
_RADIO_CONTEXTS = "車牌|車號|呼號|代號|代碼|警編|編號|警車|巡邏車|單位"

# 常見量詞/單位（後接時採數量唸法）
_MEASURES = (
    "分鐘|小時|秒|天|週|個月|年|歲|位|個|人|名|件|次|樓|號|巷|弄|段"
    "公尺|公里|公分|公斤|克|毫升|升|元|塊|萬|千|百|台|輛|隻|條|支|間|棟|瓶|張"
)

_EMERGENCY_LINES = {"110", "119", "112", "113", "165", "166", "168", "911"}


def _digit_by_digit(num: str, radio: bool = False) -> str:
    table = _DIGITS_RADIO if radio else _DIGITS
    return "".join(table[int(c)] for c in num)


def _is_radio_context(text: str, num_start: int) -> bool:
    """數字前 10 個字內有警用關鍵字（車牌/呼號/代碼…）→ 用報讀式。"""
    window = text[max(0, num_start - 10) : num_start]
    return re.search(rf"(?:{_RADIO_CONTEXTS})", window) is not None


def _quantity(num: str) -> str:
    """整數數量唸法，支援 0 ~ 99999999。"""
    n = int(num)
    if n == 0:
        return "零"
    if n >= 100000000:  # 太大就逐位唸
        return _digit_by_digit(num)

    units = ["", "十", "百", "千"]

    def _under_10000(x: int) -> str:
        s = ""
        ds = [int(c) for c in str(x)]
        L = len(ds)
        for i, d in enumerate(ds):
            pos = L - 1 - i
            if d == 0:
                if s and not s.endswith("零") and pos > 0 and any(ds[i + 1 :]):
                    s += "零"
                continue
            if d == 1 and pos == 1 and i == 0:
                s += "十"  # 10-19 → 十x 而非 一十x
            else:
                s += _DIGITS[d] + units[pos]
        return s

    if n < 10000:
        return _under_10000(n)
    high, low = divmod(n, 10000)
    s = _under_10000(high) + "萬"
    if low:
        if low < 1000:
            s += "零"
        s += _under_10000(low)
    return s


def _convert_match(m: re.Match) -> str:
    num = m.group(0)
    tail = m.string[m.end() : m.end() + 3]

    if _is_radio_context(m.string, m.start()):
        return _digit_by_digit(num, radio=True)  # 車牌/呼號/代碼 → 么兩…拐八勾洞
    if num in _EMERGENCY_LINES:
        return _digit_by_digit(num)
    if len(num) >= 4 or num.startswith("0"):
        return _digit_by_digit(num)  # 電話、編號 → 逐位
    if re.match(rf"(?:{_MEASURES})", tail):
        return _quantity(num)  # 數字+量詞 → 數量
    return _quantity(num)


def normalize_for_tts(text: str) -> str:
    """把文字中的阿拉伯數字轉成中文唸法。冪等，可安全重複呼叫。"""
    if not text:
        return text
    # 小數：3.5 → 三點五
    text = re.sub(
        r"\d+\.\d+",
        lambda m: _quantity(m.group(0).split(".")[0])
        + "點"
        + _digit_by_digit(m.group(0).split(".")[1]),
        text,
    )
    # 整數
    text = re.sub(r"\d+", _convert_match, text)
    return text


if __name__ == "__main__":
    tests = [
        "新北市警局110您好",
        "請撥打0912345678聯絡我",
        "警員大約3分鐘內到達，現場有25歲男子1名",
        "地址中山路2段15號3樓",
        "體溫38.5度",
        "肇事車輛車牌1709，車號BMW2345",
        "呼號301請回報，巡邏車8210前往支援",
        "案件編號20260707",
    ]
    for t in tests:
        print(f"{t}\n  → {normalize_for_tts(t)}\n")
