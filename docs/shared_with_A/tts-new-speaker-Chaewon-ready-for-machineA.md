# 新聲紋交付：Chaewon（給機器 A）

> 日期：2026-07-13
> 依據：`tts-speaker-naming-convention.md`

## speaker 字串

```
Chaewon
```

（區分大小寫，放進 `TtsRequest.speaker`）

## 描述

| 項目 | 值 |
|---|---|
| 性別 | 女 |
| 風格 | 年輕女聲 |
| 語言 | 參考音檔為**韓文** |

## backend 支援

| backend | port | 支援 |
|---|---|---|
| F5 adapter | 8089 | ✅ |
| Cyberon | 8088 | ❌（Cyberon 端無此聲紋） |

→ F5 專屬聲紋，須把 TTS endpoint 指向 :8089。

## ⚠️ 重大注意：韓文參考音檔，合成中文可能有腔調問題

reference 音檔內容是韓文（B 端轉寫確認：`안녕하세요…`）。F5 是 zero-shot
克隆，會沿用參考音檔母語者的發音與韻律習慣——**用韓文參考合成中文，很可能
出現外國腔、聲調異常**。B 端交付前尚未實測中文合成品質。

建議 A 端：**先用 1~2 句中文 sanity 試聽再決定是否採用**。若腔調不可接受，
兩個選項：
- 暫時不納入 filler pack（名字先保留登記，不動用）
- B 端改用該人的中文素材重錄 reference（**沿用 Chaewon 這個名字**即可，
  屬「微調」不需改名，A 端無感直接受惠）

## reference 來源

韓文口語錄音節錄 14.5s（24kHz mono）。

任何問題傳訊給機器 B 端負責人。
