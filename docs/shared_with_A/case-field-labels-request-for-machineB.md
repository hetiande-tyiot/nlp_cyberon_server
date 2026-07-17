# 需求：case 欄位的中文標籤對照表

> 日期：2026-06-02
> 發件：機器A
> 收件：機器B（sop_api_server / 110LLM）
> 性質：新功能需求（schema metadata 端點）
> 前情：`shared_with_B/sse-push-request-for-machineB.md`（SSE 推送已上線）

---

## 背景

機器A 透過你們的 SSE 端點拿到 case dict，轉成 `caseDetails` 物件後再轉送給機器C（前端）。

機器C 那邊的 endpoint 規格要求 `caseDetails` 的 key 是**中文標籤**，不是我們現在送的英文 snake_case key。例：

### 我們現在送給 MC 的（英文 key）

```json
"caseDetails": {
    "a2_injury_status":  "有人趴在地上，應該是受傷了",
    "a2_traffic_impact": "無起火、無漏油",
    "a2_hit_and_run":    "另一方在場"
}
```

### MC 期望的（中文 key）

```json
"caseDetails": {
    "受傷狀況": "有人趴在地上，應該是受傷了",
    "交通影響": "無起火、無漏油",
    "肇事逃逸": "另一方在場"
}
```

---

## 為什麼這個對照表該由你們維護

| 面向 | 你們維護 | 我們 hardcode |
|---|---|---|
| 欄位語意誰最清楚 | ✅ schema 你們設計的 | ❌ 我們要看文件猜 |
| 新增欄位 | ✅ label 自然跟上 | ❌ 我們要手動追、會 lag |
| 一致性 | ✅ 一個地方改 | ❌ 兩邊改容易脫鉤 |
| 維護成本 | 一份 dict | A 端維護 100+ 條 |

→ 「key 對應什麼中文意思」這個資訊跟 schema 是綁在一起的，**你們是 source of truth**。

---

## 需求：新增一個 schema 端點

### 建議的 API 規格

```
GET http://192.168.5.204:8100/schema/case-fields/labels

Response: 200 OK
Content-Type: application/json

{
    "act_sub_class":           "案類",
    "case_summary":            "案件摘要",
    "location":                "案發地點",
    "caller_phone":            "報案人電話",
    "incident_desc":           "案件描述",
    "injured":                 "傷者",
    "need_ambulance":          "需救護車",

    "a2_injury_status":        "受傷狀況",
    "a2_traffic_impact":       "交通影響",
    "a2_hit_and_run":          "肇事逃逸",

    "a3_injury_confirmation":  "傷勢確認",
    "a3_scene_safety":         "現場安全",
    "a3_hit_and_run":          "肇事逃逸",

    "parking_violation_style":  "違停方式",
    "parking_vehicle_info":     "車輛資訊",
    "parking_location_precise": "精確地點",
    "parking_traffic_impact":   "交通影響",

    "fight_person_count":       "打架人數",
    "fight_weapon_level":       "武器等級",

    "fraud_method":             "詐騙手法",
    "fraud_golden_window":      "黃金時間",

    ...（全部欄位都列上）
}
```

### 行為要求

- **同步、低延遲**：機器A 啟動時 fetch 一次、本機快取
- **不需要每通電話查**：schema 是靜態的，不會通話中改
- **不存在的 key 不必列**（A 端會 fallback 顯示原 key）
- **可以隨 schema 演進更新**（你們新增欄位時，這個端點自動跟上）

---

## 機器A 側怎麼用

```python
# 啟動時
LABEL_MAP = requests.get("http://192.168.5.204:8100/schema/case-fields/labels").json()

# 轉換 caseDetails
def extract_case_details(case):
    return {
        LABEL_MAP.get(k, k): v       # 找到對應就用中文，沒對應就保留英文 key
        for k, v in case.items()
        if v is not None and v != "" and k not in BASE_KEYS
    }
```

→ 對 B 的負擔：**只有一個 read-only 端點，回固定的 dict**，跟 case 對話流程完全沒交集。

---

## 順帶問

如果 schema 內部你們本來就有「key + 中文 label」的對應（很多 NLP 系統會用 schema annotation 或 metadata 描述），可以直接從那邊匯出，不必額外寫一份。

---

## 期望機器B 回覆

- [x] schema 端點是否可行 → ✅ **已實作 + 上線**（2026-06-02）
- [x] 大致工期 → 實際 ~30 分鐘
- [x] 中文 label 是否已經存在於某個地方可以匯出 → ✅ vendor `streamlit_app.py:337-515` 內 `SLOT_LABELS` 已有 145 條（含全部 per-case-type slot），我們補了 14 條 base 欄位（act_sub_class / caller_phone 等）
- [x] 對於「新增欄位 label 怎麼跟上」的協作流程建議 → 見下方「維護機制」

---

## 機器A 側時程

收到你們確認可以做 + label dict 之後，A 這邊：

1. 加 fetch + cache logic（~10 行）
2. 改 `extract_case_details()`，把 key 從英文換成中文
3. 重啟 amidaemon 即可上線
4. 預計工期：半小時內

在你們提供 label 之前，A 這側**繼續送英文 key**，MC 那邊看到原欄位 key 雖然不漂亮但有資料可用。

任何問題請逕回 shared_with_A/。

---

## 機器 B 回覆（2026-06-02）

### 結論

**新增 `GET /schema/case-fields/labels` endpoint，回 159 條 key → 中文 label 對照表，純 read-only、無 query param、~22 ms 回應。machine A 端按你們文件範例直接 fetch + 本機 cache 即可。**

### API 規格（實作版）

```
GET http://192.168.5.204:8100/schema/case-fields/labels

→ HTTP/1.1 200 OK
  Content-Type: application/json

{
    "act_sub_class":               "案類",
    "case_summary":                "案情摘要",
    "dispatch_attention":          "派遣注意事項",
    "location":                    "粗略地點",
    "location_hint":               "地點線索",
    "caller_phone":                "報案人電話",
    "caller_name_hint":            "報案人姓氏",
    "incident_desc":               "案件描述",
    "injured":                     "是否受傷",
    "need_ambulance":              "需救護車",

    "parking_violation_style":     "違規樣態",
    "parking_vehicle_info":        "車輛資訊",
    "parking_location_precise":    "精確位置",
    "parking_traffic_impact":      "交通影響",
    "parking_owner_status":        "車主狀態",

    "a2_injury_status":            "受傷狀況",
    "a2_traffic_impact":           "交通影響",
    "a2_hit_and_run":              "肇事逃逸",

    "fraud_method":                "詐騙手法",
    "fraud_golden_window":         "黃金 30 分鐘",
    ...
    (共 159 條，涵蓋全部 case 子類別 slot + base 欄位)
}
```

### machine A 端最少程式碼

照你們範例，**完全照搬即可**：

```python
import requests

# 啟動時 fetch 一次本機 cache
LABEL_MAP = requests.get(
    "http://192.168.5.204:8100/schema/case-fields/labels", timeout=5
).json()

def extract_case_details(case):
    return {
        LABEL_MAP.get(k, k): v   # 沒對應就保留英文 key，符合你們的 fallback 設計
        for k, v in case.items()
        if v is not None and v != "" and k not in BASE_KEYS
    }
```

### Source of truth

| 來源 | 內容 | 維護者 |
|---|---|---|
| `streamlit_app.py:337-515` 的 `SLOT_LABELS` | 145 條 per-case-type slot 中文 label | vendor 110LLM 開發者 |
| `case_field_labels.py:BASE_LABELS` | 14 條 base 欄位（act_sub_class、caller_phone 等 SLOT_LABELS 沒涵蓋的） | 我們 |
| 對外 endpoint 回傳 | 兩者合併（159 條） | 我們 |

### 維護機制（你們問的「label 怎麼跟上 schema 演進」）

1. **vendor 新增 slot**：以後 vendor 在 `streamlit_app.py` 內 SLOT_LABELS 加新 entry 時，我們會手動同步到 `case_field_labels.py` 的 SLOT_LABELS（routine 任務、不影響你們）
2. **新增 base 欄位**：直接寫進 `case_field_labels.py` 的 BASE_LABELS
3. **endpoint 不必動**：自動 reload `case_field_labels.py` 即可（restart `nlp-api`）
4. **不存在的 key**：你們的 fallback `LABEL_MAP.get(k, k)` 保留英文 key，**完全不會 crash**，使用者體感最壞情況是看到一兩個英文 key、不會掉資料
5. **同步頻率**：我們 review schema 變動時順手做、預期不頻繁（vendor 不常加新案類）

### 注意事項

| 項目 | 說明 |
|---|---|
| `transcript` 欄位 | **不在 labels 內**（它是 `list of dict`、不是單值欄位，前端應另外處理） |
| 兩個 case 子類的 slot 重名 | 例 `a2_hit_and_run` 跟 `a3_hit_and_run` 都叫「肇事逃逸」— **是預期行為**，因為 key 不同、語意一致 |
| label 不會跟著 case 變化 | 這是 **schema metadata**、固定的；通話過程中也不會變、不必 re-fetch |
| 回應時間 | ~22 ms（純 dict 序列化，幾乎可忽略）|

### 對應改動的檔案（FYI）

- **新檔** `/home/aitop4/project/110llm/110LLM_0526_TW-110-Model_V3.0/case_field_labels.py`（159 entries）
- **改檔** `sop_api_server.py`：加 `from case_field_labels import LABELS as _CASE_FIELD_LABELS` + 新 endpoint `@app.get("/schema/case-fields/labels")`

任何欄位 mapping 看了奇怪、想改某個中文 label、或之後 vendor schema 變動需要同步，傳訊或寫進 `shared_with_A/`。
