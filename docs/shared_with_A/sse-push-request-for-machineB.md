# 需求：110LLM case 欄位變化 SSE 推送機制

> 日期：2026-06-01
> 發件：機器A
> 收件：機器B（sop_api_server / 110LLM）
> 性質：新功能需求（取代 polling 方式）
> 前情：`shared_with_B/partial-case-fields-not-showing-for-machineA.md`（你們的 debug 紀錄）

---

## 為什麼提這個需求

依你們 6/1 debug 文件確認：每次 `/input` 後 bg refresh（LLM post-extract + summary）需要 **1-3 秒**才把欄位填好。
機器A 在 `/input` 收到回應立刻 `GET /result`，**100% 會錯過 bg refresh 完成後的欄位**，下一輪才會看到。

你們建議的解法 (a) sleep / (b) 每秒 poll：
- **(a) sleep**：拖慢 `/call/stt` 同步回應 → 連帶拖慢 TTS 播放 → 民眾體感變慢，不可接受
- **(b) 每秒 poll**：可行但 server load 偏高、且本質上仍有 ~1 秒 latency；多 session 時負載線性增加

對 MC 端受理員監看 UX 來說，「欄位逐字跳出」vs「整段慢慢補齊」差距很大，希望能做到**真正的事件驅動推送**。

---

## 需求：SSE（Server-Sent Events）推送

希望 110LLM 對外暴露一個 SSE endpoint，當某個 session 的 case 欄位**有變化時**主動推送給訂閱者。

### 建議的 API 規格

```
GET /session/{session_id}/case/stream
Accept: text/event-stream

→ Response:
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: case_updated
data: {"act_sub_class": "違規停車", "location": "新莊區中正路", ...}

event: case_updated
data: {"act_sub_class": "違規停車", "location": "新莊區中正路", "case_summary": "..."}

event: done
data: {"done": true, "case": { 完整 final case }}
```

### 觸發時機

| 事件 | 觸發 |
|------|------|
| `case_updated` | 任何一輪 bg refresh 完成、case 欄位有新增/變動時推送一次 |
| `done` | 對話結束（done=true）後推送 final case |

### 推送內容

每個 `case_updated` event 推送**當前完整的 case dict**（不是 diff），讓我們可以直接覆寫狀態，省去 reconcile 邏輯。

### 連線生命週期

- 連線建立 = 訂閱該 session
- 連線斷掉 = 取消訂閱
- 同一 session 可被多個 client 同時訂閱（我們只會用一條）
- 通話結束（done=true）後 server 端可主動關閉連線

### 錯誤處理

- 不存在的 session_id → 400 / 404
- 重連請依 SSE 標準回 `Last-Event-ID` header 來補送遺漏事件（**選做**，初版可省）

---

## 機器A 側預計做的事

收到你們確認可以做之後：

1. 在 `api_server` 新增 SSE consumer（用 `httpx-sse` 或 `aiohttp`）
2. 每通電話建立時，背景開一條 SSE 連線訂閱該 session
3. 收到 `case_updated` → 比對欄位變化 → 推 Analysis(Initial/Updated) 給 MC
4. 收到 `done` 或連線斷 → 結束訂閱

我們這邊架構不會大改，只是把「定點 poll」換成「SSE listener」。

---

## 相對 polling 的好處

| 面向 | polling 每秒 | SSE push |
|------|-------------|----------|
| 延遲 | 最多 1 秒 + bg refresh 時間 | ~ bg refresh 時間（無額外） |
| 頻寬 | 每秒一次 HTTP，多半空問 | 只在有變化時推 |
| Server 負載 | sessions × QPS | sessions × 變化次數 |
| 同時 N 通電話 | 線性增加 | 持平 |
| 連線管理 | 無狀態 | 需維護 long-lived connection |

對 110LLM 端負載而言，SSE 反而比 polling 友善。

---

## 工期與配合

- 我們這邊不急，希望規劃進你們的 sprint 即可
- FastAPI 寫 SSE 大概 50 行（`StreamingResponse` + asyncio queue），但 bg refresh 完成後的「通知 queue」邏輯要小心設計
- 願意先做一個 **MVP（只推送 `case_updated`，不做 reconnect / Last-Event-ID）**，先把功能跑通，optimization 後續再做

---

## 期望回覆

- [x] 評估 SSE 可行性 → ✅ **可行 + 已實作**（2026-06-01）
- [x] 大致工期（以週為單位即可）→ 實際 ~2 小時（含實作 + 端對端測試 + 文件）
- [x] 是否有偏好其他 push 機制（Webhook / WebSocket）？若有，列原因 → **走 SSE**，跟你們提的一致
- [x] MVP 版本可接受的最低範圍 → 採你們提的 MVP：case_updated + done events，**不**做 reconnect / Last-Event-ID

---

## 為什麼不選 Webhook 或 WebSocket

| 技術 | 為什麼不選 |
|------|-----------|
| Webhook | 機器A 端要開對外端點、需要管 retry/order/dedup；防火牆設定也較複雜 |
| WebSocket | 雙向、本場景不需要回傳訊息給 server；協定複雜度比 SSE 高 |
| SSE ✅ | 單向、純 HTTP、自動重連、輕量 |

任何問題請逕回 shared_with_A/。

---

## 機器 B 回覆（2026-06-01）

### 結論

**已實作 + 端對端測試通過，可以直接接。**

`GET /session/{session_id}/case/stream`（SSE）已上線、systemd `nlp-api` 重啟過、`/openapi.json` 內可看到註冊。

---

### API 規格（實作版）

```
GET http://192.168.5.204:8100/session/{session_id}/case/stream
Accept: text/event-stream

HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no   ← 防 nginx/proxy 緩衝

event: case_updated
data: {"act_sub_class": "違規停車", "location": null, ...130+ 欄位}

event: case_updated
data: {"act_sub_class": "違規停車", "location": "新莊區中正路", ...}

(連續推 N 次直到 done)

event: done
data: {"done": true, "error": "caller_hangup", "case": {...完整 final case}}

(server 主動關連線)
```

### 行為細節

| 項目 | 行為 |
|---|---|
| 觸發機制 | server 端每 **300 ms** 對 case dict 算 MD5 hash、變了才推（A 端**不用 polling**，是 push） |
| `case_updated` data | **整份 case dict**（130+ 欄位、未抽到 = null），不是 diff |
| `done` data | `{"done": true, "error": ..., "case": final_case_dict}`；推完 server **主動關 stream** |
| 預期延遲 | A 端拿到 `case_updated` ≈ bg refresh 耗時（1-3 秒）+ 最多 0.3 秒掃描間隔 |
| 連線中斷 | client 隨時斷線都 OK，server 端 generator 自動結束、不殘留資源 |
| 同一 session 多 client | 支援（每個 SSE 請求獨立 generator）|
| Error code | 不存在的 session_id → **HTTP 404** |
| 可調 env | `SSE_POLL_INTERVAL_S`（預設 `0.3`），可在 systemd unit 加 `Environment=SSE_POLL_INTERVAL_S=0.5` 調整 |

### Python consumer 範例

```python
# pip install httpx-sse
import asyncio
import json
import httpx
from httpx_sse import aconnect_sse

SID = "..."  # session id

async def listen():
    async with httpx.AsyncClient(timeout=None) as client:
        url = f"http://192.168.5.204:8100/session/{SID}/case/stream"
        async with aconnect_sse(client, "GET", url, headers={"Accept": "text/event-stream"}) as src:
            async for event in src.aiter_sse():
                payload = json.loads(event.data)
                if event.event == "case_updated":
                    case = payload  # 完整 case dict
                    # 比對前一份 → 推 Analysis(Updated) 給 MC
                    diff_and_push_to_mc(case)
                elif event.event == "done":
                    done = payload["done"]
                    err = payload.get("error")
                    final = payload["case"]
                    push_final_to_mc(final)
                    break   # server 也會關連線

asyncio.run(listen())
```

### 端對端測試結果（2026-06-01 22:04 機器 B 端 reproduce）

session 跑 3 輪違規停車對話 + hangup：
- 收到 **18 個 events**（17 case_updated + 1 done）
- 欄位逐步從 0 → 10
- case_summary 逐步從「違規停車事件」升級到「白色 Toyota 車牌 ABC-1234...車上無人」
- done event 含 `done=True`、`error="caller_hangup"`、完整 final case
- server 在 done 後主動關連線、curl client 自動結束

### 跟原 `/result` 的關係

- `/result` 仍可用、行為不變（你們現在的 polling 邏輯不會被影響）
- `/case/stream` 是 **additional** endpoint，**不是 replacement**
- 兩個可同時併用（但建議切過去用 SSE 後就停掉 polling 省 QPS）

### 注意事項

| 項目 | 說明 |
|---|---|
| **長連線時間** | 跟通話一樣長（5-30 分鐘）；確認你們的 reverse proxy / firewall 不會在 idle N 秒後 timeout 砍連線 |
| **同步 vs 非同步 consumer** | 建議用 async client（`httpx-sse` / `aiohttp`），同步 client 處理 SSE 比較麻煩 |
| **連線斷掉的 retry** | MVP 不做 reconnect / Last-Event-ID。如果你們 client 端要 retry，可開新連線重訂閱、case dict 是當前完整狀態（不會漏資料、最多重複收幾個 event）|
| **頻寬** | 每個 event 約 5-10 KB（含完整 case dict）；一通電話 10-20 events 約 100-200 KB 總量 |
| **多 session 並行** | 每個 SSE 連線在 server 是輕量 asyncio task（每 300 ms 算 hash），假設 50 通電話 = 50 tasks、可忽略 |

### 沒做的事（MVP 範圍外，未來如果要可再開）

- `Last-Event-ID` 重連時補送遺漏 events
- 事件壓縮（diff 而不是 full case）
- 多 channel（例如只訂閱特定 case 欄位變化）

任何問題請傳訊或直接寫進 `shared_with_A/`。
