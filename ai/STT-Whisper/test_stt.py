"""Faster-Whisper large-v3 PoC：在 5090 上跑中文 STT，測延遲、VRAM、辨識品質。

跑法:
    cd /home/aitop4/nlp_cyberon_server/ai/STT-Whisper
    /home/aitop4/nlp_cyberon_server/aienv/bin/python test_stt.py
"""

from __future__ import annotations

import os
import sys
import time

MODEL_DIR = os.path.dirname(os.path.abspath(__file__))
WAV_DIR = "/home/aitop4/nlp_cyberon_server/test_whisper_wav"

# 挑幾個有代表性的檔案測（短/中/長）
TEST_WAVS = [
    "01820241201003705.wav",
    "02020241201102853.wav",
    "01820241201025718.wav",
    "test1_16k.wav",
]


def print_vram(stage: str) -> None:
    try:
        import torch

        if not torch.cuda.is_available():
            print(f"  [{stage}] (no cuda)")
            return
        used = torch.cuda.memory_allocated() / 1024**3
        free, total = torch.cuda.mem_get_info()
        print(
            f"  [{stage}] allocated={used:.2f}GB free={free/1024**3:.2f}/{total/1024**3:.2f}GB"
        )
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    print(f"[1/3] 載入 Faster-Whisper large-v3 (cuda, fp16)")
    print_vram("before load")
    t0 = time.time()
    from faster_whisper import WhisperModel

    model = WhisperModel(
        MODEL_DIR,
        device="cuda",
        compute_type="float16",
    )
    print(f"  loaded in {time.time()-t0:.2f}s")
    print_vram("after load")

    print(f"\n[2/3] 跑 {len(TEST_WAVS)} 個 wav 測 inference")
    for fname in TEST_WAVS:
        path = os.path.join(WAV_DIR, fname)
        if not os.path.isfile(path):
            print(f"\n--- {fname} → [SKIP] 不存在 ---")
            continue

        size_kb = os.path.getsize(path) / 1024
        print(f"\n--- {fname} ({size_kb:.0f} KB) ---")

        t0 = time.time()
        try:
            segments, info = model.transcribe(
                path,
                language="zh",
                beam_size=5,
            )
            # transcribe 回 generator，要 iterate 才會真的執行
            result_segments = list(segments)
            elapsed = time.time() - t0
        except Exception as e:  # noqa: BLE001
            print(f"  [ERR] transcribe failed: {type(e).__name__}: {e}")
            continue

        full_text = "".join(s.text for s in result_segments).strip()
        rtf = elapsed / max(info.duration, 0.001)
        print(f"  duration:    {info.duration:.2f}s")
        print(f"  language:    {info.language} (prob={info.language_probability:.2f})")
        print(f"  inference:   {elapsed:.2f}s (RTF={rtf:.2f}x)")
        print(f"  segments:    {len(result_segments)}")
        print(f"  transcript:  {full_text}")

    print()
    print_vram("end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
