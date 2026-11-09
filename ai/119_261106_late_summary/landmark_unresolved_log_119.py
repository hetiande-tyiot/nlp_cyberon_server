"""「無法判別」表：地標、捷運、路燈這類地點，addrCheck 查不到或報案人否認系統找到的地點時記一筆。

用途：之後慢慢把常被講到、卻查不到的地點補進 scripts/landmarks.xlsx。
輸出：`{LOG_DIR}/landmark_unresolved.jsonl`，一筆一行（多通電話同時寫也不會互相蓋掉）。
LOG_DIR 沒設就不寫，跑測試時不會把假資料混進正式紀錄；寫入失敗也不影響報案流程。
寫法比照 fuzzy_match_log_119.py。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Optional

DEFAULT_FILENAME = "landmark_unresolved.jsonl"

# 沒採用的原因
REASON_NOT_FOUND = "查不到"
REASON_DENIED = "報案人否認"

_WRITE_LOCK = threading.Lock()


def record_unresolved(
    *,
    spoken: Optional[str],
    reason: str,
    location_type: Optional[str] = None,
    matched: Optional[str] = None,
    resolved: Optional[str] = None,
    api_hint: Optional[str] = None,
    call_uuid: Optional[str] = None,
) -> None:
    """記一筆無法判別的地點。spoken 是報案人講的話，matched／resolved 是 addrCheck 猜的地標和地址。"""
    log_dir = os.getenv("LOG_DIR")
    if not log_dir:
        return
    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "call_uuid": call_uuid,
        "spoken": spoken,
        "reason": reason,
        "location_type": location_type,
        "matched": matched,
        "resolved": resolved,
        "api_hint": api_hint,
    }
    try:
        os.makedirs(log_dir, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with _WRITE_LOCK:
            with open(os.path.join(log_dir, DEFAULT_FILENAME), "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception as exc:
        logging.getLogger(__name__).warning("[landmark_unresolved] 寫入失敗（已忽略）：%s", exc)
