# Pending Issues 狀態更新（機器 B → 機器 A）

> 日期：2026-06-02
> 對應：`shared_with_A/sse-labels-integration-ack-from-A.md` 你們列的 pending #1 #2
> 加上：本日新發現的 TransferToHuman error 字串 normalize fix

---

## TL;DR — 三件事

| 議題 | 狀態 |
|---|---|
| **#1 Whisper STT stop→FINAL 延遲** | ✅ 6/1 已 patch 在 stt-whisper.service（多個 Faster-Whisper 加速參數），但 production 切 Cyberon 後不 blocking、patch 留檔備援 |
| **#2 110LLM 第一次 /input 空白** | ✅ **5/29 已 deliver 修法 + 部署**，當時 reply doc 在 syncthing 接通前手動傳的 talk_to/from、A 端可能漏收。修法詳情見下 |
| **#6（本日新增）TransferToHuman error 字串不一致** | ✅ 6/2 已修 + 重啟 nlp-api（PID 1301399, 21:12 起），所有 transfer 觸發路徑現在 error 統一含「轉接專人」keyword |

---

## #2：110LLM 第一次 `/input` 偶爾回空白 outputs（5/29 修法回顧）

### 根因

舊版 `_drain_output(wait_secs=5.0)` 用**固定 5 秒 timeout** 等 engine `say()`。冷啟第一次 /input 實際處理鏈：

1. 主 BERT 分類（CPU，~50ms）
2. 首輪有效性 BERT（CPU，~50ms，0526 V3.0 新加）
3. `_smart_enrich_from_text` LLM extract（Qwen3.6-35B，~0.5-1s/call）
4. flow 路由 + handler 第一個 ask 的 LLM 守門（再 1-2 次 LLM call）
5. 首次 GGUF CUDA kernel JIT + CPython lazy import handler module

**冷啟可達 5-8 秒**，舊版 5s timeout 截到就回空 outputs。

### 修法（5/29 部署）

- Session 加 `_engine_ready: threading.Event`
- `QueuedIO.hear_text` block 等下一句前 `set()`、收到 input 後 `clear()` — 標示「engine 這輪完成」
- 新增 `_wait_for_turn_complete(timeout=60)`：等 `_engine_ready` 或 `done`，再 drain output_q
- `/input` 在 `input_q.put()` 前先 `clear()` engine_ready 防 stale-ready race
- `_run_engine` finally 也 set engine_ready，hangup/exception 路徑能立即解阻塞

→ /input 一律等到 engine 真正處理完這輪、回到下一個 hear_text 才 return；除非 engine 卡死超過 60s 安全網，**outputs 永遠非空**。

### 實測（5/29 同款場景）

```
/input "你好,我要報案"           → 6.03s, outputs=["為了協助您正確報案..."]
/input "在板橋區文化路有車禍..." → 3.99s, outputs=["請問車輛有沒有起火或漏油？..."]
/input "2人受傷"                 → 1.63s, outputs=["請問另一方還在現場嗎？"]
```

冷啟第一輪 6s，後續暖機後降至 1.6s 級。**5/29 之後再沒觀察到空白 outputs**。

### 對機器 A 的影響

API 介面**完全不變**。client 不必動。如果你們之後還有再觀察到空白 outputs，請貼 session_id + 時間，我們可以從 nlp-api journal 反查 engine 行為。

---

## #6（本日新增）：TransferToHuman error 字串不一致 → A 端 bridge 判定可能 miss

### 觀察

2026-06-02 16:51 journal 看到：

```
nlp-api[1073062]: [SOP 02a04c34] ⚠️  engine 例外：Caller first utterance invalid after validity retry.
```

挖出 case JSON 跟 vendor code 確認，這是**設計內的業務性 fallback**：

```
[assistant] 新北市警局 110 您好
[caller   ] 你好，我有沒有發生車禍。     ← 模糊
[assistant] 為了協助您正確報案...
[caller   ] 喂，你好。                     ← 重試仍模糊
[assistant] 轉接專人為您服務
```

vendor sop_110_assistant.py `raise TransferToHuman("Caller first utterance invalid after retry.")` — **exception message 是英文**。

### 問題

我們 5/9 給你們的 `nlp-api-for-machineA.md` 內 bridge 判定 rule 之一是 `"轉接專人" in error`。但這個英文 message **不含「轉接專人」keyword**，會讓你們判斷成「真技術錯誤」alert 維運。

| 觸發 | 修前 error 字串 | 修前 `"轉接專人" in error`？|
|---|---|---|
| 正常 transfer（vendor 預設）| `"抱歉，為了確保資訊正確，轉接專人為您服務。"` | ✅ 是 |
| validity retry 仍 invalid | **`"Caller first utterance invalid after validity retry."`** | ❌ **miss** |
| 其他英文 TransferToHuman | 各種英文 message | ❌ 可能 miss |

### 修法（6/2 部署）

`sop_api_server.py:_run_engine` 加 `except TransferToHuman` 分支，**統一把 sess.error 設成 `"轉接專人為您服務"`**，原 exc message 只 print 到 journal 做 diagnostic：

```python
except TransferToHuman as exc:
    sess.error = "轉接專人為您服務"        # ← normalize 中文 keyword
    sess.result = getattr(engine, "case", None)
    print(f"[SOP {sess.sess_id[:8]}] 轉接專人（原因：{exc}）", flush=True)
```

### 修後 error 字串

| 觸發 | error 字串（修後） |
|---|---|
| 正常 transfer | `"轉接專人為您服務"` ✓ |
| validity retry 仍 invalid | `"轉接專人為您服務"` ✓ |
| 其他 TransferToHuman 路徑 | `"轉接專人為您服務"` ✓ |
| caller_hangup | `"caller_hangup"`（不變） |
| 真正技術錯誤 | exc message（不變、行為跟舊版一樣） |

→ 你們 `"轉接專人" in error` 判 bridge **100% 命中**。

### 端到端驗證（6/2）

```
[E1] 推 "你好，我有沒有發生車禍。"
  → outputs=['為了協助您正確報案...'], done=False, error=None

[E2] 推 "喂，你好。"  (validity retry 仍 invalid)
  → outputs=['轉接專人為您服務'], done=True, error='轉接專人為您服務'  ← ✓

GET /result:
  done: True, error: '轉接專人為您服務', "轉接專人" in error: True ✓

journal:
  [SOP xxxxx] 轉接專人（原因：Caller first utterance invalid after validity retry.）
```

---

## #1：Whisper STT stop → FINAL 延遲（6/1 patch 紀錄）

### 狀態：**已 patch、但 production 切 Cyberon 後不 blocking**

你們提到「測試時目前切回 Cyberon STT」，所以這個 patch 對 production 沒影響、留檔備援。

### 已套用的 Faster-Whisper 加速參數（`stt_whisper_server.py`，6/1 動）

| 參數 | 舊值 | 新值 | 效果 |
|---|---|---|---|
| `beam_size` | 5 | **1**（greedy）| 推論 3-5x 加速、短句準確度差異小 |
| `vad_filter` | false | **true** | 跳掉錄音內靜音 chunk、明顯降低 stop→FINAL 延遲 |
| `without_timestamps` | false | **true** | 不解 segment timestamp、省解碼 token |
| `condition_on_previous_text` | true | **false** | 避免上輪 hallucination 級聯到下一句 |

env vars 都可 override（`WHISPER_BEAM` / `WHISPER_VAD_FILTER`），預設值是上述優化值。

### 你們提的 3 個小問題短答

| 問題 | 答 |
|---|---|
| #1-1 是否可改串流推論？| Whisper 架構限制無法純串流。可用 chunked + overlap 模擬但複雜度高，**目前不做**（production 用 Cyberon 不需要） |
| #1-2 其他降延遲方式？| 已套上方 4 個參數；不夠快可換 large-v3 → medium / small 模型，但準確度會降 |
| #1-3 Cyberon 復用建議？| 你們已切回 :8890、production 跑得穩定，**不建議再切回 :8891**（Whisper adapter）。Cyberon 沒理由停我們也不會主動切 |

### 你們的選擇

如果未來 Cyberon 又出狀況、要切回我們 Whisper adapter，這些 patch 已生效；不必再要求調整。

---

## 機器 B 端待辦清單（給你們追蹤）

✅ #1（Whisper 延遲）— patch 已上、production 不 blocking
✅ #2（/input 空白）— 5/29 已修部署
✅ #3（/result partial case）— 6/1 修
✅ #4（SSE 推送）— 6/1 修
✅ #5（中文 label 對照表）— 6/2 修
✅ #6（TransferToHuman error normalize）— 6/2 修

**所有 pending 都已 closed。**

---

任何欄位語意不清、實際行為跟預期不符、或新發現問題，請直接寫進 `shared_with_A/`。
