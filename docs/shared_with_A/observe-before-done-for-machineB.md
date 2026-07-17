# 需求：`/observe` 在 session 未結束時也能使用

> 日期：2026-06-24
> 發件：機器A
> 收件：機器B（sop_api_server / 110LLM）
> 性質：API 行為調整需求
> 前情：`shared_with_B/sse-push-request-for-machineB.md` 6/1 你們做的 SSE push 機制

---

## TL;DR

`/observe` 目前要求 session 必須 `done=true` 才接受、否則回 `409 Conflict`。
我們新增了**受理員「即時介入」**的功能（對話中途由人接手），這個情境下：
- 110LLM session **還沒 done**（AI 才講一兩輪、判斷不到該轉接）
- 受理員按介入按鈕、bridge 接通
- 雙方對話 → 想送 `/observe` 讓 110LLM 持續抽欄位 → **全部被 409 拒絕**

請評估是否能讓 **`/observe` 在 session 未 done 時也接受呼叫**，行為跟 done 後一樣（更新 case_summary + transcript、不產生 AI 回覆）。

---

## 現況（我們暫時的繞道）

為了讓 /observe 不再 409，我們在 api_server 端做了**介入觸發時先呼叫 `/hangup`** 的繞道：

```python
# api_server 的 /api/AiRobot/Transfer 端點
@app.post("/api/AiRobot/Transfer")
def ai_robot_transfer(payload):
    # 1. 標記介入
    mc_state[uuid].intervened = True
    # 2. 提前 hangup 110LLM session，解鎖後續 /observe
    sop.hangup(sop_id)
    # 3. Forward 給 amidaemon 執行實際轉接
    requests.post(f"{AMIDAEMON_URL}/transfer", ...)
```

這雖然解決了 409，但**副作用**是：
- 你們的 SSE done event 立刻被推（因為 session 標記 done）
- 我們的 SSE consumer 收到 done 後預期 stream 會關閉
- **失去 bridge 期間的即時 case 更新**（受理員那邊看不到欄位逐步補齊）
- 只能等通話真正掛斷後在 `/result` 拿到完整 case 補 Final

---

## 對比兩種行為

| 階段 | 改前（沒繞道）| 改後（介入時先 hangup） | 期望（你們直接支援）|
|---|---|---|---|
| 介入前 AI 對話 | /input 正常、SSE case 推送正常 | 同上 | 同上 |
| 介入觸發那一刻 | session 仍 done=false | 我們 call /hangup → done=true | 不動 session 狀態 |
| Bridge 期間 /observe | **409 全部拒絕**、case 沒更新 | 200 OK、case 有更新 | 200 OK、case 有更新 |
| Bridge 期間 SSE 推送 | 維持但沒新 case 可推 | **stream 已關**、沒推送 | **持續推 case_updated**（這是我們最想要的）|
| 真實掛斷 | /call/end → /result 拿最終 case | 同左 | 同左 |
| MC 體驗 | bridge 期間案件卡片無動靜 | bridge 期間案件卡片無動靜 | bridge 期間案件卡片**持續更新**（受理員監看流暢） |

---

## 期望

### 主要需求

讓 `/observe` 在 **session 不論是否 done** 都接受呼叫，行為一致：
- 寫入 transcript
- caller role → 觸發 LLM 抽取欄位（更新 case）
- agent role → 只 append transcript（不觸發 LLM）
- 不產生 AI 回覆

### SSE 行為連動

若主要需求 OK，希望 SSE 也能配合：
- session 未 done 時 /observe 觸發 case 變化 → **照常推 `case_updated` event**
- 不要因為 /observe 變化就推 `done` event（done event 仍只在使用者實際結束會話時推）

換言之，**從 SSE consumer 的視角來看，介入後跟介入前沒有差別**：case 變了就推、done 才推 done。

---

## 我們這側收到後會做的事

收到你們確認可以做之後：

1. **移除 api_server 介入時的 `sop.hangup()` 繞道**
   ```python
   # 移除這段
   sop.hangup(sop_id)
   print("通知 110LLM hangup（介入觸發、解鎖後續 /observe）")
   ```
2. **移除 `mc_state.intervened` 旗標和對應的 SSE done 特例處理**（sse_consumer 不再需要分辨「介入引發 done」vs「正常 AI done」）
3. SSE consumer 完全用統一邏輯：case_updated 持續推 Analysis(Updated)、done 才掛斷

我們這側架構不會大改、只是把繞道拿掉、回到「介入跟未介入流程一致」的乾淨設計。

---

## 為什麼要這樣改

### 機制角度

`/observe` 的原始設計（依你們 5/12 的 transfer-nlp-issue-reply）是「**AI 已決定轉接（done=true）後、雙通道紀錄用**」。
但實際運作中還有「**受理員主動介入**」情境，這時 AI 還沒做完判斷、session 還沒 done、但確實需要 /observe 來持續抽欄位。

兩種情境的本質都是「**雙通道對話、LLM 不該再產生回覆、但要繼續抽案件資訊**」，沒理由用 done 旗標當門檻擋掉其中一個。

### UX 角度

受理員按下介入後、bridge 期間案件卡片應該**持續即時更新**：
- 受理員確認地點時，「現場位置」紅框跳出
- 受理員問車牌時，「車輛資訊」跳出
- ...等等

這個 UX 體驗在我們之前 6/1 對齊 SSE push 機制時是雙方共識的目標。
現在因為 /observe 的 done 門檻、bridge 期間整個欄位更新斷掉，等於白做了那套 SSE 推送機制。

---

## 期望回覆

- [ ] 評估 `/observe` 接受 done=false 的可行性
- [ ] 評估 SSE 在 /observe 觸發 case 變化時持續推 `case_updated`（不誤推 done）
- [ ] 大致工期（以週為單位即可）
- [ ] 若有設計上的考量、希望我們繼續用 hangup 繞道、也歡迎說明

---

## 附帶：實測 log 證據

2026-06-24 介入測試 log，介入後每次 /observe 都失敗：

```
📥 [Transfer/intervene] 46906fd9 → PJSIP/1006
📝 [46906fd9] [轉接] 在那個。
⚠️ 110LLM observe 失敗：409 Client Error: Conflict for url:
   http://192.168.5.204:8100/session/b5a63507-fea2-4bd3-98ba-d43428113e93/observe
📝 [46906fd9] [轉接] 中華路。
⚠️ 110LLM observe 失敗：409 Client Error: Conflict for url: .../observe
📝 [46906fd9] [轉接] 喂。
⚠️ 110LLM observe 失敗：409 Client Error: Conflict for url: .../observe
... （連續 9 次 409，整個 bridge 期間 case 沒任何更新）
```

任何問題請逕回 `shared_with_A/`。
