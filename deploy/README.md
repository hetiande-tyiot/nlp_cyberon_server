# 在新電腦上安裝這個專案

程式碼走 git、模型/憑證走 scp(rsync)，兩條管道。理由見根目錄 `.gitignore`：
venv 1.9G、gguf 19.5G、BERT 權重各 391M，這些不能也不該進 git。

## 檔案分類一覽

| 類別 | 怎麼來 | 內容 |
|---|---|---|
| 程式碼、設定、小型資料 | `git clone` | `ai/119_*/`（含 scripts/tests/xlsx/csv）、`docs/`、BERT 的 config/label_map/tokenizer、STT/TTS 的 server 程式 |
| 模型權重、憑證、語者音檔 | `install_on_new_machine.sh` 自動抓，或 `push_nongit.sh` 推 | 見 `deploy/nongit_manifest.txt` |
| venv (`llmenv/`) | 目標機重建 | `requirements-119.txt` + 自行編譯 llama-cpp-python |
| `log_119/` | 目標機建空目錄 | 執行期產出 |
| `/etc/systemd/system/sop119.service` | 由 `sop119.service.template` 產生 | 不在 repo 內（系統路徑） |

不用傳的：`__pycache__/`、`*.pyc`、`*.zip` 備份、`ai/TW-119-BERT-sub_*_{bak,v2,v5,new_2}/` 舊模型快照、
`ai/TTS-F5/output_*/` 測試輸出。

## 最省事的做法：在新電腦上跑一支腳本

把 `install_on_new_machine.sh` 這**一個檔案**帶到新電腦（隨身碟、scp、或直接從 GitHub 抓），
其餘它自己處理：clone 程式碼 → 抓模型 → 建 venv → 裝服務。

```bash
# 在新電腦上
scp cyberon2@100.127.225.115:~/nlp_cyberon_server/deploy/install_on_new_machine.sh .
bash install_on_new_machine.sh --cuda-arch 120 --install-service
```

模型預設從 cyberon2 用 rsync 拉（需要新電腦能 SSH 進 cyberon2，連不上時腳本會告訴你怎麼辦）。

常用選項：

| 選項 | 用途 |
|---|---|
| `--from-dir /media/usb/nlp` | 模型改從隨身碟／外接硬碟複製，不走網路 |
| `--skip-files` | 先把環境弄好，模型晚點再補（或改由來源機推送） |
| `--all` | 連 STT／TTS／110 的模型一起（約 44G，預設只抓 119 要的 21G） |
| `--cuda-arch 120` | 照顯卡編 GPU 版 llama-cpp-python（5090=120、4090=89） |
| `--install-service` | 裝 systemd 服務（會要 sudo 密碼） |
| `--dest /path` | 專案裝到別的位置（預設 `~/nlp_cyberon_server`） |

中途斷線直接重跑同一行指令就好：已經完成的步驟會跳過，傳一半的大檔會續傳。

## 另一種：從來源機推過去

新電腦沒辦法 SSH 進 cyberon2 時（例如金鑰只設了單向），改成從 cyberon2 推：

```bash
# 在新電腦
git clone https://github.com/hetiande-tyiot/nlp_cyberon_server.git ~/nlp_cyberon_server

# 在 cyberon2
cd ~/nlp_cyberon_server
deploy/push_nongit.sh <user>@<新電腦IP> --dry-run    # 先看會傳什麼、多大
deploy/push_nongit.sh <user>@<新電腦IP>

# 回到新電腦
cd ~/nlp_cyberon_server
bash deploy/install_on_new_machine.sh --skip-files --cuda-arch 120 --install-service
```

## 裝完的確認

```bash
bash deploy/setup_new_machine.sh --check          # 逐項列出有／缺
sudo systemctl start sop119.service
curl -s http://127.0.0.1:8200/health              # 三個 loaded 都 true 才算成功
journalctl -u sop119.service -f                   # 起不來看這裡
```

`--install-service` 預設抓 `ai/` 底下最新的 `119_*` 當版本目錄，要指定用 `--version 119_0904_addrflow`。
`ADDRCHECK_API_TOKEN` 沒帶的話 unit 裡會留「請自行填入」，記得手動補上再 `systemctl daemon-reload`。

腳本不會自動 restart 既有服務 —— 119 是緊急服務，重啟前先 `curl /health` 確認 `sessions=0`。

## 維護

模型換版、新增檔案時，記得同步更新 `deploy/nongit_manifest.txt`，
不然新機器會少檔案而且沒人發現（`--check` 就是靠這份清單）。
