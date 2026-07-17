# 110 接警系統整合計畫

## 系統拓撲

```
┌─────────────────────────┐        ┌──────────────────────────────┐        ┌──────────┐
│   機器 A（Asterisk）     │        │   機器 B（NLP + STT/TTS）     │        │  機器 C  │
│                         │        │                              │        │  前端主系統│
│  amidaemon_cyberon.py   │        │  Cyberon STT Server          │        │          │
│  api_server（他人負責）  │◄──────►│  Cyberon TTS Server          │        │          │
│  MySQL                  │        │  110LLM（sop_api_server.py） │        │          │
└─────────────────────────┘        └──────────────────────────────┘        └──────────┘
```

**重要確認**：
- Asterisk 與 api_server 在同一台（機器 A）
- NLP（110LLM）、STT、TTS 在同一台（機器 B，192.168.5.204）
- 所有訊息以 **UUID** 作為唯一識別值

---

## 回答原始問題

**Q1：辨識結果應在 STT 設備產出還是 Asterisk 設備產出？**

> STT 運算在機器 B（Cyberon Server）執行，但辨識結果的文字已經透過 WebSocket 回傳到機器 A 的 `amidaemon_cyberon.py`（`on_result` callback）。因此**結果由機器 A 的 amidaemon 收到後，直接 POST 給同機的 api_server**，不需要繞回機器 B。

**Q2：TTS 語音該用音檔還是即時音訊？**

> 建議用 **WAV 音檔**。Asterisk 原本就支援 `Playback()` 播放本地音檔，實作最簡單可靠。流程：TTS 產出 WAV → 存到機器 A 指定路徑 → Asterisk 播放。即時串流較複雜，等音檔方式穩定後再考慮。

---

## 完整目標流程

```
1. 報警人說話
      ↓
2. amidaemon_cyberon.py 串流 PCM → Cyberon STT (機器B)
      ↓ on_result 收到 FINAL 文字
3. amidaemon POST → api_server（同機器A）
   payload: { uuid, text, role, timestamp }
      ↓
4. api_server 寫入 MySQL（建立或更新此 uuid 的案件紀錄）
      ↓
5. api_server POST → 110LLM sop_api_server（機器B:8100）
   payload: { session_id(=uuid), text }
      ↓
6. 110LLM 分析 → 回傳受理員回覆文字
      ↓
7. api_server POST → Cyberon TTS（機器B，端點待確認）
   payload: { text }
      ↓
8. TTS 回傳 WAV 音檔（或音訊資料）
      ↓
9. api_server 將 WAV 存到本地路徑，通知 amidaemon
      ↓
10. amidaemon 呼叫 Asterisk AMI 播放 WAV 給報警人
      ↓
11. 回到步驟 1（循環，直到流程結束）
```

---

## 分步執行計畫（一步一測試）

### ✅ 已完成
- amidaemon_cyberon.py 可連 AMI、可啟動 Cyberon STT
- cyberon_stt_client.py 測試通過，可收到 FINAL 結果

---

### Step 1：STT 結果 → api_server（機器A內部）

**目標**：amidaemon 收到 FINAL 文字後，POST 給 api_server，確認 api_server 有收到。

**需要先確認（請問 api_server 負責人）**：
- api_server 的 STT 結果接收端點是什麼？（例：`POST /stt/result`）
- 期望的 payload 格式？（建議至少包含 `uuid`、`text`、`role`、`timestamp`）
- api_server 目前是否在運行？port 是多少？

**改動範圍**：只動 `amidaemon_cyberon.py` 的 `on_result` callback，加一行 POST。

---

### Step 2：api_server → MySQL 存資料

**目標**：api_server 收到 STT 結果後寫入 MySQL。

**需要先做**：
- 建立 MySQL 資料庫與 cases 資料表（schema 見下方）
- 確認機器 A 上 MySQL 已安裝並運行

**建議 MySQL schema**：
```sql
CREATE DATABASE police110;
USE police110;

CREATE TABLE cases (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    uuid        VARCHAR(64) NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    role        VARCHAR(16),          -- 'caller' 或 'agent'
    stt_text    TEXT,                 -- STT 辨識文字
    nlp_reply   TEXT,                 -- 110LLM 回覆
    act_class   VARCHAR(64),          -- 案件分類（110LLM 填入）
    location    VARCHAR(256),         -- 地點
    caller_phone VARCHAR(32),         -- 報警人電話
    case_json   JSON,                 -- 110LLM 最終完整 JSON
    INDEX idx_uuid (uuid)
);
```

---

### Step 3：api_server → 110LLM（機器B）

**目標**：api_server 把 STT 文字送到機器 B 的 `sop_api_server.py`，確認回傳受理員文字。

**需要先做**：
- 在機器 B 上部署並啟動 `sop_api_server.py`（見下方前置作業）
- 確認機器 A 能 ping 通機器 B 的 8100 port

---

### Step 4：110LLM 回覆 → Cyberon TTS → Asterisk 播音

**目標**：把 NLP 回覆文字轉成語音播給報警人。

**需要先確認（請問 Cyberon 廠商或查機器B）**：
- Cyberon TTS 的 API 端點與格式
- 回傳音訊格式（WAV / PCM）與取樣率

---

## 機器 B 前置作業（請先部署）

在機器 B 上執行以下步驟，讓 `sop_api_server.py` 可以運行：

```bash
# 1. 安裝相依套件
pip install fastapi uvicorn

# 2. 把 sop_api_server.py 放到 110LLM_0426 目錄下
#    （從這個 repo 的 ai/llm/110LLM_0426/sop_api_server.py 複製過去）

# 3. 確認路徑設定，進到 110LLM_0426 目錄
cd <110LLM_0426 的路徑>

# 4. 測試 SopEngine 是否正常（確認模型可以跑）
printf "板橋發生車禍，有人受傷\n" | python3 sop_110_assistant.py \
    --input-mode text \
    --model-dir ../TW-110-Bert-v4/checkpoint-83352 \
    --flows-dir ./flows \
    --llm none

# 5. 如果上一步成功，啟動 API server
uvicorn sop_api_server:app --host 0.0.0.0 --port 8100

# 6. 確認 API 正常運作（在機器A或機器B都可以測）
curl http://<機器B的IP>:8100/health
# 預期回應：{"status":"ok","sessions":0}
```

---

## 目前阻塞點（需要外部確認才能繼續）

| 項目 | 需要確認的人 | 問題 |
|------|------------|------|
| api_server STT 端點 | api_server 負責人 | 接收 STT 結果的 URL 和 payload 格式 |
| Cyberon TTS API | Cyberon 廠商 / 機器B查看 | TTS 端點、輸入格式、輸出音訊格式 |
| MySQL 安裝狀態 | 機器A確認 | `systemctl status mysql` |
