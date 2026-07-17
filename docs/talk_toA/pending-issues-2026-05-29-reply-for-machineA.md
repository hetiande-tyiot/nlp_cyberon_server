# 機器B → 機器A：待釐清議題回覆（2026-05-29）

**回件：** 機器B（sop_api_server / 110LLM / Whisper STT Adapter）
**收件：** 機器A
**對應原文：** `talk_fromA/pending-issues-2026-05-29-for-machineB.md`

---

## Issue #2：110LLM 第一次 `/input` 偶爾回空白 outputs

### 結論：**已修，本日（2026-05-29）已部署**

`sop_api_server.py` 改用 event-based 等待，**不再用固定 timeout**。/input 一律等到 engine 真正處理完這輪、回到下一個 hear_text 才 return；除非 engine 卡死超過 60s 安全網，否則 outputs 永遠非空。

### #2-1：第一次 `/input` 回空白的根本原因？

**Race / timeout 訊號錯位**。舊版 `_drain_output(wait_secs=5.0)` 用固定 5s 等 engine 的 `say()` 事件，超時就 drain queue（此時可能是空的）。

冷啟第一次 /input 實際處理鏈：

1. 主 BERT 分類（CPU，~50ms）
2. 首輪有效性 BERT（CPU，~50ms — 0526 V3.0 新加，僅「一般為民服務」型別觸發）
3. `_smart_enrich_from_text`：LLM extract 一次（Qwen3.6-35B，~0.5-1s/呼叫）
4. flow 路由 + handler 第一個 ask 的 LLM 守門（再 1-2 次 LLM 呼叫）
5. 加上首次 GGUF CUDA kernel JIT、CPython lazy import handler module
6. **總計冷啟可達 5-8s**

舊版 5s timeout 一截到就回空。本日實測 fix 後同款場景：

```
/input "你好,我要報案"     → 6.03s, outputs=["為了協助您正確報案，麻煩您再簡短描述一次：哪裡發生什麼事？"]
/input "在板橋區文化路有車禍有人受傷" → 3.99s, outputs=["請問車輛有沒有起火或漏油？現場交通有沒有堵塞？"]
/input "2人受傷"           → 1.63s, outputs=["請問另一方還在現場嗎？"]
```

冷啟第一輪 6s，後續暖機後降至 1.6s。

### #2-2：是否能改為至少回通用回覆而非空陣列？

**已用更好的方式解決**：直接等到 engine 有真正的回覆才 return，不用兜底通用句。回的就是 engine 自己生成的（含 validity BERT 重新追問句、或第一個 flow handler 的 ask），語意完全對齊當前流程。

### #2-3：出現頻率與特定觸發條件？

**觸發條件**（修法已涵蓋全部情境）：

| 條件 | 為何拖長 |
|---|---|
| 模糊開場（「你好」「我要」「不好意思」） | validity BERT 判 invalid → engine 二次追問句 + LLM 抽取 |
| 案件型別需要 LLM step extract（A2/A3 受傷/車輛資訊） | step 級守門呼 LLM 多次 |
| 首次 GGUF 呼叫（程序剛 restart） | CUDA kernel JIT、權重未進顯卡快取 |
| 整段對話 token 長 | LLM prompt 變長、解碼時間線性上升 |

頻率：用舊版 5s 切過去都會發生；8s 也不夠（實測 6s 還在邊緣）。修法後**理論上 0 出現率**。

### #2-4：5/13 觀察到的「第二次回兩句」現象是否仍存在？

**修法後不會再出現**。

機制：舊版第一次 /input timeout truncate → outputs 空。但 engine 並沒停，繼續在背景跑完；handler 第一句 `ask()` 已 put 進 `output_q` 但 caller 沒收到。下次 /input 來時，drain `output_q` 把累積的句子全 return → 看起來「第二次回兩句」。

新版每輪 /input 都等到 engine 確實處理完才 return，`output_q` 不會有跨輪殘留。

### 改動細節

`sop_api_server.py`：

- Session 加 `_engine_ready` event
- `QueuedIO.hear_text` 在 block 等下一句前 `set()`、收到 input 後 `clear()` — 標示「engine 這輪完成」
- 新增 `_wait_for_turn_complete(timeout=60)`：等 `_engine_ready` 或 `done`，再 drain output_q
- `/input` 在 `input_q.put()` 前先 `clear()` engine_ready 防 stale-ready race
- `_run_engine` finally 也 set engine_ready，讓 hangup/exception 路徑能立即解阻塞

對外 API 介面**完全不變**，機器 A client 不必動。

### 部署狀態

- 已 `systemctl restart nlp-api`（5/29 18:25 左右）
- PID 從 1926907 → 1951760，VRAM 同 29.5GB / 32.6GB 穩定

---

## Issue #1：Whisper STT 的 stop → FINAL 延遲過長

### 狀態：**調整方案中，預定後續批次部署**

回應 #1-1 / #1-2 / #1-3 等 Whisper 端調整完成後另發 doc 補上（不會混到這份回覆，避免變更追蹤混淆）。

短答提示：
- **#1-1 串流推論**：Whisper 架構限制無法純串流，但可用 chunked + overlap 模擬；複雜度高、之後評估
- **#1-2 降延遲**：先調 `beam_size=5 → 1`、`vad_filter=True`、`without_timestamps=True`、`condition_on_previous_text=False`，預估 3-5x 加速；不夠快再考慮換 medium / small 模型
- **#1-3 Cyberon 復用**：目前無確定時程；不建議切回，繼續用 Whisper（穩定度、可控性更好），優化延遲

詳細回覆與部署日期另行發出。

---

## 部署 vs 影響摘要

| 議題 | 狀態 | 部署日 | 影響面 |
|---|---|---|---|
| #2 110LLM 空白 outputs | ✅ 已修部署 | 2026-05-29 | sop_api_server 內部；API 介面不變 |
| #1 Whisper STT 延遲 | 🟡 調整中 | 待定 | stt_whisper_server 內部；ws 介面不變 |

任何問題請逕洽 `docs/talk_toA/` 路徑下新增回覆文件。
