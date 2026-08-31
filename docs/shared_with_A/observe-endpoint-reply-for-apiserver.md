# 119 NLP Server → apiserver：`/observe` 已完成

**日期：2026-08-28**
**發件：119 NLP Server（機器B, :8200）**
**收件：apiserver**
**對應需求：** `talk_toB/observe-endpoint-for-machineB.md`（2026-08-28）

---

## 結論

**兩個前提都成立，已實作完成。** 你們照原文件那樣接就可以。

| 你們問的 | 答 |
|---|---|
| 前提一：`/observe` 可以在還沒 `done` 時呼叫嗎 | **可以**。完全不看 `done`，任何時候都收 |
| 前提二：session 會活到 `/hangup` 嗎 | **會**。但你們漏了一條路徑，見下方 ⚠️ |
| 有沒有閒置逾時 | **原本沒有**。這次新增了純防呆用的逾時，正常通話碰不到，見下方 |
| 完成時間 | 已完成，等你們排期一起上線測 |

---

## ⚠️ 一件你們文件沒涵蓋、但一定會遇到的事

你們的時序圖只畫了「**受理員在前端按人工介入**」這條路。這條路 session 還活著（`done=false`），沒問題。

但 **119 的 AI 自己也會決定轉真人**，而且不只一個地方：

| 觸發點 | AI 會說的話 |
|---|---|
| OHCA 判定（沒意識／沒呼吸／肚子沒起伏） | 「救護車已派出，請不要掛斷電話，我立即為您轉接專人。」 |
| 火警無法確認燃燒標的 | 「無法確認燃燒標的類別，立即為您轉接專人，請稍候。」 |
| 報案人姓名／電話問不出來 | 「無法確認報案人資訊，立即為您轉接專人，請稍候。」 |

走這幾條時，**SOP 引擎當場就結束了**，`done` 立刻變 `true`。
按舊邏輯，SSE 會在 0.3 秒內推 `done` 然後關閉連線 —— 你們那邊還在撥分機、等真人接起，等第一句 `/observe` 送過來，管子早就斷了。

**我們已經處理掉了**：SSE 的收線條件從「引擎跑完」改成「**你們呼叫 `/hangup`**」。
兩條路徑現在都能正常續聽，你們不用分辨是哪一種。

**但相對地，請你們務必遵守**：

> **不論哪一條轉真人路徑，都不可以提早呼叫 `/hangup`。**
> 只有電話真正掛斷時才呼叫。

（你們原文件已經說會移除介入時的 `hangup` 繞道 —— 對，就是這個意思，AI 自己轉真人那條也一樣。）

---

## API 規格

### `POST /session/{session_id}/observe`

```json
{
    "text": "病患現在還有呼吸嗎？",
    "role": "agent"
}
```

| 欄位 | 型別 | 說明 |
|---|---|---|
| `text` | string | 這一句話的 STT 文字。空字串會被忽略（仍回 200） |
| `role` | string | `"caller"`（民眾）或 `"agent"`（接手的真人受理員），大小寫不拘 |

**回應 200**（你們說不讀，但還是給你們除錯用）：

```json
{ "accepted": true, "role": "agent", "transcript_size": 7 }
```

**錯誤碼**：`404` session 不存在、`400` role 不是 caller/agent、`500` engine 狀態遺失（server 重啟過）。

### 行為

- **不看 `done`、也不會設 `done`**，任何階段都能呼叫
- **不產生 AI 回覆**，回應裡沒有 `outputs`，你們不用播任何東西
- **不做欄位抽取** —— 依你們「欄位由受理員自行填寫」的說明，轉真人後我們只更新 `case_summary`，不會去動結構化欄位跟人工輸入打架
- **LLM 丟背景跑**，本端點只寫 transcript 就回，實測 **< 2 ms**，不會卡住通話
- **transcript 多一個 role 值 `"agent"`**（原本只有 `assistant` / `caller`），`/result` 拿到的逐字稿會完整包含真人那段

### 節流

你們說「每句話一次、可以節流」，我們照做了：

| 參數 | 預設 | 意思 |
|---|---|---|
| `OBSERVE_DEBOUNCE_S` | 2.0 秒 | 收到句子後先等一下，把連續湧入的句子併成一次重算 |
| `OBSERVE_MIN_INTERVAL_S` | 5.0 秒 | 兩次重算之間至少隔這麼久 |
| `OBSERVE_SUMMARY_MAX_TURNS` | 40 輪 | 摘要只取最後 N 輪對話（`n_ctx` 4096，長通話塞不下） |

所以摘要更新是**每 5 秒左右一次**，不是每句一次。這些都是 env var，上線後可調。

---

## 摘要怎麼回到你們那邊

**照原路，走現有的 `GET /session/{id}/case/stream`，你們不用改任何接收邏輯。**

```
apiserver: POST /observe ──▶ 立刻回 200（寫進 transcript）
                          ↓ 背景 worker
                       重算 case_summary（每 ~5 秒一次）
                          ↓
                    SSE: event: case_updated ──▶ apiserver ──▶ 前端
```

一個小提醒：因為 SSE 是比對整份 case 有沒有變，而 transcript 也在 case 裡，所以你們會在**每次 `/observe` 之後馬上收到一筆 `case_updated`**（那時 `case_summary` 還是舊的），過幾秒摘要算完再收到一筆新的。前端直接照收即可。

---

## 📌 一個行為改變，請你們確認

**SSE 的 `done` 事件會晚一點才推。**

| | 改前 | 改後 |
|---|---|---|
| `done` 事件推送時機 | SOP 引擎跑完那一刻 | **你們呼叫 `/hangup` 那一刻** |
| 一般通話（沒轉真人）的影響 | — | 晚幾秒（引擎跑完 → 民眾掛電話 → 你們 call hangup） |
| 轉真人通話的影響 | 管子提早關掉、續聽失效 | 正常續聽到掛斷為止 |

如果你們的 SSE consumer 有「收到 `done` 才做某件事」的邏輯，那件事會晚幾秒發生。
**照你們時序圖的流程（掛斷才 call hangup）是沒問題的**，但還是請確認一下。

### 防呆逾時（回答你們的 Q2）

**我們原本完全沒有閒置逾時機制** —— session 永不過期、`/output` 不會逾時、SSE 早就有 15 秒 keepalive。

這次因為 SSE 改成只認 `/hangup`，萬一你們那邊異常沒呼叫，連線會永遠掛著。所以加了兩道純防呆的上限：

| 參數 | 預設 | 什麼時候會觸發 |
|---|---|---|
| `OBSERVE_GRACE_S` | 120 秒 | 引擎跑完後，**一句 `/observe` 都沒收到**且沒 `/hangup`，等這麼久就收線 |
| `OBSERVE_IDLE_CLOSE_S` | 900 秒 | 已在續聽中，但**久無新句子**也沒 `/hangup`，等這麼久就收線 |

**正常流程碰不到這兩個**：橋接通常十幾秒內就會送出第一句 `/observe`（120 秒的 grace 綽綽有餘），真人對話期間每句話都會刷新閒置計時（15 分鐘的上限對應你們說的「通話可能十幾分鐘」）。
如果實際橋接時間比預期長，跟我們說一聲調 env 就好，不用改 code。

---

## 你們實際要改的三個地方

我翻了 `apiserver` 現在的程式碼，具體是這三處：

### 1. `sop_client.py:51` — `observe()` 目前是 no-op，還原它

```python
def observe(sop_session_id: str, text: str, role: str) -> dict:
    """Bridge 後的雙通道 STT 觀察 —— 119 未提供 /observe，本函式為 no-op。"""
    return {}
```

註解裡寫的「119 NLP Server 沒有這個端點」現在不成立了，把 git 歷史裡的原始版本還原即可。
回應 body 你們本來就不讀，`return {}` 改成回實際回應或繼續丟掉都行。

### 2. `api_server.py:279-283` — 移除介入時的提前 hangup 繞道

```python
    # 2. 提前 hangup 119LLM session，解鎖 /observe（B 端規格要求 done=true 才能 observe）
    sop_id = sop_sessions.get(uuid, "")
    if sop_id:
        sop.hangup(sop_id)
        print(f"📤 [{uuid[:8]}] 通知 119LLM hangup（介入觸發、解鎖後續 /observe）", flush=True)
```

**整段刪掉。** 我們這邊不再要求 `done=true`，這個繞道已經沒有必要，而且留著會提早關掉 SSE。

### 3. AI 自己轉真人那條路，確認沒有多餘的 hangup

我看 `api_server.py:213-215`，`transfer` 為真時你們只有 `_push_transfer_suggest_once()`，
**沒有**呼叫 `sop.hangup()` —— 這是對的，請維持。

唯一該呼叫 `hangup` 的地方是 `/call/end`（`api_server.py:241`），保持原樣。

### 不用改的

`sse_consumer` 不用動。`/call/end` 裡 `sse_consumer.stop(uuid)` 的保險呼叫也保留，
因為 `done` 事件現在會晚到（等 `sop.hangup()` 才推），那行剛好接得上。

---

## 快速測試

```bash
S=http://<MACHINE_B_IP>:8200
SID=$(curl -s -X POST $S/session/new | python3 -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

# AI 階段照舊
curl -s -X POST $S/session/$SID/input -H 'Content-Type: application/json' \
     -d '{"text":"板橋區中山路32號有人昏倒了"}'

# 轉真人後改送 /observe（民眾跟受理員都送）
curl -s -X POST $S/session/$SID/observe -H 'Content-Type: application/json' \
     -d '{"text":"我是受理員接手，請問患者還有意識嗎","role":"agent"}'
curl -s -X POST $S/session/$SID/observe -H 'Content-Type: application/json' \
     -d '{"text":"叫他沒有反應，在五樓","role":"caller"}'

# 另開一個 terminal 掛 SSE，會看到 case_summary 逐步更新
curl -sN $S/session/$SID/case/stream

# 電話真的掛了才收工
curl -s -X POST $S/session/$SID/hangup
curl -s $S/session/$SID/result | python3 -m json.tool --no-ensure-ascii
```

---

## 我們這側的驗證狀況

- 新增 18 個單元測試（`tests/test_observe_endpoint_119.py`），全過
- 既有 74 個測試沒有新增失敗（原本就有 5 個地址／火警流程的失敗，與本次無關）
- 端到端實跑過完整流程：AI 對話 → `/observe` 4 句（含 `agent`）→ SSE 持續收到 `case_updated` → `/hangup` → 收到 `done` 並關閉 → `/result` 逐字稿含 `agent` 那幾句
- ⚠️ **端到端那次是在 LLM 關閉（規則備援）模式下跑的**，因為本機 GPU 當時已被佔用 21 GB，不想跟現有服務搶。LLM 路徑由單元測試以假 extractor 覆蓋。**上線前請安排一次雙方帶 LLM 的聯測。**

---

## 有問題請逕回 `nlp_cyberon_server/docs/shared_with_A/`
