"""Cyberon-compat STT WebSocket client test。

模擬機器 A 的 amidaemon_cyberon.py 連到 stt_whisper_server:
  1. ws connect
  2. 等 {"state": "listening"}
  3. 送 {"action": "start", "token": "...", "type": "audio/L16; rate=16000", ...}
  4. 從 wav 切 100ms frames 送 binary（模擬即時串流）
  5. 送 {"action": "stop"}
  6. 等 {"state": "result", "recog_result": "..."}
  7. 等 {"state": "listening"}（server 回到等待）
  8. close

Usage:
    /home/aitop4/nlp_cyberon_server/aienv/bin/python test_client.py <wav_path>
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

import numpy as np
import soundfile as sf
import websockets

URL = os.environ.get("STT_URL", "ws://127.0.0.1:8891/SttProxy/recognition")
TOKEN = (
    "yGFJ1D5HcTXaysVMc_GEfQto-lWfjjgruiqdAhEh0fw4YKbJ1TkYFYOOQ80nuXuv"
    "imoRqtzr99iqXE8KN5_Cxj6ksGV1uVLilv1ERRp0Je_B4MhASKJmX5evRd0VMdPf"
)


def load_wav_as_pcm(path: str) -> tuple[bytes, int]:
    """用 soundfile 讀（支援 PCM / μ-law / A-law 等），統一輸出 mono 16-bit signed PCM bytes。

    回 (pcm_int16_bytes_LE, sample_rate)。
    """
    samples, sample_rate = sf.read(path, dtype="int16", always_2d=False)
    info = sf.info(path)
    print(
        f"[wav] {os.path.basename(path)}: ch={info.channels}, "
        f"format={info.format}/{info.subtype}, rate={sample_rate}, "
        f"frames={info.frames}, dur={info.duration:.2f}s"
    )
    # 多聲道 → 取第一聲道（避免 mu-law stereo 之類）
    if samples.ndim > 1:
        samples = samples[:, 0]
    raw = samples.astype(np.int16).tobytes()
    return raw, sample_rate


async def run(wav_path: str):
    pcm, sample_rate = load_wav_as_pcm(wav_path)
    print(f"\n[client] 連 {URL}")
    async with websockets.connect(URL) as ws:
        # Step 1: 等 listening
        resp = json.loads(await ws.recv())
        print(f"[client] ← {resp}")
        assert resp.get("state") == "listening", "expected listening"

        # Step 2: 送 start
        start_msg = {
            "action": "start",
            "token": TOKEN,
            "domain": "freeSTT-zh-TW",
            "platform": "test-client",
            "uid": "test-uid",
            "type": f"audio/L16; rate={sample_rate}",
            "bIsDoEPD": False,
        }
        await ws.send(json.dumps(start_msg))
        print(f"[client] → start (rate={sample_rate})")

        # Step 3: stream binary frames (100 ms 一段，模擬即時)
        frame_bytes = sample_rate * 2 // 10  # 100 ms, 2 bytes per sample
        t0 = time.time()
        n_frames = 0
        for i in range(0, len(pcm), frame_bytes):
            chunk = pcm[i : i + frame_bytes]
            await ws.send(chunk)
            n_frames += 1
            # 模擬即時：每送一個 frame sleep 100ms
            # 為了快測，不 sleep；如果要真實模擬，加 `await asyncio.sleep(0.1)`
        send_dur = time.time() - t0
        print(f"[client] → sent {n_frames} binary frames in {send_dur:.2f}s")

        # Step 4: 送 stop
        await ws.send(json.dumps({"action": "stop"}))
        print("[client] → stop")
        t_stop = time.time()

        # Step 5: 等 result
        resp_text = await ws.recv()
        resp = json.loads(resp_text)
        recog_latency = time.time() - t_stop
        print(f"[client] ← result (after stop {recog_latency:.2f}s):")
        print(f"  err_code     = {resp.get('err_code')}")
        print(f"  state        = {resp.get('state')}")
        print(f"  isFinish     = {resp.get('isFinish')}")
        print(f"  recog_index  = {resp.get('recog_index')}")
        print(f"  sen_end_ms   = {resp.get('sen_end_ms')}")
        print(f"  recog_result = {resp.get('recog_result')!r}")
        print(f"  recog_nbest  = {resp.get('recog_nbest')}")

        # Step 6: 等下一輪 listening
        resp2 = json.loads(await ws.recv())
        print(f"[client] ← {resp2}")
        assert resp2.get("state") == "listening", "expected listening again"
        print("[client] OK 進入下一輪 listening；close")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: test_client.py <wav_path>")
        sys.exit(2)
    asyncio.run(run(sys.argv[1]))
