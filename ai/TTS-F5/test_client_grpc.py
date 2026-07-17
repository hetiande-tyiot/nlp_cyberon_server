"""Cyberon-compat gRPC client test。

用同樣的 grpclib + skip-verify SSL pattern（跟機器 A 的 client 模式一致），
直接打 tts_f5_server，確認 protocol 完全相容。

Usage:
    /home/aitop4/nlp_cyberon_server/aienv/bin/python test_client_grpc.py
"""

from __future__ import annotations

import asyncio
import os
import ssl
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 用 grpclib（跟之前給機器 A 的 client 一致）
from grpclib.client import Channel

# 注意：我們 server 用 grpcio 生 stub，但 client 是 grpclib。需要分別生 stub。
# 為了測試方便：直接 sys.path 引用之前 ai/cyberon/TTS_gRPC/ 內已有的 grpclib stubs
sys.path.insert(0, "/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC")
import service_pb2 as pb  # message defs（兩個方向通用）
import service_grpc as pb_grpc  # grpclib client stub

TOKEN = (
    "yGFJ1D5HcTXaysVMc_GEfQto-lWfjjgruiqdAhEh0fw4YKbJ1TkYFYOOQ80nuXuv"
    "imoRqtzr99iqXE8KN5_Cxj6ksGV1uVLilv1ERRp0Je_B4MhASKJmX5evRd0VMdPf"
)
HOST = os.environ.get("TTS_HOST", "127.0.0.1")
PORT = int(os.environ.get("TTS_PORT", "8089"))

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_grpc")
os.makedirs(OUT_DIR, exist_ok=True)

TEST_TEXTS = [
    ("新北市警局 110 您好，請問哪裡發生什麼事？", "wav"),
    ("請問現場有多少人受傷？", "wav"),
    ("我已為您紀錄案件內容，警員馬上前往處理。", "pcm8"),
]


def make_skip_verify_ssl() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2"])
    return ctx


async def call_one(stub, text: str, outfmt: str, out_name: str) -> None:
    req = pb.TtsRequest(
        serviceName="e2e",
        text=text,
        outfmt=outfmt,
        language="zh-TW",
        speaker="Sharon",  # 雖然我們忽略 speaker，但 client 還是會帶
        token=TOKEN,
    )
    print(f"\n--- text={text!r}, outfmt={outfmt} ---")
    t0 = time.time()
    chunks: list[bytes] = []
    async with stub.TTS.open() as stream:
        await stream.send_message(req, end=True)
        async for resp in stream:
            chunks.append(resp.data)
    elapsed = time.time() - t0
    audio = b"".join(chunks)
    out_path = os.path.join(OUT_DIR, out_name)
    with open(out_path, "wb") as f:
        f.write(audio)
    print(
        f"  收 {len(chunks)} chunks, {len(audio)} bytes in {elapsed:.2f}s → {out_path}"
    )
    if outfmt == "wav" and audio[:4] == b"RIFF":
        sr = int.from_bytes(audio[24:28], "little")
        bps = int.from_bytes(audio[34:36], "little")
        ch = int.from_bytes(audio[22:24], "little")
        print(f"  WAV header: RIFF OK, sr={sr}, bits={bps}, channels={ch}")
    elif outfmt == "pcm8":
        print(f"  pcm8: raw {len(audio)} bytes (~{len(audio)/8000:.2f}s @ 8kHz/8bit)")


async def main():
    print(f"[client] 連 grpcs://{HOST}:{PORT} (skip-verify SSL)")
    ssl_ctx = make_skip_verify_ssl()
    channel = Channel(HOST, PORT, ssl=ssl_ctx)
    try:
        stub = pb_grpc.StreamServiceStub(channel)
        for i, (text, outfmt) in enumerate(TEST_TEXTS, 1):
            await call_one(stub, text, outfmt, f"grpc_{i}.{outfmt}")
    finally:
        channel.close()


if __name__ == "__main__":
    asyncio.run(main())
