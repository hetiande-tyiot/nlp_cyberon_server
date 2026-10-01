#!/usr/bin/env python3
# ============================================================
# 119 通話測試腳本
# 用法：
#   本機測：  llmenv/bin/python test_call.py                  # 照下面 MESSAGES 劇本跑
#   別台測：  python3 test_call.py 192.168.5.294
#   自訂句子：llmenv/bin/python test_call.py -t "我家失火了" -t "新北市板橋區文化路一段1號"
#   互動模式：llmenv/bin/python test_call.py -i               # 每一句自己即時輸入
#   換劇本：  改下面 MESSAGES
# 互動模式：空行或 Ctrl-D 結束通話；輸入 /case 可看目前抽到的欄位。
# 注意：每一通都會在 log_119 留下一份案件紀錄。
# ============================================================
import argparse, urllib.request, urllib.error, json, time, sys

# ── 你要改的地方：報案人依序講的話（預設劇本）──────────────
MESSAGES = [
    "我要報案，對面麵包店燒起來",
    "新北市板橋區南雅南路2段152號4樓",
    "對",
    "有黑煙",
    "沒有很大",
]

PORT = 8100


def post(base, ep, payload):
    req = urllib.request.Request(
        base + ep, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=180).read())


def get(base, ep):
    return json.loads(urllib.request.urlopen(base + ep, timeout=60).read())


def dump_case(base, sid, title):
    """印出案件裡有值的欄位（逐字稿除外）。"""
    r = get(base, f"/session/{sid}/result")
    case = r.get("case") or r.get("fields") or r
    print(f"\n--- {title}（非空欄位）---")
    if isinstance(case, dict):
        for k, v in case.items():
            if k == "transcript":
                continue
            if v not in (None, "", [], {}):
                print(f"  {k}: {v}")


def iter_turns(turns, base, sid):
    """turns 有值就照劇本跑；為 None 則進互動模式，逐句從鍵盤讀。"""
    if turns is not None:
        yield from turns
        return

    print("互動模式：輸入報案人說的話，按 Enter 送出。空行或 Ctrl-D 結束通話；/case 看目前欄位。\n")
    while True:
        try:
            text = input("me : ").strip()
        except EOFError:
            print()
            return
        if not text:
            return
        if text == "/case":
            dump_case(base, sid, "目前的抽取結果")
            print()
            continue
        yield text


def main():
    p = argparse.ArgumentParser(description="模擬一通 119 電話")
    p.add_argument("host", nargs="?", default="127.0.0.1",
                   help="服務主機，預設本機（如 192.168.5.131）")
    p.add_argument("-t", "--turn", action="append", dest="turns",
                   help="自訂報案人說的每一句，可重複給。給了就不用預設劇本")
    p.add_argument("-i", "--interactive", action="store_true",
                   help="互動模式：每一句自己即時輸入（會忽略 -t）")
    args = p.parse_args()

    base = f"http://{args.host}:{PORT}"
    # None 代表互動模式，交給 iter_turns 從鍵盤讀
    turns = None if args.interactive else (args.turns or MESSAGES)

    print(f"→ 連線 {base}")
    t0 = time.time()
    s = post(base, "/session/new", {})
    sid = s["session_id"]
    print("bot:", s["outputs"])

    try:
        for text in iter_turns(turns, base, sid):
            t = time.time()
            d = post(base, f"/session/{sid}/input", {"text": text})
            if turns is not None:  # 互動模式下這句是自己打的，不用再印一次
                print("me :", text)
            print("bot:", d.get("outputs"), "| done:", d.get("done"), f"| {time.time() - t:.1f}s")
            if d.get("done"):
                break
    except KeyboardInterrupt:
        # 中斷也要掛斷，否則服務那邊的通話會一直留著
        print("\n（已中斷，仍會正常掛斷）")

    post(base, f"/session/{sid}/hangup", {})
    dump_case(base, sid, "抽取結果")
    print(f"\n[耗時 {time.time() - t0:.1f}s]")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as e:
        print(f"❌ 連不上服務：{e}")
        print("   確認服務有起（systemctl is-active sop119）、防火牆有開 8100。")
        sys.exit(1)
