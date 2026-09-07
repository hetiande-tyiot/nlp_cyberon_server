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

> ⑩-2 ～ ⑩-13 的**改造全程**（每個問題怎麼發現、怎麼修、以及數則「修過頭又收回」
> 的紀錄）另見 `119-0904-address-flow-devlog.md`。動這一區之前值得先讀，
> 裡面記了哪些看似合理的修法實際上會弄壞別的東西。

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

**⑤ reason 接引擎（`sop_119_engine.py`，動 vendor）— 2026-09-04 已完成**：`_validate_location_once` 各分支改吃 API 的 reason，不再用固定訊息。
- address 分支：`reason = addrcheck_failure_reason(result.api_reason)`，取代寫死的「地址查無管轄單位」
- intersection / highway 分支：`verify_address_status` 改叫 `verify_address_detail`（三元組 `status, hint, api_reason`），失敗訊息同樣走 `addrcheck_failure_reason(api_reason)`
- import 需補 `addrcheck_failure_reason` + `verify_address_detail`
- API 無法使用時的訊息統一為「地址驗測 API 無法使用」（舊字串「地址轄區 API 無法使用」是 jurisdiction 年代遺留）
- ⚠️ **「管轄單位」字樣不該再出現在任何 119 錯誤訊息**（119 走 addrCheck 不查分局）；port 後用 `grep -rn 管轄 --include=*.py` 自檢，只該剩 `case_field_labels` / `case_info` 的欄位標籤
- mrt 分支仍走本地 `validate_mrt`，維持「查無捷運車站」不變

**⑥ 地址抽取層口語贅詞防護（`sop_utils_119.py`，動 vendor）— 2026-09-04 新增**：vendor 的 regex 會把報案人的口語贅詞吃進地址元件，拼出的地址送 addrCheck 必然查無。**兩處都要重加**：
- `_KNOWN_DISTRICTS`（新北29＋北市12＋基隆4＋桃園13）+ `extract_address_district()` 改先掃名單、取「區」字前最長合法區名，名單未收錄才退回 `_DISTRICT_RE`
  - 事故：`欸我住在那個辦土城區…` → 區被抽成「個辦土城區」→ 有效地址被判查無 → 要求重報 → 轉真人
  - ⚠️ 光把 `{1,4}區` 縮成 `{2,3}` 沒用，「辦土城區」照樣中；必須用名單
  - 註：`address_mapper_119.py` 另有 `_DISTRICT_CANDIDATES_FOR_NORM`（僅新北、供臺語模糊比對），用途不同、兩份並存；增修行政區時要一起看。該表目前寫的是「萬裡區」（簡繁誤字，正確為「萬里區」）
- `_ROAD_PREFIX_FILLERS` + `strip_road_fillers()`，`extract_address_road()` 回傳前先剝贅詞
  - 事故：`嗯，那個亞洲路3號2樓` → 路被抽成「那個亞洲路」
  - ⚠️ 只在剝完仍能 `_ADDRESS_ROAD_RE.fullmatch()` 時才剝，否則「那個路口」會被剝成非法路名「路」

**⑦ 地址鎖 `_address_locked`（`sop_119_engine.py`，動 vendor）— 2026-09-04 新增**：vendor 的 `_apply_location_rules` 在每輪報案人輸入都會跑，判到地標/捷運/路口字樣就**無條件覆寫** `case.address`，不看地址是否已成立、是否已派遣。
- 事故（2026-09-04 09:45 孕婦急產）：救護車已派出後，AI 問「在哪裡產檢？」報案人答「國泰醫院」→ `address` 被蓋成醫院名、`location_type` 變 landmark，**派遣地址錯誤**（元件欄位仍是土城區亞洲路3號）。`classify_location_type` 靠「醫院」關鍵字即判 landmark，不需地標名單（該名單其實是空的）
- 作法：`__init__` 加 `self._address_locked = False`；原 `_run_address_flow` 改名 `_run_address_flow_inner`，外層新 `_run_address_flow` 用 `try/finally` 呼叫並在 finally 設 `True`（內層有 5 個提前 return，用 finally 才涵蓋得完）
- `_apply_location_rules` 的 `intersection/highway/mrt/landmark` 分支加守衛：`self._address_locked and is_usable_address(self.case.address)` 時**跳過覆寫**（含 `location_type`，否則 case 會自相矛盾）
- ⚠️ 守衛條件不可改用 `address_confirmed` / `address_validation_status=="valid"`：出事那通兩者分別是 False / invalid，擋不住
- 未鎖（地址流程進行中）行為完全不變；已鎖但無地址時仍允許補抽，不影響地址抽取失敗案件的救援路徑

**⑧ STT 誤聽防護 — 2026-09-04 新增**：報案人的回答經過 STT，錯字會直接變成地址元件。三處要重加：
- `sop_utils_119.py` `_NON_DISTRICT_WORDS` — 以「區」結尾但不是行政區的詞（不分區／學區／社區／轄區…），`extract_address_district` 的 regex 退路要濾掉
  - 事故：問「請告訴我是那一區？」STT 聽成「不分區」→ 組出「不分區亞洲路3號」→ addrCheck 查無 → 要求整段重報
- `address_mapper_119.py` `DISTRICT_FUZZY_MIN_SCORE`（預設 0.6，env `ADDR_DISTRICT_FUZZY_MIN` 可調）— `_fuzzy_match_district_by_tl` 原本 `best_score` 由 **-1.0** 起跳、**無門檻**，任何輸入都必定回傳某一區
  - ⚠️ 實測「不分區」被比成**「瑞芳區」**（0.583），形成看似合法、實際完全錯誤的派遣地址。這比不比對更危險
  - 實測分數可作調參依據：板橋去→板橋區 0.909、土成區→土城區 0.800、汐只區→汐止區 0.636；非行政區的詞多在 0.58 以下
- **猜了必須覆誦確認，不得靜默改寫**（`address_mapper_119.py` + `sop_119_engine.py`）：
  - mapper 新增 `map_location_detail()` → `(映射後文字, (原片段, 猜出的區) | None)`；`map_location()` 保持原介面。**猜測資訊必須走回傳值**——mapper 是進程內單例，多 session 共用，用實例狀態會互相污染
  - 引擎 `_district_guess` 記錄猜測；`_normalize_location_fields` 改用 detail 版收集
  - 覆誦話術改成「我聽到的地址是…，請確認行政區是「XX區」對嗎？」，把區單獨點出來讓報案人有機會否認
  - `_mark_address_failure` 先呼叫 `_revert_unconfirmed_district_guess()`：**沒走完覆誦就失敗時，把猜測還原成原文**，不把未確認的猜測當已知資訊留給接手的真人
  - 覆誦 `confirmed is True` 時清掉 `_district_guess`（猜測已獲確認）

**⑨ 傷病患人數不可誤收胎數（`sop_119_engine.py` + `sop_utils_119.py`）— 2026-09-04 新增**：`looks_like_pregnancy_count()`（比對「胞胎／雙胎／龍鳳胎」），`_apply_extracted_fields` 遇 `patient_count` 命中就丟棄。
- 事故：孕婦急產案問「單胞胎還是雙胞胎？」答「三胞胎」→ `patient_count` 被填成「三胞胎」（該通根本沒問過傷患人數）。胎數屬 `multiple_pregnancy`，傷病患是孕婦本人

**⑩ 子分類重問換句話（`sop_119_engine.py`）— 2026-09-04 新增**：`_SUB_REASK_QUESTIONS` 兩句輪替，取代原本固定重問「請問發生了什麼事？」。
- 觸發重問多半是 STT 聽錯（實例：「羊水」→「涼水」，關鍵詞沒命中 → conf < 0.7 → 重問，第二次聽對後 conf=1.0）。機制本身正確，但一字不差地再問一次，報案人會以為系統沒聽到

**⑩-2 一般門牌地址五步流程（`address_hint_119.py` + `sop_119_engine.py`）— 2026-09-04 新增**：vendor 的地址流程是線性的，一失敗就 `_reset_location_for_correction()` 清光區/路/號整段重報。改成五步：

1. **歷史對話補抽** — `_ensure_address_from_caller_history()`，每次進地址流程走一次（**不是每輪**；每輪都跑就會重蹈 09-04「國泰醫院」覆轍）
2. **缺什麼問什麼** — 音近猜測先核對（「我聽到的是土城區中央路，對嗎？」），再依缺項補問；非建築物不問樓層
3. **addrCheck ＋ hint 導向** — 失敗時解析 hint 決定下一句問話，**只清該重問的元件**（`_HINT_CLEAR_FIELDS`），已驗證的區和路保留
4. **引導式逐級** — 必問只有 區→路→號；段/巷/弄不主動問，但報案人主動講的會被 `extract_address_road` 一併收下
5. **回報受理員** — `_address_failure_report()` 把「失敗原因｜報案人講過：候選…｜系統提示：hint」一起寫進 `address_error_reason`，流程繼續往下走

要點：
- **`address_hint_119.py` 是獨立新檔，換版整檔複製即可**，不必逐行 port。引擎只接三個入口：`parse_address_hint()` / `build_hint_question()` / `floor_suppress_reason()`
- hint 是 API 端決定的自然語言，**解析失敗一律退回泛用問句**，不讓 API 改文案就弄壞整條流程。已知五種格式見該檔 docstring；注意 `road_only` 涵蓋三種不同情況（缺門牌／缺段／缺號），**光看 reason 不夠，必須解析 hint**
- ⚠️ **總提問預算 `_ADDRESS_ASK_BUDGET = 10`**：五步疊起來最壞會問二十幾次，急案不能這樣拖。所有地址提問走 `_address_ask()`，用完直接收斂到第五步
- ⚠️ **引導式必須連 `case.address` 一起清**，否則 `_fill_components_from_address()` 會立刻從舊地址把元件補回來，引導式等於沒作用；失敗時再用 `_restore_address()` 還原，別讓受理員接到空白
- 候選累積 `_address_candidates` 重問不清空（09-02 那通講對過的地址被清掉就回不來）
- `_complete_and_validate_location` 對 address 型態只在 **API 異常**（retryable）時才走整段重報；其餘失敗由五步自行收斂
- intersection / highway / mrt / landmark 分支**維持原判斷邏輯不動**

**⑩-3 地址話術口語化 — 2026-09-04**：原本三種失敗共用一句「地址無法確認，請重新提供完整正確的事發地點。」，太僵硬也不像人講話。話術常數集中在 `address_hint_119.py`：

| 情況 | 話術 |
|---|---|
| 門牌查無 | 這條路好像沒有{N}欸，麻煩再幫我看一下門牌？ |
| 缺段 | {路}有分一段、二段…，請問是哪一段？ |
| 路名查無、有建議 | 這邊查不到{X}，是{Y}嗎？ |
| 同名路分佈多區 | {路}有好幾個區都有，請問是{區1}、{區2}？ |
| 路名查無、無建議 | 這條路我這邊查不到，麻煩再說一次路名？ |
| 整段對不上（fallback） | 不好意思，地址我這邊對不起來，麻煩再說一次事發地點？ |
| 補問 | 請問是哪一區？／請問是什麼路？／請問是幾號？／請問是幾樓？ |
| 引導式開場 | 我們一項一項來，請問是哪一區？ |

**⑩-4 地標／捷運模糊比對必須確認（`address_hint_119.py` + `sop_119_engine.py`）— 2026-09-04 新增**：**addrCheck 的地標比對沒有相似度門檻**，只要含「市場」「捷運」「站」這類通用詞就硬配一個最相近的並回 `status=true`。實測：

```
捷運頂埔站出口1   → 捷運新埔站（完全不同的站）          status=true
捷運不存在站出口9 → 捷運亞東醫院站2號出口                status=true
未知市場旁邊      → 市場 → 文山區景隆街2號附近（跨臺北市）status=true
阿飄鬼屋 / xyz    → status=false（完全對不上才會 false）
```

API 自己的 hint 就寫著「（模糊比對）…**若不確定請向報案人確認是否為此處**」，但 vendor 程式碼直接把 `status=true` 當通過。作法：
- `parse_landmark_hint()` 依 hint 開頭的 `（模糊比對）` 判定，解析出配到的地標、對應地址、其他可能
- 引擎 landmark / mrt 合併成 `_validate_landmark_like()`，模糊比對時問「我這邊找到的是{地標}（{地址}），是這裡嗎？」；**報案人確認後才把 address 改寫成 API 解析出的地址**
- 否認 → invalid 重問；提問預算用盡 → 標 invalid「地標為模糊比對，未經確認」交受理員，**不敢逕自採用猜測**
- 精確比對（hint 無「（模糊比對）」）維持原行為，不多問
- ⚠️ 這裡不再呼叫 `validate_landmark()` / `validate_mrt()`（它們只回 bool、丟掉 hint），改用 `verify_address_detail()`；engine 的那兩個 import 要一併移除
- ⚠️ 這是 **API 端**的無門檻比對，我們改不了，只能在流程上要求確認。和 §3.5⑧ 的行政區音近比對是同一類問題

**⑩-5 地下樓層不可遺失（`sop_utils_119.py`）— 2026-09-04**：`compose_street_address` 的樓層 regex 只認「樓」字，地標驗測回的「…民生路三段2號**B1**」重建後會變成「…2號」，**地下樓層整個消失**。regex 補 `[Bb][0-9]+(?:[Ff])?`，B1／b2f／地下2樓都保留。

**⑩-6 模糊比對取樣（`fuzzy_match_log_119.py`）— 2026-09-04 新增**：地址判斷有兩處猜測都沒有可靠門檻——addrCheck 的地標比對（API 端，改不了）與 `address_mapper` 的行政區音近比對（本地，門檻 0.6 是**估的**）。門檻要調得準，靠的是實際通話裡「報案人到底接不接受這個猜測」，所以把每次模糊比對連同報案人的回應寫成 JSONL 累積樣本。

- **獨立新檔，換版整檔複製**；引擎只呼叫 `record_fuzzy_match()`
- 輸出 `{LOG_DIR}/fuzzy_matches.jsonl`（與 case JSON 同目錄，`ts` + `session` 可對回完整通話）；`FUZZY_LOG_PATH` 可覆寫
- ⚠️ **兩個 env 都沒設就不寫**。這是刻意的：預設寫死路徑會讓跑測試時把測試資料混進正式樣本，那份樣本是要拿來調門檻的，混進假資料就沒有分析價值。service 有設 `LOG_DIR`，正式環境照常取樣
- 每筆記 `spoken`（報案人原話）→ `matched`（猜出來的）→ `outcome`（**confirmed / denied / unconfirmed**）。`outcome` 是人工標註的 ground truth，調參真正要看的就是它；`api_hint` 保留原始字串，API 日後改格式時舊樣本仍可重新解析
- 行政區比對另記 `score`（臺語相似度）；地標比對 **API 不提供分數**，故 `score` 恆為 null，只能靠 spoken→matched→outcome 判斷
- 同一次猜測只取樣一次（`_district_guess_sampled` 旗標）——否則「否認 → 還原」會重複計數、污染統計
- `sop_api_server.py` 建 engine 後要設 `engine._session_tag = sess.sess_id[:8]`
- 分析：`python fuzzy_match_log_119.py` 直接印統計，**`max_denied_score`（被否認過的最高分）就是門檻至少該拉到的位置**

**⑩-7 合法行政區不得被歸一化改寫（`sop_utils_119.py` + `address_mapper_119.py`）— 2026-09-04**：離線重放真實通話時發現報案人講「台北市信義區松高路1號」被改成「台北市**萬裡區**松高路1號」。兩個來源，**皆為既有行為（0903 線上版相同）**：
- 音近比對：信義區→萬裡區 0.700、中正區→新莊區 0.733、**文山區→金山區 0.769**，都高於真實 STT 錯誤（汐只區→汐止區 0.636），**光調門檻擋不掉**
- `scripts/map_city.json`（4188 條）有 **7 條把真實行政區映射掉**：中正區→中和區、萬華區→中和區、北投區→板橋區、士林區→樹林區、新屋區→新莊區、桃園區→泰山區、蘆竹區→蘆洲區

作法：`sop_utils_119.is_known_district()`；`_apply_district_with_fallback` 開頭若判定文字已含合法區名，**整個行政區歸一化（表映射＋音近比對）都跳過**。env `DISTRICT_PROTECT_KNOWN=0` 可關閉。⚠️ 這是治標——`map_city.json` 那 7 條建議由資料端刪除。

**⑩-8 失敗時回到最完整候選（`sop_119_engine.py`）— 2026-09-04**：hint 導向補問會清掉該重問的元件，補問沒問到時 `case.address` 會停在殘缺狀態（重放實測「土城區要走路1段2號」被削成「土城區」，19 通如此）。`_mark_address_failure` 前呼叫 `_restore_best_candidate()`：先取 `api_status == valid` 的候選，否則用 `_merge_candidate_components()` 按元件各取最完整。
- ⚠️ 元件合併**只在「區相同、路名互為前綴」時進行**——報案人改報別的地址時硬合併會拼出不存在的門牌
- 為什麼不用 `merge_address()`：真實通話（case119_20260901_142234）報案人先講「吳鳳路90號」，被打回後補「吳鳳路2段」，`merge_address` 兩個方向都會丟一邊（→「吳鳳路2段」或「吳鳳路90號」），得按元件合併才拿得到「吳鳳路2段90號」
- 修正後「資訊變少」由 19 通降至 4 通

**⑩-9 「不知道」不等於「對」（`address_hint_119.py`）— 2026-09-04**：`parse_yes_no("不知道")` 回 `None`。猜測的確認若寫成「不是明確否認就當確認」，報案人一句「不知道」就會讓系統把猜測當事實採用。`is_uncertain_answer()` 涵蓋不知道／不清楚／不確定／沒印象等，地標與行政區的確認一律**視同未確認、不採用猜測**。

**⑩-10 上線首日實測修正（2026-09-04 19:54–20:02 四通）**：0904 切上線後第一批真實通話抓到五個問題，**四通中兩通派遣地址被覆寫**：

| 現象 | 根因 | 修正 |
|---|---|---|
| 「我是路人，所以我沒有開車」→ 路名變**我是路人路**；「不知道他躺在路邊」→ 變**不知道他躺在路**，還被唸出來覆誦 | `_address_locked` 只擋 landmark/mrt/路口/國道，**漏了 address 型態**（`_apply_location_rules` 的 address 分支無條件 `setattr` 覆寫元件）| address 分支補上同一道鎖 |
| 「那個新北市五股區…」→ 組出**個新北市**五股區…，API 認不出縣市，回「明德路有好幾個區都有」，繞三輪 | `compose_street_address` 的縣市 regex `{2,3}[市縣]` 貪婪吃贅詞，與 §3.5⑥ 行政區同病 | `_KNOWN_CITIES` 白名單 + `extract_address_city()` |
| 「新北市三重正義南路」→ 組出**新北市新北市**三重正義南路 | 路名已含縣市，`compose` 又加一次 | 元件已帶縣市就不再加 |
| 「三重區的正義南路」→ 路名變**的正義南路** | 贅詞清單缺「的」、缺區名前綴 | 加「的」＋完整區名剝除 |
| 59 字整段話被存成 `case.address`（句中有「醫院」→ 判 landmark）| `is_usable_address` 只擋「未知」佔位，任何非空字串都通過 | `MAX_USABLE_ADDRESS_LEN = 40` |
| 「這條路好像沒有12號欸」連問兩次 | 第三步迴圈每次失敗都問，不管上一輪有沒有進展 | 送驗地址與 reason 都沒變就 break 進引導式 |

⚠️ **只剝完整區名，不剝省略「區」字的簡稱**：簡稱與路名無法從結構區分——「三重正義南路」的「三重」該剝，「中山北路二段」的「中山」不能剝，而剝完剩下的「北路二段」照樣 fullmatch 成合法路名，守衛擋不住。少剝一個交給 hint 導向修正，好過把正確路名剝壞。

修正後重跑那四通：五股區明德路從 6 句問答降到 2 句且 valid（預算 1）；三重正義南路正確組出「新北市三重區正義南路12號」（invalid 屬正確，API 實測該路只有 4/6/20 號）。

**⑩-11 真實通話測試資料（`tests/data/real_calls_119.json`）— 持續累積中**：把 `log_119` 的真實通話轉成測試資料，換版後可直接驗證「這些真實講法還處理得對嗎」。

- 產生：`ADDRCHECK_API_URL=… ADDRCHECK_API_TOKEN=… PYTHONPATH=. python scripts/build_real_call_fixture.py`
- 使用：`tests/test_real_calls_119.py`（11 項），**離線可跑**——API 回應存成快照，不依賴外部服務
- 2026-09-06 現況：**15 通 / 32 句 / 16 筆 API 快照**，每筆對應一起真實事故或一種真實講法
- ⚠️ **每批實測後都要把新通話加進來**，流程見 §2 的「每次實測後」小節
- ⚠️ **只記不受問句影響的東西**：報案人回答序列是固定的、問句會隨版本改變，兩者一錯位，原本回答「哪一區」的那句就會被當成對覆誦的回答，測出來的 status 是錯位造成的**假回歸**。所以 fixture 記的是「原話 → 期望元件」與「地址 → API 判定」，流程層只斷言不崩／不超預算／已鎖地址不被改寫
- ⚠️ **期望值人工判讀，不是錄當下行為**——錄行為會把錯誤一起鎖進測試
- API 地址庫更新導致快照過期時，重跑產生腳本即可

**⑩-12 敘述句不得被當成路名（`sop_utils_119.py`）— 2026-09-04**：路名 regex `{1,12}(路|街|大道)` 會把任何以「路」結尾的詞組當路名。實測兩通中招：「我是路人，所以我沒有開車」→ **我是路人路**、「不知道他躺在路邊」→ **不知道他躺在路**。`_ROAD_REJECT_TOKENS`（我/你/他/是/不/沒/躺/倒/知道/看到/聽到/感覺）＋ `looks_like_real_road()`，命中就回 None。已驗證中山北路／和平東路／三民路／大同路／自強路／安樂路等真實路名零誤殺。

**⑩-13 覆誦當下地址被換掉要重驗（`sop_119_engine.py`）— 2026-09-04**：報案人常一邊說「對」一邊補上新地址，那輪的抽取會把 `case.address` 就地改掉。原本只看「對」就標成已確認 → **case 顯示「已確認、有效」，但存的是從未驗證過的地址**（09-02 那通驗的是 61巷、存的是二十六11巷）。覆誦前記下 address，回來後若變了就 `confirmed = None` 並走更正重驗。

**⑩-14 「API 查無」與「報案人沒確認」分開標記 — 2026-09-04**：`_mark_address_failure` 原本無條件把 `address_validation_status` 覆蓋成 `invalid`，但那是 API 判定，跟報案人有沒有確認是兩回事。實測 20:55 那通地址其實有效（API 回「地址有效：新北市三重區仁愛街283巷28號」），卻被標成「地址搜尋失敗」。改為：API 已驗證通過時不覆蓋狀態，標籤用新增的 `地址未確認`（`important_tags_119.IMPORTANT_TAGS` 要一併加）；真的查無才標 `地址搜尋失敗`。

**⑩-15 第六種 hint：`ambiguous` — 2026-09-04**：`「重陽路」的 一段、二段、四段 都有 1 號，是不同的地點，請追問報案人是哪一段。` 同一門牌號在多個路段都存在，不追問會派到錯的段。`_AMBIGUOUS_SECTION_RE` 解析成 `need_section`；`ADDRCHECK_REASON_TEXT` 加 `ambiguous`。

**⑩-16 街路映射延後到 addrCheck 查無之後（`address_mapper_119.py` + `sop_119_engine.py`）— 2026-09-04**：`map_street.json` 是 vendor 用臺語音近自動生成的（1707 個真實路名 × 平均 15 個變體），生成時**沒排除「變體本身已是另一條真實路名」**。實測 20:57 真實火警通話：報案人講「重陽路跟新北大道」，存檔成 `板橋區三和路與新新新新新新思源路口` 且已派遣。

- `map_location_detail(text, include_street=False)` 可跳過街路映射
- 引擎 `_street_mapping_enabled` 預設 **False**：第三步先拿報案人原話問 addrCheck，**查得到就不套表**；查無才啟用並重查一次。`STREET_MAPPING_MODE=eager` 可切回舊行為（驗證前就套表）
- ⚠️ **排除清單套用後，兩種順序的提問趟數差 0.004 句/通**（226 通中 225 通完全持平）。延後的價值不在減少問話，而在保護尚未驗證的條目；表已全表驗證後兩者等價
- 行政區映射不延後（它有 §3.5⑩-7 的合法區名保護）
- ⚠️ 判型（`_refresh_location_type`）在映射前做，看的是路/號/區的結構，不受影響

**⑩-17 街路映射排除清單（`scripts/map_street_exclude.json`）— 2026-09-06 全表驗證**：`map_street.json` 是 vendor 用臺語音近自動生成的（1707 個真實路名 × 平均 15 個變體），含 AI 生成常見的幻想條目。**寧可少映射**（交給 addrCheck 的 hint 導向去問報案人），也不要錯誤映射。

排除 **3081 條（12.1%）**，剩餘 22358 條有效映射：

| 判準 | 條數 | 為什麼 |
|---|---|---|
| 來源本身是真實路名 | 21 | 套用會把報案人講對的路改成另一條街（已在真實通話出事）|
| 臺語相似度 <0.50 | 3067 | 不是音近，起不到修正 STT 的作用 |
| 人工判讀 | 2 | `高速公路`（非路名，害國道案件走錯分支）、`新北大道路`（目標寫錯）|

- **獨立成檔**：vendor 更新 `map_street.json` 不受影響，換版只需 port 這個小檔
- **要加回來時**：把該 key 從 `excluded` 移除，附上 case JSON 檔名當證據。清單的 `reactivate` 欄位有說明
- 226 通離線重放：**改善 20 通、回歸 0、提問次數不變**（相較只排除 25 條的版本再改善 6 通、零變差）

⚠️ **驗證判準踩過四次坑，都是抽樣或在地知識才發現的**：

| 判準 | 初判 | 修正後 | 錯在哪 |
|---|---|---|---|
| 來源是真實路名 | 586 | **21** | 用 `reason` 判斷，但 `ambiguous` 多半是「來源查無、同音的存在」；`valid` 也可能是模糊比對到別條路 |
| 目標不存在 | 246 | **整層廢棄** | 「不帶行政區查 addrCheck」對很多路名不可靠——汐科路、漁澳路、擺街堡路等實際存在卻查無 |
| 相似度過低 | 4275 | **3067** | 1208 條是 `ese.py` 拼音表未收錄該字（「龙门路」只有「路」被轉），分數失真 |
| 區前綴比對 | — | 非貪婪 | 貪婪會把「板橋區**區**運路」吃成「板橋區區」，剩「運路」對不上 |

**教訓：自動化判準必須抽樣驗證，而且 API 的 `reason` 是給流程分支用的，不是給語意判斷用的。**

- 審閱清單：`scripts/map_street_review.md`（含每條的相似度與臺語拼音）
- 給 vendor 的回報：`docs/localprogress/119-vendor-map-street-report.md`
- ⚠️ 跑 audit 一定要帶 `ADDRCHECK_API_URL` / `ADDRCHECK_API_TOKEN`，否則全部查詢失敗、結果檔會是空的（腳本已加 `usable` 旗標）；全表約 2 小時

**⑩-18 採用 addrCheck 回傳的正規化地址 — 2026-09-04**：驗證通過時 hint 會帶回 API 認可的標準地址（`地址有效：…` 或 `已依讀音修正為「…」`）。`normalized_address_from_hint()` 解析後由 `_adopt_normalized_address()` 採用，樓層自己接回去（addrCheck 不處理樓層）。報案人講「南亞南路」、API 回 valid 並說明修正為「南雅南路」時，case 存的才是實際派遣點。

**⑩-19 樓層來源改「現有地址優先、原話備援」 — 2026-09-04**：`_apply_location_rules` 組地址時只看 `case.address` 取樓層，但第一輪它還是 None，且可能是 `extract_address_hint` 截斷過的殘值（「板橋區南亞南路2段15號3樓」→「板橋區南亞南路2」），樓層在組地址時就消失（既有行為，0903 亦同）。改為現有地址沒樓層時從本輪原話補。

**⑩-20 還原候選時同步驗證狀態 — 2026-09-04**：`_restore_best_candidate` 採用的候選若是 addrCheck 驗證通過的，`address_validation_status` 要跟著回到 `valid`，否則會出現「地址正確但標成查無」（09-02 那通最後還原成有效的 61巷地址，狀態卻停在中途那次的 invalid）。

**⑩-21 巷弄單獨補述要併回路名（`sop_utils_119.py` + `sop_119_engine.py`）— 2026-09-05**：路名 regex 需要「X路」開頭，報案人單獨補一句「還有31巷」「648巷6號」時抽不到，巷弄就此消失。實測兩通因此覆誦時唸成「國光路11號」「仁愛街28號」，報案人連續否認、通話被拉長。

- `extract_lane_alley()` / `road_has_lane()`：獨立抽「N巷」「N巷N弄」
- 引擎 `_merge_lane_into_road(text)` 在三處呼叫：補問後、hint 重問後、**覆誦後**（覆誦那次要在偵測 `addr_before_confirm` 變動之前併，地址才會走更正重驗）
- 路名已含巷弄就不附加（避免「國光路31巷31巷」）；「11號」不會被誤認為巷
- ⚠️ **`_resolve_address_correction` 要濾掉「純巷弄補述」**：「還有136巷8弄」原本會被
  當成新地址合併成「新北市板橋區還有136巷8弄」，**路名整個消失**、覆誦又唸回
  「光武街16號」，報案人連講三次都沒被接住。判準：`extract_address_road(c)` 為空
  且 `extract_lane_alley(c)` 有值 → 不是新地址

**⑩-22 路名開頭重複行政區要剝掉（`sop_utils_119.py` + `sop_119_engine.py`）— 2026-09-06**：報案人常把區和路連著講（「中和景平路」「板橋國光路」「新莊的中港路」），組地址時變成「中和區**中和**景平路27號」，addrCheck 查無，白繞一輪 hint 導向。API 實測「中和景平路431巷27號」本身就是 valid，是我們組壞了才查無。

- `strip_district_prefix_from_road(road, district)`，在 `build_street_address` 與 `_rebuild_street_address` 呼叫；後者同步更新 `case.address_road` 欄位，免得 address 與元件對不起來
- ⚠️ **只在「與已知行政區重複」時才剝**——這是與 §3.5⑥ `_ROAD_PREFIX_DISTRICTS` 的關鍵差異。單看路名無法判斷「中山北路」的「中山」該不該剝（剝了變「北路二段」仍是合法路名，fullmatch 守衛擋不住）；有了行政區條件，「淡水區」＋「中山北路」自然不受影響
- 實測效果：中和景平路那通 **14 句 AI 發話降到 5 句**，且不再問「這邊查不到中和景平路」

**⑩-23 段也要能單獨補述併回路名 — 2026-09-06**：`_merge_lane_into_road` 擴充成同時處理「N段」。實測 01:25：報案人講「一段22號」，`extract_address_road` 需要路名開頭所以抽不到「一段」，最終存「明德路22號」，API 回「最接近的是 明德路一段22號（報案人未提及段別）」。修正後該通由 invalid 變 valid。

- `extract_road_section()` / `road_has_section()`
- ⚠️ **段要接在巷之前**（「中央路三段61巷」），所以先併段再併巷；路名已有巷弄時不再插段，免得組出「中央路61巷三段」

**⑩-24 第三步半：LLM 整合整段對話（`llm_extractor_119.consolidate_address` + `sop_119_engine._consolidate_with_llm`）— 2026-09-06 新增**

規則抽取只看**單輪**（`extract_address(caller_text)`），分多次補述的巷弄、口誤更正、STT 音近錯字都接不住；而 `generate_summary` 吃的是**全部**逐字稿，所以摘要裡的地址一直比 `case.address` 完整——這是找出方向的線索。

離線評測 14 通真實通話（`scripts/eval_consolidate_address.py`）：

| | 對照人工正解 |
|---|---|
| 規則抽取 | **5/14** |
| `consolidate_address` | **13/14** |

規則錯的全是同一類：`國光路11號`（缺31巷）、`橫科路31號`（缺351巷）、`大觀路1段4號`（缺28巷6弄）、`仁愛路283巷`（STT 未修正）、`實踐路132號`（整句抽不到）。

接入位置與防線：

```
第三步 addrCheck 失敗 → 第三步半 LLM 讀整段對話 → 送 addrCheck
                                              valid → 採用 → 覆誦確認
                                              其他 → 不採用，照走引導式
```

- **只在規則失敗時才叫**，延遲只花在失敗案例上；不問報案人，不消耗提問預算
- **不採信 `confidence`**：實測 14 通全回 `high`，包含判錯那通。改用 addrCheck 當關卡，後面還有覆誦確認
- `need_ask` 欄位保留但目前不使用（一次都沒觸發）
- LLM 拋例外時安靜退回規則路徑，不中斷報案（有測試守住）
- ⚠️ **跑評測要用 CPU**：線上服務佔約 24GB/32GB VRAM，模型 20GB，用 GPU 會 OOM（runbook §7）。`LLM_DEVICE=cpu` 並用 `taskset` 限制核心數

**⑩-25 引導式保留已確認的元件 — 2026-09-06**：第四步原本清空所有元件從「請問是哪一區」重來，但 addrCheck 回 `road_only` 時區和路是確定的。`_HINT_CONFIRMS` 依 hint 種類決定保留：`nearby_numbers`/`need_number` → 保留區與路，`need_section` → 保留區。實測 03:12 那通從 **17 句降到 5 句**，且直接問「這條路好像沒有4號欸」而非從頭重來。

**⑩-26 兩個 hint／巷弄解析修正 — 2026-09-06**（都由 03:12 那通暴露）：
- 鄰近門牌支援「N號**之M**」：`_TAIL_NUMBER_RE` 原本要求結尾是「N號」，遇到「6弄5號之1」解析不到，整個 hint 退回泛用問句
- 巷與弄之間的標點：`extract_lane_alley` 沒套 `_ROAD_SEGMENT_PUNCT_RE`，「28巷。6弄」只抽到「28巷」，6弄 在第一次送驗就丟了

**⑩-27 門牌號取巷弄之後的那個 — 2026-09-06**：`extract_address_number` 原本取第一個「N號」。實測 03:12 報案人口誤更正「28號28巷」，取到 28號 而非真正的門牌 4號，之後 API 一直回「這條路沒有28號」，繞到引導式重來。改為只在巷／弄之後搜尋（地址結構是 路→段→巷→弄→號→樓），巷弄後沒有號才退回全句。

**⑩-28 省略「區」的口語區名 — 2026-09-06**：`extract_address_district` 只認得帶「區」的寫法。實測 04:42／04:44 連兩通開場都是「救護車在那個鶯歌」，抽不到區 → 落到**地標**分支 → AI 問「確定是鶯歌這個地址嗎？」。新增 `_bare_district()`，前後都要有線索才認：

```
前　句首／標點／虛詞（在到於個是的那這來去往從）
後　那邊之類的方位詞、標點、句尾，或緊接一個路名
```

**只收新北市 29 區**（`_NEW_TAIPEI_DISTRICTS`）。臺北市的「中山」「信義」「大安」同時是路名前綴，「中山北路」會被拆成「中山區」＋「北路」——與 ⑩-6 剝區名剝壞路名是同一個坑，受理範圍外不值得冒險。前置線索是「台大金山醫院」不被判成金山區的關鍵（「金山」前面是「大」）。

**⑩-29 日期不是門牌 — 2026-09-06**：國語的「號」同時是門牌與日期的量詞。報案人交代病史或事發時間會出現裸的「N號」（「他3月23號開過刀」），取第一個匹配就填成門牌。`_first_house_number()` 跳過「號」前面是年／月／日（可夾標點）的匹配，繼續往後找，所以「3月23號那次是在中央路3段61巷2號」仍抽得到 2號。

**⑩-30 第二輪重問只問缺的元件 — 2026-09-06**：`ask_questions` 是固定兩句，第二句「請問事發地址在哪裡？幾樓？」等於要報案人從頭講一次。`_narrowed_reask()` 在已知元件時改口：

| 已知 | 問句 |
|---|---|
| 區 | `{區}的哪一條路呢？` |
| 區＋路 | `{區}{路}幾號呢？` |
| 只有路，沒有區 | 維持通用問句（同名路可能跨區） |

**⑩-31 沒派車就不能說「已派出」 — 2026-09-06**：OHCA 轉真人的話術寫死「救護車已派出，請不要掛斷電話…」。但生命征象是在地址流程**之後**才問的，任何在派遣前就轉出去的通話（地址查不到、報案人講不清楚、打錯電話）都會聽到這句不實陳述。新增 `_dispatch_announced`，只有真的講過 `dispatch_line` 才是 True；否則轉接話術省略前半句。

**⑩-32 路名前緣的贅詞逐字剝除 — 2026-09-06**：`extract_address_road` 的切點只有「區」和縣市，兩個都沒有就從句首開始比對。實測 10:35「我這邊是民生路2段」抽出「我這邊是民生路2段」，含人稱被 `looks_like_real_road` 整個否決 → 路名 None → 覆誦後倒退問「請問是什麼路？」。

新增 `_ROAD_FILLER_CHARS`，剝掉路名前緣連續的口語用字：

```
我你妳他她牠它們這那個的了是不在到就跟幫請欸呃嗯喔啊哦嘿啦吧呢嗎邊裡裏
```

⚠️ **這張表刻意不收任何可能當路名開頭的字**（中民光忠仁信和大新長文復興南北東西三五永青自由成功明德福有…），剝過頭就是⑩-6 的「中山北路」→「北路」。另外只在「目前的值不合格時」才剝，合格的值一個字都不動。

同批補了三個判準：疑問詞（什麼／哪／怎）與「路人」列入 `_ROAD_REJECT_TOKENS`；「馬路／路口／道路」等通稱列入 `_GENERIC_ROAD_WORDS`（只擋完全相等）；路名主體（路／街／大道之前那段）**全由贅詞字組成**時不算路名（擋「那個路」，比逐一列舉可靠）。

408 通 1659 句 A/B：10 句由 None 變成正確路名，**0 句回歸**。

**⑩-33 addrCheck 否決過的候選不得復活 — 2026-09-06**：`_best_candidate_address()` 挑選只比「哪個字多」。LLM 整合出來的地址往往最長，被 API 判 `not_found`／`road_only` 之後，仍會在 `_restore_best_candidate()` 被選為「最完整的候選」寫進 `case.address`。加上 `_API_REJECTED_REASONS` 過濾。

`api_status` 為 `None`（還沒驗過）**不算**否決，仍可復活——09-02 那通還原第一次講的有效地址就是靠這條路徑。

> 這個漏洞是⑩-32 打開的：測試用的假路名「不存在路」原本因為含「不」被路名 regex 擋掉，根本走不到記錄候選那一步，`test_llm_result_rejected_when_api_invalid` 一直是**巧合**通過的。

自檢：

```bash
cd ai/119_0904_addrflow
PYTHONPATH=. python -c "
from sop_utils_119 import extract_address_district as d, extract_address_number as n
assert d('救護車在那個鶯歌。') == '鶯歌區'
assert d('我要送台大金山。開刀。') is None      # 醫院名
assert d('中山北路二段100號') is None          # 路名前綴
assert n('我那個115年3月。23號叫救護車') is None  # 日期
print('ok')"
```

```bash
PYTHONPATH=. python -c "
from sop_utils_119 import extract_address_road as r
assert r('我這邊是民生路2段。兩百。號之18樓。') == '民生路2段'
assert r('中山北路二段') == '中山北路二段'      # 不得剝成北路
assert r('他躺在中山北路二段') is None          # 敘述動詞仍作廢
assert r('我不知道什麼路欸') is None            # 疑問詞
assert r('他就在馬路旁邊。') is None             # 通稱
assert r('就在那個路口') is None                # 主體全是贅詞字
print('ok')"
```

**⑩-34 講了卻沒進地址的細節要回頭問 — 2026-09-06**：STT 把「200之1號8樓」拆成「兩百。號之18樓」，規則只撿得到門牌號，覆誦就唸成「200號」，得等報案人自己發現、自己更正——那是把校對工作丟給正在急著求救的人。`dropped_address_details()` 比對原話與組出的地址，缺哪個問哪個：

| 缺 | 問句 |
|---|---|
| 之N ＋ 樓層 | `剛剛沒聽清楚，是幾號之幾？幾樓？` |
| 只缺之N | `{門牌}號之幾呢？` |
| 只缺樓層 | `ASK_FLOOR` |

只在原話裡真的有、地址裡真的沒有時觸發，整通只問一次（`_dropped_details_asked`），樓層那半還要先過 `_should_ask_floor()`。

**⑩-35 補述不得吃掉路名 — 2026-09-06**：覆誦「民生路二段200號」後報案人更正「200之1號8樓」，逐輪 LLM 抽出的片段沒有路名，`merge_address` 只保留**區名**前綴：

```
merge("新北市板橋區民生路二段200號", "200之1號8樓")
  → "新北市板橋區200之1號8樓"        ← 路名整段消失 → 下一句問「請問是什麼路？」
```

`_keep_road_prefix()` 把前綴保留到**完整路名**。⚠️ 必須用 `extract_address_road()` 而不是 `_extract_road_core()`——後者只回「民生路」，「二段」還是會丟。同批修掉區名重複（`_needs_prefix()` 比對用「板橋區」而非「新北市板橋區」，否則組出「新北市板橋區板橋區民生路…」）。

**⑩-36 LLM 路徑也要受地址鎖約束 — 2026-09-06**：`_address_locked` 只擋規則路徑（`_apply_location_rules`）。派遣後的閒聊一樣會進 `extract_slots`，所以那道「地址流程結束後不再改寫」的保護，只要 LLM 有輸出就形同虛設。`_apply_extracted_fields` 的 address 分支補上同樣的檢查。

同批：地址被**整個換掉**時 `location_type` 要跟著走（`_adopt_llm_location_type`）。`location_type` 走「空欄位才填入」的字串規則，一旦是 `address` 就改不動；內容換成地標名、型別卻停在 address，拿地標去做門牌驗證必然查無。

**⑩-37 型態判不出來時改用 addrCheck 自動判斷 — 2026-09-07**：`classify_location_type()` 回 `None` 時，`_refresh_location_type` 原本預設成 `address`，於是用 `type=House` 去查。實測學校類地標在 House 層**全數查無**、自動層**全數命中**：

```
板橋國小      House → 查無「國小」          Auto → 文化路一段23號
板橋高中      House → 查無「高中」          Auto → 文化路一段25號
南山高中      House → 是否為南山路？        Auto → 中和區南山高中
土城清水國小   House → 是否為清水路？        Auto → 土城區清水國小
陸光新城      House → not_found            Auto → not_found（一致）
```

House 層會把「板橋國小」切成「國小」去找路名。API 自己也在提示：「指定 type=House，但文字中找不到路名，請確認分類或改用 **Auto**」。

新增 `_probe_location_type()`：不帶 type 查詢，用 `landmark_layer_from_hint()` 從 hint 開頭反推命中哪一層（地標比對成功／地址有效／國道定位成功／…交會）。查無就退回 `address` 並**寫回 case**，同一個地址不會重複探測。命中地標時結果直接交給 `_validate_landmark_like`，不多打一次 API。

> 這也讓「`_is_landmark_only` 的 19 個關鍵字不全」不再是安全問題——不用去猜還漏了國中、大學、幼兒園、國宅…，交給 addrCheck。

**⑩-38 純區名／縣市名不送驗 — 2026-09-07**：⑩-37 的前提。自動層會盡力配一個地標給你且回 `valid`：

```
五股區 → valid → 五股區公所
新北市 → valid → 樹林區「新北市肉品市場」
```

`is_bare_district_or_city()` 擋掉。報案人只講到區，正確反應是繼續問路。

**⑩-39 映射表的通用名詞與疊加替換 — 2026-09-07**：⑩-37 一開始沒有用，因為映射在探測**之前**就把名字改壞了。`map_other_road.json` 有三筆通用名詞當鍵：

```
"國小" → "插角國小"   板橋國小 → 板橋插角國小、土城清水國小 → 土城清水插角國小
"大道" → "縣民大道"   新北大道 → 新新北大道、台灣大道 → 台灣縣民大道
"社區" → "尖山湖"     五股區社區活動中心 → 五股區尖山湖活動中心
```

兩個判準分開處理：

1. **通用名詞當鍵** → 排除清單 `scripts/map_other_road_exclude.json`（沿用 map_street 的作法，vendor 覆蓋原檔不受影響）
2. **目標名稱已在原文裡就不替換** → 通則，一次擋掉表上 15 筆「鍵是自己值的子字串」的條目。「北大道→新北大道」碰上「新北大道」跳過；「冷飯→冷飯坑」碰上「冷飯坑」也不會變「冷飯坑坑」，但輸入真的是「冷飯」時仍會補全

408 通 1659 句 A/B：映射結果改變 **6 句，全部是修好原本被改壞的文字，0 回歸**。其中兩句「新新北大道→新北大道」正是 vendor 報告裡那通火警（09-04 20:57）的病根，同型態從另一張表冒出來。

**⑩-40 正規化過的地址不得被原話蓋回去 — 2026-09-07**：實測 17:04，報案人說「永和區永鎮路128號」，addrCheck 回「查無此路名，已依讀音修正為永貞路128號」。流程採用永貞路、覆誦也唸永貞路、報案人答「對」——然後**逐輪 LLM 從原話又抽一次「永鎮路」把它蓋回去**：

```
merge("新北市永和區永貞路128號", "新北市永和區永鎮路128號")
  → "新北市永和區永鎮路128號"     ← 存檔存了一條不存在的路，狀態卻是 valid
```

`_is_same_place_as_current()`：寫入前拿映射表正規化新地址，等於現在這個就跳過（映射表本來就知道永鎮路→永貞路）。報案人真的改地址時兩者不會相等，擋不到正常更正。

同批：`_fill_components_from_address(overwrite=True)`。原本「已有值不動」，所以 `address_road` 還停在「永鎮路」——受理員會看到不存在的路名，`_rebuild_street_address` 也可能拿它把地址組回錯的。地址被整個換掉之後（讀音修正、LLM 整段重判）一律重抽。

**⑩-41 讀音修正要標記給受理員 — 2026-09-07**：addrCheck 的 hint 自己就寫著「注意：兩者讀音相同，向報案人複述路名無法分辨，如需確認請改問門牌號、樓層或附近路口」。AI 唸「永貞路」、報案人答「對」，那個「對」不具鑑別力。

新增 case 欄位 `address_corrected_note`，走 `to_dict()` 由 `case_update` 事件帶給前端：

```
系統依讀音將「永鎮路128號」修正為「新北市永和區永貞路128號」；
兩者讀音相同，覆誦無法分辨，如需確認請問門牌號或附近路口
```

**不攔流程**——API 只在「本轄同音路名僅此一條」時才修，沒有第二個候選會弄錯，不值得為它多問一輪。提示文字沿用 API 自己的建議。已列入 `filled_fields_for_summary` 的排除清單，不進摘要 prompt。

自檢：

```bash
cd ai/119_0904_addrflow
PYTHONPATH=. python -c "
from sop_utils_119 import is_bare_district_or_city as b, landmark_layer_from_hint as l, merge_address as m
from address_hint_119 import phonetic_correction_note as n
from address_mapper_119 import get_location_mapper
assert b('五股區') and b('新北市') and not b('板橋區文化路')
assert l('地標比對成功：地標：板橋國小 → 新北市板橋區文化路一段23號') == 'landmark'
assert m('新北市板橋區民生路二段200號','200之1號8樓') == '新北市板橋區民生路二段200之1號8樓'
assert get_location_mapper().map_location('板橋國小') == '板橋國小'
assert get_location_mapper().map_location('新北大道一段100號') == '新北大道一段100號'
assert n('「永鎮路128號」查無此路名，已依讀音修正為「新北市永和區永貞路128號」')
print('ok')"
```

⚠️ **這個修正的意義是安全等級**：修正前組出「大觀路1段28巷28號」，而該門牌**恰好存在**（臨28號），API 回 `valid` 一路過關直接派遣——**地址錯了卻沒有任何警訊**。修正後組出正確的「28巷6弄4號」，API 回查無，標記讓受理員確認。

**⑪ systemd `sop119.service` env**：`WorkingDirectory`→新版；`ADDRCHECK_API_URL=http://100.107.145.7:8088` + `ADDRCHECK_API_TOKEN` + `ADDRCHECK_API_TIMEOUT=2.5`（0901 起不需 `JURISDICTION_API_URL`）；其餘 `GGUF_MODEL_PATH`/`BERT_MODELS_BASE`/`LOG_DIR`/`BERT_DEVICE` 不變。

**⑫ 模型目錄 / 換子分類模型**：子分類統一用**無後綴**目錄名 `TW-119-BERT-sub_{救護|火警|緊急救援}` 當「原版檔名」。
**換新模型慣例：原版目錄改名 `_bak_<日期>`、新版內容放進無後綴原檔名，`_MODEL_DIRS` 路徑不用改。** 例：0903 換火警 → 無後綴 `火警`(13類) 改 `火警_bak_0903`、`火警_v5`(21類) 放進無後綴 `火警`。
⚠️ **vendor 從 0901 起把火警 `_MODEL_DIRS` 寫成 `火警_v2`（多後綴、偏離無後綴慣例），每次換版必須 sed 改回無後綴**：
```bash
sed -i 's#TW-119-BERT-sub_火警_v2#TW-119-BERT-sub_火警#g' classifier_with_llm.py
```
救護本來就無後綴（vendor 正確）、緊急救援靠 ① 補註冊。

### 每次實測後：把新通話加進測試集（**例行工作，不要跳過**）

真實通話是最有價值的測試資料——每一通都帶著 STT 的真實錯法。**每批實測後都要把
新通話加進 `tests/data/real_calls_119.json`**，否則下次改動時無法確認會不會破壞
先前修好的規則。實際發生過：改「去標點抽巷弄」時，fixture 裡的舊通話立刻抓到
「蘆洲成功國小旁邊。長安街」被連成一個路名。

```bash
cd ai/119_09XX_xxx
# 1. 看每句的實際抽取結果，逐句人工判讀期望值
PYTHONPATH=. ../../llmenv/bin/python -c "
import json; from sop_utils_119 import extract_street_address_components as X
d=json.load(open('/home/cyberon2/nlp_cyberon_server/log_119/case119_XXXX.json'))
for t in d['transcript']:
    if t['role']=='caller': print(repr(t['text']), X(t['text']))"

# 2. 把該通加進 scripts/build_real_call_fixture.py 的 EXPECTED
#    （原話 → 期望區/路/號；純敘述句或巷弄補述三項填 None）
#    順便把該通的完整地址加進 PROBE_ADDRESSES

# 3. 重新產生 fixture（需要 addrCheck env）
ADDRCHECK_API_URL=… ADDRCHECK_API_TOKEN=… \
  PYTHONPATH=. ../../llmenv/bin/python scripts/build_real_call_fixture.py

# 4. 跑測試
PYTHONPATH=. ../../llmenv/bin/python -m unittest tests.test_real_calls_119
```

⚠️ **期望值要人工判讀，不能把當下行為錄下來**——錄行為會把錯誤一起鎖進測試。
判讀原則：這句話裡報案人**實際講出來的**地址元件是什麼。抽不到的（如 STT 把
路名斷成「明里。路」）就照實填 `None` 並在說明裡註記是已知限制。

2026-09-06 現況：15 通 / 32 句 / 16 筆 API 快照。

### 離線重放（切 systemd 前的低風險驗證）

拿 `log_119/case119_*.json` 的報案人回答重放地址流程，比對新舊版差異。無 LLM（只驗規則路徑）、打真實 addrCheck、**不動線上服務**。腳本見 §7 踩雷的說明；2026-09-04 用 226 通實跑的結果：

| 指標 | 0903 → 0904 |
|---|---|
| 型態 | 通數 | 改善 | 回歸 | 例外 |
|---|---|---|---|---|
| address | 120 | 3 | 0 | 0 |
| （未判定）| 77 | 1 | 0 | 0 |
| landmark | 15 | 0 | 0 | 0 |
| highway | 5 | 0 | 0 | 0 |
| mrt | 5 | 0 | 0 | 0 |
| intersection | 2 | 0 | 0 | 0 |

提問總數平均 3.37 → 4.29（最大 7 → 8，未超出預算 10）；地址資訊變多 58 通、變少 4 通（皆為地標解析成真實地址或少了「新北市」前綴）。

⚠️ **重放證明不了五步流程的核心價值**：hint 導向問句（「這條路好像沒有3號欸」）需要真人回答才有意義，重放時餵的是原通話對「別的問題」的回答，答非所問。重放能證明的是「不會炸、不回歸、提問不失控」——三個既有缺陷（⑩-7/⑩-8/⑩-9）都是這樣抓出來的。

### 未來提升項目：非新北市地址的識別

**現況（2026-09-04，刻意不處理）**：本專案只受理新北市，addrCheck 也只有新北市地址庫。報案人講其他縣市地址時：

```
台北市信義區松高路1號
  → 行政區合法，不被歸一化改寫（§3.5⑩-7 的保護）
  → 照送 addrCheck → 查無
  → 打「地址搜尋失敗」標籤 + address_error_reason，流程繼續問案情
  → 由前端受理員判斷是否轉接（引擎不轉真人，這是 0813 起的設計）
```

`address_error_reason` 會帶完整脈絡讓受理員判讀：
`查無此路段｜報案人講過：台北市信義區松高路1號｜系統提示：查無「松高路」，是否為 新北市新店區寶高路…`

**可提升之處**：目前只能靠受理員從 reason 看出「這是外縣市」。日後可加主動識別——抽到的縣市非新北市時，直接標記「非受理轄區」而不是走一輪查無。§3.5⑩-7 的 `_KNOWN_DISTRICTS` 已含臺北／基隆／桃園區名，是現成的判斷依據。

⚠️ **統計時要留意**：拿 `log_119` 做離線重放比較版本時，非新北市的**門牌地址**會恆為查無，混進去會低估通過率。地標／國道／捷運／路口則**一律保留**（那些型態不受縣市限制，且引擎分支不同，必須驗證）。2026-09-04 的 226 通樣本中，符合排除條件的只有 2 通。

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
- **改到不是線上跑的那份**：換版後 `WorkingDirectory` 已指向新目錄，但人還在舊目錄改 code，改完測試全過卻完全沒生效。**動手前先確認線上進程真正的 cwd**：
  ```bash
  ls -l /proc/$(systemctl show sop119.service -p MainPID --value)/cwd
  ```
  2026-09-02 的地址修正就是改在 `119_0901_FireDispatchCard`，而線上早已切到 `119_0903_addr_fixbug`，兩天後才發現。
- **vendor 版覆蓋掉客製修改**：§3.5 的每一項在換版時都會被 vendor 版蓋掉。換版後用這組 grep 自檢（都該 > 0）：
  ```bash
  grep -c _KNOWN_DISTRICTS sop_utils_119.py          # ⑥ 行政區名單
  grep -c strip_road_fillers sop_utils_119.py        # ⑥ 路名贅詞
  grep -c _address_locked sop_119_engine.py          # ⑦ 地址鎖
  grep -c addrcheck_failure_reason sop_119_engine.py # ⑤ reason 接引擎
  grep -c _NON_DISTRICT_WORDS sop_utils_119.py       # ⑧ 非行政區詞
  grep -c DISTRICT_FUZZY_MIN_SCORE address_mapper_119.py  # ⑧ 音近門檻
  grep -c _district_guess sop_119_engine.py          # ⑧ 猜測覆誦/還原
  grep -c looks_like_pregnancy_count sop_utils_119.py # ⑨ 胎數≠人數
  grep -c _SUB_REASK_QUESTIONS sop_119_engine.py     # ⑩ 重問換句
  ls address_hint_119.py                             # ⑩-2 hint 模組（整檔複製）
  grep -c _resolve_street_address sop_119_engine.py  # ⑩-2 五步流程
  grep -c _ADDRESS_ASK_BUDGET sop_119_engine.py      # ⑩-2 提問預算
  grep -c parse_landmark_hint sop_119_engine.py      # ⑩-4 地標模糊比對確認
  ls fuzzy_match_log_119.py                          # ⑩-6 取樣模組（整檔複製）
  grep -c _session_tag sop_api_server.py             # ⑩-6 取樣的 session 標記
  grep -c is_known_district address_mapper_119.py   # ⑩-7 合法區名保護
  grep -c _restore_best_candidate sop_119_engine.py # ⑩-8 回到最完整候選
  grep -c is_uncertain_answer sop_119_engine.py     # ⑩-9 「不知道」不算確認
  grep -c _street_mapping_enabled sop_119_engine.py # ⑩-16 街路映射延後
  ls scripts/map_street_exclude.json                # ⑩-17 排除清單（要 port）
  grep -c normalized_address_from_hint sop_119_engine.py # ⑩-18 採用 API 正規化地址
  grep -c _merge_lane_into_road sop_119_engine.py   # ⑩-21 巷弄併回路名
  grep -c strip_district_prefix_from_road sop_utils_119.py # ⑩-22 路名去重區名
  grep -c extract_road_section sop_utils_119.py     # ⑩-23 段的補述併回
  grep -c consolidate_address llm_extractor_119.py  # ⑩-24 LLM 整段對話整合
  grep -c _HINT_CONFIRMS sop_119_engine.py          # ⑩-25 引導式保留已確認元件
  grep -c _KNOWN_CITIES sop_utils_119.py            # ⑩-10 縣市白名單
  grep -c MAX_USABLE_ADDRESS_LEN sop_utils_119.py   # ⑩-10 地址長度上限
  ls tests/data/real_calls_119.json                 # ⑩-11 真實通話測試資料
  grep -c looks_like_real_road sop_utils_119.py     # ⑩-12 敘述句不當路名
  grep -c addr_before_confirm sop_119_engine.py     # ⑩-13 覆誦時換址要重驗
  # 下面這行應只剩註解／欄位標籤／測試字串，不該有錯誤訊息用到「管轄」
  grep -rn 管轄 --include=*.py .
  ```
- **既有的 6 項測試失敗（不是新壞的，換版時可對照）**：`test_jurisdiction_requires_nonempty_office_name` / `test_jurisdiction_empty_office_is_invalid`（vendor 舊測試仍期望分局名，0901 起 119 不取）、`test_intersection_reasks_for_second_road`、`test_classifier_loads_fire_v2`（期望 `火警_v2`，與 §3.5⑫ 的無後綴慣例互斥，照 runbook 做它必紅）、`test_landmark_loader_supports_aliases` / `test_real_mrt_csv_uses_second_column_cp950`（斷言不存在的地標要回 False，但 API 無門檻比對會硬配 → 這兩項其實是 §3.5⑩-4 的來源）。改動前後比對失敗清單，只要沒新增就是安全的：
  ```bash
  PYTHONPATH=. ../../llmenv/bin/python -m unittest discover -s tests -p "test_*.py" 2>&1 | grep -E "^FAIL:" | sort
  ```
- **地址欄位自相矛盾要當紅旗**：case 的 `address` 與 `address_district/road/number` 對不起來（例：address=國泰醫院 但元件是土城區亞洲路3號），代表 address 被後段對話覆寫過。看 case JSON 時這是最快的異常訊號。

## 版本沿革

| 日期 | 版本 | 重點 |
|---|---|---|
| 2026-07 | 119_0625_code → 119_0721_v2 | 引擎升級 handlers 化；hangup 改 END_FLOW_SENTINEL；case 用 to_dict |
| 2026-07-30 | 119_0721_v2 → 119_0724_add_2maincategory | 新增火警/緊急救援兩主類別流程；case_info +6 火警欄位；API 介面不變。上線驗證：火警分類 conf 0.999、火警欄位正常抽取 |
| 2026-09-04 | 119_0903_addr_fixbug（線上） | 地址三修：①行政區/路名口語贅詞防護（§3.5⑥）②地址鎖，防地標字樣覆寫已派遣地址（§3.5⑦）③addrCheck reason 接引擎，錯誤說明改「查無此門牌/查無此路段」（§3.5⑤）；④STT 誤聽防護：非行政區詞濾除、音近比對加門檻、猜測必須覆誦確認否則還原（§3.5⑧）⑤胎數不計入傷患數（§3.5⑨）⑥子分類重問換句（§3.5⑩）。新增 `tests/test_address_regression_119.py`（25 項，鎖兩起真實事故）。全套 162 測試，失敗數與改動前基線相同（6 項既有） |
| 2026-09-04 | 119_0903_addr_fixbug → **119_0904_addrflow**（**尚未上線**） | 一般門牌地址改五步流程（§3.5⑩-2）＋話術口語化（§3.5⑩-3）。新增 `address_hint_119.py`（hint 解析／話術／樓層規則表）與 `tests/test_address_five_step_119.py`（17 項）。兩起真實事故端到端重跑：09-02 贅詞案一次通過、09-04 亞洲路案靠 hint 問出正確門牌後派遣（預算 2/10）。另修：地標／捷運模糊比對必須向報案人確認（§3.5⑩-4，API 端無門檻比對會把「捷運頂埔站」配成「捷運新埔站」）、地下樓層 B1 不再遺失（§3.5⑩-5）。另新增模糊比對取樣 `fuzzy_match_log_119.py`（§3.5⑩-6，累積 confirmed/denied 樣本供日後調 API 門檻）。另修三項既有缺陷（合法行政區被改寫 §3.5⑩-7、失敗時地址被削殘 §3.5⑩-8、「不知道」被當成確認 §3.5⑩-9）。全套 204 測試，失敗數與 0903 基線相同（6 項既有）；226 通真實通話離線重放零回歸。⚠️ 上線前需走 §2 的 Step 4～6 驗證 |
