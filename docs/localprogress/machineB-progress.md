# 機器 B 進度筆記（內部用）

最後更新：2026-05-29（含 NLP API 升級 0526 V3.0 + Qwen3.6-35B GGUF；Cyberon STT/TTS 暫停、自架 Whisper / F5-TTS adapter）

## docs/ 目錄結構

```
docs/
├── localprogress/      內部進度（machineB-setup, machineB-progress, integration-plan）
├── shared_with_A/      ← 5/30 新增！Syncthing 雙向同步資料夾（folder id shared-with-b）
├── talk_fromA/         機器 A 傳來的文件（歷史紀錄，新檔不再放這）
└── talk_toA/           我們回給機器 A 的文件（歷史紀錄，新檔不再放這）
```

**5/30 起的新工作模式**：給機器 A 的新文件**直接寫 `shared_with_A/`**，秒級同步、不必手動傳檔。`talk_to/from` 保留作歷史。

## 機器定位

- 同一台機器同時擔任兩個角色：**NLP server** + **STT/TTS server**（Cyberon 暫停期間由我們自架的 Whisper/F5 adapter 暫代）
- IP: `192.168.5.204`
- Hostname: `aitop4-GIGABYTE-ARL997`
- 對接機器 A（Asterisk，192.168.5.x）：NLP 走 HTTP（:8100）、STT 走 WebSocket（:8891）、TTS 走 gRPC TLS（:8089）

## 系統架構

### 跨機器訊息流

```
┌─────────────────────────────────┐         ┌─────────────────────────────────────┐
│   機器 A（Asterisk 192.168.5.x） │         │   機器 B（192.168.5.204）            │
│                                 │         │                                     │
│  ┌───────────────────┐          │ audio   │  ┌────────────────────────────┐    │
│  │ amidaemon_cyberon │ ─────────┼─PCM────►│  │ Cyberon STT :8890 (ws)     │    │
│  │ + 自加 VAD        │ ◄────────┼─text────│  │ → 拋 FINAL 文字回 amidaemon │    │
│  └─────────┬─────────┘          │         │  └────────────────────────────┘    │
│            │ POST                │         │                                     │
│  ┌─────────▼─────────┐          │ text    │  ┌────────────────────────────┐    │
│  │ api_server         │ ─────────┼────────►│  │ 110LLM SOP API :8100 (我們) │    │
│  │ + MySQL            │ ◄────────┼─text────│  │ (sop_api_server.py)         │    │
│  └─────────┬─────────┘          │         │  └────────────────────────────┘    │
│            │ gRPC                │ text    │  ┌────────────────────────────┐    │
│            │ (grpclib)           │────────►│  │ Cyberon TTS :8088 (gRPC)   │    │
│            │                     │ ◄WAV────│  │ stream WAV chunks          │    │
│            ▼                     │         │  └────────────────────────────┘    │
│  ┌───────────────────┐          │         │                                     │
│  │ Asterisk          │          │         │                                     │
│  │ Playback() WAV   │          │         │                                     │
│  └───────────────────┘          │         │                                     │
└─────────────────────────────────┘         └─────────────────────────────────────┘
```

### 機器 B 上跑的服務清單

| 服務 | Port | 啟動方式 | Owner |
|---|---|---|---|
| **110LLM SOP API（NLP）** | 8100 | systemd `nlp-api.service` | **我們** |
| **STT-Whisper adapter**（5/28 加）| 8891 | systemd `stt-whisper.service` | **我們**（Cyberon STT 替代） |
| **TTS-F5 adapter**（5/29 加）| 8089 | systemd `tts-f5.service` | **我們**（Cyberon TTS 替代） |
| Cyberon STT proxy | 8890 | docker `cyberonsttproxyfile` | Cyberon vendor（**暫停**） |
| Cyberon STT engine | 9999 (內部) | docker `cyberonstt` | Cyberon vendor（**暫停**） |
| Cyberon TTS gateway | 8088 | docker `cyberontts` (process_proxy) | Cyberon vendor（**暫停**） |
| Cyberon Web admin | 8080 | docker `cyberonweb` | Cyberon vendor |
| Cyberon Adapt | 8084 | docker `cyberonadapt` | Cyberon vendor |
| Cyberon Celf / pproxy | 8086 | docker `cyberoncelf` | Cyberon vendor |
| Cyberon filesync | 8092 | docker `cyberon_filesyncd` | Cyberon vendor |
| Cyberon DB | 內部 | docker `cyberondb` | Cyberon vendor |
| MySQL | 3306 | systemd（host）| 共用 |

### 架構決策摘要

| 議題 | 決定 | 原因 |
|---|---|---|
| **TTS 呼叫者** | 機器 A 的 api_server 自己 call（A 方案）| 與 integration-plan 一致、職責分離 |
| **TTS 音訊格式** | wav (16kHz/16-bit/mono) | 直接給 Asterisk Playback，省 header 處理 |
| **STT 延遲解法** | 機器 A client-side VAD + 主動送 stop | 不動 STT vendor image / 同時解拆段問題 |
| **NLP BERT 裝置** | CPU（主分類器 + validity BERT） | 5090 留給 LLM + STT + TTS |
| **NLP LLM extractor** | **Qwen3.6-35B-A3B GGUF**（5/29 升級，原 Qwen3-4B HF 已換掉） | 升 35B 抽取力大幅提升、API 合約零變動 |
| **CUDA toolchain** | **`/usr/local/cuda-12.9`** | 5090 sm_120 要 12.9 nvcc 重編 llama-cpp-python，系統 12.0 nvcc 不行 |
| **partial case 取得** | 在 sop_api_server exception handler 抓 engine.case | 報案人掛斷／SOP fallback 也能保留分類結果 |

## 已完成

### NLP API（110LLM SOP API） — **2026-05-29 升級到 0526 V3.0 + Qwen3.6-35B GGUF**

**現役路徑（生產用）**：
- 工作目錄：`/home/aitop4/project/110llm/110LLM_0526_TW-110-Model_V3.0/`
- 入口檔：同目錄下 `sop_api_server.py`（我們客製，**不是** 110LLM 開發者寫的）
- venv：同目錄下 `venv/`（Python **3.12.3**，自帶 fastapi/uvicorn/llama-cpp-python CUDA 版）
- systemd: `/etc/systemd/system/nlp-api.service`（active + enabled，bind 0.0.0.0:8100）
  - 內含 `Environment=LD_LIBRARY_PATH=/usr/local/cuda-12.9/lib64`（llama-cpp-python 需要 CUDA 12.9）

**模型**：

| 用途 | 路徑 | 裝置 | VRAM |
|---|---|---|---|
| 主分類器 TW-110-Bert | `/home/aitop4/project/110llm/model/TW-110-Bert-v4/TW-110-Bert-v4/checkpoint-83352` | CPU | — |
| 首輪有效性 BERT（0526 V3.0 新加） | `/home/aitop4/project/110llm/model/tw110-validity-bert/660k_valid_vs_220k_invalid` | CPU | — |
| LLM extractor: Qwen3.6-35B-A3B GGUF Q4_K_S | `/home/aitop4/project/110llm/110LLM_Qwen3.6-35B/models/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_S.gguf` | 5090 全層 | ~21 GB（peak ~29.5 GB） |

**保留的 API（機器 A 端 zero change）**：`/session/new` / `/input` / `/observe` / `/hangup` / `/result` / `/health`、`/output`。

**核心 env vars**（全有預設值，要 override 在 systemd unit 加 `Environment=...`）：
- `LLM_STEP_MODE=extract`（關鍵，per-step LLM 抽槽位）
- `LLM_POST_MODE=upgrade`（hangup 後對 transcript re-extract 升級欄位）
- `GGUF_N_GPU_LAYERS=-1`（全 GPU；VRAM 緊時改成 ~30 做 partial offload）
- `GGUF_FLASH_ATTN=on`
- 降回純 BERT 模式：`GGUF_MODEL_PATH=/nonexistent`

**舊路徑（已沒服務在用，但檔案仍存在）**：
- `ai/110LLM_0426/`、`ai/TW-110-Model/`（HF Qwen3-4B）、`aienv/`（Py3.10）
- 5/11 在那邊的 LLM extractor 整合工作已被新版包含

**對機器 A 的 spec 文件**：`docs/talk_toA/nlp-api-for-machineA.md`（API 合約沒變動，**不必更新**）
**細節記憶**：`memory/project_qwen3_llm_extractor.md`、`memory/project_cuda_nvcc_build.md`

### TTS 端點調查 + Python PoC
- Cyberon TTS 是 **gRPC，不是 HTTP/WS**（端點 `192.168.5.204:8088`，process `process_proxy`）
- 自簽 cert without SAN/CN → Python 必須用 **grpclib**（不能用 grpcio，hostname verify 過不去）
- PoC 通過：`ai/cyberon/TTS_gRPC/test_tts.py`，0.66 秒合成 5.3 秒 16kHz/16-bit/mono WAV
- 抽出的 server cert：`ai/cyberon/TTS_gRPC/cyberon-server.crt`
- proto 雙版本生成：`service_pb2.py`（共用）、`service_pb2_grpc.py`（grpcio，不會用）、`service_grpc.py`（grpclib，PoC 用這個）
- 對機器 A 的 spec 文件：`docs/talk_toA/tts-investigation-for-machineA.md`（含 grpclib Python 範例 + Go 範例 reference）
- 細節記憶：見 `~/.claude/projects/.../memory/project_cyberon_tts.md`

### TTS 整合架構決定（5/10）
- **走 A 方案** — 機器 A 的 api_server 自己呼叫 Cyberon TTS（不經 sop_api_server）
- 跟 `docs/localprogress/integration-plan.md` Step 7-10 一致
- 機器 B 這邊**不需要改 sop_api_server.py**、不引入 grpclib 依賴
- 推薦給機器 A 用 `outfmt="wav"`（含 RIFF header，直接給 Asterisk Playback；如要省檔案再切 pcm8 + 6 行 helper）
- 回覆機器 A 的文件：`docs/talk_toA/tts-plan-confirm-for-machineA.md`

### TTS-F5 adapter（Cyberon TTS 替代，5/29）
- Cyberon TTS 暫時停用 → 自架 F5-TTS-based **Cyberon-compat gRPC server**
- Service: `tts-f5.service`（systemd, active+enabled）
- Endpoint: `192.168.5.204:8089` (gRPC + TLS 自簽 cert)
- Proto: `streamservice.StreamService.TTS`（同 Cyberon proto）
- Voice: **單一 voice clone**，reference = `ai/TTS-F5/reference/malevoice.wav`（user 提供的男聲 17s）
- 模型: F5-TTS_v1_Base（Apache 2.0），VRAM ~3.3 GB
- 程式: `ai/TTS-F5/tts_f5_server.py`（grpcio sync server, ~180 行）
- 自簽 cert: `ai/TTS-F5/cert.pem` + `key.pem`（CN=tts-f5）
- 機器 A client 完全不必動（grpclib skip-verify SSL 跟現有同 pattern）
- 對機器 A 文件: `docs/talk_toA/tts-f5-switch-for-machineA.md`
- 細節記憶: `memory/project_tts_f5_adapter.md`

### STT-Whisper adapter（Cyberon STT 替代，5/28）
- Cyberon STT 暫時停用 → 自架 Faster-Whisper-based **Cyberon-compat WebSocket server**
- Service: `stt-whisper.service`（systemd, active+enabled）
- Endpoint: `ws://192.168.5.204:8891/SttProxy/recognition`（避 Cyberon 8890）
- 模型: Faster-Whisper large-v3（`Systran/faster-whisper-large-v3`, CTranslate2 / float16）
- 模型路徑: `ai/STT-Whisper/`，VRAM ~3.65 GB
- 程式: `ai/STT-Whisper/stt_whisper_server.py`（FastAPI WebSocket, ~200 行）
- **不實作 server-side EPD**（client 用 VAD + active stop，per 5/10 reply）；**不實作 partial 結果**（only final on stop）
- 機器 A client 完全不必動，只切 endpoint URL :8890 → :8891
- 對機器 A 文件: `docs/talk_toA/stt-whisper-switch-for-machineA.md`
- 細節記憶: `memory/project_stt_whisper_adapter.md`

### `/schema/case-fields/by-type` endpoint 完整 revert（6/3 晚）
- 6/3 早實作的 by-type 分組 endpoint，**A 端 6/3 晚通知撤回整合**（MC 表示前端會自己預設寫好欄位、不需要 dynamic schema）
- A 說「不必動」但 user 決定 clean revert 避免技術債
- 砍掉 `sop_api_server.py` 內 BY_TYPE import + `/by-type` handler
- 砍掉 `case_field_labels.py` 內 `SOP_SCHEMAS`(33 案類)、`EXCLUDED_BY_TYPE`、`_build_by_type()`、`BY_TYPE`（396→216 行）
- 保留 `/schema/case-fields/labels`（平面 159 條）— A 端仍在用
- 對機器 A 確認文件：`docs/shared_with_A/by-type-revert-ack-for-machineA.md`
- 若未來 MC 改主意要 dynamic schema，重做 ~30 分鐘（vendor SOP_SCHEMAS 仍在 streamlit_app.py:201-333）

### TransferToHuman error 字串 normalize（6/2 晚）
- 觀察：journal 看到 `engine 例外：Caller first utterance invalid after validity retry.` 是 SOP 設計內的業務性 fallback（validity BERT 重試仍 invalid → transfer 真人），不是 bug
- 問題：vendor 不同 transfer 觸發點 raise 的 TransferToHuman exception **message 有中有英不一致**（預設中文、validity retry 英文），讓機器 A 端的 `"轉接專人" in error` bridge 判定**會 miss 英文 case**
- 解法：`sop_api_server.py:_run_engine` 加 `except TransferToHuman as exc:` 分支，sess.error **統一設成 `"轉接專人為您服務"`**；原 exc message 只 print 到 journal diagnose 用
- 結果：所有 transfer 路徑 error 字串都含「轉接專人」keyword，機器 A 端判定 100% 命中
- 寫進統整文件給 A：`docs/shared_with_A/pending-issues-update-2026-06-02-for-machineA.md`（順便補 #1 Whisper、#2 /input 空白的 status）

### `/schema/case-fields/labels` schema metadata endpoint（6/2）
- 機器 A 提需求：MC 前端要 case dict 的 **中文 label**（不是英文 snake_case key），請 B 端提供 schema metadata
- 新增 `GET /schema/case-fields/labels` 回 159 條 key → 中文 label 對照表
- Source of truth：vendor `streamlit_app.py:337-515` `SLOT_LABELS`（145 條）+ 我們補的 `case_field_labels.py:BASE_LABELS`（14 條 base 欄位 act_sub_class / caller_phone 等）
- 新檔 `case_field_labels.py` 放在 prod path，不動 vendor（streamlit_app.py 不能直接 import 因頂層有 streamlit dep）
- 維護機制：vendor 改 SLOT_LABELS → 手動同步到 `case_field_labels.py`；新增 base 欄位直接在 BASE_LABELS 加
- 端點 ~22ms 回應、純 dict 序列化、無 GPU/state coupling
- A 端用法：啟動時 fetch + 本機 cache，`LABEL_MAP.get(k, k)` fallback 保留英文 key
- 對機器 A 文件：`docs/shared_with_A/case-field-labels-request-for-machineB.md`（A 端原檔尾段加「機器 B 回覆」+ 完整 spec + 維護機制說明）

### SSE push endpoint `/case/stream`（6/1）
- 機器 A 提需求：polling 拖慢 TTS 同步路徑（每次 STT FINAL → /input → 等 bg refresh 1-3s → TTS 也延後），改用事件驅動 push
- 新增 `GET /session/{id}/case/stream`（FastAPI `StreamingResponse`，SSE / text/event-stream）
- 內部設計：每 300ms 對 case dict 算 MD5 hash、變了才推 `case_updated`；hash compare 純 CPU、極輕量
- Events：`case_updated`（完整 case dict）+ `done`（含 final case + 自動關連線）
- env `SSE_POLL_INTERVAL_S=0.3`（可調，systemd unit 內加 `Environment=...`）
- 端對端測 18 events 全收到、欄位逐步累積、done 後 server 主動關連線
- 對機器 A 文件：`docs/shared_with_A/sse-push-request-for-machineB.md`（在 A 端原檔尾段加「機器 B 回覆」+ 完整 spec + Python httpx-sse consumer 範例 + 注意事項）
- 細節記憶：`memory/project_observe_endpoint.md` 末尾擴展（同一個 sess.engine 設計支援 /observe + /result partial + /case/stream 三個功能）

### `/result` 在對話中也回 partial case（5/30）
- 機器 A 提需求：前端要「Analysis Initial / Updated / Final」三階段即時更新案件卡片
- 之前 `/result` 在 `done=false` 時固定回 `{done: False}`，A 端拿不到 in-flight partial case
- 解法：**只動 `get_result()` endpoint**，移除 done=false 的 early return
  - done=true → `sess.result`（含 LLM post-extract 升級欄位）
  - done=false → `sess.engine.case`（SopEngine instance live snapshot；reuse 5/12 為 `/observe` 保留的 engine instance）
- 機器 A client 完全不必動，現有 poll `/result` 邏輯就會拿到 partial case
- 端到端驗證：推一句 → `act_sub_class` 出來；推第二句 → `a2_injury_status` 出來；hangup → done=true + 完整 case
- 對機器 A 文件：`docs/shared_with_A/result-during-call-for-machineB.md`（直接在 A 端的需求文件內加「機器 B 回覆」段，sync 過去）
- 細節記憶補在：`memory/project_observe_endpoint.md`（同 engine.case live snapshot 概念）

### `/observe` endpoint — bridge 後雙通道對話接收（5/12，**沿用到 0526 V3.0**）
- 機器 A 反映「轉接真人後，受理員講話無法送 NLP，case_summary 只有 caller」
- 解法：**新增 `POST /session/{id}/observe`**（**不動 SopEngine、不改 /input 行為**）
- body: `{"text": "...", "role": "caller" | "agent"}`
- 行為：
  - 必須 `done=true` 才能用（否則 409）
  - append `{role, text}` 進 `sess.result.transcript`
  - **caller 發言**才觸發 `sess.engine._llm_post_extract()` 抽取（reuse 既有，upgrade mode）
  - **agent 發言**只 append、不抽取（受理員問句通常無欄位資訊）
  - 同步 rewrite 本機 case JSON log（含 bridge 期間更新）
  - 回 `{updated_fields, transcript_size}`
- 實測通過：`location` 從「板橋」upgrade 為「板橋區中正路 50 號路口」、`a2_hit_and_run` 從 None 補成「肇事逃逸」、`a2_injury_status` 沒被誤覆寫
- Session class 新增 `engine` / `lock` / `result_log_path` 三個欄位
- 對機器 A 的 spec 文件：`docs/talk_toA/transfer-nlp-issue-reply-for-machineA.md`
- 細節記憶：`memory/project_observe_endpoint.md`

### Qwen3-4B LLM extractor 啟用（5/11，**已於 5/29 升級為 Qwen3.6-35B GGUF**）

> 上方「NLP API 升級」段落是當前實況。以下保留是因為紀錄當初 LLM 整合的設計決策歷程。


- `ai/TW-110-Model/`（Qwen3-4B base，~8GB bf16）整合進 `sop_api_server.py`
- VRAM ~7.5 GB on 5090，cold load 5-10s，inference 0.02-0.5s 級
- 4 處新增 + 1 處修改（imports / env vars / `_shared_llm_extractor` 載入區塊 / `_run_engine` 傳 SopEngine 4 個 mode 參數）
- env vars 全部有預設值、可不設：`HF_MODEL_DIR / HF_DEVICE / HF_DTYPE / HF_MAX_NEW_TOKENS / LLM_POST_MODE / LLM_STEP_MODE / LLM_STEP_MAX_REASK`
- **`LLM_STEP_MODE=extract` 是關鍵**（CLI default 是 off，我們改 extract），沒這個 LLM 不會在 in-flight 對話被呼叫
- 端到端驗證：之前掛 transfer_to_human 的「兩個人，一個流血、一個骨折」場景現在順利推進 + `location` 從 null 升級為「板橋」
- API 合約**零變動**，機器 A 不必動 client
- 若要關閉：env `HF_MODEL_DIR=/nonexistent` 或重命名 model dir
- 細節記憶：`memory/project_qwen3_llm_extractor.md`

### STT 延遲/拆段議題決定（5/10）
- **不動 STT server config / docker container / 模型** — user 限制
- 推薦機器 A 走「客戶端 VAD + 主動送 stop」路線（剛好同時解他們的「拆段」需求，一石二鳥）
- 預期延遲從 6-7 秒 → 1-2 秒
- 已找到 server 端真兇候選：`/var/cyberon/Tyiot/stt/iSirDNN/freeSTT-zh-TW/DNN.ini` 內**註解掉**的 `--rule1.min-trailing-silence=5000`（5000ms 跟實測 6-7 秒延遲相符）— 但**目前不動**
- 機器 B 端可選支援（待機器 A 來要）：stop latency 測試 client / VAD Python 範例 / STT log 對照（路徑 `/audio/data/stt`）
- 回覆機器 A 的文件：`docs/talk_toA/stt-issue-reply-for-machineA.md`

## 待辦 / 還沒做

- TransferToHuman exception 路徑沒嚴格實測 partial case 抓取（理論上跟 EndOfInput 同 fix 邏輯通用）
- 等機器 A 端切到 stt-whisper :8891 + tts-f5 :8089 + 跑一通電話驗證整條 pipeline
- 視 STT/TTS 機器 A 回報結果，看要不要 fine-tune（例如 STT 數字辨識誤、TTS 文字預處理「110」念法等）

## 已知坑 / 不可改

- **絕對不要動 110LLM vendor code**：`classifier_class.py` / `sop_110_assistant.py` / `flow_registry.py` / `case_info.py`（不論在 0426 還是 0526 V3.0 目錄）。我們的客製化全部集中在 `sop_api_server.py`（server-only 入口檔）
- **VRAM 吃緊**：三個 GPU service 同時 active 用掉 ~29.5 GB / 32.6 GB（free 剩 ~2.5 GB）。多加任何 GPU service 前要先評估 partial offload 或停其他 service
- **CUDA 12.9 nvcc 必要**：5090 sm_120 要 12.9 nvcc 重編 llama-cpp-python，系統預設 12.0 nvcc 不行。詳見 `memory/project_cuda_nvcc_build.md`
- sklearn InconsistentVersionWarning（舊 0426 路徑用 0426 venv）：留著不動
- **stt-whisper / tts-f5 是 Cyberon 暫代品**：Cyberon 恢復時，client 切回原 endpoint，這兩個 service 可以 `systemctl disable` 省 VRAM
- 機器 A 那邊 IP 是 192.168.5.x（不是 .204）

## 對接機器 A 的文件清單（`docs/talk_toA/`）

- `nlp-api-for-machineA.md` — NLP API 規格
- `tts-investigation-for-machineA.md` — TTS 端點 + Python grpclib 範例（A 方案下機器 A 會用）
- `tts-plan-confirm-for-machineA.md` — 確認 A 方案 + 回答機器 A 的 3 個技術問題
- `stt-issue-reply-for-machineA.md` — STT 延遲/拆段議題回覆（推 client-side VAD + stop 方案）
- `transfer-nlp-issue-reply-for-machineA.md` — bridge 後雙通道對話 → 新增 `/observe` endpoint 規格
- `stt-whisper-switch-for-machineA.md` — Cyberon STT 暫停期間，切到我們 :8891 Whisper adapter 的指引
- `tts-f5-switch-for-machineA.md` — Cyberon TTS 暫停期間，切到我們 :8089 F5-TTS adapter 的指引

## 機器 A 那邊發來的請求 / 文件（`docs/talk_fromA/`）

- `tts-investigation-for-machineB.md`（5/9 收到）→ 已回覆
- `tts-plan-for-machineB.md`（5/10 收到）→ 已回覆，雙方確認走 A 方案
- `stt-issue-for-machineB.md`（5/10 收到）→ 已回覆，雙方確認走 client-side VAD + stop
- `transfer-nlp-issue-for-machineB.md`（5/12 收到）→ 已回覆，新增 `/observe` endpoint，實測通過

## 機器 A 那邊規劃的依據

- `docs/localprogress/integration-plan.md` — 5/8 留下的整合計畫，已讀完
  - Step 1-3: STT 結果 → MySQL → 110LLM（機器 A 端負責）
  - Step 4-6: 110LLM 回覆（已實作完成）
  - Step 7-10: TTS 由 api_server call → 存 WAV → Asterisk 播（5/10 確認 A 方案）
