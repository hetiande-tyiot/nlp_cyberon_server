# F5-TTS：短 prompt 不 respect `speed` 參數

> 日期：2026-07-10
> 相關：`docs/shared_with_B/tts-speed-gain-for-machineA.md`（B 端 07-07 給的 speed/gain 規格）

## TL;DR

F5-TTS Adapter（:8089）在**短句 prompt**（1~3 字）時、無論 `speed=1.0` 或 `1.3`
產出的 WAV 位元組數**完全一致**——`speed` 對短句沒作用。長句（>5 字）則正常 respect。

## 實測結果

機器A 側用 apiserver 的 `_tts_async` 直接送 `TtsRequest`、其他欄位固定
（`serviceName="e2e", outfmt="wav", language="zh-TW", speaker="Sharon", gain=1.5, token=...`）、
只切 `speed=1.0` 與 `speed=1.3`、8kHz/16-bit/mono 存檔：

### 短句（承接詞用途，5 句）

| 文字 | 字數 | bytes @ speed=1.0 | bytes @ speed=1.3 |
|---|---|---|---|
| 嗯 | 1 | 10752 | **10752**（相同） |
| 好的 | 2 | 21846 | **21846**（相同） |
| 我了解 | 3 | 32940 | **32940**（相同） |
| 收到 | 2 | 21846 | **21846**（相同） |
| 請稍等 | 3 | 32940 | **32940**（相同） |

觀察：短句 bytes ≈ `字數 × 10752`（常數 window）、speed 完全不改變輸出長度。

### 長句（對照組）

同一句「請問是火災還是救護？」（10 字）、runtime 實測：

| speed | bytes | 相對比例 |
|---|---|---|
| 1.3 | 27308 | 1.00 |
| 1.0 | 32940 | 1.21 |

長句 speed 從 1.3 → 1.0、bytes 多了 21%、`speed` 明顯有效。

## 推測

F5-TTS 對短 prompt 用固定長度的 generation window、window 內是否加速對總輸出無影響。
長 prompt 走另一條路徑、才實際依 speed 調整生成節奏。

## 影響範圍（機器A）

我方要預生一組「承接詞」音檔（1~3 字：嗯、好的、我了解、收到、請稍等）
用於 VAD 判斷民眾一句話結束當下、立刻墊話掩蓋 STT+NLP+TTS 延遲。
這幾句希望比正常對話語速再稍快（避免搶到後續 AI 回覆）、需要 `speed=1.2 ~ 1.3`。
目前 F5 無法達成、只能用預設語速。

## 期望

F5-TTS Adapter 對短 prompt 也 respect `speed` 欄位、行為與長 prompt 一致。

## 備援方案（若 F5 無法修）

機器A 這邊可以用 sox `tempo` 後製時間拉伸（pitch 不變）當 workaround、
但這樣就跟長句走 F5 內建 speed 兩條路、不理想、盡量希望 B 端統一。

任何需要補的資料傳訊給機器 A 端負責人。
