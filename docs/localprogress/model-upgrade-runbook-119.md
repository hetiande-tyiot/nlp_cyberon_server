# 119 智能報案系統 — 模型 / 版本升級 runbook

> 用途：把 119 舊版換成新版，維持 `sop_api_server.py` 對機器 A 的 REST API 合約零變動。
> 首次撰寫：2026-07-30，整合 0625→0721、0721→0724 兩次換版經驗。
> 方法論對照同目錄 `model-upgrade-runbook.md`（那份是 **110LLM** 系統的）；119 是仿 110 架構所建。
> 適用：之後開發者出新版（119_{date}）只要結構接近，依此走即可。

## 0. 升級的不變原則

| 原則 | 意義 |
|---|---|
| **不動 vendor 上游檔** | `sop_119_engine.py` / `case_info_119.py` / `inference_pipeline.py` / `classifier_with_llm.py` / `llm_extractor_119.py` / `handlers/*` / `subcategory_keywords_119.py` 視為 vendor code |
| **客製集中在 `sop_api_server.py`** | server-only 入口檔（不在開發者的 Streamlit release 裡），所有 endpoint、log 寫檔、queue bridge 都在這。**新版通常只給 Streamlit `app_119.py`、不含此檔，每次都要從舊版 port 過來** |
| **API 合約零變動** | endpoint path / payload / response 結構維持 — 機器 A client 一行都不必改 |
| **env var 控旋鈕** | 模型路徑、device 全走 env var；systemd unit 改 `Environment=` 不必動程式碼 |

## 1. 架構速覽

- **機器**：cyberon2（開發主力，192.168.5.132）。⚠️ 別跟 204/aitop4（那是 **110 系統**）搞混。切換 systemd 一定在 cyberon2。
- **線上服務**：systemd `sop119.service`，REST API `http://0.0.0.0:8200`
- **進入點**：`sop_api_server:app`（uvicorn），`WorkingDirectory` = 當前版本目錄（2026-09-01 起 = `ai/119_0813_adjustSOP/`）
- **venv**：`/home/cyberon2/nlp_cyberon_server/llmenv/`（Python 3.12）
- **部署目標機**：aitop6（見 memory `deploy-aitop6-tailscale`，git push + rsync 雙管道）

service 環境變數（`/etc/systemd/system/sop119.service`）：

| env | 值 | 控制 |
|---|---|---|
| `GGUF_MODEL_PATH` | `.../models/TW-119-Model.gguf` | LLM 抽取模型（gguf） |
| `BERT_MODELS_BASE` | `.../ai/` | BERT 主/子分類器根目錄 |
| `BERT_DEVICE` | `cpu` | BERT 運算裝置 |
| `LOG_DIR` | `.../log_119` | 案件 JSON log |

## 2. 換版 7 步流程（換整套 code 版本）

```
[1] Pre-flight：diff 新舊目錄、確認介面相容、盤點模型
[2] Port sop_api_server.py + case_field_labels_119.py（新版通常缺這兩個）
[3] 依賴檢查：requirements 有無變、輕量 import（不載模型）
[4] Smoke test：alt port(8201) 降級模式跑 API 契約（不佔 GPU、不影響線上）
[5] 切 systemd：改 WorkingDirectory → daemon-reload → restart
[6] 完整驗證：/health + 真實對話（含新增流程）
[7] 更新 memory + docs
```

### Step 1 — Pre-flight

```bash
cd /home/cyberon2/nlp_cyberon_server/ai
SRC=<舊版>; DST=<新版>
comm -23 <(ls -1 $SRC|sort) <(ls -1 $DST|sort)   # 舊有新缺 → 要 port（通常含 sop_api_server.py）
comm -13 <(ls -1 $SRC|sort) <(ls -1 $DST|sort)   # 新增檔
for f in sop_119_engine.py case_info_119.py inference_pipeline.py classifier_with_llm.py llm_extractor_119.py; do
  echo "$f: $(diff $SRC/$f $DST/$f 2>/dev/null|grep -cE '^[<>]') 行"; done
# 介面相容（API 層會用，簽名必須不變）
diff <(sed -n '/class SopEngine119/,/debug: bool/p' $SRC/sop_119_engine.py) \
     <(sed -n '/class SopEngine119/,/debug: bool/p' $DST/sop_119_engine.py)   # 應無輸出
grep -cE "END_FLOW_SENTINEL|class DialogueIO|class SopEngine119|class TransferToHumanError|def emit" $DST/sop_119_engine.py
diff <(ls $SRC/handlers/) <(ls $DST/handlers/)   # 新增主類別會多 handler
```

### Step 2 — Port sop_api_server.py + case_field_labels_119.py

```bash
cp $SRC/sop_api_server.py $SRC/requirements-119.txt $DST/
# 改 sop_api_server.py 版本標識（docstring 部署路徑、FastAPI version=）
```

**⚠️ 119 每次必做：`case_field_labels_119.py` 要跟新版 `case_info_119.py` 欄位同步。**
新版常新增欄位（0724 就加了 6 個火警欄位 fire_or_smoke…fire_floor）。重建後交叉驗證，**兩個列表都必須為空**：

```bash
cd $DST
/home/cyberon2/nlp_cyberon_server/llmenv/bin/python -c "
import sys; sys.path.insert(0,'.')
from case_info_119 import CaseInfo119; from case_field_labels_119 import LABELS
c=CaseInfo119(); d=c.to_dict()
print('labels 有但 case 沒有:', [k for k in LABELS if not hasattr(c,k)])
print('case 有但 labels 漏(transcript 除外):', [k for k in d if k not in LABELS and k!='transcript'])
"
```

### Step 3 — 依賴 + 輕量 import

```bash
diff $SRC/requirements-119.txt $DST/requirements-119.txt   # 通常無變 → 沿用 llmenv（不重建 venv）
cd $DST && /home/cyberon2/nlp_cyberon_server/llmenv/bin/python -m py_compile sop_api_server.py case_field_labels_119.py
/home/cyberon2/nlp_cyberon_server/llmenv/bin/python -c "
import sys; sys.path.insert(0,'.')
from sop_119_engine import END_FLOW_SENTINEL, DialogueIO, SopEngine119, TransferToHumanError, FlowAbortedError
import importlib
# 把新版 handlers/ 內每個新 handler 都 import 一遍
print('OK')"
```

### Step 4 — Smoke test（降級模式，alt port，不影響線上）

5090 一次放不下兩份模型（VRAM 雷），用**降級模式**（不載 gguf/BERT）在 8201 驗 API 契約：

```bash
GGUF_MODEL_PATH=/nonexistent ENABLE_MAIN_CLASSIFIER=0 ENABLE_SUB_CLASSIFIER=0 LOG_DIR=/tmp/logtest \
/home/cyberon2/nlp_cyberon_server/llmenv/bin/uvicorn --app-dir $DST sop_api_server:app --host 127.0.0.1 --port 8201 &
# 測 /health /session/new /input /hangup /result /schema/case-fields/labels
# 通過：hangup→result="manual_end"、labels 條數 = case 欄位-1(transcript)、新欄位出現在 /schema
```

### Step 5 — 切 systemd

```bash
sudo cp /etc/systemd/system/sop119.service /etc/systemd/system/sop119.service.bak.$(date +%Y%m%d_%H%M%S)
sudo sed -i "s#WorkingDirectory=.*#WorkingDirectory=$DST_ABS#" /etc/systemd/system/sop119.service
sudo systemctl daemon-reload && sudo systemctl restart sop119.service
```

### Step 6 — 完整驗證

```bash
curl -s http://127.0.0.1:8200/health   # 三個 loaded 皆 true
# 真實對話（換版若加了新主類別，測那條流程）。火警範例：
B=http://127.0.0.1:8200; PY=/home/cyberon2/nlp_cyberon_server/llmenv/bin/python
SID=$(curl -s -X POST $B/session/new|$PY -c "import sys,json;print(json.load(sys.stdin)['session_id'])")
curl -s -X POST $B/session/$SID/input -H "Content-Type: application/json" -d '{"text":"我家失火了濃煙一直冒"}'
curl -s -X POST $B/session/$SID/input -H "Content-Type: application/json" -d '{"text":"台北市信義區松高路1號5樓"}'
curl -s -X POST $B/session/$SID/input -H "Content-Type: application/json" -d '{"text":"對"}'
curl -s $B/session/$SID/result | $PY -m json.tool   # 確認 main_category=火警、火警欄位有抽取
```

### Step 7 — 更新 memory + docs

- memory `119-model-swap`：工作目錄改成新版
- `ai/<舊版>/換模型步驟.md`：架構速覽的工作目錄
- 本 runbook §「版本沿革」補一筆

## 3. 119 每次升級都要對照的檢查（vendor 習慣）

| 檢查 | 命令 | 目前狀態 |
|---|---|---|
| **case_field_labels 同步新欄位** | 見 Step 2 交叉驗證 | 每次都要，0724 補了火警 6 欄位 |
| **承接詞前綴**（好的，/了解，，避免跟 A 端 TTS 重複） | `grep -rnE '"(好的\|了解\|收到)[，,]' handlers/*.py` | 119 目前**無**，若未來 vendor 帶回要剝 |
| **vendor 硬編路徑** `/root/autodl-tmp` | `grep -rn "/root/autodl-tmp" *.py` | 只在函式 DEFAULT，API 全靠 env 覆蓋 → 無妨 |
| **介面符號簽名** | 見 Step 1 | SopEngine119.__init__ / END_FLOW_SENTINEL / to_dict 至今未變 |

## 3.5 換版客製修改清單（vendor 版沒有／原用 jurisdiction，每次要重新套用）

vendor 新 Streamlit 版只含 `app_119.py` + 引擎/handlers，以下 server 端客製要 port / 重加：

**① `sop_api_server.py`（整檔 port，vendor 沒有）**
- 從當前線上版 cp + 改版本標識（docstring 部署路徑、`FastAPI(version=)`）
- 含 `/observe` 端點（轉真人後聽對話 + 背景重算 `case_summary`；SSE 收線改由 `/hangup`；相依 `build_fallback_summary` / `StreamingResponse` / `OBSERVE_*` env）
- **緊急救援子分類補註冊**（vendor `build_classifiers` 只註冊救護+火警）：
  ```python
  from classifier_with_llm import build_classifiers, SubCategoryClassifier
  _es_dir = os.path.join(BERT_MODELS_BASE, "TW-119-BERT-sub_緊急救援")
  if os.path.isdir(_es_dir):
      _shared_sub_classifiers.register(SubCategoryClassifier(
          main_category="緊急救援", model_dir=_es_dir, llm_model_path=None, device=BERT_DEVICE))
  ```

**② `case_field_labels_119.py`（重建，vendor 沒有）** — 對照新版 `case_info` 重建 + 交叉驗證（缺/多皆空）。0901 = 106 欄 / 105 labels。

**③ 地址驗測改 addrCheck（`location_validation_119.py`）** — vendor 原用 jurisdiction 轄區 API，每次要改成 addrCheck：
- 常數 `DEFAULT_ADDRCHECK_BASE_URL` / `ADDRCHECK_VERIFY_PATH` / `LOCATION_TYPE_TO_API_TYPE`（address→House、intersection→Crossroad、highway→Freeway、landmark/mrt→Landmark）
- 核心 `verify_address_detail()`→(status,hint,reason) + `verify_address_status()` 薄包裝 + `_addrcheck_token()`
- reason 分類 `ADDRCHECK_REASON_TEXT` + `addrcheck_failure_reason()`；`JurisdictionResult.api_reason`
- `query_jurisdiction`(→House) / `validate_landmark` / `validate_mrt`(→Landmark) 改走 addrCheck
- **119 只看 `status:true`、不取分局名**（分局是 110 才要）；地標/捷運本地檔 `landmarks.xlsx`/`MRTstation.csv` 保留（引擎用於「型態分類」）

**④ 引擎 intersection/highway 分支改 addrCheck（`sop_119_engine.py`，動 vendor）** — import `verify_address_status`；兩分支組出地址後加 addrCheck 驗證（True→valid / False→invalid reask / None→error）。highway 需帶里程才驗得過。

**⑤ reason 接引擎 — TODO（尚未做）**：`location_validation` 已備 `addrcheck_failure_reason()` / `verify_address_detail`(回 reason) / `api_reason`，但引擎失敗仍用固定訊息（「路口查無」等）。待辦：引擎各 invalid 分支改用 `addrcheck_failure_reason(result.api_reason)` 產生正確錯誤說明（查無門牌/查無路段…）。

**⑥ systemd `sop119.service` env**：`WorkingDirectory`→新版；`ADDRCHECK_API_URL=http://100.107.145.7:8088` + `ADDRCHECK_API_TOKEN` + `ADDRCHECK_API_TIMEOUT=2.5`（0901 起不需 `JURISDICTION_API_URL`）；其餘 `GGUF_MODEL_PATH`/`BERT_MODELS_BASE`/`LOG_DIR`/`BERT_DEVICE` 不變。

**⑦ 模型目錄 / 換子分類模型**：子分類統一用**無後綴**目錄名 `TW-119-BERT-sub_{救護|火警|緊急救援}` 當「原版檔名」。
**換新模型慣例：原版目錄改名 `_bak_<日期>`、新版內容放進無後綴原檔名，`_MODEL_DIRS` 路徑不用改。** 例：0903 換火警 → 無後綴 `火警`(13類) 改 `火警_bak_0903`、`火警_v5`(21類) 放進無後綴 `火警`。
⚠️ **vendor 從 0901 起把火警 `_MODEL_DIRS` 寫成 `火警_v2`（多後綴、偏離無後綴慣例），每次換版必須 sed 改回無後綴**：
```bash
sed -i 's#TW-119-BERT-sub_火警_v2#TW-119-BERT-sub_火警#g' classifier_with_llm.py
```
救護本來就無後綴（vendor 正確）、緊急救援靠 ① 補註冊。

## 4. 只換模型（程式不動）

- **換 LLM gguf**：改 service `GGUF_MODEL_PATH` → `daemon-reload` + `restart`。新模型 chat_format/prompt 若不同，`llm_extractor_119.py` 的 prompt 可能要調。
- **換 BERT**：覆蓋 `ai/TW-119-BERT_main` / `TW-119-BERT-sub_*`（保持目錄名），`restart`。改根目錄則改 `BERT_MODELS_BASE`。
- 詳見 `ai/119_0721_v2/換模型步驟.md`（情境 A/B）。

## 5. 部署到目標機 aitop6

程式走 `git push prod master`、模型走 rsync（gguf + 5 個 TW-119-BERT*）。新機環境用 `deploy_setup.sh`（建 venv→裝套件→CUDA 編譯 llama-cpp-python→寫 service）。詳見 memory `deploy-aitop6-tailscale`。

## 6. 驗證 / 回滾

回滾：還原 `sop119.service.bak.*` → `daemon-reload` → `restart`。舊版程式目錄保留未動，可作 code 層級回滾。

## 7. 踩雷紀錄

- **VRAM 雙開 OOM**：5090 一次放不下兩份 ~20GB gguf。完整 sanity/smoke 前必須停舊服務；平時驗證用降級模式(§Step4)避開。
- **跑錯機器**：119 在 cyberon2，不是 204/aitop4（110 系統）。切換 systemd 一定在 cyberon2。
- **只 port sop_api_server 忘了 case_field_labels**：新版沒有 labels 檔且 case_info 加了欄位 → `/schema` 會缺、或 import 失敗。

## 版本沿革

| 日期 | 版本 | 重點 |
|---|---|---|
| 2026-07 | 119_0625_code → 119_0721_v2 | 引擎升級 handlers 化；hangup 改 END_FLOW_SENTINEL；case 用 to_dict |
| 2026-07-30 | 119_0721_v2 → 119_0724_add_2maincategory | 新增火警/緊急救援兩主類別流程；case_info +6 火警欄位；API 介面不變。上線驗證：火警分類 conf 0.999、火警欄位正常抽取 |
