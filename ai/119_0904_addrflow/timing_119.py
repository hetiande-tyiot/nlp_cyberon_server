"""每輪各階段耗時紀錄（LLM / BERT / addrCheck）。

為什麼要這個
------------
「一句話等了 4 秒」拆不開就沒法優化。這台只看得到 LLM + BERT + addrCheck；
STT 與 TTS 在機器 A（交換機側），本模組量不到，別誤以為這裡的總和就是
報案人感受到的延遲。

輸出格式（journal 可直接 grep）：
    [TIMING] sid=f91714ac kind=llm op=extract_address ms=412 in=1523 out=48
以 kind 分段，配合 deploy/llama-server/turn_latency.py 聚合成每輪明細。

執行緒安全：只做 print，不共用可變狀態；併發下各 slot 各自輸出。
"""
from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

# 預設開啟——這是營運可觀測性，不是 debug。要關：TIMING_LOG=0
_ENABLED = os.environ.get("TIMING_LOG", "1") != "0"


def enabled() -> bool:
    return _ENABLED


def current_sid() -> str:
    """從執行緒名稱取出 session id。

    sop_api_server 起 engine thread 時取名 "sop119-<sid前8碼>"，
    背景摘要 worker 同理。有了 sid，併發時每行 TIMING 才歸得了戶——
    否則 8 通同時跑，靠時間先後根本分不出哪行屬於哪通。
    """
    name = threading.current_thread().name
    if name.startswith("sop119-"):
        return name[len("sop119-"):][:8]
    return "-"


def emit(kind: str, op: str, ms: float, *, in_size: Optional[int] = None,
         out_size: Optional[int] = None, extra: str = "") -> None:
    if not _ENABLED:
        return
    parts = [f"sid={current_sid()}", f"kind={kind}", f"op={op}", f"ms={ms:.0f}"]
    if in_size is not None:
        parts.append(f"in={in_size}")
    if out_size is not None:
        parts.append(f"out={out_size}")
    if extra:
        parts.append(extra)
    print("[TIMING] " + " ".join(parts), flush=True)


@contextmanager
def track(kind: str, op: str, *, in_size: Optional[int] = None) -> Iterator[dict]:
    """with track("llm", "extract_address", in_size=len(prompt)) as t: ...

    區塊內可設 t["out"] 紀錄輸出大小。例外照樣往外拋，但仍會記時間
    （逾時/失敗的耗時往往才是要查的那個）。
    """
    box: dict = {"out": None}
    t0 = time.perf_counter()
    try:
        yield box
    finally:
        emit(kind, op, (time.perf_counter() - t0) * 1000.0,
             in_size=in_size, out_size=box.get("out"))
