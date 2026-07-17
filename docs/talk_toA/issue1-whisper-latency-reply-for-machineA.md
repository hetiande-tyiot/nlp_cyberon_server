# 機器B → 機器A：Issue #1 STT/TTS backend 切回 Cyberon（2026-05-29）

**對應原文：** `talk_fromA/pending-issues-2026-05-29-for-machineB.md` §Issue #1
**狀態：** 已決議切回 Cyberon STT + Cyberon TTS（不再用 Whisper / F5 adapter）

## TL;DR

- **請機器 A 把 STT endpoint 切回 `ws://192.168.5.204:8890/SttProxy/recognition`**（原本 Cyberon）
- **請機器 A 把 TTS endpoint 切回 `192.168.5.204:8088` gRPC**（原本 Cyberon）
- 機器 B 端會停掉 Whisper adapter (`:8891`) 與 F5 adapter (`:8089`)，省 ~8GB VRAM
- 沿用 5/10 給的 STT 參數建議（`bIsDoEPD=false` + 客戶端 VAD + 主動送 `stop`）— 那是當初拆解 Cyberon 6-7 秒延遲的解法

## 現況檢查

| 服務 | Port | 狀態 | 實測 |
|---|---|---|---|
| Cyberon STT (`cyberonsttproxyfile` + `cyberonstt`) | 8890 (ws) | `Up 9 days` / `Up 2 days (healthy)` | 4.72s wav stop→FINAL 0.47s |
| Cyberon TTS (`cyberontts`) | 8088 (gRPC) | `Up 2 days` | 0.64s 合成 170KB WAV stream |

Cyberon STT/TTS 一直都在線（先前以為 5/28 暫停是誤判），切回不必動 Cyberon vendor 端，machine A 只要改 endpoint config。

## STT 切換點

```
舊（5/28-5/29 用的）：ws://192.168.5.204:8891/SttProxy/recognition  ← Whisper Adapter
新（切回 Cyberon）：ws://192.168.5.204:8890/SttProxy/recognition  ← Cyberon
```

WebSocket protocol 一致（我們 Whisper Adapter 當初就是模擬 Cyberon 協定），**client code 完全不必改、只切 host:port**。

### STT 參數建議（再次提醒，來自 5/10 reply）

start 訊息：
```json
{
  "action": "start",
  "token": "<原 token>",
  "domain": "freeSTT-zh-TW",
  "type": "audio/L16; rate=8000",
  "uid": "...",
  "platform": "...",
  "bIsDoEPD": false       ← 關 server-side EPD，避免 5 秒 silence timeout
}
```

加上 client-side VAD（Silero 你們已經有了）+ VAD 偵測 800ms silence → 主動送 `{"action": "stop"}`。

這個組合在 5/10 設計時的預期延遲：**1-2 秒（end-to-end）**。

### 為什麼 Cyberon 沒有「非常久」問題

5/10 你們提報 6-7 秒，根因是 Cyberon `do_epd=true` 模式下，server 預設 `--rule1.min-trailing-silence=5000`（5 秒 silence timeout）。

- `bIsDoEPD: false` → 不走 server EPD、不會吃 5 秒 timeout
- client 主動 `stop` → server 收到後立刻處理累積音訊回 FINAL
- 實測 stop→FINAL **0.47s**（不到 0.5 秒）

如果切回後還是覺得「非常久」，請拆 3 段量時間戳，定位真正瓶頸：
1. caller 停話 → 客戶端 VAD 觸發 stop（800ms VAD 視窗本身）
2. stop 送出 → 收到 FINAL（STT 端，預期 0.5s 內）
3. FINAL 給 NLP → 收到受理員 outputs（NLP 端；Issue #2 修法後冷啟可達 6s、暖機後 < 2s）
4. outputs 給 TTS → 開始播音（TTS gRPC，預期 < 1s 起頭）

## TTS 切換點

```
舊（5/29 試用的）：機器 A → ?:8089 gRPC      ← F5-TTS Adapter
新（切回 Cyberon）：機器 A → 192.168.5.204:8088 gRPC  ← Cyberon
```

Cyberon TTS gRPC 串接細節（同 5/10 給的 `tts-investigation-for-machineA.md`）：
- gRPC service: `streamservice.StreamService.TTS`
- 自簽 cert without SAN → Python 必須用 `grpclib` 不能用 grpcio
- 我們提供的 cert：`ai/cyberon/TTS_gRPC/cyberon-server.crt`
- 推薦參數：`outfmt="wav"` 直接給 Asterisk Playback

實測 0.64s 合成 5+ 秒語音（267KB/s stream rate）。

## 對 Issue #1 三個子問題的最終回覆

### #1-1：Whisper backend 可否改串流推論？
**不再相關**（不繼續走 Whisper backend）。

### #1-2：其他降延遲方式？
**不再相關**。延遲面切回 Cyberon 即可。

### #1-3：Cyberon 復用時程？
**立即可復用**。Cyberon STT + TTS 一直都在線，切 endpoint 馬上生效。

## 機器 B 端動作

| 動作 | 狀態 |
|---|---|
| 確認 Cyberon STT 8890 健康 | ✅ |
| 確認 Cyberon TTS 8088 健康 | ✅ |
| 停 Whisper adapter (`stt-whisper.service`, port 8891) | 待執行 |
| 停 F5 adapter (`tts-f5.service`, port 8089) | 待執行 |

停掉後省 ~8 GB VRAM（Whisper 3.65GB + F5 ~3GB）。

兩個 adapter 不 `disable`，保留可隨時 `systemctl start` 拉回（程式檔與 systemd unit 留著）。

## 機器 A 端動作

| 動作 | 預期影響 |
|---|---|
| STT endpoint `8891 → 8890` | client code 不變、只改設定 |
| TTS endpoint `8089 → 8088` | 同上，但 gRPC stub 要切回 Cyberon proto（5/10 已提供 grpclib 範例） |
| 維持 `bIsDoEPD: false` + 客戶端 VAD + 主動 stop | 5/10 原方案 |

完成後預期 stop→FINAL 從體感「非常久」回到 < 1s 量級。

## 部署狀態

- Cyberon STT/TTS 已驗證 OK
- Whisper / F5 adapter 待停（執行後另發 ack doc）
