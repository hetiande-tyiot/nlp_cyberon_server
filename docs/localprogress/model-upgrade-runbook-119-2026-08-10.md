# 119 智能報案系統 — 升級 runbook（草稿）

> **狀態：Claude 起草，2026-08-10，未經審閱。** 依 0724→0808 換版的實作經驗改寫為不分機器的通用流程。
> 現行權威文件仍是 `model-upgrade-runbook-119.md`；本檔審過後再決定是否取代它。
> 適用：**任何一台跑 119 的機器**（開發機 cyberon2、部署機 aitop6，或未來新增的）。
> 每一步以「條件」判斷該不該做，不以機器身分區分；條件不成立就跳過。

## 0. 不變原則

| 原則 | 意義 |
|---|---|
| **不動 vendor 上游檔** | `sop_119_engine.py`／`case_info_119.py`／`inference_pipeline.py`／`classifier_with_llm.py`／`llm_extractor_119.py`／`sop_utils_119.py`／`location_validation_119.py`／`important_tags_119.py`／`handlers/*`／`tests/*` 視為 vendor code，只讀不改 |
| **客製集中在 `sop_api_server.py`** | server-only 入口檔，不在開發者的 Streamlit release 裡。所有 endpoint、log 寫檔、queue bridge 都在這 |
| **API 合約零變動** | endpoint path／payload／response 結構維持，機器 A client 一行都不必改 |
| **env var 控旋鈕** | 模型路徑、device、外部 API 全走 env var；改 systemd `Environment=` 不必動程式碼 |
| **`llmenv/` 全版本共用** | service 只換 `WorkingDirectory`，Python 環境不隨版本切換 |

## 1. 架構速覽

- **線上服務**：systemd `sop119.service`，uvicorn 跑 `sop_api_server:app` on `0.0.0.0:8200`
- **`WorkingDirectory`** = 當前版本目錄（`ai/119_{date}_{tag}/`），換版就是換這個值
- **venv**：`<repo>/llmenv/`（Python 3.12），與版本目錄無關
- **機器角色**：cyberon2 = 開發主力（192.168.5.132），新版在此組裝與驗證；aitop6 = 部署目標，經 git push 收成品（見 memory `deploy-aitop6-tailscale`）
- ⚠️ **204／aitop4 是 110 系統，與 119 無關**，別走錯機器

service 環境變數：

| env | 值 | 控制 |
|---|---|---|
| `GGUF_MODEL_PATH` | `<repo>/models/TW-119-Model.gguf` | LLM 抽取模型 |
| `BERT_MODELS_BASE` | `<repo>/ai/` | BERT 主／子分類器根目錄 |
| `BERT_DEVICE` | `cpu` | BERT 運算裝置（VRAM 留給 gguf） |
| `LOG_DIR` | `<repo>/log_119` | 案件 JSON log |
| `JURISDICTION_API_URL` | `http://61.216.64.19:8055/Template/Office/data` | 地址轄區校驗（0808 起） |
| `JURISDICTION_API_TIMEOUT` | `2.5` | 同上，秒 |

## 2. 開始前：先確認你在哪

```bash
hostname; systemctl show sop119.service -p WorkingDirectory --value   # 現行版本
curl -s http://127.0.0.1:8200/health                                   # 三個 loaded 應皆 true
```

以下 `$REPO` = repo 根目錄、`$PY` = `$REPO/llmenv/bin/python`、`$SRC` = 現行版本目錄、`$DST` = 新版目錄。

---

## 3. 換版流程

### A — 取得新版程式

**條件：新版目錄還不存在。**

- 開發機：開發者交付的壓縮檔解到 `$REPO/ai/119_{date}_{tag}/`
- 其他機：`git pull`（模型不走 git；gguf／BERT 有換才另外 rsync）

**解完立刻檢查有沒有多包一層同名目錄**（0808 踩過）：

```bash
ls $DST     # 若只看到一個跟 $DST 同名的資料夾，就是包了兩層
cd $DST && git mv 119_xxx/* . && rmdir 119_xxx     # 未進 git 時用 mv
find $DST -name __pycache__ -type d -exec rm -rf {} +
```

### B — 判斷 `sop_api_server.py` 能不能直接沿用

**條件：`$DST` 缺 `sop_api_server.py`（幾乎每次都缺）。**

先盤點缺什麼、vendor 改了多少：

```bash
cd $REPO/ai
comm -23 <(ls -1 $SRC|grep -v __pycache__|sort) <(ls -1 $DST|sort)   # 舊有新缺 → 要補
comm -13 <(ls -1 $SRC|grep -v __pycache__|sort) <(ls -1 $DST|sort)   # 新增檔
for f in $DST/*.py; do b=$(basename $f); n=$(diff $SRC/$b $f 2>/dev/null|grep -cE '^[<>]'); [ "$n" != "0" ] && echo "$b: $n 行"; done
```

再驗耦合面。`sop_api_server.py` 只透過這些符號碰引擎，**任一條命中就是重寫，不是複製**：

| 檢查 | 命中代表 |
|---|---|
| `SopEngine119.__init__` 參數增減／改名 | 建構呼叫要改 |
| `run()` 改回吃參數，或終止方式從 exception 改成回傳值 | `_run_engine()` 要改 |
| `DialogueIO` 新增抽象方法 | `QueuedIO119` 起不來（`TypeError`），**最易漏，它是繼承關係、不在 import 清單裡** |
| `END_FLOW_SENTINEL` 消失或強制結束機制改掉 | `/hangup` 要重寫 |
| `to_dict()` 消失或改巢狀 | `/result` 形狀變 → 破 API 合約 |
| 輸出 event 型別改名／改結構 | `/input` 的 `outputs` 過濾要改 |

```bash
diff <(sed -n '/class SopEngine119/,/debug: bool/p' $SRC/sop_119_engine.py) \
     <(sed -n '/class SopEngine119/,/debug: bool/p' $DST/sop_119_engine.py)   # 應無輸出
diff <(sed -n '/^class DialogueIO/,/^END_FLOW_SENTINEL/p' $SRC/sop_119_engine.py) \
     <(sed -n '/^class DialogueIO/,/^END_FLOW_SENTINEL/p' $DST/sop_119_engine.py)
grep -cE "END_FLOW_SENTINEL|class DialogueIO|class SopEngine119|class TransferToHumanError|def emit" $DST/sop_119_engine.py
```

全數通過才複製，並改三處版本標識：docstring 部署路徑、changelog 段落、`FastAPI(version=)`。

```bash
cp $SRC/sop_api_server.py $DST/
```

### C — 重建 `case_field_labels_119.py`

**條件：`$DST` 缺此檔（每次都缺），或 `case_info_119.py` 有動。**

新版幾乎每次都加欄位（0724 +6，0808 +43 −2）。這步是**唯一無法自動化的內容創作** —— 欄位的中文名要人取。取完跑交叉驗證，**三項全過才算數**：

```bash
cd $DST && $PY -c "
import sys; sys.path.insert(0,'.')
from dataclasses import fields
from case_info_119 import CaseInfo119
from case_field_labels_119 import LABELS
c=CaseInfo119()
print('labels 有但 case 沒有:', [k for k in LABELS if not hasattr(c,k)])          # 須為 []
print('case 有但 labels 漏:', [k for k in c.to_dict() if k not in LABELS and k!='transcript'])  # 須為 []
order=[f.name for f in fields(CaseInfo119) if f.name!='transcript']
print('順序與 dataclass 一致:', list(LABELS)==order)                              # 須為 True
print('條數:', len(LABELS))
"
```

### D — 環境對齊

**條件：`pip freeze` 與 `$REPO/requirements-119.txt` 有落差。**

`requirements-119.txt` 放 **repo 根目錄、全版本共用一份**，是 pip freeze 紀錄（供新機重建 venv），不是執行期依賴。

```bash
diff <($REPO/llmenv/bin/pip freeze | grep -viE "^llama[-_]cpp[-_]python") \
     <(grep -vE "^#|^--|^$" $REPO/requirements-119.txt)
```

新版引入新套件時（0808 = `openpyxl`），先裝再把快照重產，**檔頭那段 llama-cpp-python 需自行 CUDA 編譯、torch 走 CPU extra-index 的註解要手動貼回**（freeze 不會產出來）。

```bash
$REPO/llmenv/bin/pip install <新套件>
```

### E — 外部相依連通性

**條件：service 有指向外部服務的 env（目前 = 轄區 API）。**

新機或新網段一定要先測，不通會讓每次地址校驗空等到 timeout 才失敗。

```bash
curl -s -m 5 -G "http://61.216.64.19:8055/Template/Office/data" \
  --data-urlencode "addr=新北市板橋區中山路一段161號"
# 期望：status":"Success" 且 officeName 非空（應為「海山分局海山所」）
```

⚠️ 參數名是 **`addr`**，不是 `address`。用錯會回「地址解析失敗」，看起來像 API 壞了。

### F — 離線驗證（不佔 VRAM，不影響線上）

VRAM 一次放不下兩份 ~20GB gguf，所以這段全程不載模型。

**F-1 vendor 自帶 tests**（新版若附 `tests/`）。`tests/` 沒有 `__init__.py`，`unittest discover` 會報 `Start directory is not importable`，逐支跑：

```bash
cd $DST && for t in tests/test_*.py; do echo "── $t"; PYTHONPATH=. $PY "$t" 2>&1|tail -4; done
```

**F-2 編譯與 import**。⚠️ **`import sop_api_server` 不是輕量操作** —— 它 module-level 就載 gguf 與 BERT，裸 import 會去搶 VRAM。要 import 它一律先給降級三件組：

```bash
cd $DST && $PY -m py_compile sop_api_server.py case_field_labels_119.py
GGUF_MODEL_PATH=/nonexistent ENABLE_MAIN_CLASSIFIER=0 ENABLE_SUB_CLASSIFIER=0 $PY -c "
import sys, importlib, pkgutil; sys.path.insert(0,'.')
from sop_119_engine import END_FLOW_SENTINEL, DialogueIO, SopEngine119, TransferToHumanError, FlowAbortedError
import handlers
for m in pkgutil.iter_modules(handlers.__path__): importlib.import_module(f'handlers.{m.name}')
import sop_api_server as s; print('OK', s.app.version, DialogueIO.__abstractmethods__)"
```

**F-3 降級模式 smoke（alt port 8201）**。線上 8200 不受影響：

```bash
GGUF_MODEL_PATH=/nonexistent ENABLE_MAIN_CLASSIFIER=0 ENABLE_SUB_CLASSIFIER=0 LOG_DIR=/tmp/logtest \
  $REPO/llmenv/bin/uvicorn --app-dir $DST sop_api_server:app --host 127.0.0.1 --port 8201 &
```

驗收：`/health` 三個 loaded 皆 **false**（確認沒吃 VRAM）→ `/schema/case-fields/labels` 條數 = case 欄位數 −1（transcript）且新欄位在、被移除的欄位不在 → `/session/new` → `/input` 有回話 → `/hangup` 後 `/result` 的 `result` = `manual_end`。驗完 `kill` 掉。

### G — 切換 service

```bash
sudo cp /etc/systemd/system/sop119.service /etc/systemd/system/sop119.service.bak.$(date +%Y%m%d_%H%M%S)
sudo sed -i "s#WorkingDirectory=.*#WorkingDirectory=$DST#" /etc/systemd/system/sop119.service
# 新版引入新 env（如 0808 的 JURISDICTION_*）就一併補 Environment= 行，顯式寫死不靠程式碼 default
sudo systemctl daemon-reload && sudo systemctl restart sop119.service
```

`daemon-reload` 只讓 systemd 重讀 unit，**一定要 `restart` 進程才會載新目錄的程式碼**。重起要重載模型，`TimeoutStartSec=300`。需 sudo 密碼。

### H — 上線驗證

`/health` 三個 loaded 皆 true 之後，跑真實對話。**新增流程一定要各跑一條**，只驗 `/health` 不算數。

⚠️ **測試地址必須用新北市的。** 轄區 API 是新北市系統：台北地址會回 `status:Success` 但 `officeName` 為空 → 程式判 invalid → 走 `human_transfer`。可用地址：`新北市板橋區中山路一段161號`。

⚠️ **對話要逐題照答，不要用固定腳本硬餵。** 新流程問句是動態的（火警會依 `fire_category` 分四支），答非所問會讓 LLM 把答案抽到錯欄位（實測把「是住宅大樓」抽進 `address`，看起來像 bug 其實是測試方法錯）。

0808 版的驗收基準：

| 情境 | 開場白 | 期望 |
|---|---|---|
| 火警—建築物 | 我家失火了濃煙一直冒 | `main_category=火警` conf≈0.999、`fire_category=建築物`、火警欄位有抽取、`result=dispatched` |
| 地址校驗 | 同上 | `address_validation_status=valid`、`jurisdiction_office=海山分局海山所` |
| 局內回報—支援 | 這裡是海山分隊回報，我要請求支援 | `support_vehicle_type/count`、`result=support_dispatched` |
| 局內回報—現場 | 這裡是海山分隊回報現場狀況 | `field_report_content` 有值、`result=report_recorded` |
| 救護 OHCA 回歸 | 我爸爸昏倒了沒有反應 | `is_ohca=True`、`ImportantCase=2`、`result=ohca_transfer` |
| 地址失敗降級 | 給台北地址兩次 | `address_suspect_error=True`、`result=human_transfer`，之後再送 input 回 HTTP 409 |

`/result` 在流程結束前回 `case: null`（`sess.case` 要 `run()` 收斂後才寫入），中途要看狀態請讀 `/input` 回應裡的 `events`。

### I — 收尾

- memory `119-model-swap`：工作目錄改成新版
- 本 runbook §踩雷、§版本沿革 各補一筆
- git commit（模型不進 git）；要部署才 `git push prod master`

---

## 4. 只換模型（程式不動）

換 gguf：改 `GGUF_MODEL_PATH` → `daemon-reload` → `restart` → 走 §H。新模型 chat_format／prompt 若不同，`llm_extractor_119.py` 的 prompt 可能要調。

換 BERT：覆蓋 `ai/TW-119-BERT_main`／`TW-119-BERT-sub_*`（保持目錄名）→ `restart` → 走 §H。改根目錄則改 `BERT_MODELS_BASE`。

兩者都跳過 §A–F，其餘相同。

## 5. 回滾

還原 `sop119.service.bak.*` → `daemon-reload` → `restart`。舊版程式目錄保留未動，可作 code 層級回滾；`llmenv` 多裝的套件對舊版無害。

## 6. 踩雷紀錄

- **VRAM 雙開 OOM**：一次放不下兩份 ~20GB gguf。任何會載模型的動作（含裸 `import sop_api_server`）都要先停舊服務，或用降級三件組。
- **`import sop_api_server` 會載模型**：module-level 就載，不是輕量 import。
- **巢狀目錄**：0808 交付時多包一層同名資料夾，不攤平會讓所有路徑與 rsync 錯位。
- **轄區 API 參數叫 `addr`**：用 `address` 會回「地址解析失敗」，誤判成 API 故障。
- **轄區 API 只涵蓋新北市**：台北地址 `status:Success` 但 `officeName` 空 → invalid。測試地址別用台北。
- **測試對話答非所問**：會污染抽取結果，看起來像系統 bug。
- **只 port `sop_api_server` 忘了 `case_field_labels`**：`/schema` 會缺或 import 失敗。
- **跑錯機器**：119 在 cyberon2／aitop6，不是 204／aitop4（110 系統）。
- **`tests/` 無 `__init__.py`**：`unittest discover` 用不了，要逐支跑。

## 7. 版本沿革

| 日期 | 版本 | 重點 |
|---|---|---|
| 2026-07 | 0625_code → 0721_v2 | 引擎 handlers 化；hangup 改 `END_FLOW_SENTINEL`；case 改 `to_dict`。**`sop_api_server.py` 有重寫** |
| 2026-07-30 | 0721_v2 → 0724_add_2maincategory | 新增火警／緊急救援兩主類別；case_info +6 火警欄位；API 介面不變 |
| 2026-08-10 | 0724 → 0808_loc_feedback | 地址五型態＋轄區校驗；火警細分建築物／工廠／車輛／露天四支；新增局內同仁回報流程（`report_recorded`／`support_dispatched`）；通用標記 `ImportantCase`／`ImportantTag`／`NeedAmbulance`；欄位 46→87；新依賴 `openpyxl`；API 介面不變 |
