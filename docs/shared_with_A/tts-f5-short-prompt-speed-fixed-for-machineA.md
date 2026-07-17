# 已修復：F5-TTS 短 prompt 現在 respect `speed`（回覆 07-10 回報）

> 日期：2026-07-10
> 回覆：`tts-f5-short-prompt-speed-ignored-for-machineB.md`

## TL;DR

已在 B 端 adapter 修復。**A 端不用改任何東西**，同一組 request 重測即可。
承接詞 `speed=1.2~1.3` 的需求可以達成，不需要 sox 後製 workaround。

## 根因

你們的推測方向正確。F5-TTS upstream 原始碼
（`f5_tts/infer/utils_infer.py` `_infer_basic`）寫死：

```python
local_speed = speed
if len(gen_text.encode("utf-8")) < 10:   # ≤3 個中文字
    local_speed = 0.3                     # 強制慢速，忽略呼叫方 speed
```

gen_text < 10 UTF-8 bytes（= 中文 ≤3 字）時強制 `local_speed=0.3`，
這是 upstream 防止超短句被唸太快糊掉的保守 heuristic。你們五個承接詞
（嗯 3B、好的 6B、我了解 9B、收到 6B、請稍等 9B）全部中招；
對照組 10 字句 30B 所以正常。這也解釋了 bytes ≈ 字數 × 常數的觀察。

## 修法（B 端 adapter）

不動 upstream 套件。adapter 收到短句時改走 F5 的 `fix_duration` 參數，
沿用 upstream 同一套時長公式、**保留 0.3 慢速基準（保音質），但把請求的
speed 乘回去**：

- `speed=1.0` 或長句（≥10 bytes）→ 完全維持原行為（回溯相容，bytes 不變）
- 短句 + `speed≠1.0` → 時長按 speed 等比縮放

## B 端實測（你們的測試矩陣）

| 文字 | speed=1.0 | speed=1.3 | 比例 |
|---|---|---|---|
| 嗯 | 0.67s | 0.52s | 1.29 |
| 好的 | 1.37s | 1.06s | 1.29 |
| 我了解 | 2.06s | 1.59s | 1.30 |
| 收到 | 1.37s | 1.06s | 1.29 |
| 請稍等 | 2.06s | 1.59s | 1.30 |
| 請問是火災還是救護？（對照） | 2.06s | 1.58s | 1.30 |

- speed=1.0 的時長跟你們量到的 bytes 完全吻合（嗯 0.67s ≈ 10752B @8k/16bit）→ 預設行為零變動
- 1.3 倍速的音檔用 Whisper 反向轉寫驗證仍清楚（「好的」「請稍等」都正確辨識）

## 生效時機

修改在 `tts_f5_server.py`，**下次 tts-f5 服務啟動時生效**。
如果你們測試時服務已在跑，跟 B 端說一聲 restart（`sudo systemctl restart tts-f5`）。

## 建議

承接詞預生時建議 speed 別超過 1.5——超短句本來就短，太快會影響聽感；
1.2~1.3（你們原本的需求區間）實測沒問題。

任何問題傳訊給機器 B 端負責人。
