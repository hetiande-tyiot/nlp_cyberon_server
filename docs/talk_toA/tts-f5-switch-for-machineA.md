# TTS 切換指引：Cyberon → F5-TTS Adapter（給機器 A）

> 日期：2026-05-29
> 對應狀況：Cyberon 暫時停用，機器 B 端架了 F5-TTS-based 的 Cyberon-compat gRPC adapter

## 結論

**機器 A 的 grpclib client 程式完全不必動**（連 skip-verify SSL 都跟原本同 pattern），只切 endpoint host:port 即可。等 Cyberon 復用時把 endpoint 改回去。

| | 原 Cyberon | 切換 → 新 F5-TTS Adapter |
|---|---|---|
| 端點 | `192.168.5.204:8088` | `192.168.5.204:8089` |
| 協定 | gRPC over TLS（self-signed） | **同樣 gRPC + TLS + self-signed** |
| Proto package | `streamservice.StreamService.TTS` | **同 proto，pb 檔不必重生** |
| Token | `yGFJ1D5HcT...` | **接受同 token** |
| Request 欄位 | `serviceName, text, outfmt, language, speaker, token, vbr_quality, ...` | **全部接受**（speaker / vbr_quality / phrbrk 等忽略；單 voice 模式）|
| Response | `stream TtsResponse(data=bytes)` | **同樣 stream chunks** |
| 自簽 cert 處理 | `tls.Config{InsecureSkipVerify: true}` (Go) / `check_hostname=False, verify_mode=CERT_NONE` (Python grpclib) | **完全一樣** |

→ **改 host:port 一個 config 就好**。

---

## 支援的 `outfmt`

| outfmt | 規格 | 適合場景 |
|---|---|---|
| `wav`（**推薦預設**） | RIFF/WAVE PCM, **16 kHz, 16-bit, mono** | Asterisk Playback() 直接吃，無需轉檔 |
| `pcm` | 16 kHz, 16-bit, mono, **raw（無 header）** | 餵 16k 音訊管線 |
| `pcm8` | 8 kHz, 8-bit unsigned PCM, **raw** | 電話線 8k channel 直接餵 |
| `mp3` | **未實作**，會 fallback 成 wav 回傳 | (留位給未來) |

→ 你們之前已選 `wav`、機器 B 也是用 `wav`，這個保持不變。

---

## Backend 細節（FYI）

- **引擎**：F5-TTS_v1_Base（HuggingFace `SWivid/F5-TTS`），Apache 2.0 授權
- **聲音**：**單一 voice**（由機器 B 提供的男聲 reference clone 出來，內部 cache）
  - 我們的 `request.speaker` 收到後**忽略**，永遠回固定 voice
- **延遲**：每次合成約 **0.5-1 秒**（cold call 因 warmup 約 5 秒），純 5090 GPU
- **TLS cert**：我們自己生的 self-signed，issuer/subject `O=TTS-F5-Adapter, CN=tts-f5`
  - 對你們 skip-verify client 透明
- **音質**：voice cloning 質感、中文發音準確；**比 Cyberon Sharon 風格不同**，但清楚易懂、適合受理員場景

---

## 跟 Cyberon 行為差異（請知悉）

| 面向 | 差異 |
|---|---|
| **聲音風格** | 跟 Cyberon Sharon 不同（不同 voice、不同來源），但都是清楚男聲（或女聲，視 reference）|
| **vbr_quality** | 因 mp3 沒實作所以這個 field 也忽略 |
| **speaker** 切換 | 我們**忽略**這個 field（單 voice）；要切多 voice 之後可加，但目前一個 reference 一個 voice |
| **gender / language 切換** | language="zh-TW"/"zh-CN"/"zh" 行為一致（F5-TTS 看模型內部 tokenizer 處理） |

---

## 切換後快速 sanity 測試（在機器 A 端跑）

```python
# 你們現有的 grpclib client 程式碼，改 host:port 就好
# (per talk_toA/tts-investigation-for-machineA.md 範例)

HOST = "192.168.5.204"
PORT = 8089  # 改這裡

# request 內容完全不變
req = pb.TtsRequest(
    serviceName="e2e",
    text="新北市警局 110 您好",
    outfmt="wav",
    language="zh-TW",
    speaker="Sharon",  # 忽略
    token=TOKEN,
)
# 預期: 收到 stream chunks、組成 WAV 檔、Asterisk Playback() 能放
```

---

## 待 Cyberon 恢復後

把 endpoint port 改回 `8088`，**client 程式不必動**。tts-f5.service 可以照常跑（port 不同不衝突），要關省 VRAM：

```bash
sudo systemctl stop tts-f5
sudo systemctl disable tts-f5
```

---

## 對應的歷史文件

- `talk_toA/tts-investigation-for-machineA.md` — 5/9 Cyberon TTS 規格 + grpclib 範例（架構基礎）
- `talk_toA/tts-plan-confirm-for-machineA.md` — 5/10 確認 A 方案（api_server call TTS）
- `talk_toA/tts-f5-switch-for-machineA.md` — **本文件**（Cyberon 暫停期間的臨時 backend）

任何問題傳訊給機器 B 端負責人。
