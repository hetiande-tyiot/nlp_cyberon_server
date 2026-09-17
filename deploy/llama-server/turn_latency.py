#!/usr/bin/env python3
"""從 sop119 的 journal 算出每句話的回應時間。

用法：
  turn_latency.py                 # 最近 2 小時所有通話
  turn_latency.py --since "today" # 指定範圍（journalctl 語法）
  turn_latency.py --sess e05e68ce # 只看某一通
一句「回應時間」＝ 報警人說完 → 受理員下一句出現 的間隔。
"""
import argparse, re, statistics as st, subprocess, sys
from datetime import datetime

# 用 short-unix（epoch 秒）而非人類可讀時間：不受 locale 影響（中文 locale 會印「9月 15」）
LINE = re.compile(
    r"^(?P<ts>\d+\.\d+).*?\[SOP119 (?P<sid>[0-9a-f]{8})\] "
    r"(?P<who>受理員|報警人)：(?P<text>.*)$"
)

def parse(since, sess):
    cmd = ["journalctl", "-u", "sop119", "-o", "short-unix", "--no-pager", "--since", since]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    calls = {}
    for ln in out.splitlines():
        m = LINE.match(ln)
        if not m: continue
        sid = m["sid"]
        if sess and not sid.startswith(sess): continue
        ts = datetime.fromtimestamp(float(m["ts"]))
        calls.setdefault(sid, []).append((ts, m["who"], m["text"]))
    return calls

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="-2h")
    ap.add_argument("--sess", default=None)
    a = ap.parse_args()

    calls = parse(a.since, a.sess)
    if not calls:
        print("查無通話紀錄（試試 --since 'today'）"); return
    alllat = []
    for sid, evs in calls.items():
        print(f"\n━━ 通話 {sid} ━━ (共 {len(evs)} 句)")
        pending = None
        lat = []
        for ts, who, text in evs:
            if who == "報警人":
                pending = ts
                print(f"  {ts:%H:%M:%S.%f}          報警人：{text[:44]}")
            else:
                if pending is not None:
                    d = (ts - pending).total_seconds()
                    lat.append(d); alllat.append(d)
                    flag = " ⚠️" if d > 5 else ""
                    print(f"  {ts:%H:%M:%S.%f}  {d:6.2f}s  受理員：{text[:44]}{flag}")
                    pending = None
                else:  # 同一輪連續多句（不另計時）
                    print(f"  {ts:%H:%M:%S.%f}     ↳    受理員：{text[:44]}")
        if lat:
            print(f"  → 本通 {len(lat)} 輪：中位 {st.median(lat):.2f}s  "
                  f"最快 {min(lat):.2f}s  最慢 {max(lat):.2f}s")
    if alllat:
        alllat.sort()
        p = lambda q: alllat[min(int(len(alllat)*q), len(alllat)-1)]
        print(f"\n═══ 全部 {len(alllat)} 輪 ═══")
        print(f"  中位 {st.median(alllat):.2f}s | p90 {p(0.9):.2f}s | p95 {p(0.95):.2f}s | "
              f"最慢 {max(alllat):.2f}s | >5s 的有 {sum(1 for x in alllat if x>5)} 輪")

main()
