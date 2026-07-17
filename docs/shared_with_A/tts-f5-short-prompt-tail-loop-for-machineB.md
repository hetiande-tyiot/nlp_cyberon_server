# F5-TTS：特定短 prompt 尾端出現重複發音

> 日期：2026-07-10
> 相關：
> - `tts-f5-short-prompt-speed-fixed-for-machineA.md`（B 07-10 修 speed）
> - `tts-f5-short-prompt-leading-silence-fixed-for-machineA.md`（B 07-10 修前置 silence）

## TL;DR

前置 silence trim 那份 patch 已生效、聲音立刻出來、非常好。但實測 5 句
承接詞 speed=1.3 產出、**「我了解」與「請稍等」尾段可清楚聽到重複發音**、
另外三句（「嗯」「好的」「收到」）沒問題。像是 F5 生成期在收尾 phoneme
被 hallucinate loop。

## 影響情境

承接詞會在民眾停話當下播放、末尾多冒出一段重複的字非常突兀、感覺像
系統結巴。目前 A 端只能把這兩句從承接詞清單暫時拿掉、可用的只剩三句、
變化度太少（連續多輪對話會被聽出重複）。

## 實測

- speed=1.3、經過 07-10 head-trim patch 的 adapter：
  - 嗯：正常
  - 好的：正常
  - **我了解：尾段重複「解」音**
  - 收到：正常
  - **請稍等：尾段重複「等」音**

（無數據附檔、以試聽為準；B 端可用 `aplay` 或轉譯直接確認）

## 推測

F5 diffusion 對特定 phoneme 組合的收尾容易 loop、跟長度不完全相關
（「我了解」3 字有問題、「請稍等」3 字有問題、但同為 3 字的其他組合可能 OK）。
先前 B 端提過「嗯」純鼻音會讓 Whisper 反轉譯幻覺 loop、可能是同一類的
模型偏好、只是這次直接在生成端出現、而非後端 ASR。

## 期望

擇一：
- **(a) 調 F5 生成參數**：CFG scale、sampling steps、或 stop token 判斷、
  讓收尾更果斷不 loop
- **(b) adapter 加尾部去重偵測**：檢查最後 N ms 是否為前 N ms 的近似重複、
  若是就 trim
- **(c) B 端能提供「哪些短 prompt 會 loop」的經驗清單**：A 端避開這些字組
  也可接受

(a) 是根本解、(b) 是繞道、(c) 是最低成本 workaround。優先順序希望
(a) → (b) → (c)。

任何問題傳訊給機器 A 端負責人。
