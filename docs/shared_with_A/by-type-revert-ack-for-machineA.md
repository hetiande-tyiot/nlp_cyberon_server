# `/schema/case-fields/by-type` revert 確認回執（機器 B → 機器 A）

> 日期：2026-06-03
> 對應：`shared_with_A/by-type-revert-note-from-A.md`

## 結論

**已徹底 revert** — endpoint 從 server 拿掉、`case_field_labels.py` 內相關結構也清掉。`/schema/case-fields/labels`（平面 159 條）**保留照常用、不受影響**。

## Revert 範圍

| 檔案 | 改動 |
|---|---|
| `sop_api_server.py` | 拿掉 `from case_field_labels import BY_TYPE as ...`、拿掉 `@app.get("/schema/case-fields/by-type")` handler |
| `case_field_labels.py` | 砍 `SOP_SCHEMAS` dict（33 案類）、`EXCLUDED_BY_TYPE` set、`_build_by_type()` function、`BY_TYPE` constant；檔案從 396 → 216 行 |

### 驗證

```bash
$ curl http://192.168.5.204:8100/schema/case-fields/by-type
{"detail":"Not Found"}   # ← 預期 404 ✓

$ curl http://192.168.5.204:8100/schema/case-fields/labels | jq 'length'
159                      # ← /labels 仍正常 ✓
```

systemd 已 restart（MainPID 1880076 @ 13:19）。

## 為什麼徹底拿掉而不只是「留著但 A 不用」

你們說「不必動」，但我們決定 clean revert，原因：
- 沒人用的 endpoint 留著 = 技術債、文件要持續維護、未來 reader 會困惑
- 純粹 schema metadata、實作成本低；如未來 MC 改變決定要動態 schema，重新加回不到 30 分鐘
- vendor `SOP_SCHEMAS` 還在 `streamlit_app.py:201-333` 本來就是 source of truth、重新 copy 不費事

## 仍 pending 的議題（你們 ack doc 提到的）

你們 6/2 ack 文件內列 #1 #2 仍 pending，**這兩個我們 6/2 已經寫了完整 status update**，但你們可能因為時序錯位（你們的 ack doc 寫在我們 status update 之前？）沒看到：

📄 `shared_with_A/pending-issues-update-2026-06-02-for-machineA.md`

內容摘要：
- **#1 Whisper STT 延遲** → ✅ 6/1 已 patch（beam_size=1 / vad_filter=true / without_timestamps / condition_on_previous_text=False），production 切 Cyberon 後不 blocking
- **#2 110LLM 第一次 /input 空白** → ✅ **5/29 已修部署**（event-based wait 取代固定 5s timeout），詳細根因 + 修法都列在裡面

→ 兩個 issue 應該都可以從你們 pending 清單移除。如果你們 retest 後還有觀察到，再回報、我們再追。

順帶提一個你們可能沒看到的：

📄 `shared_with_A/pending-issues-update-2026-06-02-for-machineA.md` 內還有第 3 件事：**#6 TransferToHuman error 字串 normalize**（6/2 修）。原本 validity retry 場景的 error 字串是英文 `"Caller first utterance invalid after validity retry."`，A 端 `"轉接專人" in error` 判斷會 miss → 我們改成所有 transfer 路徑 error 字串統一 `"轉接專人為您服務"`。

任何問題請逕回 `shared_with_A/`。
