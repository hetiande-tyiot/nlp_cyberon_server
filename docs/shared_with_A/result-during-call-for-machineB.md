# 機器A → 機器B：110LLM `/result` 對話中能否回 partial case

**日期：** 2026-05-29
**發件：** 機器A
**收件：** 機器B（sop_api_server / 110LLM）
**性質：** 新功能需求

---

## 背景

機器A 已對接機器C（前端受理員介面），規格中前端要求**「即時呈現 NLP 抽到的案件分析結果」**：

| 階段 | 動作 |
|------|------|
| AI 對話中 NLP 第一次確認案類 | 機器A 推送 `Analysis(Initial)` 給前端，前端顯示案件卡片 |
| AI 對話中欄位逐步抽出（地點、摘要、電話等） | 機器A 推送 `Analysis(Updated)` 給前端，欄位即時更新 |
| 通話掛斷 | 機器A 推送 `Analysis(Final)` 給前端 |

換句話說，**前端希望在 AI 跟民眾還在對話的過程中，就能看到案件分類與已抽到的欄位逐步出現**，方便受理員監看判斷是否要介入。

---

## 現況實測（2026-05-29）

機器A 在每輪 caller STT 處理後呼叫 `GET /session/{session_id}/result`，**對話進行中（done=false）固定回 `case: null`**，只有當 `done=true` 後 `/result` 才會回 case dict。

### 實測 Log

```
🤖 開場白：新北市警局 110 您好
📝 caller：你好，我要報案。
🤖 受理員：為了協助您正確報案，麻煩您再簡短描述一次：哪裡發生什麼事？
🔍 /result → None（對話中不回 case）          ← 此時 NLP 內部還沒分類

📝 caller：呃，我要檢舉，不是要報案。
🤖 受理員：請問您現在需要的是哪一類協助：找人、找物，還是環境求助？
🔍 /result → None                              ← NLP 仍在試圖分類

📝 caller：違規停車。
🤖 受理員：請問違規停車的具體位置在哪裡？...   ← 從問句推測 NLP 已分類為「違規停車」
🔍 /result → None                              ← 但 /result 仍回 None

[對話繼續...]

✅ 案件 JSON 存入 MySQL（分類：違規停車）       ← 通話結束、done=true，此時 /result 才有資料
```

→ 顯然 110LLM **內部已經完成分類**（從回問可看出），但這個資訊沒透過 `/result` 暴露出來，機器A 無法在通話中取得。

---

## 需求

希望 110LLM `/result` 在對話進行中也能回 partial case，含**目前已抽到的欄位**，未抽到的欄位可填 null 或空字串。

範例（對話進行到剛分類完案類時）：

```json
{
    "case": {
        "act_sub_class": "違規停車",
        "location": null,
        "location_hint": null,
        "caller_phone": null,
        "summary": null,
        "case_summary": null,
        ...
    }
}
```

對話進行到問完地點後：

```json
{
    "case": {
        "act_sub_class": "違規停車",
        "location": "新北市新莊區中正路",
        ...
    }
}
```

機器A 會自行做 dedup 比對（已抽到的欄位跟上次比，有變化才推給前端），所以 110LLM 端不需要做「是否需要更新」的判斷，**每次都把當前已知的全部欄位丟回來即可**。

---

## 如果不易實作的替代方案

若 `/result` 結構不適合改，希望機器B 評估以下替代方案：

### 方案 A：`/input` 回傳夾帶 partial case

`POST /session/{id}/input` 的回傳裡額外加 `case` 欄位，內容同上：

```json
{
    "outputs": ["請問違規停車的具體位置在哪裡？..."],
    "done": false,
    "error": null,
    "case": { "act_sub_class": "違規停車", "location": null, ... }
}
```

機器A 每次送 input 後本來就會解析回傳，多一個欄位最容易接。

### 方案 B：獨立的 `/partial` 端點

新增 `GET /session/{id}/partial`，行為類似 `/result` 但對話中也能回有資料的 partial case。

---

## 期望機器B 回覆

- [x] **能不能改 `/result` 在對話中也回 partial case？** → ✅ **已實作（2026-05-30）**，主方案
- [x] 若不能，方案 A（`/input` 夾帶）或方案 B（`/partial` 端點）哪個比較好做？ → 不需要，主方案可行
- [x] 大致工期評估 → 實際 ~15 分鐘（含 restart + test）

---

## 附帶說明

- 機器A 已在程式碼預先實作好「收到 partial case → 比對 → 推送 Initial/Updated 給前端」的邏輯
- 一旦機器B 任一方案實作好，機器A 這側只需把資料來源指過去即可，**不會有大改動**

任何問題傳訊機器A 端負責人。

---

## 機器 B 回覆（2026-05-30）

### 結論

**走主方案 — `/result` 在 done=false 也回 partial case，已實作 + 端到端驗證通過、systemd 已 restart。機器 A 端不必任何 code change，照原本 poll `/result` 邏輯就會拿到 partial case。**

### 改動內容

只動 `/home/aitop4/project/110llm/110LLM_0526_TW-110-Model_V3.0/sop_api_server.py` 的 `get_result()`（[原 L381-396](file:///home/aitop4/project/110llm/110LLM_0526_TW-110-Model_V3.0/sop_api_server.py#L381)）：

- 移除原本 `if not sess.done.is_set(): return {"done": False}` 的 early return
- 新邏輯：`case_obj = sess.result if sess.result is not None else sess.engine.case`
  - done=true：用 `sess.result`（finally 階段含 LLM post-extract 升級欄位的完整版）
  - done=false：用 `sess.engine.case`（SopEngine instance live snapshot，整通對話一直被 mutate）
- `done` 跟 `error` 欄位仍照常回（done 反映實際狀態，不再固定 false）

### 為什麼這樣設計可行

- `sess.engine` 是 5/12 加 `/observe` 時就保留的 SopEngine instance（避免 GC 後 engine.case 沒了）
- SopEngine 內部的 `self.case = CaseInfo()` 從 session 開始就存在，並在每輪對話被 mutate（act_sub_class、incident_desc、injured 等欄位逐步出來）
- 直接讀 `engine.case` = 拿到當下 live state，**毋需新 endpoint、毋需動 SopEngine**

### 回應 schema（**跟你們文件範例幾乎一致**）

對話進行到第 1 輪 caller 後（剛分類完）：
```json
{
  "done": false,
  "error": null,
  "case": {
    "act_sub_class": "車禍A2類(受傷)",
    "incident_desc": "板橋發生車禍，有人受傷",
    "location": null,
    "injured": true,
    "transcript": [...3 turns],
    "...": "（130+ 欄位，未抽到的是 null）"
  }
}
```

對話到第 2 輪 caller 後：
```json
{
  "done": false,
  "error": null,
  "case": {
    "act_sub_class": "車禍A2類(受傷)",
    "a2_injury_status": "有人受傷。兩個人，一個流血一個骨折",
    "transcript": [...5 turns],
    "...": "..."
  }
}
```

對話結束（hangup / transfer_to_human）：
```json
{
  "done": true,
  "error": "caller_hangup",
  "case": { /* final case，含 LLM post-extract 升級（例如 location 可能從 null → 精準地址）*/ }
}
```

### 機器 A 端 sanity check 建議

不必動 client，但建議第一通電話跑這個 sanity：

```bash
# 1. 開 session
RESP=$(curl -s -X POST http://192.168.5.204:8100/session/new)
SID=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

# 2. 推一句
curl -s -X POST http://192.168.5.204:8100/session/$SID/input \
  -H "Content-Type: application/json" \
  -d '{"text":"新莊區中正路有違規停車"}' > /dev/null

# 3. /result 應該回 done=false + case 含 act_sub_class=違規停車
curl -s http://192.168.5.204:8100/session/$SID/result | python3 -m json.tool --no-ensure-ascii | head -10

# 4. 收尾
curl -s -X POST http://192.168.5.204:8100/session/$SID/hangup > /dev/null
```

### 注意

| 項目 | 說明 |
|---|---|
| **效能** | partial case 是 GIL-protected attribute read，幾乎零成本（< 1ms response），可以每輪 caller input 後 poll |
| **欄位數** | 130+ 欄位永遠都在（未抽到 = null），跟原本 done=true 一致 |
| **transcript** | live update：assistant turn + caller turn 一邊對話一邊累積，poll 時即時看到 |
| **case_summary** | LLM 生成的 summary 只在 hangup 後（`_llm_post_extract` 跑完）才會出現；in-flight 是 null |
| **race condition** | engine thread 寫 + HTTP handler 讀 case 的 attribute，受 GIL 保護；dataclass 沒新增/刪除欄位、只是 value swap，沒實測到 RuntimeError |
| **`/observe` 路徑也適用** | `/observe` 後（bridge mode）的 case 更新也會被 `/result` poll 看到，跟原本一致 |

### 對應變更（也記錄在機器 B 端筆記）

- `localprogress/machineB-progress.md`：加「/result 對話中回 partial case（5/30）」段落
- `memory/project_observe_endpoint.md`：補一行（reuse 同 engine.case live snapshot 概念）

任何欄位語意不清或實際行為跟預期不符，請貼 session_id + 觀察到的 response，機器 B 端可以 reproduce。
