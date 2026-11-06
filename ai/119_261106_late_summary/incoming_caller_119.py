"""
incoming_caller_119.py
━━━━━━━━━━━━━━━━━━━━━
通話開始時取得來電號碼與地址。

目前回傳寫死的模擬資料。接上真正的 GET 時，只改 fetch_incoming_caller
的函式本體，呼叫端不用動。回傳格式維持 {"phone": ..., "address": ...}。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

# 模擬用。phone 空、"null" 走原流程；09 開頭為行動；其餘有數字的號碼為市話。
SIMULATED_INCOMING_CALLER: Dict[str, Optional[str]] = {
    "phone": "02-29681234",
    "address": "新北市板橋區文化路一段100號",
}


def fetch_incoming_caller() -> Dict[str, Any]:
    """取得本通來電的號碼與地址。失敗時由呼叫端當成空號。"""
    return dict(SIMULATED_INCOMING_CALLER)


def classify_incoming_line(phone: Any) -> str:
    """依來電號碼分行動、市話或未知。

    回傳 "mobile"（09 開頭）、"landline"（其他有數字的號碼）或 "unknown"
    （空、null、沒有數字）。+886 / 886 會先轉成 0 開頭再判斷。
    """
    if phone is None:
        return "unknown"
    raw = str(phone).strip()
    if not raw or raw.lower() in {"null", "none", "n/a", "na"}:
        return "unknown"
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("886"):
        digits = "0" + digits[3:]
    if not digits:
        return "unknown"
    if digits.startswith("09"):
        return "mobile"
    return "landline"
