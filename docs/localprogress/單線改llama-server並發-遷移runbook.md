# 單線 in-process → llama-server 並發 遷移 runbook

把一個「route A 型、in-process GGUF、單線序列化」的 110/119 NLP 服務，改成
**llama-server 多 slot 後端（真並發）**，API 合約完全不變、機器 A / client 零改動。
整合自 204（主）+ 131 的實作與踩雷。路徑/服務名用佔位符，套用時替換。

> 佔位符：`<USER>`（如 aitop4/cyberon1）、`<PROJ>`（專案根，如 `/home/<USER>/nlp_cyberon_server`）、
> `<APPDIR>`（服務工作目錄，含 sop_api_server.py）、`<SVC>`（現有服務名，如 nlp-api / sop110 / sop119）、
> `<VENV>`（venv bin，如 `.../venv/bin` 或 `.../llmenv/bin`）、`<MODEL_GGUF>`（抽取 LLM gguf 路徑）、`<PORT>`（服務埠，如 8100/8200）。

---

## 0. 適用前提

- 服務是 **route A 型**：`uvicorn sop_api_server:app`，in-process GGUF（`GgufLlamaCppFieldExtractor`），LLM 被單一 `_gen_lock` 序列化 → 多通會排隊接力。
- 硬體：**RTX 5090（sm_120）32GB / Ubuntu 24.04**，且已裝 **cuda-12.9 nvcc**（`/usr/local/cuda-12.9`）。
- 一份 20GB gguf + 8 slot/65536 ctx ≈ 22–28GB，32GB 放得下（無其他大 GPU 佔用時餘裕更多）。

## 1. 原理（為什麼這樣改）

| | 改前（in-process） | 改後（llama-server） |
|---|---|---|
| 抽取器 | `GgufLlamaCppFieldExtractor`（**有 `_gen_lock`**）| `LlamaServerFieldExtractor`（**無 gen lock**，共用 thread-safe httpx.Client） |
| 並發 | 最多 1 通跑 LLM，其餘等鎖 | llama-server `--parallel N` 個 slot，真並發 batching |
| API 合約 | route A | **完全不變**（同 endpoint / payload） |

- slot 數 = `--parallel`；`--ctx-size` = 總 context；每 slot = ctx ÷ parallel。8 slot/65536 = 每 slot 8192。
- 一通電話一輪 = 多個 LLM task（前景 step 抽取 ~2-3 + 背景 refresh：post_extract 主 + dispatch_attention + summary = 3，合計 ~6）；slot 是「同時在跑的生成數」，故 ~2 通就可能占滿 4 slot。

## 2. 程式前提：`sop_api_server.py` 要有 `LLM_BACKEND` 分支

檢查：
```bash
grep -c "LLM_BACKEND" <APPDIR>/sop_api_server.py    # 0=沒有,要加;≥1=已有
grep -c "def close_session" <APPDIR>/sop_api_server.py   # DELETE /session 清理(建議一起有)
grep -c "session-reaper\|last_activity" <APPDIR>/sop_api_server.py  # 閒置防呆 reaper
```

**若沒有 `LLM_BACKEND` 分支**，把 extractor 實例化那段（原本 `_shared_llm_extractor = GgufLlamaCppFieldExtractor(...)`）改成向後相容分支（預設 gguf＝原行為，設 env 才走 llama-server）：
```python
_shared_llm_extractor = None
LLM_BACKEND = os.environ.get("LLM_BACKEND", "gguf").strip().lower()
if LLM_BACKEND in ("llama-server", "llama_server", "server"):
    from llm_extractors import LlamaServerFieldExtractor
    _shared_llm_extractor = LlamaServerFieldExtractor(
        base_url=os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8081"),
        model=os.environ.get("LLAMA_SERVER_MODEL", "tw-110-model-v2"),
        max_new_tokens=GGUF_MAX_NEW_TOKENS,
        timeout_s=float(os.environ.get("LLAMA_SERVER_TIMEOUT", "180")),
    )
    print("✅ llama-server LLM extractor 就緒", flush=True)
elif os.path.isfile(GGUF_MODEL_PATH):
    _shared_llm_extractor = GgufLlamaCppFieldExtractor(model_path=GGUF_MODEL_PATH, max_new_tokens=GGUF_MAX_NEW_TOKENS)
```
> `LlamaServerFieldExtractor` 已在 `llm_extractors.py`（vendor 內建）。確認它的 `_cache_lock` 只鎖 cache 讀寫、不含 HTTP 生成（才有並發）。

（可選但建議）**session 清理**：若沒有 `DELETE /session/{id}` + 閒置 reaper，`_sessions` dict 會只增不減（記憶體洩漏）。從 204/131 版 `sop_api_server.py` port 這兩段（`close_session` endpoint + `last_activity` + `_session_reaper_loop`）。

## 3. 取得 sm_120 `llama-server` binary

**方法 A（推薦，快）：從已建好的機器複製**（免裝 cmake/編譯）
```bash
# 在來源機（如 204）→ 目標機
rsync -az /home/aitop4/project/110llm/llama.cpp/build-sm120/bin/  <USER>@<目標IP>:<PROJ>/llama-server-sm120/bin/
```
⚠️ **binary 的 rpath 指向來源機絕對路徑**，所以執行時 `LD_LIBRARY_PATH` **必須包含 binary 所在的 bin 目錄本身** + cuda-12.9 lib64（見第 4 節 service）。

**方法 B：目標機自己編**（缺 binary 又不能複製時）
```bash
# 需要 cmake（sudo apt install cmake）+ 原碼
cd <某處> && git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -S . -B build-sm120 -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 \
      -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.9/bin/nvcc -DCMAKE_BUILD_TYPE=Release
cmake --build build-sm120 --config Release --target llama-server -j "$(nproc)"
```

驗證 binary（目標機上，帶 LD_LIBRARY_PATH）：
```bash
BIN=<PROJ>/llama-server-sm120/bin
LD_LIBRARY_PATH=$BIN:/usr/local/cuda-12.9/lib64 $BIN/llama-server --list-devices   # 要看到 RTX 5090
```

## 4. 建 `llama-server.service`（`/etc/systemd/system/`，需 sudo）

```ini
[Unit]
Description=llama-server (8-slot) — <SVC> 併發後端
After=network-online.target
Wants=network-online.target
StartLimitBurst=5
StartLimitIntervalSec=600

[Service]
Type=simple
User=<USER>
Group=<USER>
Environment=LD_LIBRARY_PATH=<PROJ>/llama-server-sm120/bin:/usr/local/cuda-12.9/lib64
ExecStart=<PROJ>/llama-server-sm120/bin/llama-server \
  --model <MODEL_GGUF> \
  --alias tw-110-model-v2 \
  --host 127.0.0.1 --port 8081 \
  --n-gpu-layers 99 --ctx-size 65536 --parallel 8 \
  --cont-batching --flash-attn on --batch-size 2048 --ubatch-size 512 --slots
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=llama-server

[Install]
WantedBy=multi-user.target
```
> VRAM 緊時降 slot/ctx：`--parallel 4 --ctx-size 32768`（每 slot 一樣 8192）。

## 5. 給現有服務加 drop-in（`/etc/systemd/system/<SVC>.service.d/llama-backend.conf`，需 sudo）

health gate 用 **/dev/tcp**（很多機器沒裝 curl）：先建 wait 腳本（家目錄，免 sudo）：
```bash
cat > <PROJ>/wait_llama.sh <<'EOF'
#!/bin/bash
for i in $(seq 1 60); do (echo > /dev/tcp/127.0.0.1/8081) 2>/dev/null && exit 0; sleep 2; done
echo "llama-server 8081 not ready" >&2; exit 1
EOF
chmod +x <PROJ>/wait_llama.sh
```
drop-in：
```ini
[Unit]
After=llama-server.service
Requires=llama-server.service

[Service]
Environment=LLM_BACKEND=llama-server
Environment=LLAMA_SERVER_URL=http://127.0.0.1:8081
Environment=LLAMA_SERVER_MODEL=tw-110-model-v2
Environment=LLAMA_SERVER_TIMEOUT=180
ExecStartPre=<PROJ>/wait_llama.sh
```

## 6. 套用（⚠️ OOM-safe 順序，需 sudo）

**必須先停舊服務**（釋放它 in-process 的 ~20GB），否則跟 llama-server 兩份模型同載會 OOM：
```bash
sudo cp llama-server.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/<SVC>.service.d
sudo cp llama-backend.conf /etc/systemd/system/<SVC>.service.d/
sudo systemctl daemon-reload
sudo systemctl stop <SVC>            # ① 先停舊(釋放 in-process 20GB)
sudo systemctl enable --now llama-server.service   # ② 起 llama-server(載模型 ~20s)
sudo systemctl start <SVC>           # ③ 起服務(這次走 llama-server 後端)
```

## 7. 驗證

```bash
systemctl is-active llama-server.service <SVC>
python3 -c 'import urllib.request,json;print(len(json.load(urllib.request.urlopen("http://127.0.0.1:8081/slots",timeout=5))),"slots")'   # 應=8
journalctl -u <SVC> -n 20 | grep "llama-server LLM extractor"    # 應看到「就緒」
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader   # 一份模型 ~22-28GB
# e2e smoke（無 curl 用 python）：
python3 - <<'PY'
import urllib.request,json
B="http://127.0.0.1:<PORT>"
def h(m,p,b=None):
    d=json.dumps(b).encode() if b is not None else None
    r=urllib.request.Request(B+p,data=d,headers={"Content-Type":"application/json"},method=m)
    with urllib.request.urlopen(r,timeout=30) as x: return json.loads(x.read()) if x.length!=0 else {}
sid=h("POST","/session/new")["session_id"]
print("input:",h("POST",f"/session/{sid}/input",{"text":"板橋文化路車禍有人受傷"})["outputs"])
h("DELETE",f"/session/{sid}"); print("health:",h("GET","/health"))
PY
```

## 8. 回退（回 in-process 序列化）

```bash
sudo rm /etc/systemd/system/<SVC>.service.d/llama-backend.conf
sudo systemctl disable --now llama-server.service
sudo systemctl daemon-reload
sudo systemctl restart <SVC>
```

## 9. 踩雷清單（照做省事）

1. **binary rpath**：複製來的 binary 找不到自己的 `.so`（`libllama-server-impl.so cannot open`）→ `LD_LIBRARY_PATH` 要含 **bin 目錄本身**（不是只有 cuda lib）。
2. **OOM 順序**：換後端時**先 stop 舊服務**再起 llama-server（兩份模型同載 = 40GB > 32GB）。
3. **無 curl**：很多機器沒裝 curl → health gate 用 `/dev/tcp` 或 python，別用 curl。
4. **slot/ctx 關係**：`--parallel`=slot 數、`--ctx-size`=總量、每 slot=ctx÷parallel。改要動 **`/etc/` 那份**（不是家目錄範本）→ `daemon-reload` → restart。
5. **冷啟動慢**：GPU 沒穩定流量會掉深閒置，第一發等時脈爬升（2–8s），暖機後 0.3–0.4s。要根治：`sudo nvidia-smi -pm 1`（persistence）或每 30s keep-warm ping。**非參數/cache 問題**（cache 設定各機一樣）。
6. **GPU 一次一份模型**：同機不能同時載 in-process + llama-server。
7. **雙後端分流的正確架構**：電話（SIP/STT/TTS）永遠進主機（95），**只把新機的 `:<PORT>` 加進 client 的 SOP 後端池（LB）**；**不要把電話本身路由到新機**（那樣通話連主機都沒進、0 請求）。
8. **每次模型升級沿用**：`LLM_BACKEND` 分支 + DELETE/reaper 是我們的客製，vendor 升級 cp 覆蓋時要保留（見 [model-upgrade-runbook.md](model-upgrade-runbook.md) §4.1 diff 對照）。

## 10. 實測數據（信心佐證，TW-110-Model_V2.0 + 5090）

- 單筆 LLM 生成 **<1s**（最長 941ms、輸出短），非「18-21s 長生成」（那是舊 Qwen 時代）。
- 8 slot / 65536 ctx idle ~22–28GB（視有無其他 GPU 佔用），壓測峰值僅 +0.3GB、不 OOM。
- HTTP 併發 2/4 通：**全部完成、無餓死**；39 通爆量壓測 ~30s 排空、無崩潰。
- 「餓死」若在 voice 層重現，多半是**話務端 VAD/測試工具**問題（音檔播完不送連續媒體流 → VAD 不 finalize → /input 沒出門），非 LLM 後端。

---

## 對照:本場景已完成的機器

| 機器 | 服務名 | 後端 | 狀態 |
|---|---|---|---|
| 204（aitop4，主 110）| `nlp-api.service` :8100 | llama-server 8-slot | ✅ |
| 131（cyberon1，第二 110）| `sop110.service` :8100 | llama-server 8-slot | ✅ |
| 132（cyberon2，119）| `sop119.service` :8200 | **目前仍 in-process 單線** | ← 可用本 runbook 改 |

（119 在 132 用 sop_api_server:app + 共用 Qwen gguf；若要改並發，先確認其 `sop_api_server.py` 有無 `LLM_BACKEND` 分支，缺就照第 2 節加。）
