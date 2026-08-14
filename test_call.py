#!/usr/bin/env python3
# ============================================================
# 110 通話測試腳本
# 用法：
#   本機測：  llmenv/bin/python test_call.py
#   別台測：  python3 test_call.py 192.168.5.131
#   換對話：  改下面 MESSAGES
# ============================================================
import urllib.request, json, time, sys

# ── 你要改的地方：報案人依序講的話 ──────────────────────────
MESSAGES = [
    "我要報案，這裡有小孩跌倒了",
    "新北市板橋區文化路一段跟中山路口",
    "有流血，還有意識",
]

# 目標主機：預設本機，可用第一個參數覆蓋（如 192.168.5.131）
HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = 8100
BASE = f"http://{HOST}:{PORT}"


def post(ep, payload):
    req = urllib.request.Request(
        BASE + ep, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=180).read())


def get(ep):
    return json.loads(urllib.request.urlopen(BASE + ep, timeout=60).read())


def main():
    print(f"→ 連線 {BASE}")
    t0 = time.time()
    s = post("/session/new", {})
    sid = s["session_id"]
    print("bot:", s["outputs"])

    for text in MESSAGES:
        d = post(f"/session/{sid}/input", {"text": text})
        print("me :", text)
        print("bot:", d.get("outputs"), "| done:", d.get("done"))
        if d.get("done"):
            break

    post(f"/session/{sid}/hangup", {})
    r = get(f"/session/{sid}/result")
    case = r.get("case") or r.get("fields") or r

    print("\n--- 抽取結果（非空欄位）---")
    if isinstance(case, dict):
        for k, v in case.items():
            if k == "transcript":
                continue
            if v not in (None, "", [], {}):
                print(f"  {k}: {v}")
    print(f"\n[耗時 {time.time() - t0:.1f}s]")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as e:
        print(f"❌ 連不上 {BASE}：{e}")
        print("   確認服務有起（systemctl is-active sop110）、防火牆有開 8100。")
        sys.exit(1)
