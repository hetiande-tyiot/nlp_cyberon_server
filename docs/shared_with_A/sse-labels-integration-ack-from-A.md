# SSE + Labels 整合完成回執（機器A → 機器B）

> 日期：2026-06-02
> 對應前次需求：
>   - `shared_with_B/sse-push-request-for-machineB.md`（SSE 推送）
>   - `shared_with_B/case-field-labels-request-for-machineB.md`（label 端點）

---

## 結論

機器A 端**已整合上線、端對端 MC 串通成功**。感謝你們 6/1 和 6/2 兩天連續實作 + 30 分鐘交付的效率。

---

## 已整合的內容

### 1. SSE 推送

- 機器A `amidaemon` 啟動 `sse_consumer.py`，每通電話建立後即時連到 `GET /session/{sid}/case/stream`
- 收到 `case_updated` → dedup → 推 Analysis(Initial/Updated) 給機器C
- 收到 `done` → 推 Analysis(Final) 給機器C、SSE thread 自然結束
- amidaemon Hangup 時設 `stop_event`（雙保險，但通常 B 自己會關連線、不會用到）
- 不再走每輪 `/result` polling（雖然該邏輯保留向下相容、給 db.save_case 在 done 時用）

### 2. Labels 對照表

- amidaemon 啟動時 fetch 一次 `GET /schema/case-fields/labels` → 載入 159 條
- cache 在 `machinec_client._LABEL_MAP`，整個 process 共用
- `extract_case_details()` 用 `_LABEL_MAP.get(k, k)` 翻譯（沒對應就保留英文 key）
- 失敗時印 warning、保持空 dict、所有欄位回 fallback 用英文 key（**不會掉資料**）

### 3. 串通機器C 的踩坑紀錄（給你們參考）

MC 端是 ASP.NET Core，他們有兩個額外要求踩過：

| 規格 | 為什麼 |
|------|--------|
| `caseDetails` 必須是 **JSON 字串**，不是 nested object | ASP.NET model binding 把 caseDetails 綁成 `string` 屬性 |
| `caseDetails` 內所有 value 必須是 **string** | MC 端 validator 不收 boolean / number |
| 我們解法：boolean 用 `"是"`/`"否"`、其他 `str(v)` | 維持語意 + 符合規格 |

最終送出範例：

```json
{
    "callId":        "uuid",
    "caseTypeName":  "車禍A2類(受傷)",
    "caseAddr":      "板橋區福州橋",
    "caseSummary":   "...",
    "callerPhone":   "",
    "analysisState": "Updated",
    "caseDetails":   "{\"案件描述\":\"我這裡發生車禍。\",\"是否受傷\":\"是\",\"受傷狀況\":\"...\",\"交通影響\":\"...\",\"肇事逃逸\":\"另一方在場\"}"
}
```

---

## 目前 pending 議題清單（你們之前回過的）

- ✅ Issue #3 `/result` 對話中回 partial case（6/1 實作）
- ✅ Issue #4 SSE 推送（6/1 實作）
- ✅ Issue #5 中文 label 對照表（6/2 實作）
- ⏳ Issue #1 Whisper STT stop → FINAL 延遲（仍待你們評估）
- ⏳ Issue #2 110LLM 第一次 `/input` 偶爾回空白 outputs（仍待釐清根因）

如果有空可以順手回 #1 跟 #2，文件在 `shared_with_A/pending-issues-2026-05-29-for-machineB.md`。
（測試時我們目前切回 Cyberon STT，Whisper 議題沒在阻塞，但確認下還是好的。）

---

任何事直接寫進 `shared_with_A/` 就好。Syncthing 通道運作良好、辛苦了。
