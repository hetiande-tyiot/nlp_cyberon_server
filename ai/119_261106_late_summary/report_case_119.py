"""
report_case_119.py
━━━━━━━━━━━━━━━━━━
回報流程用來對上既有案件。

目前固定回傳一筆模擬案件，並一律視為對上。接上真正的查詢時，只改
fetch_report_case 的函式本體，呼叫端不用動。
"""

from __future__ import annotations

from typing import Any, Dict

# 模擬用。第三句的例子是燙傷，所以這筆案件的案類用燒燙傷。
SIMULATED_REPORT_CASE: Dict[str, str] = {
    "time": "14:32",
    "address": "新北市板橋區文化路一段100號",
    "case_category": "燒燙傷",
}


def fetch_report_case(caller_text: str = "") -> Dict[str, Any]:
    """依報案人提供的線索對案件。目前忽略內容，固定對上模擬案件。"""
    del caller_text
    return dict(SIMULATED_REPORT_CASE)
