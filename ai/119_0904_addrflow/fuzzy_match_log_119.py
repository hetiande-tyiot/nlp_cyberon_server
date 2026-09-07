"""模糊比對取樣記錄（119 客製，vendor 版沒有）。

換版時整檔複製即可。引擎只需呼叫 `record_fuzzy_match()`。

用途：地址判斷裡有兩處「猜測」，都沒有可靠的相似度門檻——
  1. addrCheck 的地標比對（API 端，我們改不了）
     「捷運頂埔站出口1」→ 捷運新埔站、「未知市場旁邊」→ 文山區景隆街2號附近
  2. address_mapper 的行政區臺語音近比對（本地，門檻目前 0.6 是估的）
     「不分區」→ 瑞芳區（0.583）

門檻要調得準，靠的不是猜，是實際通話裡「報案人到底接不接受這個猜測」。
本模組把每次模糊比對連同報案人的回應寫成 JSONL，累積成調參用的樣本。

輸出：`FUZZY_LOG_PATH`，未設則用 `{LOG_DIR}/fuzzy_matches.jsonl`（LOG_DIR 與
case JSON 同一個目錄，時間戳可與 case119_*.json 對照回完整通話）。
**兩個 env 都沒有就不寫**——不預設寫死路徑，免得跑測試時把測試資料混進
正式樣本，那份樣本是要拿來調 API 門檻的，混進假資料就沒有分析價值。
sop119.service 有設 LOG_DIR，正式環境照常取樣。

寫檔失敗一律吞掉——取樣是附帶功能，不能影響報案流程。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Sequence

DEFAULT_FILENAME = "fuzzy_matches.jsonl"

# 比對種類
KIND_LANDMARK = "landmark_fuzzy"   # addrCheck 地標／捷運模糊比對
KIND_DISTRICT = "district_fuzzy"   # address_mapper 行政區臺語音近比對

# 報案人對這個猜測的反應——調門檻真正要看的欄位
OUTCOME_CONFIRMED = "confirmed"      # 報案人說對
OUTCOME_DENIED = "denied"            # 報案人否認 → 猜錯了
OUTCOME_UNCONFIRMED = "unconfirmed"  # 沒問到（預算用盡／流程中斷）

_WRITE_LOCK = threading.Lock()


def fuzzy_log_path() -> Optional[str]:
    """取樣輸出位置；兩個 env 都沒設時回 None（代表停用取樣）。"""
    explicit = os.getenv("FUZZY_LOG_PATH")
    if explicit:
        return explicit
    log_dir = os.getenv("LOG_DIR")
    if not log_dir:
        return None
    return os.path.join(log_dir, DEFAULT_FILENAME)


def record_fuzzy_match(
    kind: str,
    *,
    spoken: Optional[str],
    matched: Optional[str] = None,
    resolved: Optional[str] = None,
    outcome: str = OUTCOME_UNCONFIRMED,
    score: Optional[float] = None,
    alternatives: Sequence[str] = (),
    api_hint: Optional[str] = None,
    location_type: Optional[str] = None,
    session: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """寫一筆模糊比對取樣；回傳是否寫成功（失敗不拋例外）。

    spoken   報案人原話（STT 結果）——調參時的輸入
    matched  系統猜出來的地標／行政區
    outcome  報案人的反應，見 OUTCOME_*
    """
    record: Dict[str, Any] = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "kind": kind,
        "spoken": spoken,
        "matched": matched,
        "resolved": resolved,
        "outcome": outcome,
        "location_type": location_type,
        "session": session,
    }
    if score is not None:
        record["score"] = round(float(score), 4)
    if alternatives:
        record["alternatives"] = list(alternatives)
    if api_hint:
        # 完整保留原始 hint：API 日後改格式時，舊樣本仍可重新解析。
        record["api_hint"] = api_hint
    if extra:
        record["extra"] = extra

    path = fuzzy_log_path()
    if not path:
        return False
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return True
    except Exception as exc:
        # 取樣失敗不能影響報案流程。
        logging.getLogger(__name__).warning(
            "[fuzzy_match_log] 寫入失敗（已忽略）：%s", exc
        )
        return False


def load_samples(path: Optional[str] = None) -> list[Dict[str, Any]]:
    """讀回樣本供分析；壞掉的行跳過，不讓單行毀損擋住整份資料。"""
    target = path or fuzzy_log_path()
    if not target:
        return []
    samples: list[Dict[str, Any]] = []
    try:
        with open(target, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return samples


def summarize(samples: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """統計各類模糊比對的接受率，作為調門檻的依據。

    denied 的樣本最有價值：那是系統猜錯、而且被報案人抓到的案例。
    """
    rows = list(samples if samples is not None else load_samples())
    summary: Dict[str, Any] = {"total": len(rows), "by_kind": {}}
    for row in rows:
        kind = row.get("kind") or "unknown"
        bucket = summary["by_kind"].setdefault(
            kind,
            {"total": 0, "confirmed": 0, "denied": 0, "unconfirmed": 0,
             "denied_scores": []},
        )
        bucket["total"] += 1
        outcome = row.get("outcome") or OUTCOME_UNCONFIRMED
        if outcome in bucket:
            bucket[outcome] += 1
        if outcome == OUTCOME_DENIED and row.get("score") is not None:
            bucket["denied_scores"].append(row["score"])
    for bucket in summary["by_kind"].values():
        answered = bucket["confirmed"] + bucket["denied"]
        bucket["accept_rate"] = (
            round(bucket["confirmed"] / answered, 3) if answered else None
        )
        scores = bucket.pop("denied_scores")
        # 被否認過的最高分：門檻至少要拉到這之上才擋得掉已知的錯誤比對。
        bucket["max_denied_score"] = max(scores) if scores else None
    return summary


if __name__ == "__main__":
    print(json.dumps(summarize(), ensure_ascii=False, indent=2))
