# STT 切換指引：Cyberon → Faster-Whisper Adapter（給機器 A）

> 日期：2026-05-28
> 對應狀況：Cyberon 暫時停用，機器 B 端架了 Faster-Whisper-based 的 Cyberon-compat WebSocket adapter

## 結論

**機器 A 只要改一個 endpoint URL**，client 端程式（含 amidaemon、VAD + 主動 stop 邏輯）**完全不必動**。等 Cyberon 復用時把 URL 切回去即可。

| | 原 Cyberon | 切換 → 新 Whisper Adapter |
|---|---|---|
| URL | `ws://192.168.5.204:8890/SttProxy/recognition` | `ws://192.168.5.204:8891/SttProxy/recognition` |
| WebSocket protocol | listening → start → binary → stop → result → listening | **完全一致** |
| Token | `yGFJ1D5HcT...mc_GEfQto...` | **接受同 token**（也可選 env var 關閉驗證） |
| Audio 格式 | PCM/μ-law/etc, 8k/16k | 同樣支援，server 端自動 resample 到 16k 餵 Whisper |
| 回傳 fields | `state, isFinish, recog_result, recog_nbest, recog_index, sen_end_ms, err_code, err_msg` | **同樣 fields**（少部分延伸如 SD/NLU 沒實作回空 list）|

→ **改 host:port 一個 config 就好**。

---

## Backend 細節（FYI，不用管也行）

- **引擎**：Faster-Whisper large-v3 + CTranslate2，跑 5090 GPU
- **語言**：強制 `zh`（語音辨識預設中文）
- **延遲**：50 秒音檔約 ~11 秒推論（RTF 0.22x），real-time 場景沒問題
- **endpointing**：**不實作 server-side EPD**（依照之前 5/10 我們的回覆 `stt-issue-reply-for-machineA.md`，由機器 A 端的 VAD + 主動送 `stop` 控制）
- **partial 結果**：**不實作**（client 設 `isGetPartial: true` server 會忽略，只回 final `isFinish=true`）

→ 這意味著機器 A 的 `bIsDoEPD: false` + active stop 邏輯**剛好對得起來**，毋需任何 client 修改。

---

## 跟 Cyberon 行為差異（請知悉）

| 面向 | 差異 |
|---|---|
| **辨識品質** | Whisper large-v3 對長句佳、對極短句（< 5s）可能有誤字。對 110 場景跑通沒問題、不影響流程 |
| **數字辨識** | 「119」常被聽成「19」「111」「1之1」之類；可能要在後處理階段（NLP 端）做 normalization |
| **連續錄音** | 兩端都支援連續多次 start/stop 用同一個連線 |
| **err_code** | 我們實作了 0 / -2（parse）/ -4（內部錯誤）/ -5（token 錯）；其他 code 沒實作 |

---

## 切換後快速 sanity 測試（在機器 A 端跑）

```bash
# 用既有 client 程式碼，只改 endpoint host:port，跑一通電話試試
# 預期：FINAL 出來、文字大致正確（可能個別字誤）
```

→ 第一通電話如果 FINAL 出來、文字大致對，協定就 OK。

---

## 待 Cyberon 恢復後

把 endpoint config 從 `:8891` 改回 `:8890`，**client 程式不必動**。我們這邊的 stt-whisper.service 可以照常跑（不影響 Cyberon、port 不同）；如果要關省 VRAM：

```bash
sudo systemctl stop stt-whisper
sudo systemctl disable stt-whisper  # 不再開機自動啟
```

---

## 對應的歷史文件

- `talk_fromA/stt-issue-for-machineB.md` — 5/10 你們提的 STT 延遲問題
- `talk_toA/stt-issue-reply-for-machineA.md` — 5/10 回覆推 client-side VAD + stop
- `talk_toA/stt-whisper-switch-for-machineA.md` — **本文件**（Cyberon 暫停期間的臨時 backend）

任何問題傳訊給機器 B 端負責人。
