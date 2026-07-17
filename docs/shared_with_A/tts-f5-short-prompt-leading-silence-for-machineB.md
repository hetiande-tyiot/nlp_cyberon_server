# F5-TTS：短 prompt 前置 silence 過長

> 日期：2026-07-10
> 相關：`docs/shared_with_B/tts-f5-short-prompt-speed-fixed-for-machineA.md`（B 端 07-10 修好的 fix_duration speed 縮放）

## TL;DR

短 prompt（承接詞「嗯」「好的」「我了解」…）產出的 WAV **前段是 silence、
聲音壓在尾部**、實測前置 silence 甚至 ≥1s。承接詞用途下這個 padding 讓
「即時墊話」的效果失效。希望 B 端把 silence 改塞後面、或 adapter 產完自動
trim 前置 silence 再回。

## 影響情境

機器A 側承接詞流程：
1. VAD 判定民眾一句話結束當下（VAD 靜音達 800ms）
2. 立刻 Redirect `[ai-filler]` → `Playback(fillers/filler_N.wav)`
3. 期望：民眾停話 → 立刻聽到「嗯」→ AI 真回覆的 TTS 接管

現況：步驟 3 變成「停話 → 沉默 1s+ → 才聽到『嗯』」、承接詞本來要掩蓋
STT+NLP+TTS 延遲、反而自己貢獻 1s 靜音、效果反效果。

## 推測根因

07-10 修 short-prompt speed 那份 patch 是用 `fix_duration` 沿用 upstream
時長公式。fix_duration canvas 是固定 window、實際 voice 只佔一小段、
剩下的 window 被 silence 填滿；upstream 傾向把 silence 放前面。

## 期望

擇一：
- **(a) adapter 層 trim**：F5 生成完成後、adapter 從波形頭掃描第一個
  非 silence sample（例如 abs > 500 in int16、或 -40dB）、cut 掉前面
  再回 client。
- **(b) 改 silence 位置**：把 fix_duration 的 padding 改塞後面、
  保持 voice 從時間 0 開始。

(a) 對呼叫方最無感、不會改變總 API 行為；(b) 需要動 F5 upstream 邏輯、
可能較麻煩。建議走 (a)。

## 實測

以「嗯」為例、speed=1.3、產出 WAV 8kHz/16-bit/mono：
- 檔案總長：約 0.5s
- 前置 silence：約 ??s（B 端可用 sox stat 或 audacity 直觀看到）
- 實際「嗯」聲音：只在最後 ~0.15s

（我方沒直接量 silence 長度、只從播放體感描述；B 端可自行 sox stat 驗證）

## 備援方案（若 B 端無法修）

機器A 這邊 gen_fillers.py 加後製、trim 前置 silence（audioop 或 sox）。
但這樣會有兩條路徑不一致（runtime TTS 走 F5 原樣、承接詞走 A 端 trim）、
盡量希望 B 端統一處理。

任何問題傳訊給機器 A 端負責人。
