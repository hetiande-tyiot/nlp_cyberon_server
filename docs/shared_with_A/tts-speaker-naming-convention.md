# TTS 聲紋命名與交付共識

> 日期：2026-07-13
> 目的：定義新聲紋（speaker）在 A/B 兩端的命名規範與交付方式、避免後續每加一個聲紋都要重新對齊。

## 背景

- A 端呼叫 TTS 時、`TtsRequest.speaker` 欄位是**字串**、B 端 adapter 用這字串挑對應聲紋模型／reference audio。
- 目前只有 `Sharon` 一個聲紋（女聲）、B 端首發做出來時就用這名字，A 端從此寫死沿用。
- 未來雙方會加更多聲紋、需要一套穩定命名 + 交付流程、避免「B 生了但 A 不知道叫什麼」或「B 改名 A 就壞掉」。

## 命名規則

`speaker` 字串遵守以下規則：

1. **字母開頭、英文字母／數字／連字號組成**：例：`Sharon`、`Kevin`、`Amy-Warm`、`Guy02`
2. **首字大寫、駝峰或連字號分詞**：例：`Kevin`、`AmyWarm` 或 `Amy-Warm`；不用底線
3. **避免以下字元**：空白、中文、特殊符號、`.`、`/`
4. **一旦命名不要改**：A 端會把這名字硬編或列入配方、B 端改名 A 端就壞掉。若聲音需要調整、
   - 微調（音色小改、rescanning）→ **沿用原名**、A 端無需改動、直接受惠
   - 顯著改動（音色明顯不同）→ **另取新名**、原名保留一段時間（舊 pack 仍能用）

## 交付流程

當 B 端做好一個新聲紋，發一份文件到 `shared_with_A/`（Syncthing 目錄），檔名格式：

```
tts-new-speaker-<Name>-ready-for-machineA.md
```

文件內容至少包含：

- **speaker 字串**：A 端要放進 `TtsRequest.speaker` 的準確字串（區分大小寫）
- **性別 / 風格描述**：例「男性、沉穩、40 歲左右」、方便 A 端在 pack 命名與挑選時參考
- **backend 支援情況**：F5（`port 8089`）、Cyberon（`port 8088`）是否都可用
- **reference audio 來源**：（選填、方便日後查對）例「客服錄音節錄 5s」
- **試聽範例**（選填）：如果 B 端方便附一段 5~10s wav 到 Syncthing、A 端可直接聽

## A 端收到後的動作

1. 在 `ai/ami/gen_fillers.py` 的 `PACKS` 加一列、例如：
   ```python
   "kevin": {"speaker": "Kevin", "port": 8089},
   ```
2. `python3 gen_fillers.py kevin` 產成一個承接詞 pack
3. 需要時改 `ami/config.py` `FILLER_PACK = "kevin"` 切換
4. 若 A 端測試發現音質有問題（loop、silence、含糊等）、回覆一份
   `shared_with_A` → 但檔名放到 `shared_with_B/`（Syncthing 雙向）、
   格式 `tts-speaker-<Name>-issue-<描述>-for-machineB.md`

## B 端實作狀態（2026-07-13 更新）

F5 adapter（:8089）的 speaker 分派已實作，機制：

- `speaker` 字串（**區分大小寫**、須符合上面命名規則）對應 B 端
  `ai/TTS-F5/reference/speakers/<Name>.wav`；同名 `<Name>.txt` 放參考逐字稿（選配）
- **沒對到的 speaker → fallback 預設聲紋**（目前 = malevoice 男聲），不會報錯。
  所以 A 端現在送 `Sharon` 到 :8089 的行為不變
- 一個釐清：**F5 的 `Sharon` 從來不是 Cyberon Sharon 的聲音**，只是欄位被忽略時
  回的預設男聲。表格分開登記如下

## 現況登記

| speaker | 性別 | 風格 | F5 | Cyberon | 備註 |
|---|---|---|---|---|---|
| Sharon | 女 | 中性、清晰 | ⚠️ fallback | ✅ | Cyberon 首發聲紋；F5 端無此聲紋、送了會拿到 Malevoice |
| Malevoice | 男 | 沉穩、40 歲語感 | ✅ | ❌ | F5 預設男聲；**同時是所有未註冊 speaker 的 fallback**。交付：`tts-new-speaker-Malevoice-ready-for-machineA.md` |
| Shuhua | 女 | 年輕、口語自然 | ✅ | ❌ | 中文參考。⚠️ 交付前未完整試聽。`tts-new-speaker-Shuhua-ready-for-machineA.md` |
| Chaewon | 女 | 年輕女聲 | ✅ | ❌ | ⚠️ **韓文參考、合成中文恐有腔調**、交付前未實測。`tts-new-speaker-Chaewon-ready-for-machineA.md` |

未來 B 端每加一個聲紋、在這個表格加一列（雙方各自更新這份文件、Syncthing 會同步）。

## 沒有「查 speaker 清單」的 API

目前雙方沒有實作「列出所有可用 speaker」的 endpoint。清單就是這份文件的表格。
若未來雙方覺得有需要、B 端可以加 `GET /tts/speakers` 之類的、A 端啟動時抓一次快取——
但短期內用文件就夠。

任何修訂請雙方在這份文件上直接改、Syncthing 會自動同步、無需另發文件。
