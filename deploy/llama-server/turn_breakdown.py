#!/usr/bin/env python3
"""每一句話的回應時間拆解：LLM / BERT / addrCheck / 其他。

用法：
  turn_breakdown.py --since today
  turn_breakdown.py --sess f91714ac
  turn_breakdown.py --since today --detail    # 連每個 LLM task 都列

⚠️ 這台量不到 STT / TTS——那兩段在機器 A（交換機側）。這裡的「回應時間」
是「報警人那句進了本服務 → 受理員下一句出現」，報案人實際感受還要加上
STT 辨識與 TTS 合成的時間。
"""
import argparse, io, re, statistics as st, subprocess
from datetime import datetime

TALK = re.compile(
    r"^(?P<ts>\d+\.\d+).*?\[SOP119 (?P<sid>[0-9a-f]{8})\] "
    r"(?P<who>受理員|報警人)：(?P<text>.*)$"
)
TIME = re.compile(
    r"^(?P<ts>\d+\.\d+).*?\[TIMING\] sid=(?P<sid>\S+) kind=(?P<kind>\w+) "
    r"op=(?P<op>\S+) ms=(?P<ms>[\d.]+)"
)

KINDS = ("llm", "bert", "addrcheck")


def journal(since, path=None):
    """journal（線上）或檔案（測試實例的 uvicorn log）。

    檔案沒有 journal 的 epoch 前綴，這裡補一個遞增的假時間戳：順序仍正確，
    但「總計」欄位量不到真實間隔，只有各段耗時可信。
    """
    if path:
        out = []
        for i, ln in enumerate(io.open(path, encoding="utf-8", errors="replace")):
            out.append(f"{i * 0.001:.6f} {ln.rstrip()}")
        return out
    cmd = ["journalctl", "-u", "sop119", "-o", "short-unix", "--no-pager", "--since", since]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="-2h")
    ap.add_argument("--sess", default=None)
    ap.add_argument("--detail", action="store_true", help="列出每個 LLM task")
    ap.add_argument("--file", default=None, help="改讀 log 檔（測試實例用）")
    a = ap.parse_args()

    # 先把所有事件按時間排成一條線；TIMING 沒有 sid，靠時間落在哪一輪來歸戶
    events = []
    for ln in journal(a.since, a.file):
        m = TALK.match(ln)
        if m:
            events.append((float(m["ts"]), "talk", m.groupdict())); continue
        m = TIME.match(ln)
        if m:
            events.append((float(m["ts"]), "timing", m.groupdict()))
    events.sort(key=lambda e: e[0])

    # 每個 session 各自維護「目前這一輪」，TIMING 依 sid 歸戶。
    # 靠時間先後歸戶在併發時會把 A 通的 LLM 算到 B 通頭上。
    turns = []          # 每輪：{sid, t_start, t_end, ops:[(kind,op,ms)]}
    open_turns = {}     # sid → 進行中的那一輪
    for ts, typ, d in events:
        if typ == "timing":
            cur = open_turns.get(d["sid"])
            if cur is not None:
                cur["ops"].append((d["kind"], d["op"], float(d["ms"])))
            continue
        sid = d["sid"]
        if d["who"] == "報警人":
            open_turns[sid] = {"sid": sid, "t_start": ts, "text": d["text"], "ops": []}
        elif sid in open_turns:
            cur = open_turns.pop(sid)
            cur["t_end"] = ts
            cur["reply"] = d["text"]
            turns.append(cur)
    turns.sort(key=lambda t: t["t_start"])

    from_file = bool(a.file)
    if a.sess:
        turns = [t for t in turns if t["sid"].startswith(a.sess)]
    if not turns:
        print("查無資料（試試 --since today；TIMING 需服務重啟後才有）"); return

    tot = {k: [] for k in KINDS}
    tot["other"] = []
    tot["total"] = []
    cur_sid = None
    for t in turns:
        if t["sid"] != cur_sid:
            cur_sid = t["sid"]; print(f"\n━━ 通話 {cur_sid} ━━")
        by = {k: sum(ms for kk, _, ms in t["ops"] if kk == k) for k in KINDS}
        n_llm = sum(1 for kk, _, _ in t["ops"] if kk == "llm")
        if from_file:
            # 檔案模式沒有真時間戳，「總計」只能是各段相加，也就沒有「其他」
            total_ms = sum(by.values())
            other = 0.0
        else:
            total_ms = (t["t_end"] - t["t_start"]) * 1000.0
            other = max(0.0, total_ms - sum(by.values()))
        for k in KINDS: tot[k].append(by[k])
        tot["other"].append(other); tot["total"].append(total_ms)

        print(f'\n  報警人：{t["text"][:50]}')
        print(f'  受理員：{t["reply"][:50]}')
        line = (f'    {"各段合計" if from_file else "總計"} {total_ms/1000:6.2f}s  =  '
                f'LLM {by["llm"]/1000:5.2f}s ({n_llm}次)  '
                f'BERT {by["bert"]/1000:5.2f}s  '
                f'addrCheck {by["addrcheck"]/1000:5.2f}s')
        if not from_file:
            line += f'  其他 {other/1000:5.2f}s'
        print(line)
        if a.detail:
            for kk, op, ms in t["ops"]:
                print(f'        {kk:9} {op:28} {ms:7.0f}ms')

    n = len(tot["total"])
    print(f"\n═══ {n} 輪合計 ═══")
    if not tot["total"]:
        return
    rows = [("LLM", "llm"), ("BERT", "bert"), ("addrCheck", "addrcheck")]
    if not from_file:
        rows.append(("其他", "other"))
    for label, key in rows:
        share = sum(tot[key]) / sum(tot["total"]) * 100 if sum(tot["total"]) else 0
        print(f"  {label:10} 中位 {st.median(tot[key])/1000:5.2f}s  "
              f"佔比 {share:5.1f}%")
    label = "每輪各段合計" if from_file else "每輪總計"
    print(f"  {label:10} 中位 {st.median(tot['total'])/1000:5.2f}s  "
          f"最慢 {max(tot['total'])/1000:5.2f}s")
    print("\n  ⚠️ 不含 STT / TTS（在機器 A），報案人實際感受還要再加那兩段。")
    if from_file:
        print("  ⚠️ --file 模式沒有真時間戳：只有各段耗時可信，沒有「其他」欄。")


main()
