"""TTS PoC: minimal call to verify Cyberon TTS gRPC endpoint works.

用 grpclib（不是 grpcio），因為 Cyberon TTS server 是自簽 cert 且沒有 CN/SAN，
標準 grpcio 無法跳過 hostname verification。grpclib 接受自訂 ssl.SSLContext，
等效於 Go 端 Cyberon 官方 sample 使用的 InsecureSkipVerify=true。

Usage:
    cd /home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC
    /home/aitop4/nlp_cyberon_server/aienv/bin/python test_tts.py
"""

from __future__ import annotations

import asyncio
import os
import ssl
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from grpclib.client import Channel

import service_pb2 as pb
import service_grpc as pb_grpc

TOKEN = (
    "yGFJ1D5HcTXaysVMc_GEfQto-lWfjjgruiqdAhEh0fw4YKbJ1TkYFYOOQ80nuXuv"
    "imoRqtzr99iqXE8KN5_Cxj6ksGV1uVLilv1ERRp0Je_B4MhASKJmX5evRd0VMdPf"
)
HOST = "192.168.5.204"
PORT = 8088
TEXT = "新北市警局 110 您好，請問哪裡發生什麼事？"
OUTFMT = "wav"
OUT_PATH = "/tmp/tts_poc.wav"


def make_insecure_tls_context() -> ssl.SSLContext:
    """跳過憑證驗證的 TLS context，等效於 Go 的 InsecureSkipVerify=true。

    Cyberon 自簽 cert 沒有 CN 也沒有 SAN，標準驗證一定 fail，
    依官方 PDF 建議「略過憑證安全性檢查」。
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2"])
    return ctx


async def main() -> int:
    print(f"[1/4] 建 grpclib channel: {HOST}:{PORT} (TLS, skip verify, ALPN h2)")
    ssl_ctx = make_insecure_tls_context()
    channel = Channel(HOST, PORT, ssl=ssl_ctx)
    stub = pb_grpc.StreamServiceStub(channel)

    print(f"[2/4] 構造 request: text={TEXT!r}, outfmt={OUTFMT}")
    req = pb.TtsRequest(
        serviceName="e2e",
        text=TEXT,
        outfmt=OUTFMT,
        language="zh-TW",
        speaker="Sharon",
        token=TOKEN,
    )

    print("[3/4] 呼叫 TTS()，等 streaming response...")
    chunks: list[bytes] = []
    t0 = time.time()
    try:
        async with stub.TTS.open() as stream:
            await stream.send_message(req, end=True)
            async for resp in stream:
                chunks.append(resp.data)
                print(f"  chunk #{len(chunks)}: {len(resp.data)} bytes")
        elapsed = time.time() - t0
    except Exception as e:  # noqa: BLE001
        print(f"[ERR] {type(e).__name__}: {e}")
        return 1
    finally:
        channel.close()

    audio = b"".join(chunks)
    rate = len(audio) / max(elapsed, 0.001)
    print(
        f"[4/4] 收齊：{len(chunks)} chunks，總長 {len(audio)} bytes，"
        f"耗時 {elapsed:.2f}s（{rate:.0f} bytes/s）"
    )

    with open(OUT_PATH, "wb") as f:
        f.write(audio)
    print(f"[OK] 寫入 {OUT_PATH}")

    if OUTFMT == "wav" and len(audio) >= 36:
        magic = audio[:4]
        if magic == b"RIFF":
            sample_rate = int.from_bytes(audio[24:28], "little")
            bits_per_sample = int.from_bytes(audio[34:36], "little")
            channels = int.from_bytes(audio[22:24], "little")
            print(
                f"[OK] WAV header: RIFF magic OK, "
                f"sample_rate={sample_rate}Hz, bits={bits_per_sample}, channels={channels}"
            )
        else:
            print(f"[WARN] WAV header check 失敗：預期 RIFF，實際 {magic!r}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
