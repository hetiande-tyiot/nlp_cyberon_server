#!/usr/bin/env python3
"""切換後 e2e 煙霧測試：建 session → 送一句 → 看 outputs → /health。"""
import json, sys, time, urllib.request

B = "http://127.0.0.1:8200"

def h(m, p, b=None, timeout=60):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B + p, data=d,
                               headers={"Content-Type": "application/json"}, method=m)
    with urllib.request.urlopen(r, timeout=timeout) as x:
        raw = x.read()
        return json.loads(raw) if raw else {}

print("health:", h("GET", "/health"))

# llama-server 自己的 slot 數
try:
    with urllib.request.urlopen("http://127.0.0.1:8081/slots", timeout=5) as x:
        print("llama-server slots:", len(json.load(x)))
except Exception as e:
    print("⚠️  /slots 讀不到:", e)

sid = h("POST", "/session/new")["session_id"]
t0 = time.time()
out = h("POST", f"/session/{sid}/input", {"text": "板橋文化路車禍有人受傷"})
print(f"input ({time.time()-t0:.2f}s):", json.dumps(out.get("outputs"), ensure_ascii=False))
h("POST", f"/session/{sid}/hangup")
print("health:", h("GET", "/health"))
