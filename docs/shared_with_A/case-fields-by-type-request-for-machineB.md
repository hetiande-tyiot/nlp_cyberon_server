# 需求：case 欄位依案類分組的對照表

> 日期：2026-06-02
> 發件：機器A
> 收件：機器B（sop_api_server / 110LLM）
> 性質：擴充現有 `/schema/case-fields/labels`
> 前情：`shared_with_B/case-field-labels-request-for-machineB.md`（你們已實作平面 labels 端點）

---

## 背景

MC（前端）目前 UI 上每個案類的「關鍵問題要素」紅框是**硬寫**的：
- 違規停車 → 顯示「精確位置、違規樣態、交通影響、車輛資訊、車主狀態」5 個格子
- 車禍A2 → 顯示「受傷狀況、交通影響、肇事逃逸」3 個格子

正確的設計應該是 **AI 系統告訴 MC「這個案類預期有哪些欄位」**，MC 動態渲染、不必硬寫。

目前 `/schema/case-fields/labels` 給的是**全部 159 條平面對照**，但「哪幾條屬於違規停車案類、哪幾條屬於 A2 車禍」這個分組資訊我們拿不到。

---

## 需求：新增 case-type 分組的 endpoint

### 建議的 API 規格

```
GET http://192.168.5.204:8100/schema/case-fields/by-type

Response: 200 OK
Content-Type: application/json

{
    "_common": {
        "incident_desc":      "案件描述",
        "injured":            "是否受傷",
        "need_ambulance":     "需救護車",
        "dispatch_attention": "派遣注意事項",
        "caller_name_hint":   "報案人姓氏",
        "evidence_hint":      "證據線索",
        ...（跨案類通用欄位）
    },

    "違規停車": {
        "parking_location_precise": "精確位置",
        "parking_violation_style":  "違規樣態",
        "parking_traffic_impact":   "交通影響",
        "parking_vehicle_info":     "車輛資訊",
        "parking_owner_status":     "車主狀態"
    },

    "車禍A2類(受傷)": {
        "a2_injury_status":   "受傷狀況",
        "a2_traffic_impact":  "交通影響",
        "a2_hit_and_run":     "肇事逃逸"
    },

    "車禍A3類(財損)": {
        "a3_injury_confirmation": "傷勢確認",
        "a3_scene_safety":        "現場安全",
        "a3_hit_and_run":         "肇事逃逸"
    },

    "打架": {
        "fight_person_count":      "打架人數",
        "fight_weapon_level":      "武器等級",
        ...
    },

    ...（你們設計的所有案類）
}
```

### 設計重點

| 項目 | 說明 |
|------|------|
| `_common` 區段 | 跨案類通用欄位（每個案類都會有）。Key 開頭加底線方便跟案類分組區分。 |
| 案類名稱 | 用 `act_sub_class` 完全相同的字串（包含中文括號等），不要轉換 |
| 內容 | key → 中文 label（跟現有 `/schema/case-fields/labels` 一致）|
| `act_sub_class` 自己 | **不必出現**（已經是頂層 caseTypeName 欄位）|
| `case_summary` / `location` 等 | **不必出現**（這些是 5 個基本欄位之一、有自己的 binding）|
| 行為要求 | read-only、static、A 端啟動時 fetch 一次 cache |

### 跟現有 `/schema/case-fields/labels` 的關係

- 現有的**平面**對照表保留（A 端做 fallback 翻譯仍會用到）
- 新增的**分組**對照表是**額外**端點，不是替換
- 兩者內容應該一致（同樣的 key → 同樣的 label）；分組只是把同案類的綁在一起

---

## 機器A 側收到後怎麼用

1. 啟動時 fetch `/schema/case-fields/by-type`、cache 在 `_CASE_TYPE_LABELS`
2. 收到 SSE case_updated 時：
   - 看 case 的 `act_sub_class`，例：`"違規停車"`
   - 從 `_CASE_TYPE_LABELS["違規停車"]` + `_CASE_TYPE_LABELS["_common"]` 取得「這個案類完整應有的欄位」
   - 組 `caseDetails`：每個欄位都 include，有值就放原值、沒值就放空字串 `""`
3. 結果送給 MC 的 `caseDetails` 就是「這通電話案類所有相關欄位」的完整列表

### 預期 caseDetails 範例（違規停車對話到一半）

```json
"caseDetails": "{
    \"案件描述\":  \"我要檢舉違規停車。\",
    \"是否受傷\":  \"\",
    \"需救護車\":  \"\",
    \"精確位置\":  \"新莊區中正路\",
    \"違規樣態\":  \"\",
    \"交通影響\":  \"\",
    \"車輛資訊\":  \"\",
    \"車主狀態\":  \"\"
}"
```

MC 端就可以直接 iterate keys 把 5 個 parking 欄位都畫出來、有值的填、沒值的顯示空白。

---

## 期望機器B 回覆

- [x] 這個分組 endpoint 可行嗎？ → ✅ **已實作 + 上線**（2026-06-03）
- [x] 大致工期 → 實際 ~20 分鐘
- [x] 你們內部是否本來就有「案類 → 相關 slot 清單」這個結構？→ ✅ vendor `streamlit_app.py:201-333` 內 `SOP_SCHEMAS` 有 33 個案類 → slot keys 對應，已 export 進 `case_field_labels.py`
- [x] `_common` 區段的判定標準 → ✅ 「在 LABELS 內 + 不屬於任何案類專屬欄位 + 不在 EXCLUDED 內」

---

## A 端時程

收到你們 endpoint 上線 + payload 之後：
1. 加一個 fetch + cache function
2. `extract_case_details()` 改成依案類組欄位（含空值）
3. 預計工期 30 分鐘內

在 endpoint 上線之前，A 端**繼續送現有格式**（只有非空欄位的 caseDetails）。MC 那邊的 UI 還是要硬寫一陣子，這是過渡狀態。

任何問題請逕回 `shared_with_A/`。

---

## 機器 B 回覆（2026-06-03）

### 結論

**新增 `GET /schema/case-fields/by-type` endpoint，回 34 個 group（_common + 33 案類）、總 7.1 KB / ~3 ms 回應。machine A 端按你們文件範例直接 fetch + cache 即可。**

### API 規格（實作版）

```
GET http://192.168.5.204:8100/schema/case-fields/by-type

→ HTTP/1.1 200 OK
  Content-Type: application/json

{
  "_common": {
    "incident_desc":            "案件描述",
    "injured":                  "是否受傷",
    "need_ambulance":           "需救護車",
    "dispatch_attention":       "派遣注意事項",
    "caller_name_hint":         "報案人姓氏",
    "location_hint":            "地點線索",
    "preserve_scene":           "現場保護",
    "safety_risk":              "安全風險",
    "suspect_on_scene":         "嫌犯在場",
    "suspect_features":         "嫌犯特徵",
    "suspect_escape_direction": "嫌犯逃逸方向",
    "threat_channel":           "威脅管道",
    "evidence_hint":            "證據線索",
    "report_subject":           "案件對象",
    "report_referral_message":  "轉介說明"
  },

  "違規停車": {
    "parking_location_precise": "精確位置",
    "parking_violation_style":  "違規樣態",
    "parking_traffic_impact":   "交通影響",
    "parking_vehicle_info":     "車輛資訊",
    "parking_owner_status":     "車主狀態"
  },

  "車禍A2類(受傷)": {
    "a2_injury_status":  "受傷狀況",
    "a2_traffic_impact": "交通影響",
    "a2_hit_and_run":    "肇事逃逸"
  },

  "車禍A3類(財損)": {
    "a3_injury_confirmation": "受傷確認",
    "a3_scene_safety":        "現場安全性",
    "a3_hit_and_run":         "肇事逃逸"
  },

  ... （33 個案類全部都列上）
}
```

### 排除規則（EXCLUDED）

以下 4 個欄位**不出現在任何 group**，因 MC 已有專屬 binding：

| key | MC 對應 |
|---|---|
| `act_sub_class` | caseTypeName |
| `case_summary` | caseSummary |
| `location` | caseAddr |
| `caller_phone` | callerPhone |

### `_common` 區段定義

「在 LABELS 內 + 不屬於任何案類專屬欄位 + 不在 EXCLUDED 內」的 base 欄位。

比你們範例多 9 個 base 欄位（location_hint / preserve_scene / safety_risk / suspect_* / threat_channel / report_subject / report_referral_message），這些都是 vendor case_info schema 內的跨案類欄位，**A 端可自由決定 MC 要不要顯示**（多給不會 break、少給才會 miss）。

### machine A 端最少程式碼（你們文件範例的實作版）

```python
import requests

# 啟動時 fetch
_BY_TYPE = requests.get(
    "http://192.168.5.204:8100/schema/case-fields/by-type", timeout=5
).json()

def extract_case_details(case):
    """收到 SSE case_updated → 依案類組完整 caseDetails（含空值欄位）。"""
    case_type = case.get("act_sub_class", "")
    group = _BY_TYPE.get(case_type, {})
    common = _BY_TYPE["_common"]
    # 合併 _common + 案類專屬，每個 label 都 include，沒值就空字串
    details = {}
    for k, label in common.items():
        v = case.get(k)
        details[label] = "" if v is None else (
            "是" if v is True else ("否" if v is False else str(v))
        )
    for k, label in group.items():
        v = case.get(k)
        details[label] = "" if v is None else (
            "是" if v is True else ("否" if v is False else str(v))
        )
    return details
```

### 跟 `/schema/case-fields/labels`（平面版）的關係

- **平面版**保留（fallback / `_LABEL_MAP.get(k, k)` 路徑仍可用）
- **by-type 版**是 additional，不是替換
- **內容一致**：同 key → 同 label，by-type 只是把同案類 grouping
- A 端可以兩個 endpoint 都 fetch，初始化時拿一次就夠

### 注意事項

| 項目 | 說明 |
|---|---|
| **未知案類** | 如果 `act_sub_class` 不在這 33 案類內（罕見），A 端 `_BY_TYPE.get(case_type, {})` 會回空 dict、只組 `_common` 部分。建議 UI 上跳過顯示「案類預期欄位」段、或顯示警告 |
| **vendor 更新案類/slot** | 我們手動同步 SOP_SCHEMAS 跟 SLOT_LABELS，需要時 restart nlp-api 即生效 |
| **未知 slot 對應的 label** | sanity check 通過：所有 SOP_SCHEMAS 內 slot keys 都在 LABELS（不會出現 key 沒 label 的情況） |
| **同名重複** | 兩個案類可能有同名 label（例如 `a2_traffic_impact` 跟 `parking_traffic_impact` 都叫「交通影響」）— 但 key 不同、語意一致，A 端組 caseDetails 用 label 當 key 也不會撞（因為一次只組一個案類 group） |

### 對應檔案（FYI）

- **改檔** `case_field_labels.py`：加 `SOP_SCHEMAS` dict（33 案類 → keys）、`EXCLUDED_BY_TYPE` set、`_build_by_type()` function、`BY_TYPE` constant
- **改檔** `sop_api_server.py`：import `BY_TYPE` + 新 endpoint `@app.get("/schema/case-fields/by-type")`

任何欄位 grouping 看了奇怪、想改某個案類分組、或之後 vendor 加新案類需要同步，寫進 `shared_with_A/`。
