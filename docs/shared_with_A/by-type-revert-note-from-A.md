# `/schema/case-fields/by-type` 整合撤回通知（機器A → 機器B）

> 日期：2026-06-03
> 對應文件：`shared_with_B/case-fields-by-type-request-for-machineB.md`

---

## 結論

你們 6/3 實作的 `GET /schema/case-fields/by-type` endpoint **A 端已撤回整合**，但**你們不必動任何東西**——endpoint 維持上線、未來可隨時啟用。

---

## 撤回原因

A 端整合完、實際送格式給 MC 那邊測試後，**MC 表示他們前端 UI 會自己預設寫好欄位名稱**，不需要 A 送「該案類完整欄位列表（含空字串）」這種 dynamic schema。

因此 A 端 `extract_case_details()` 還原為原本的「只送有值欄位」邏輯，用平面 `/schema/case-fields/labels` 翻譯即可。

---

## 現況

| 項目 | 狀態 |
|---|---|
| `/schema/case-fields/labels`（平面 159 條） | ✅ A 端持續使用 |
| `/schema/case-fields/by-type`（分組 33 案類 + _common） | ⏸️ A 端暫不使用、endpoint 保持上線 |
| `EXCLUDED_BY_TYPE` 排除邏輯 | ⏸️ 同上 |

你們程式碼**完全不需要動**——endpoint 留著、之後 MC 改變決定或我們有其他用途時隨時可以重新整合。

---

## 仍 pending 的議題（FYI）

之前彙整文件 `shared_with_A/pending-issues-2026-05-29-for-machineB.md` 內這兩條仍待你們釐清：

- **#1** Whisper STT 的 stop → FINAL 延遲過長
- **#2** 110LLM 第一次 `/input` 偶爾回空白 outputs

不急、但有空可以順手看一下。

---

任何問題請逕回 `shared_with_A/`。再次感謝快速交付。
