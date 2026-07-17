# Syncthing 設定回報（機器 B → 機器 A）

> 對應文件：[`talk_fromA/syncthing-setup-for-machineB.md`](../talk_fromA/syncthing-setup-for-machineB.md)
> 日期：2026-05-29

## 機器 B 端已完成

| 項目 | 值 |
|---|---|
| 套件 | `syncthing v1.27.2-ds4`（Ubuntu apt） |
| 執行方式 | `systemctl --user enable --now syncthing.service`（active + enabled） |
| 開機自動跑 | `loginctl enable-linger aitop4`（Linger=yes） |
| 共用資料夾 ID | `shared-with-b`（跟 A 端一致） |
| 共用資料夾 Label | `shared_with_B` |
| 同步模式 | `sendreceive`（雙向） |
| 防火牆 | 機器 B 端無 ufw active（不必開 port） |

## 機器 B 連線資訊（請寫進你們設定）

| 項目 | 值 |
|---|---|
| **Device ID** | `S7YUY56-JXJWJXD-YCS374C-6DA3YLK-ERI7SRU-QUJBQLV-KOHZZ6N-NOA4MAB` |
| **本機路徑** | `/home/aitop4/nlp_cyberon_server/docs/shared_with_A/` |
| **區網 IP** | `192.168.5.204` |
| Sync TCP/UDP | `22000`（listening） |
| 區網探索 | `21027/udp`（listening） |
| Web GUI | `127.0.0.1:8384`（僅本機） |

## 機器 B 端動作摘要

1. 已用 REST API 把 **機器 A Device ID `4DB5V5L-OZ4SM2V-MIOZSDX-TKHGA3U-QJ7ZBPC-ZNLOFQN-UCVOKIF-HWUS5QO`** 加為遠端裝置
2. 已加入 folder `shared-with-b`，devices 含 A + B 兩端
3. 已 verify 設定寫入（`/rest/config/folders/shared-with-b` 回 200）

## 接下來請機器 A 端做

1. 在 A 端 syncthing GUI 或 REST API **接受機器 B Device ID `S7YUY56-...`**
2. A 端接受後雙向 handshake，雙方會看到 `connected=True`
3. A 端在 `/home/sipuser/policestation_project/docs/shared_with_B/` 建任意檔案測試
4. 機器 B 端會在 `/home/aitop4/nlp_cyberon_server/docs/shared_with_A/` 秒級內收到該檔
5. **回報連線時間**（隨意，例如貼一張 GUI 截圖、或 curl `/rest/system/connections` 顯示 `connected=True` 的時間）

## 命名差異 FYI

機器 A 文件建議的路徑是 `~/policestation_shared_with_A/`，機器 B 端選擇用 `~/nlp_cyberon_server/docs/shared_with_A/`，**整合進現有 docs/ 結構並列管理**（跟 `docs/talk_fromA/` / `docs/talk_toA/` 同層）。folder ID `shared-with-b` 保持一致，協定不受影響。

## 確認連線指令（機器 B 端可隨時跑）

```bash
API_KEY=$(grep -oP '(?<=<apikey>)[^<]+' ~/.local/state/syncthing/config.xml | head -1)
curl -s -H "X-API-Key: $API_KEY" http://127.0.0.1:8384/rest/system/connections \
  | python3 -m json.tool | head -30
```

→ 看到機器 A 那行 `"connected": true` 即代表連線成功。

## 連線測試成功時間

- 機器 B 端設定完成：**2026-05-29**
- 機器 A 接受 B device + 第一次同步成功：**2026-05-30 00:31**（收到 A 端的 `handshake-test-from-A.md`）
- B→A 方向回測：**2026-05-30**（B 端寫 `shared_with_A/handshake-test-from-B.md`，A 端應秒級內收到）
- 之後新檔交換直接寫共用資料夾 `shared-with-b`，本 `talk_toA/` 保留歷史紀錄

任何問題傳訊給機器 B 端負責人。
