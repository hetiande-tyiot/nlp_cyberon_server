# 110LLM 模型升級 runbook

> 用途：把舊版 110LLM 換成新版，並維持 `sop_api_server.py` 對機器 A 的 API 合約零變動。
> 首次撰寫：2026-05-29，根據 0426 → 0526 V3.0 + Qwen3.6-35B GGUF 實作過程整理。
> 適用：之後 110LLM 開發者那邊出新版（0613、0701…）只要結構接近，依此 runbook 走即可。

## 0. 升級的不變原則

| 原則 | 意義 |
|---|---|
| **絕對不動 110LLM 上游檔** | `sop_110_assistant.py` / `classifier_class.py` / `flow_registry.py` / `case_info.py` / `llm_extractors.py` / `handlers/*` / `flows/*` 全部視為 vendor code，動了 rebase 會炸 |
| **所有客製集中在 `sop_api_server.py`** | 是 server-only 入口檔（不在 110LLM 原始 release 裡），全部介面客製、log 寫檔、bridge endpoint 都寫這 |
| **API 合約零變動** | endpoint path / payload / response 結構維持 — 機器 A client 一行都不必改 |
| **env var 控旋鈕** | 所有可調設定（模型路徑、device、LLM mode）都走 env var，systemd unit 改 `Environment=` 不必動程式碼 |

## 1. 通用流程（每次升級都跑這 7 步）

```
[1] Pre-flight：盤點當前狀態、目標版本結構、模型/CUDA 兼容性
 ↓
[2] 環境準備：venv 補依賴、CUDA 工具鏈、llama-cpp-python（如 GGUF）
 ↓
[3] Sanity test：新 LLM 載入 + 一次 inference 確認 GPU 跑得起
 ↓
[4] Port sop_api_server.py：對著當前 production 版改差異
 ↓
[5] Smoke test：在 alt port 或停舊服務後跑新 server
 ↓
[6] 切 systemd unit：WorkingDirectory / ExecStart / Environment 對齊新版
 ↓
[7] 更新 memory + docs
```

每一步「先確認再進下一步」，不要把整份一次跑完。

## 2. 0426 → 0526 V3.0 + Qwen3.6-35B GGUF 實際命令紀錄

### Step 1 — Pre-flight

**盤點當前 production**：

```bash
# 當前服務檔
cat /etc/systemd/system/nlp-api.service
# → WorkingDirectory / ExecStart / venv 路徑

# 當前 sop_api_server.py 的所有客製
grep -n "import\|os.environ.get\|app.post\|app.get" /home/aitop4/.../nlp-api/sop_api_server.py
# 把所有 env var、endpoint、import 列出來 — 等下要 port 過去
```

**比對新舊目錄差異**：

```bash
diff -q /OLD/path/ /NEW/path/
# 看哪些檔變了、哪些檔新增。重點關注：
#  - classifier_class.py（介面有沒有變）
#  - llm_extractors.py（class 名稱、kwargs）
#  - sop_110_assistant.py（SopEngine.__init__ kwargs、有沒有新模型/handler）
#  - requirements.txt（新依賴）
```

**檢查新版 SopEngine 介面**：

```bash
grep -n "^class SopEngine\|def __init__" /NEW/path/sop_110_assistant.py
# 看新版 SopEngine 接哪些 kwargs；舊有的 kwargs 通常向後相容，新增的（如 validity_classifier）要決定要不要傳
```

**GPU / 模型兼容性**：

```bash
# 模型實際路徑與大小
ls -lh /path/to/new/model.gguf

# 5090 = sm_120 = compute_120a (Blackwell)；要 CUDA 12.8+
nvcc --version
nvidia-smi
```

### Step 2 — 環境準備

**先決定走「複用 venv」還是「重建 venv」**：

| 條件 | 走法 |
|---|---|
| 新版 requirements.txt 跟舊版 **沒差** | **複用舊版 venv**（推薦，省 CUDA 重編 10 分鐘） |
| 模型路徑/類別介面變了 | 仍可複用，只要 SopEngine.__init__ kwargs 向後相容 |
| GGUF backend / Python 版本 / 大幅升 transformers | 重建 venv |

#### 路線 A：**複用舊版 venv（推薦）**

`requirements.txt` 沒變就走這條 — 不必動 venv，systemd ExecStart 直接指舊版 binary：

```bash
# Production source of truth：用 nlp_cyberon_server/ai/<new_ver>/
# venv：沿用舊版 /home/aitop4/project/110llm/<old_ver>/venv/
# systemd 改 WorkingDirectory 到新版、ExecStart 不動

diff /OLD/requirements.txt /NEW/requirements.txt  # 必須無輸出
$OLD_VENV/bin/pip list | grep -iE "fastapi|pydantic|llama_cpp"  # 必要套件都還在
```

驗證 imports 可以從新版目錄解析（**舊版目錄不可刪**，是 venv host）：

```bash
cd /home/aitop4/nlp_cyberon_server/ai/<new_ver>/
GGUF_MODEL_PATH=/nonexistent LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64 \
  $OLD_VENV/bin/python -c "
import sys, os
sys.path.insert(0, os.getcwd())
from classifier_class import TW110BertClassifier
from flow_registry import load_flows_from_dir
from llm_extractors import GgufLlamaCppFieldExtractor, LLMFieldExtractor
from sop_110_assistant import CaseInfo, DialogueIO, EndOfInput, SopEngine, TransferToHuman, TW110ValidityBertClassifier
from case_field_labels import LABELS
print('OK')
"
```

#### 路線 B：重建 venv

新版可能用獨立 venv（0526 自帶 `venv/`），也可能要新增依賴到既有 venv。先決定 venv，然後對齊：

```bash
# 確認 venv 缺什麼
NEW_VENV=/home/aitop4/project/110llm/110LLM_0526_TW-110-Model_V3.0/venv
$NEW_VENV/bin/pip list | grep -iE "fastapi|pydantic|torch|transformers|llama_cpp|grpc"

# 補上 server 必要套件
$NEW_VENV/bin/pip install fastapi pydantic

# 如果走 GGUF + 是 5090（sm_120）：見 [[cuda-nvcc-build]] memory
sudo apt-get install -y cuda-nvcc-12-9   # 如果 nvcc 還沒 12.8+

CUDA_HOME=/usr/local/cuda-12.9 \
PATH=/usr/local/cuda-12.9/bin:$PATH \
LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64:$LD_LIBRARY_PATH \
CMAKE_ARGS='-DGGML_CUDA=on -DGGML_USE_NCCL=off -DCMAKE_CUDA_ARCHITECTURES=120 -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.9/bin/nvcc' \
  $NEW_VENV/bin/pip install llama-cpp-python==<version> --force-reinstall --no-cache-dir

# 編完驗證
find $NEW_VENV -name "libggml-cuda.so" 2>&1   # 應該找得到
```

### Step 3 — Sanity test

停舊 nlp-api 釋放 VRAM，跑 sanity：

```bash
sudo systemctl stop nlp-api
```

```python
# 直接用 venv python 跑（不要過 sop_api_server.py，先驗 LLM 純載入）
import time, subprocess
from llama_cpp import Llama
t0 = time.time()
llm = Llama(model_path="/path/to/model.gguf", n_gpu_layers=-1, n_ctx=4096,
            flash_attn=True, chat_format="qwen", verbose=False)
print(f"load: {time.time()-t0:.2f}s")
print(subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv"],
                     capture_output=True, text=True).stdout)
out = llm.create_chat_completion(messages=[
    {"role":"system","content":"你是 JSON 抽取器，輸出 {location,name,phone}。"},
    {"role":"user","content":"/no_think\n\n板橋區文化路車禍，我姓張0912345678"},
], max_tokens=128, temperature=0.0)
print(out['choices'][0]['message']['content'])
```

通過條件：
- 載入無 error
- VRAM 不會 OOM（35B Q4_K_S 約 25-29GB on 5090）
- inference 出合理輸出（即使有 `<think>` block 也 OK，extractor 內有 `_strip_think_and_fences` 會清）

### Step 4 — Port sop_api_server.py

把當前 production 版本 cp 到新目錄，然後對著新版 API 改差異：

| 區塊 | 0426 → 0526 實際改了什麼 |
|---|---|
| imports | `HFLocalLLMFieldExtractor` → `GgufLlamaCppFieldExtractor`、加 `TW110ValidityBertClassifier` |
| 路徑 env vars | `HF_MODEL_DIR` → `GGUF_MODEL_PATH`、新增 `VALIDITY_MODEL_DIR` / `VALIDITY_DEVICE` |
| LLM init | `HFLocalLLMFieldExtractor(model_dir=, device=, dtype=)` → `GgufLlamaCppFieldExtractor(model_path=, max_new_tokens=)` |
| Validity classifier 預載 | 新增整個 block（讀 `VALIDITY_MODEL_DIR`、`TW110ValidityBertClassifier(...)`、fail 時 fallback 跳過）|
| `SopEngine(...)` kwargs | 加 `validity_classifier=_shared_validity_classifier` |
| 既有 endpoints `/session/new` `/input` `/observe` `/hangup` `/result` `/output` `/health` | **完全保留**，不要動 |
| 既有客製端 endpoints / case log JSON dump / streaming endpoint 等 | **完全保留**，逐項 port 過去（用 grep 對照不要漏） |

**重要：** 寫完之後跟舊版做 `diff` 對照，確保新增功能（如某次升級時加的 `/observe`、`/stream`、`case_field_labels` 等）都被搬過去。

### Step 5 — Smoke test

舊服務還在跑：

```bash
# 在 alt port 跑新版
cd /NEW/path
LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64 \
  venv/bin/uvicorn sop_api_server:app --host 127.0.0.1 --port 8101 &
# 測 /health、/session/new、/input、/hangup、/result 全部走一遍
```

舊服務已停（VRAM 不夠雙開時）：

```bash
# 直接綁 8100 試跑
cd /NEW/path
LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64 \
  venv/bin/uvicorn sop_api_server:app --host 127.0.0.1 --port 8100 &
```

通過條件：
- /health 200
- /session/new 回 greet
- /input 第一次（冷啟）非空 outputs（Issue #2 修法已涵蓋；如果舊版仍有 `wait_secs` timeout 可能會空）
- /hangup → /result 拿到完整 CaseInfo

### Step 6 — 切 systemd unit

```ini
[Unit]
Description=110LLM SOP API Server (FastAPI/Uvicorn) — <版本標題>
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aitop4
Group=aitop4
WorkingDirectory=/NEW/path
Environment=PYTHONUNBUFFERED=1
Environment=LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64
ExecStart=/NEW/path/venv/bin/uvicorn sop_api_server:app --host 0.0.0.0 --port 8100
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nlp-api

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp /tmp/nlp-api.service /etc/systemd/system/nlp-api.service
sudo systemctl daemon-reload
sudo systemctl restart nlp-api
sudo systemctl status nlp-api --no-pager
```

驗證：

```bash
curl -fsS http://127.0.0.1:8100/health
# 跑一次 /session/new + /input 確認流程
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

### Step 7 — 更新 memory + docs

- 改 `project_qwen3_llm_extractor.md`（或對應 NLP 服務 memory）反映新版路徑/env vars/實測數字
- 改 `project_machineB_role.md` 的 sop_api_server 路徑
- 更新 `MEMORY.md` index 的 one-line hook
- 跟機器 A 寫 ack doc（`docs/talk_toA/`）說明：「API 合約不變、無需動 client」
- 如有 CUDA 工具鏈變更：更新 [[cuda-nvcc-build]]

## 3. 踩雷紀錄（下次不要重蹈）

### 雷 1：pypi `nvidia-cuda-nvcc-cu12` 不含 nvcc binary
裡面只有 `ptxas` + `libnvvm.so` + headers，**沒有 nvcc 本體**。要 nvcc 必須走 apt（`sudo apt-get install cuda-nvcc-12-9`，從 NVIDIA repo）。

### 雷 2：兩份目錄混淆
專案目錄常有 dev 跟整合版兩份 copy（例如 `/home/aitop4/project/110llm/` 跟 `/home/aitop4/nlp_cyberon_server/ai/`）。pip shebang 會 hardcode 原始 venv 路徑，導致從 copy 那邊跑 pip 其實裝去原 venv。**選定一個目錄做為 production source of truth**，systemd 都指那一個。建議走 `/home/aitop4/project/110llm/.../`（venv 跟程式碼同地）。

### 雷 3：VRAM 雙開 OOM
新 35B GGUF 載入要 ~25-29GB。舊服務佔 9GB + 新 35B = 超出 32.6GB，OOM crash。Sanity test 跟 smoke test 前**先停舊服務**或用 alt port + 限制 GPU layer 數量。

### 雷 4：5090 sm_120 不被舊 CUDA 認得
Ubuntu 24.04 預設 `nvidia-cuda-toolkit` 是 CUDA 12.0（最高 sm_90），編出來的 cubin 跑不上 5090（Blackwell）。要 CUDA 12.8+ 才支援 sm_120。

### 雷 5：libstdc++ 版本
如果 llama-cpp-python 編譯 import 時報 `GLIBCXX_*` not found：`conda install -c conda-forge libstdcxx-ng` 或 `sudo apt install --reinstall libstdc++6`。

### 雷 6：systemd Environment LD_LIBRARY_PATH 漏設
新 nvcc 裝到 `/usr/local/cuda-12.9/`，但 systemd unit 不繼承 shell PATH。**一定要在 unit 加 `Environment=LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64`**，否則 `libggml-cuda.so` 找不到 `libcudart.so.12`。

### 雷 7：Issue #2 風險
舊版 `_drain_output(wait_secs=...)` 會在冷啟第一次 /input 因 LLM 慢 timeout truncate 回空 outputs。**新 port 過去的 `sop_api_server.py` 一定要保留 event-based `_engine_ready` 等待**（見 2026-05-29 Issue #2 修法）。

## 4. 下次升級檢查清單

```
[ ] git log / changelog 看完，知道新版動了哪些 handler、flow、欄位
[ ] 跑 diff 對比新舊目錄
[ ] 確認 SopEngine.__init__ kwargs 都還在（向後相容）
[ ] 確認 LLM extractor class 名稱
[ ] 模型 GGUF 路徑、大小、quantization 量化版本記到 memory
[ ] CUDA toolchain 是否需要升（新模型架構可能需要更新 ggml）
[ ] Port sop_api_server.py，逐 endpoint diff 對照當前 production
[ ] 保留 _engine_ready event-based 等待邏輯
[ ] 保留所有客製 endpoint（/observe、/stream、/schema/case-fields/labels 等）
[ ] 保留所有 env var 出口（讓退路存在）
[ ] 保留 LOG_DIR JSON dump
[ ] Sanity test：模型載入 + 1 inference + VRAM
[ ] Smoke test：/health + /session/new + 3 句 /input + /hangup + /result
[ ] systemd unit 修 WorkingDirectory、ExecStart、Environment
[ ] systemctl restart + status + log
[ ] 給機器 A ack doc（強調 API 不變）
[ ] 更新所有 memory：NLP 服務 memory + Machine B 角色 + MEMORY.md index
```

## 相關 memory

- [[NLP API LLM extractor (Qwen3.6-35B GGUF)]]
- [[cuda-nvcc-build]]
- [[Machine B 角色與架構]]
