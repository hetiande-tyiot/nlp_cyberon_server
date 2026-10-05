#!/usr/bin/env python3
"""重放 bench/cases_50.json 到 sop119 API，量延遲 / 吞吐。純 stdlib。

模式：
  latency    — 序列跑完所有案件，逐輪計時；報 p50/p95/mean（整體 + 火警/救護）
  throughput — N 個案件併發跑，報 turns/sec 與負載下 per-turn p95
  sweep      — throughput 掃 1,2,4,8,16 併發，一次列表

用法：
  replay.py --host http://127.0.0.1:8100 --mode latency  --out out_lat.json
  replay.py --host http://127.0.0.1:8100 --mode throughput --concurrency 8 --out out_tp.json
  replay.py --host http://127.0.0.1:8100 --mode sweep --out out_sweep.json

量到的「每輪延遲」= POST /input 的 round-trip（server 端完整處理一輪：
BERT+多次LLM+addrCheck+摘要）。不含 STT/TTS（在機器 A）。
"""
import argparse, json, statistics as st, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

def _req(host, method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(host + path, data=data,
                               headers={"Content-Type": "application/json"},
                               method=method)
    with urllib.request.urlopen(r, timeout=timeout) as x:
        raw = x.read()
        return json.loads(raw) if raw else {}

def run_case(host, case, timeout=120):
    """跑完一個案件，回傳每輪記錄 list。"""
    recs = []
    try:
        sid = _req(host, "POST", "/session/new")["session_id"]
    except Exception as e:
        return [{"case_id": case["case_id"], "cat": case["main_category"],
                 "turn": 0, "ms": None, "ok": False, "err": f"new:{e}"}]
    try:
        for i, text in enumerate(case["caller_turns"]):
            t0 = time.perf_counter()
            try:
                _req(host, "POST", f"/session/{sid}/input", {"text": text}, timeout)
                ms = (time.perf_counter() - t0) * 1000.0
                recs.append({"case_id": case["case_id"], "cat": case["main_category"],
                             "turn": i, "ms": ms, "ok": True})
            except Exception as e:
                ms = (time.perf_counter() - t0) * 1000.0
                recs.append({"case_id": case["case_id"], "cat": case["main_category"],
                             "turn": i, "ms": ms, "ok": False, "err": str(e)[:80]})
                break  # 這通後面不再送
    finally:
        try: _req(host, "DELETE", f"/session/{sid}", timeout=10)
        except Exception:
            try: _req(host, "POST", f"/session/{sid}/hangup", timeout=10)
            except Exception: pass
    return recs

def pct(xs, q):
    if not xs: return None
    xs = sorted(xs)
    return xs[min(int(len(xs) * q), len(xs) - 1)]

def summarize(recs):
    ok = [r["ms"] for r in recs if r["ok"] and r["ms"] is not None]
    fire = [r["ms"] for r in recs if r["ok"] and r["cat"] == "火警"]
    amb = [r["ms"] for r in recs if r["ok"] and r["cat"] == "救護"]
    def box(xs):
        if not xs: return None
        return {"n": len(xs), "p50": round(st.median(xs)), "p95": round(pct(xs, .95)),
                "mean": round(st.mean(xs)), "max": round(max(xs))}
    return {"all": box(ok), "火警": box(fire), "救護": box(amb),
            "turns_ok": len(ok), "turns_fail": sum(1 for r in recs if not r["ok"])}

def warmup(host, cases, n=2):
    for c in cases[:n]:
        run_case(host, c)

def mode_latency(host, cases):
    t0 = time.perf_counter()
    recs = []
    for c in cases:
        recs += run_case(host, c)
    wall = time.perf_counter() - t0
    s = summarize(recs)
    s["wall_s"] = round(wall, 1)
    return {"mode": "latency", "summary": s, "records": recs}

def mode_throughput(host, cases, concurrency):
    t0 = time.perf_counter()
    recs = []
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for part in ex.map(lambda c: run_case(host, c), cases):
            with lock: recs += part
    wall = time.perf_counter() - t0
    ok = [r for r in recs if r["ok"]]
    s = summarize(recs)
    s["wall_s"] = round(wall, 1)
    s["throughput_turns_per_s"] = round(len(ok) / wall, 2) if wall else 0
    s["concurrency"] = concurrency
    return {"mode": "throughput", "summary": s, "records": recs}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://127.0.0.1:8100")
    ap.add_argument("--cases", default="bench/cases_50.json")
    ap.add_argument("--mode", choices=["latency", "throughput", "sweep"], default="latency")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--sweep-levels", default="1,2,4,8,16")
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cases = json.load(open(a.cases, encoding="utf-8"))
    print(f"host={a.host}  cases={len(cases)}  mode={a.mode}", flush=True)

    print(f"暖機 {a.warmup} 案…", flush=True)
    warmup(a.host, cases, a.warmup)

    if a.mode == "latency":
        res = mode_latency(a.host, cases)
        s = res["summary"]
        print(f"\n[latency] {s['turns_ok']} 輪 OK / {s['turns_fail']} 失敗，牆鐘 {s['wall_s']}s")
        for k in ("all", "火警", "救護"):
            b = s[k]
            if b: print(f"  {k:4} n={b['n']:3}  p50={b['p50']}ms  p95={b['p95']}ms  "
                        f"mean={b['mean']}ms  max={b['max']}ms")
    elif a.mode == "throughput":
        res = mode_throughput(a.host, cases, a.concurrency)
        s = res["summary"]
        print(f"\n[throughput c={a.concurrency}] {s['throughput_turns_per_s']} turns/s，"
              f"牆鐘 {s['wall_s']}s，p95={s['all']['p95']}ms")
    else:  # sweep
        levels = [int(x) for x in a.sweep_levels.split(",")]
        rows = []
        for c in levels:
            r = mode_throughput(a.host, cases, c)
            s = r["summary"]
            rows.append({"concurrency": c, "throughput": s["throughput_turns_per_s"],
                         "p95_ms": s["all"]["p95"], "wall_s": s["wall_s"],
                         "turns_fail": s["turns_fail"]})
            print(f"  c={c:3}  {s['throughput_turns_per_s']:6.2f} turns/s  "
                  f"p95={s['all']['p95']}ms  wall={s['wall_s']}s  fail={s['turns_fail']}",
                  flush=True)
        res = {"mode": "sweep", "rows": rows}

    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n→ 寫入 {a.out}")

if __name__ == "__main__":
    main()
