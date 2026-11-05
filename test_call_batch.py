#!/usr/bin/env python3
# ============================================================
# 119 批次通話測試：照案情清單一次打好幾通（預設四通同時），由 LLM 扮演報案人。
# 用法：
#   全部跑：      llmenv/bin/python test_call_batch.py
#   只跑某案類：  llmenv/bin/python test_call_batch.py --main 火警
#   只跑前幾筆：  llmenv/bin/python test_call_batch.py --limit 4
#   只跑指定編號：llmenv/bin/python test_call_batch.py --ids 009,107
#   改同時幾通：  llmenv/bin/python test_call_batch.py --parallel 2
# 結果存到 test_results/日期時間/：
#   calls/編號.json  每一通的對話、每一輪的反應時間、抽取結果
#   summary.md       案類、次案類對照，反應時間分布，最慢的幾輪花在哪
# 慢的那幾輪會去 911 服務的系統日誌找同一通的時間紀錄，拆出分類模型、LLM 抽取各花多久。
# 注意：每一通都會在服務的案件紀錄資料夾留下一份案件紀錄。
# ============================================================
import argparse, json, os, re, subprocess, threading, time
from concurrent.futures import ThreadPoolExecutor

from test_call_llm import run_call

SCENARIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_scenarios", "119_scenarios.json")
SLOWEST_SHOWN = 20


def server_timings(unit, since, until):
    """從服務的系統日誌撈出這段時間的時間紀錄，依通話分組：{sid前8碼: [(時間, 種類, 動作, 毫秒)]}。"""
    out = subprocess.run(
        ["journalctl", "-u", unit, "--since", since, "--until", until, "--no-pager", "-o", "short-unix"],
        capture_output=True, text=True).stdout
    found = {}
    pat = re.compile(r"^(\d+\.\d+) .*\[TIMING\] sid=(\w+) kind=(\w+) op=(\S+) ms=(\d+)")
    for line in out.splitlines():
        m = pat.match(line)
        if m:
            ts, sid, kind, op, ms = m.groups()
            found.setdefault(sid, []).append((float(ts), kind, op, int(ms)))
    return found


def percentile(values, p):
    values = sorted(values)
    if not values:
        return 0
    k = (len(values) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 2)


def main():
    p = argparse.ArgumentParser(description="119 批次通話測試，LLM 扮演報案人")
    p.add_argument("host", nargs="?", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8100, help="8100 是 911，8300 是 912，預設 8100")
    p.add_argument("--parallel", type=int, default=4, help="同時打幾通，預設 4")
    p.add_argument("--main", help="只跑這個案類")
    p.add_argument("--limit", type=int, help="只跑前幾筆")
    p.add_argument("--ids", help="只跑這些編號，用逗號分開，例如 009,107")
    args = p.parse_args()

    unit = "sop119" if args.port == 8100 else "sop119-test"
    base = f"http://{args.host}:{args.port}"
    scenarios = json.load(open(SCENARIO_FILE, encoding="utf-8"))
    if args.main:
        scenarios = [s for s in scenarios if s["main"] == args.main]
    if args.ids:
        wanted = set(args.ids.split(","))
        scenarios = [s for s in scenarios if s["id"] in wanted]
    if args.limit:
        scenarios = scenarios[:args.limit]

    out_dir = os.path.join("test_results", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(os.path.join(out_dir, "calls"), exist_ok=True)
    print(f"→ {base}，共 {len(scenarios)} 通，同時 {args.parallel} 通，結果存到 {out_dir}")

    print_lock = threading.Lock()
    done_count = [0]
    t_begin = time.time()

    def one(sc):
        # 批次跑時不印每一輪，只在每通結束時印一行
        record = run_call(base, sc["facts"], sc["style"], log=lambda *a: None)
        record.update({k: sc[k] for k in ("id", "main", "sub")})
        with open(os.path.join(out_dir, "calls", f"{sc['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=1)
        case = record["case"]
        with print_lock:
            done_count[0] += 1
            print(f"[{done_count[0]}/{len(scenarios)}] {sc['id']} 預期 {sc['main']}/{sc['sub']} → "
                  f"{case.get('main_category')}/{case.get('sub_category')}，{len(record['turns'])} 輪，"
                  f"{record['ended']}，{record['total_seconds']}s", flush=True)
        return record

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        records = list(pool.map(one, scenarios))
    t_end = time.time()

    write_summary(out_dir, records, unit, t_begin, t_end, args.parallel)
    print(f"\n完成，總共 {t_end - t_begin:.0f}s，報告：{out_dir}/summary.md")


def write_summary(out_dir, records, unit, t_begin, t_end, parallel):
    # 每一輪送出的那一刻，同時有幾通在等 119 回應（含自己）
    all_turns = []
    for r in records:
        for i, t in enumerate(r["turns"]):
            all_turns.append((r, i, t))
    for r, i, t in all_turns:
        t["waiting_calls"] = sum(1 for _, _, o in all_turns if o["start"] <= t["start"] < o["end"])

    timings = server_timings(unit, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t_begin - 5)),
                             time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t_end + 5)))

    lines = [f"# 119 批次通話測試 {os.path.basename(out_dir)}", "",
             f"- 共 {len(records)} 通，同時 {parallel} 通，總共 {t_end - t_begin:.0f} 秒",
             ""]

    # ── 案類、次案類對照 ──
    main_ok = sum(1 for r in records if r["case"].get("main_category") == r["main"])
    sub_ok = sum(1 for r in records if r["case"].get("sub_category") == r["sub"])
    finished = sum(1 for r in records if r["ended"] == "done")
    lines += ["## 分類結果", "",
              f"- 主案類對：{main_ok}/{len(records)}",
              f"- 次案類對：{sub_ok}/{len(records)}",
              f"- 正常跑完：{finished}/{len(records)}", "",
              "| 編號 | 預期案類 | 實際案類 | 預期次案類 | 實際次案類 | 結束 | 輪數 |",
              "|---|---|---|---|---|---|---|"]
    for r in records:
        c = r["case"]
        mark_main = "" if c.get("main_category") == r["main"] else " ❌"
        mark_sub = "" if c.get("sub_category") == r["sub"] else " ❌"
        lines.append(f"| {r['id']} | {r['main']} | {c.get('main_category')}{mark_main} | {r['sub']} | "
                     f"{c.get('sub_category')}{mark_sub} | {r['ended']}（{c.get('result')}） | {len(r['turns'])} |")

    # ── 反應時間 ──
    secs = [t["seconds"] for _, _, t in all_turns]
    lines += ["", "## 反應時間（送出報案人的話到收到 119 回覆，不含語音辨識、語音合成）", "",
              f"- 共 {len(secs)} 輪：中位數 {percentile(secs, 50)}s、90% {percentile(secs, 90)}s、"
              f"95% {percentile(secs, 95)}s、最慢 {max(secs) if secs else 0}s", ""]
    lines += ["| 同時等回應的通數 | 輪數 | 中位數 | 95% | 最慢 |", "|---|---|---|---|---|"]
    for n in sorted({t["waiting_calls"] for _, _, t in all_turns}):
        v = [t["seconds"] for _, _, t in all_turns if t["waiting_calls"] == n]
        lines.append(f"| {n} | {len(v)} | {percentile(v, 50)}s | {percentile(v, 95)}s | {max(v)}s |")

    # ── 最慢的幾輪，拆出時間花在哪 ──
    lines += ["", f"## 最慢的 {SLOWEST_SHOWN} 輪", ""]
    for r, i, t in sorted(all_turns, key=lambda x: -x[2]["seconds"])[:SLOWEST_SHOWN]:
        sid = r["session_id"][:8]
        # 同一個動作會分好幾組同時跑，所以依動作合併：做了幾次、最長一次多久
        by_op = {}
        for ts, kind, op, ms in timings.get(sid, []):
            if t["start"] - 0.5 <= ts <= t["end"] + 0.5:
                by_op.setdefault(f"{kind}:{op}", []).append(ms)
        parts = [f"{op} {len(v)} 次、最長 {max(v) / 1000:.1f}s"
                 for op, v in sorted(by_op.items(), key=lambda x: -max(x[1]))]
        lines += [f"- **{t['seconds']}s**｜{r['id']} 第 {i + 1} 輪｜同時 {t['waiting_calls']} 通",
                  f"  - 報案人：{t['caller']}",
                  f"  - 119：{''.join(t['bot'])}",
                  f"  - 花在：{'、'.join(parts) if parts else '（日誌沒有對到時間紀錄）'}"]

    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
