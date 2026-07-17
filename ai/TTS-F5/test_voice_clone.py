"""F5-TTS 聲紋克隆測試：指定任意參考人聲，合成多句文字，聽聲紋像不像。

跑法:
    cd /home/aitop4/nlp_cyberon_server/ai/TTS-F5
    /home/aitop4/nlp_cyberon_server/aienv/bin/python test_voice_clone.py [ref.wav] [ref_text]

    ref.wav   參考人聲（5-15 秒、乾淨無背景音最佳），預設 reference/malevoice.wav
    ref_text  參考音檔的逐字稿（可省略；省略時 F5 內部用 Whisper 自動 transcribe，
              但中文自動辨識偶爾出錯會影響克隆品質，手動給逐字稿通常更穩）

輸出到 output_clone/<ref檔名>/gen_*.wav
"""

from __future__ import annotations

import os
import sys
import time

import soundfile as sf

from text_normalize import normalize_for_tts

_HERE = os.path.dirname(os.path.abspath(__file__))

REF_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "reference", "malevoice.wav")
REF_TEXT = sys.argv[2] if len(sys.argv) > 2 else ""

GEN_TEXTS = [
    "新北市警局 110 您好，請問哪裡發生什麼事？",
    "好的，我了解了，請您先保持冷靜，警員大約五分鐘內會到達現場。",
    "測試一二三 ，這是聲紋克隆的效果驗證，Listen and see if it sounds like the original voice。",
]

SEEDS = [123456]  # 想聽不同隨機性可加，例如 [42, 7, 1234] 123，888，2024
SPEED = 1.5   # 節奏緊湊感：1.0 正常，偏好乾脆俐落可試 1.1~1.2（範圍 0.5~2）


def main() -> int:
    if not os.path.isfile(REF_FILE):
        print(f"[ERR] 找不到參考音檔: {REF_FILE}")
        return 1

    info = sf.info(REF_FILE)
    print(f"參考音檔: {REF_FILE}")
    print(f"  {info.duration:.1f}s @ {info.samplerate} Hz, {info.channels} ch")
    if info.duration > 15:
        print("  ⚠️  超過 15 秒，F5 會截斷，建議剪成 5-15 秒的乾淨片段")
    print(f"參考逐字稿: {REF_TEXT!r}" + ("（空 → Whisper 自動辨識）" if not REF_TEXT else ""))

    out_dir = os.path.join(_HERE, "output_clone", os.path.splitext(os.path.basename(REF_FILE))[0])
    os.makedirs(out_dir, exist_ok=True)

    print("\n載入 F5-TTS_v1_Base …")
    t0 = time.time()
    from f5_tts.api import F5TTS

    f5 = F5TTS()
    print(f"  loaded in {time.time()-t0:.2f}s\n")

    for seed in SEEDS:
        for i, gen_text in enumerate(GEN_TEXTS, 1):
            gen_text = normalize_for_tts(gen_text)  # 數字→中文（110→一一零 等）
            print(f"--- seed={seed} gen {i}: {gen_text!r}")
            t0 = time.time()
            try:
                wav, sr, _ = f5.infer(
                    ref_file=REF_FILE,
                    ref_text=REF_TEXT,
                    gen_text=gen_text,
                    seed=seed,
                    speed=SPEED,
                )
            except Exception as e:  # noqa: BLE001
                print(f"  [ERR] infer failed: {type(e).__name__}: {e}")
                continue
            elapsed = time.time() - t0
            out_path = os.path.join(out_dir, f"gen_s{seed}_x{SPEED}_{i}.wav")
            sf.write(out_path, wav, sr)
            dur = len(wav) / sr
            print(f"  {elapsed:.2f}s → {dur:.2f}s audio (RTF {elapsed/max(dur,0.001):.2f})")
            print(f"  {out_path}")

    print(f"\n完成，輸出在 {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
