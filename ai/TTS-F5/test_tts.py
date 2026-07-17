"""F5-TTS PoC：中文 voice clone TTS，跑 3 個受理員語氣的句子，看延遲、VRAM、音質。

跑法:
    cd /home/aitop4/nlp_cyberon_server/ai/TTS-F5
    /home/aitop4/nlp_cyberon_server/aienv/bin/python test_tts.py
"""

from __future__ import annotations

import os
import sys
import time

import soundfile as sf

# 用 F5-TTS 自帶的中文 reference（套件 site-packages 內）
F5_PKG = "/home/aitop4/nlp_cyberon_server/aienv/lib/python3.10/site-packages/f5_tts"
REF_FILE = "/home/aitop4/nlp_cyberon_server/ai/TTS-F5/reference/malevoice.wav"
REF_TEXT = ""  # 空字串 → F5-TTS 內部用 Whisper 自動 transcribe reference

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUT_DIR, exist_ok=True)

GEN_TEXTS = [
    "新北市警局 110 您好，請問哪裡發生什麼事？",
    "請問現場有多少人受傷？傷勢如何？有沒有流血、骨折或昏迷的情況？",
    "我已為您紀錄案件內容，警員馬上前往處理，請您保持冷靜並注意自身安全。",
]


def print_vram(stage: str) -> None:
    try:
        import torch
        if not torch.cuda.is_available():
            return
        used = torch.cuda.memory_allocated() / 1024**3
        free, total = torch.cuda.mem_get_info()
        print(
            f"  [{stage}] alloc={used:.2f}GB free={free/1024**3:.2f}/{total/1024**3:.2f}GB"
        )
    except Exception:
        pass


def main() -> int:
    print("[1/3] 載入 F5-TTS_v1_Base（首次跑會 download ~1.4 GB 到 HF cache）")
    print_vram("before load")
    t0 = time.time()
    from f5_tts.api import F5TTS

    f5 = F5TTS()  # device=auto, 預設用 cuda（若可）
    print(f"  loaded in {time.time()-t0:.2f}s")
    print_vram("after load")

    print(f"\n[2/3] 跑 {len(GEN_TEXTS)} 個合成（ref={os.path.basename(REF_FILE)}）")
    for i, gen_text in enumerate(GEN_TEXTS, 1):
        print(f"\n--- gen {i}: {gen_text!r} ---")
        t0 = time.time()
        try:
            wav, sr, _ = f5.infer(
                ref_file=REF_FILE,
                ref_text=REF_TEXT,
                gen_text=gen_text,
                seed=42,
            )
            elapsed = time.time() - t0
        except Exception as e:  # noqa: BLE001
            print(f"  [ERR] infer failed: {type(e).__name__}: {e}")
            continue

        out_path = os.path.join(OUT_DIR, f"gen_{i}.wav")
        sf.write(out_path, wav, sr)
        audio_dur = len(wav) / sr
        rtf = elapsed / max(audio_dur, 0.001)
        print(f"  inference: {elapsed:.2f}s")
        print(f"  audio:     {audio_dur:.2f}s @ {sr} Hz, mono")
        print(f"  RTF:       {rtf:.2f}x")
        print(f"  output:    {out_path}")

    print()
    print_vram("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
