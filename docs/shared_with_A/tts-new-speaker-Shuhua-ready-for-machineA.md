# 新聲紋交付：Shuhua（給機器 A）

> 日期：2026-07-13
> 依據：`tts-speaker-naming-convention.md`

## speaker 字串

```
Shuhua
```

（區分大小寫，放進 `TtsRequest.speaker`）

## 描述

| 項目 | 值 |
|---|---|
| 性別 | 女 |
| 風格 | 年輕女聲、口語自然 |
| 語言 | 中文（zh-TW） |

## backend 支援

| backend | port | 支援 |
|---|---|---|
| F5 adapter | 8089 | ✅ |
| Cyberon | 8088 | ❌（Cyberon 端無此聲紋） |

→ F5 專屬聲紋，須把 TTS endpoint 指向 :8089。

## reference 來源

中文口語錄音節錄 14.5s（24kHz mono）。參考音檔本身是中文，
克隆中文的先天條件良好。

## 交付狀態提醒

⚠️ **此聲紋 B 端尚未做完整克隆試聽驗證即交付**（依使用者要求先發）。
建議 A 端建 filler pack 前先用 1~2 句 sanity 試聽確認音質可接受，
再決定是否正式納入配方。若有 loop / 含糊 / 腔調等問題，回報
`tts-speaker-Shuhua-issue-<描述>-for-machineB.md`。

任何問題傳訊給機器 B 端負責人。
