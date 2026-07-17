# 新聲紋交付：Malevoice（給機器 A）

> 日期：2026-07-13
> 依據：`tts-speaker-naming-convention.md`

## speaker 字串

```
Malevoice
```

（區分大小寫，放進 `TtsRequest.speaker`）

## 描述

| 項目 | 值 |
|---|---|
| 性別 | 男 |
| 風格 | 沉穩、中性、約 40 歲語感 |
| 語言 | 中文（zh-TW） |

這就是 F5 adapter 從單聲紋時期沿用至今的預設男聲（原 `malevoice.wav`）。
現在正式登記成可具名選取的 speaker，同時**仍是所有未註冊 speaker 的 fallback**。

## backend 支援

| backend | port | 支援 |
|---|---|---|
| F5 adapter | 8089 | ✅ |
| Cyberon | 8088 | ❌（Cyberon 端無此聲紋） |

→ 這是 F5 專屬聲紋。要用 Malevoice 必須把 TTS endpoint 指向 :8089。

## 已知特性

- 這個聲紋在 B 端經過最完整測試（前置 silence / 尾端重複 / speed 各 patch 都以它驗證）。
- 短句承接詞（嗯、好的…）speed 上限 1.2，長句不受限（見
  `tts-f5-short-prompt-tail-loop-fixed-for-machineA.md`）。

## reference 來源

使用者提供的男聲錄音，17.5s（F5 內部取前段建 voice embedding）。

任何問題傳訊給機器 B 端負責人。
