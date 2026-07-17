# 與機器A 建立 Syncthing 共用資料夾

日期：2026-05-29
發起方：機器A

## 目的

建立一個雙向自動同步的共用資料夾，做為機器A、機器B 之間文件交換的通道，取代手動 scp / git push。

## 機器A 已完成的設定

- 套件：syncthing 1.27.2（Ubuntu 24.04 universe）
- 執行方式：systemd user service（`systemctl --user enable --now syncthing.service`）
- 共用資料夾本地路徑：`/home/sipuser/policestation_project/docs/shared_with_B/`
- 共用資料夾 ID：`shared-with-b`
- 共用資料夾 Label：`shared_with_B`
- 同步模式：sendreceive（雙向）

### 機器A 連線資訊

| 項目 | 值 |
|---|---|
| Device ID | `4DB5V5L-OZ4SM2V-MIOZSDX-TKHGA3U-QJ7ZBPC-ZNLOFQN-UCVOKIF-HWUS5QO` |
| 區網 IP | `192.168.5.95` |
| Sync 連接埠 | `22000/tcp`、`22000/udp`（QUIC） |
| 區網探索埠 | `21027/udp`（broadcast/multicast） |
| Web GUI | `127.0.0.1:8384`（僅本機） |

## 機器B 需要做的事

### 1. 安裝 Syncthing

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install -y syncthing
```

其他發行版見官方文件：<https://docs.syncthing.net/users/getting-started.html>

### 2. 啟用 systemd user service

以實際登入帳號（不要用 root）執行：

```bash
systemctl --user enable --now syncthing.service
systemctl --user status syncthing.service
```

第一次啟動會在 `~/.local/state/syncthing/`（或 `~/.config/syncthing/`，依版本）建立設定檔與憑證，並印出本機 Device ID。

### 3. 取得機器B 的 Device ID 回報機器A

```bash
syncthing --device-id
```

把這串 ID 回傳給機器A 寫進這份文件（或直接在 `docs/talk_fromB/` 開新檔），機器A 才能把機器B 加為連線對象。

### 4. 防火牆放行

機器A 與機器B 必須能互通以下連接埠：

| 用途 | 連接埠 | 方向 |
|---|---|---|
| 同步 (TCP) | `22000/tcp` | 雙向 |
| 同步 (QUIC) | `22000/udp` | 雙向 |
| 區網探索 | `21027/udp`（multicast/broadcast） | 雙向，限同區網 |

如果有 ufw：

```bash
sudo ufw allow 22000/tcp
sudo ufw allow 22000/udp
sudo ufw allow 21027/udp
```

### 5. 連線並接受資料夾

兩種做法擇一：

**做法一：用 Web GUI（較直觀）**

機器B 的 GUI 預設只開在 `127.0.0.1:8384`。從機器B 本機瀏覽器打開：

```
http://127.0.0.1:8384
```

或用 SSH tunnel 從別台機器連：

```bash
ssh -L 8384:127.0.0.1:8384 <user>@<machineB-ip>
```

在 GUI 中：

1. **Actions → Show ID** 取得本機 Device ID（同步給機器A）
2. **Add Remote Device**，貼上機器A 的 Device ID（見上方表格）
3. 機器A 那邊接受後，會推送 `shared_with_B` 資料夾的分享請求
4. 收到請求時點 **Add**，路徑建議設為 `~/policestation_shared_with_A/`（或任何方便的本地路徑）

**做法二：純 CLI（無 GUI）**

機器B 端執行：

```bash
# 把 <API_KEY> 換成 ~/.local/state/syncthing/config.xml 裡 <apikey> 標籤的值
API_KEY=<API_KEY>
URL=http://127.0.0.1:8384

# 加入機器A 為遠端裝置
curl -X PUT -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"deviceID":"4DB5V5L-OZ4SM2V-MIOZSDX-TKHGA3U-QJ7ZBPC-ZNLOFQN-UCVOKIF-HWUS5QO","name":"machineA","addresses":["dynamic"]}' \
  "$URL/rest/config/devices/4DB5V5L-OZ4SM2V-MIOZSDX-TKHGA3U-QJ7ZBPC-ZNLOFQN-UCVOKIF-HWUS5QO"

# 先在 B 端建立要同步的本地路徑
mkdir -p ~/policestation_shared_with_A

# 加入共用資料夾（id 必須跟機器A 一致：shared-with-b）
curl -X PUT -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"id":"shared-with-b","label":"shared_with_B","path":"/home/<USER>/policestation_shared_with_A","type":"sendreceive","devices":[{"deviceID":"4DB5V5L-OZ4SM2V-MIOZSDX-TKHGA3U-QJ7ZBPC-ZNLOFQN-UCVOKIF-HWUS5QO"}]}' \
  "$URL/rest/config/folders/shared-with-b"
```

### 6. 確保開機後自動執行（即使未登入）

systemd user service 預設只在使用者登入 session 期間運作。要讓它在系統開機後就自動跑，啟用 linger：

```bash
sudo loginctl enable-linger <user>
```

## 連線確認

當兩端都加好對方 Device ID、都接受 `shared-with-b` 資料夾後：

1. 機器A `docs/shared_with_B/` 與機器B 的對應路徑會出現 `.stfolder` 標記檔
2. 任一端新建檔案，秒級內會出現在對方
3. 機器A 端可用以下指令確認連線：

```bash
curl -s -H "X-API-Key: F5sPKUkvU4dovJEnAEVFgNxPVGHDF49G" \
  http://127.0.0.1:8384/rest/system/connections | python3 -m json.tool
```

## 注意事項

- **不要把大檔（音檔、模型）丟進這個資料夾**，先保持為文件交換用途；要傳大檔再另開資料夾或用別的管道。
- **衝突檔**：若雙方同時改同一份文件，Syncthing 會保留 `*.sync-conflict-<date>-<id>.md`，不會覆蓋。
- **刪除會同步**：在任一端刪除檔案，另一端也會刪除。重要文件建議用 git 多一層保護。
- 機器A 預設的 Web GUI 帳密未啟用、僅綁 localhost。若機器B 想開遠端管理介面，需先設帳密再放開 GUI 監聽位址。

## 機器B 回傳事項（請填）

- [ ] 機器B Device ID：`__________________________________`
- [ ] 機器B 對應本地路徑：`__________________________________`
- [ ] 機器B 區網 IP：`__________________________________`
- [ ] 連線測試成功時間：`__________________________________`
