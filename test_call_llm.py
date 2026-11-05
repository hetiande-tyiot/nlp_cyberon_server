#!/usr/bin/env python3
# ============================================================
# 119 通話測試腳本（LLM 扮演報案人）
# 給一段案情，每一輪由 LLM 看系統問了什麼，照案情用報案人的口氣回答，
# 不會像固定劇本那樣答非所問。報案人會照「說話方式」講話，案情分好幾次才講完，像真的報案人。
# 用法：
#   打 911：  llmenv/bin/python test_call_llm.py
#   打 912：  llmenv/bin/python test_call_llm.py --port 8300
#   換案情：  llmenv/bin/python test_call_llm.py -s "板橋區文化路一段1號的透天厝二樓起火，冒黑煙"
#   換說話方式：加 --style "很慌張，一直重複講同一句"
# 一次跑很多通、每類兩筆：用 test_call_batch.py。
# 扮演報案人的 LLM 用 GPU1 的 vLLM（port 8000），被測的 911 用 GPU0。
# 注意：每一通都會在服務的案件紀錄資料夾留下一份案件紀錄。
# ============================================================
import argparse, json, time, sys, urllib.request, urllib.error

from test_call import post, get, dump_case

# 沒給案情時用的預設案情
DEFAULT_SCENARIO = (
    "我是路過的人，看到新北市板橋區南雅南路二段152號一樓的麵包店起火，"
    "店面冒出黑煙，火還不大，看不出裡面有沒有人。"
    "那是一棟五層樓的公寓，一樓是店面，樓上是住家。"
    "我姓王，電話是0912345678。"
)
DEFAULT_STYLE = "一般民眾，講話正常，但不會一次講完，被問到才說。"

CALLER_LLM_URL = "http://127.0.0.1:8000/v1/chat/completions"
CALLER_LLM_MODEL = "/mnt/D/models/Qwen3.6-35B-A3B-FP8"
MAX_TURNS = 25

CALLER_RULES = """你在扮演打 119 報案的民眾。

你知道的全部情況：
{scenario}

你的說話方式：
{style}

回答規則：
1. 像真的在講電話：口語、短句，可以有「呃」「欸」「那個」，慌張時會重複字詞。
2. 不要一次把知道的事情講完。每次只講一點，主要回答 119 最後問的那一題，被問到才補其他細節。
3. 情況裡沒寫的事情就說不知道或不清楚，不可以自己編。
4. 119 在確認資訊時，對的就說對，不對就更正。
5. 只輸出你要說的話，不要加引號、說明或旁白。"""


def caller_reply(scenario, style, transcript):
    """把案情、說話方式和目前的對話送給 LLM，拿回報案人下一句要說的話。
    119 說的話當成對方（user），報案人說過的話當成自己（assistant）。"""
    messages = [{"role": "system", "content": CALLER_RULES.format(scenario=scenario, style=style)}]
    for role, text in transcript:
        messages.append({"role": "user" if role == "bot" else "assistant", "content": text})
    payload = {
        "model": CALLER_LLM_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 80,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        CALLER_LLM_URL, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    return r["choices"][0]["message"]["content"].strip()


def run_call(base, scenario, style=DEFAULT_STYLE, log=print):
    """打一通電話，回傳整通的紀錄：每一輪說了什麼、119 回了什麼、花了幾秒，以及最後的抽取結果。
    每一輪的開始、結束時間也記下來，批次跑的時候用來算同時有幾通在等回應。"""
    record = {"scenario": scenario, "style": style, "turns": [], "ended": None}
    t0 = time.time()
    s = post(base, "/session/new", {})
    sid = s["session_id"]
    record["session_id"] = sid
    log("bot:", s["outputs"])
    # 對話紀錄給 LLM 看：("bot" 或 "me", 說的話)
    transcript = [("bot", "".join(s["outputs"]))]

    try:
        for _ in range(MAX_TURNS):
            text = caller_reply(scenario, style, transcript)
            transcript.append(("me", text))
            start = time.time()
            d = post(base, f"/session/{sid}/input", {"text": text})
            end = time.time()
            outputs = d.get("outputs") or []
            record["turns"].append({
                "caller": text, "bot": outputs, "done": bool(d.get("done")),
                "seconds": round(end - start, 2), "start": start, "end": end,
            })
            log("me :", text)
            log("bot:", outputs, "| done:", d.get("done"), f"| {end - start:.1f}s")
            if d.get("done"):
                record["ended"] = "done"
                break
            transcript.append(("bot", "".join(outputs)))
        else:
            record["ended"] = "max_turns"
            log(f"（已跑滿 {MAX_TURNS} 輪還沒結束，直接掛斷）")
    except KeyboardInterrupt:
        # 中斷也要掛斷，否則服務那邊的通話會一直留著
        record["ended"] = "interrupted"
        log("（已中斷，仍會正常掛斷）")
    except Exception as e:  # 單通出錯也要掛斷，並把錯誤記下來
        record["ended"] = f"error: {e}"
        log(f"（出錯：{e}，仍會正常掛斷）")

    post(base, f"/session/{sid}/hangup", {})
    r = get(base, f"/session/{sid}/result")
    record["case"] = r.get("case") or r.get("fields") or r
    record["total_seconds"] = round(time.time() - t0, 1)
    return record


def main():
    p = argparse.ArgumentParser(description="模擬一通 119 電話，由 LLM 扮演報案人")
    p.add_argument("host", nargs="?", default="127.0.0.1", help="服務主機，預設本機")
    p.add_argument("--port", type=int, default=8100, help="8100 是 911，8300 是 912，預設 8100")
    p.add_argument("-s", "--scenario", default=DEFAULT_SCENARIO, help="案情：報案人知道的全部情況")
    p.add_argument("--style", default=DEFAULT_STYLE, help="報案人的說話方式")
    args = p.parse_args()

    base = f"http://{args.host}:{args.port}"
    print(f"→ 連線 {base}")
    print(f"案情：{args.scenario}")
    print(f"說話方式：{args.style}\n")
    record = run_call(base, args.scenario, args.style)
    dump_case(base, record["session_id"], "抽取結果")
    print(f"\n[耗時 {record['total_seconds']}s]")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as e:
        print(f"❌ 連不上服務：{e}")
        print("   確認 119 服務有起（systemctl is-active sop119），扮演報案人的 vLLM 有起（systemctl is-active vllm-gpu1）。")
        sys.exit(1)
