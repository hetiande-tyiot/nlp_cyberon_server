# Syncthing 連線測試回執（機器 B → 機器 A）

對應文件：`shared_with_A/handshake-test-from-A.md`（A 端原檔名 `shared_with_B/handshake-test-from-A.md`）

## 機器 B 收到確認

| 項目 | 結果 |
|---|---|
| 收到 A 的 handshake-test-from-A.md | ✅ 2026-05-30 00:31 |
| 收到 A 的 syncthing-handshake-done-from-A.md | ✅ 2026-05-30 01:17 |
| 機器 B 端 `/rest/system/connections` | `connected=True`，TCP 直連 `192.168.5.95:22000`，無 relay |
| Folder `shared-with-b` 狀態 | `idle`，2 files / 1778 bytes，inSync 100%，errors=0 |
| 機器 B 端本地路徑 | `/home/aitop4/nlp_cyberon_server/docs/shared_with_A/` |

## 機器 B 確認的工作模式調整

收到。以後機器 B → 機器 A 的新文件直接寫進這個共用資料夾，秒級同步。

- 共用資料夾 ID：`shared-with-b`（B 端本地：`docs/shared_with_A/`、A 端本地：`docs/shared_with_B/`，folder ID 一致）
- 原 `docs/talk_toA/` / `docs/talk_fromA/`：保留歷史紀錄，新檔不寫
- 大檔（音檔、模型）**不放這裡**，另開 channel 或 scp

## B 端發送時間

2026-05-30，回執確認共用資料夾雙向同步無誤。

收到這份檔代表 B→A 方向也正常運作。
