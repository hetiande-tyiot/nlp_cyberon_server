# `/result` 對話中欄位沒呈現的 debug 紀錄（機器 B → 機器 A）

> 日期：2026-06-01
> 對應前次需求文件：`shared_with_A/result-during-call-for-machineB.md`（已實作回 partial case）
> 對應前次需求 follow-up：機器 A 端實測前端只看到 `act_sub_class` 出現，其他欄位「沒抓取更新」

## 摘要

機器 A 觀察：通話中前端只看到案類（`act_sub_class`）有出現，其他關鍵欄位（地點、車輛、違停方式、case_summary 等）「沒抓取自動填入」。

**機器 B 端反向驗證：server 端有抓到 8 個欄位、含完整 case_summary。問題不在 NLP 抽取本身，疑似在機器 A → 機器 C 推送鏈或 poll timing。**

請機器 A 端協助診斷以下幾個方向。

---

## 機器 B 端實測：server 抓到的欄位（**真的有**）

以你們 2026-06-01 17:23-17:24 跑的 session `0eb23cf7-7aab-461c-9d2e-a9e5b916f3f1` 為例，從機器 B 本機 case JSON log 看：

📁 `/home/aitop4/nlp_cyberon_server/log/case_20260601_172443_0eb23cf7.json`

```
非空欄位 (8 個)：
  act_sub_class            : 違規停車
  case_summary             : 新莊區中正路有白色TOYOTA車輛違規停車，車牌A B C1234，車輛停在紅線並擋住公車站牌。
  location                 : 新莊區中正路
  incident_desc            : 你好，我要檢舉違規停車。
  parking_location_precise : 新莊區中正路
  parking_violation_style  : 停在紅線擋住公車站牌
  parking_traffic_impact   : 紅線擋住公車站牌
  parking_vehicle_info     : 白色所有塔 A B C1234     ← STT 把 "Toyota" 識別成 "所有塔"、車牌帶空格
```

對應的 transcript（10 turns，含 SOP 引擎自動走完流程後 done=true）：

```
[assistant ] 新北市警局 110 您好
[caller    ] 你好，我要檢舉違規停車。
[assistant ] 請問違規停車的具體位置在哪裡？...
[caller    ] 在新莊區中正路。
[assistant ] 請問車輛是怎麼違停的？例如併排、紅線、停在人行道...
[caller    ] 請在紅線擋住公車站牌。
[assistant ] 請問違規車輛的廠牌、顏色及車牌號碼是多少？
[caller    ] 嗯，白色所有塔。車牌A B C1234。
[assistant ] 請問違規車輛的廠牌、顏色及車牌號碼是多少？     ← LLM step 重問一次
[caller    ] 白色的TOYOTA。
```

→ **8 個欄位都在 server 的 case dict 內**，case_summary 也整合好整段資訊。

---

## 三個可能的原因（請機器 A 端逐一檢查）

### 假設 1：機器 A 端前端只 binding `act_sub_class`，其他欄位沒對應 UI

**機率最高**，因為這跟「只看到案類有更新、其他沒更新」的觀察吻合。

**檢查方式**：
- 機器 A → 機器 C 推送的 payload 是含**所有 130+ 欄位**還是**特定欄位 subset**？
- 機器 C 的「Analysis Updated」UI 卡片**綁哪些欄位**？是否只有 `act_sub_class` 有 UI 元素、其他欄位 dropped？
- 把機器 A 推給機器 C 的真實 payload 印一次出來，看跟上述 8 欄位是否對得起來

### 假設 2：機器 A 端 poll `/result` 太早，bg refresh 還沒跑完

**機率中**。每次 `/input` 之後 server 端會 fire-and-forget 一個背景 thread 跑 LLM post-extract + summary，大約**需要 1-3 秒**才完成。

**檢查方式**：
- 機器 A 端在 `/input` 收到 response 後**立刻** poll `/result`？
- 從 journal 看（17:23:35, 17:23:53, 17:24:13, 17:24:29 等）你們確實**每次 input 後 1 秒內 GET /result**，那次 GET 多半 bg refresh 還沒跑完，只能拿到 SOP step extract 抽到的（act_sub_class + step 對應 slot）

**建議**：
- (a) 每次 `/input` 後 sleep 2-3 秒再 poll 一次；或
- (b) 同一 session 每秒 poll 一次，看欄位變化（dedup 邏輯已在你們端，重複 poll 沒副作用）

### 假設 3：你看的是 in-flight 那個瞬間、不是 final

**機率低**，但可以排除一下。每通電話結束（done=true）的最後一個 `/result` response 應該是最完整的。

**檢查方式**：
- 把通話結束後最後一次 `/result` 拿到的 payload **整份 dump** 給我看，跟上述 8 欄位對照

---

## 機器 A 端可做的測試（**任選一個就好**）

### 測試 A（最快）：直接 dump payload

在機器 A 的 api_server 內，把每次 `GET /result` 拿到的 response 整個 `log.info(json.dumps(resp))`，下次測試完跑一次：

```bash
grep "result response" /var/log/api_server.log | tail -20
```

把最後幾筆貼到 shared_with_A 給機器 B 看。可以馬上判斷是 client parse 問題還是 timing 問題。

### 測試 B：用 curl 直接打 /result 比對

機器 A 端用 curl 直接打機器 B 的 `/result` endpoint，看回應：

```bash
SID=<最近一通的 session_id>
curl -s http://192.168.5.204:8100/session/$SID/result \
  | python3 -m json.tool --no-ensure-ascii | head -30
```

如果 curl 拿到的跟前端顯示的不一致 → 100% 是機器 A→C 之間問題。

### 測試 C：用機器 B 提供的 sniff script

如果要看「in-flight 期間欄位**何時**出現」，告訴我，我可以給你一個小 bash script 在背景每秒 poll 一個 session、把 non-null 欄位 diff 印出來，這樣能精準看到 bg refresh 是不是 ~3 秒後才把欄位塞進去。

---

## 機器 B 端確認的狀態（FYI）

| 項目 | 狀態 |
|---|---|
| `/result` 在 `done=false` 也回 partial case | ✅ 5/30 啟用 |
| bg refresh（每 `/input` 後背景跑 LLM post-extract + summary） | ✅ 6/1 啟用 |
| `case_summary` 對話中逐輪更新 + hangup 時 fresh regenerate | ✅ 6/1 修好 |
| 130+ 欄位 schema 沒變、機器 A 端 client 不必動 | ✅ |
| GPU VRAM 跟 service 狀態都健康 | ✅ |

---

## 對應的歷史文件

- `shared_with_A/result-during-call-for-machineB.md` — 5/29 機器 A 提需求、5/30 機器 B 實作
- `shared_with_A/partial-case-fields-not-showing-for-machineA.md` — **本文件**

任何問題傳訊給機器 B 端負責人，或直接寫進 `shared_with_A/` 內任意檔案（會自動 sync 過來）。
