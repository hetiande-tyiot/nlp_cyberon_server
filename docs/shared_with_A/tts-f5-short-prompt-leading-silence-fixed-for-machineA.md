# 已修復：F5-TTS 前置 silence 已在 adapter 層 trim（回覆 07-10 回報）

> 日期：2026-07-10
> 回覆：`tts-f5-short-prompt-leading-silence-for-machineB.md`

## TL;DR

採你們建議的方案 (a)：adapter 生成完自動 trim 前置 silence（保留 50ms 前導）再回。
**A 端不用改任何東西**，重新產一次承接詞即可。實測「嗯」總長從 0.52s 縮到
0.21s、聲音 50ms 內起音。

## 根因釐清（跟你們推測略有不同）

前置 silence **不是 07-10 fix_duration patch 造成的**。B 端實測對照：
speed=1.0（完全走 upstream 原始路徑、無 fix_duration）前置 silence 反而更長
（「我了解」1.33s、「請稍等」1.23s）。這是 F5 upstream 對短句強制 0.3 慢速
window 的固有行為——模型把聲音生在 window 尾端、前面填 silence。
長句也有少量（0.16~0.34s）前置 silence，一併受惠。

## 修法

adapter 在 gain 之後、編碼之前統一做 head-trim：
- threshold：該次輸出 peak 的 -40dB（相對值、不受底噪影響）
- 保留 50ms 前導（起音不突兀）
- 尾端實測本來就 ~0，不動
- **所有請求統一套用**（短句長句、各 outfmt 一致），不會有兩條路徑

## B 端實測（trim 後）

| 文字 | speed | 總長 | trim 掉 | 現在前置 silence |
|---|---|---|---|---|
| 嗯 | 1.3 | 0.21s | 0.31s | 50ms |
| 好的 | 1.3 | 0.47s | 0.59s | 50ms |
| 我了解 | 1.3 | 0.73s | 0.86s | 50ms |
| 收到 | 1.3 | 0.61s | 0.45s | 50ms |
| 請稍等 | 1.3 | 0.81s | 0.78s | 50ms |
| 請問是火災還是救護？（長句對照） | 1.3 | 1.42s | 0.16s | 50ms |

speed=1.0 版本同樣驗證 OK（trim 0.39~1.28s）。「好的」「請稍等」Whisper
反向轉寫正確；「嗯」是純鼻音、ASR 會幻覺 loop 屬正常、請以試聽為準。

## 生效時機

修改在 `tts_f5_server.py`，需要 restart 服務生效（B 端會處理）。
restart 完成後你們重跑 gen_fillers.py 重新預生承接詞即可。

任何問題傳訊給機器 B 端負責人。
