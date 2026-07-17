"""F5-TTS gRPC server — Cyberon-compat streamservice.StreamService/TTS。

模擬 Cyberon TTS gRPC（含 TLS、自簽 cert、token 驗證、stream TtsResponse chunks）。
機器 A 那邊的 grpclib client（skip-verify SSL）不必動，只切 endpoint :8088 → :8089。

跑法（測試）:
    cd /home/aitop4/nlp_cyberon_server/ai/TTS-F5
    /home/aitop4/nlp_cyberon_server/aienv/bin/python tts_f5_server.py

跑法（systemd 推薦）:
    /home/aitop4/nlp_cyberon_server/aienv/bin/python tts_f5_server.py
"""

from __future__ import annotations

import io
import math
import os
import re
import sys
import threading
import time
import uuid
import wave
from concurrent import futures

import grpc
import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import service_pb2 as pb
import service_pb2_grpc as pb_grpc

# ── 設定 ───────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("TTS_HOST", "0.0.0.0")
PORT = int(os.environ.get("TTS_PORT", "8089"))
CERT_FILE = os.environ.get("TTS_CERT_FILE", os.path.join(_HERE, "cert.pem"))
KEY_FILE = os.environ.get("TTS_KEY_FILE", os.path.join(_HERE, "key.pem"))

REF_FILE = os.environ.get(
    "F5_REF_FILE",
    os.path.join(_HERE, "reference", "malevoice.wav"),
)
REF_TEXT = os.environ.get("F5_REF_TEXT", "")  # 空 = F5 內部自動 transcribe

# 多聲紋註冊目錄（見 docs/shared_with_A/tts-speaker-naming-convention.md）：
# reference/speakers/<Name>.wav 即註冊 speaker "<Name>"（區分大小寫），
# 可選同名 <Name>.txt 放參考逐字稿（沒有則 Whisper 自動辨識）。
# request.speaker 沒對到任何檔案 → fallback 到 REF_FILE 預設聲紋。
SPEAKER_DIR = os.environ.get("F5_SPEAKER_DIR", os.path.join(_HERE, "reference", "speakers"))

EXPECTED_TOKEN = os.environ.get(
    "TTS_TOKEN",
    "yGFJ1D5HcTXaysVMc_GEfQto-lWfjjgruiqdAhEh0fw4YKbJ1TkYFYOOQ80nuXuv"
    "imoRqtzr99iqXE8KN5_Cxj6ksGV1uVLilv1ERRp0Je_B4MhASKJmX5evRd0VMdPf",
)
TOKEN_REQUIRED = os.environ.get("TTS_TOKEN_REQUIRED", "1") == "1"
CHUNK_BYTES = int(os.environ.get("TTS_CHUNK_BYTES", "4096"))

# ── 載入 F5-TTS ─────────────────────────────────────────
print(f"⏳ 載入 F5-TTS_v1_Base（device=auto，首次跑會 download ~1.4 GB）…", flush=True)
from f5_tts.api import F5TTS

_model = F5TTS()
_model_lock = threading.Lock()
print(f"✅ F5-TTS 就緒（ref={REF_FILE}）", flush=True)

# 短句正常路徑的 speed 上限：1.3 起最後一字易含糊（「請稍等」實測變「請稍后」）
SHORT_TEXT_MAX_SPEED = 1.2


def _prep_short_text(text: str, speed: float) -> tuple[str, float]:
    """<10 utf-8 bytes 短句處理。upstream（utils_infer.py _infer_basic）對這種
    gen_text 強制 local_speed=0.3：忽略呼叫方 speed，且慢速大 window 會產生
    前置 silence（可達 1.3s）與尾端重複音節（A 端 07-10 回報「我了解→解」）。

    解法：補「。」把 byte 數撐過 10 門檻、改走正常生成路徑 —— window 緊、
    speed 原生生效、無 artifact 空間。句號只產生尾端短靜音，不出聲。
    speed 同時 clamp 到 SHORT_TEXT_MAX_SPEED（短句壓太快最後一字會糊）。"""
    if len(text.encode("utf-8")) >= 10:
        return text, speed
    padded = text
    while len(padded.encode("utf-8")) < 10:
        padded += "。"
    return padded, min(speed, SHORT_TEXT_MAX_SPEED)


def _resolve_speaker(speaker: str) -> tuple[str, str, str]:
    """speaker 字串 → (ref_file, ref_text, 實際使用的 speaker 標籤)。

    命名規約（跟 A 端共識）：字串區分大小寫、對應 SPEAKER_DIR/<Name>.wav。
    同名 .txt 存在就用其內容當逐字稿。沒對到 → 預設聲紋（back-compat：
    目前 A 端送 "Sharon" 也是拿預設聲紋）。
    """
    if speaker and re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", speaker):
        wav = os.path.join(SPEAKER_DIR, f"{speaker}.wav")
        if os.path.isfile(wav):
            txt = os.path.join(SPEAKER_DIR, f"{speaker}.txt")
            ref_text = ""
            if os.path.isfile(txt):
                with open(txt, encoding="utf-8") as f:
                    ref_text = f.read().strip()
            return wav, ref_text, speaker
    return REF_FILE, REF_TEXT, "default"


# ── audio helpers ────────────────────────────────────────
def _trim_leading_silence(
    samples: np.ndarray, sr: int, thresh_db: float = -40.0, pad_ms: int = 50
) -> tuple[np.ndarray, float]:
    """去掉波形頭部的 silence（保留 pad_ms 前導）。回 (trimmed, 去掉的秒數)。

    F5 短句走 0.3 慢速 window 時聲音壓在尾端，前置 silence 可達 1s+，
    承接詞情境（A 端墊話掩蓋延遲）會反效果，故 adapter 統一 trim。
    threshold 相對該次輸出的 peak（-40dB），避免底噪影響判定。
    """
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak <= 0:
        return samples, 0.0
    nz = np.where(np.abs(samples) > peak * 10 ** (thresh_db / 20))[0]
    if len(nz) == 0:
        return samples, 0.0
    start = max(0, int(nz[0]) - int(sr * pad_ms / 1000))
    return samples[start:], start / sr



def _f32_to_int16(samples: np.ndarray) -> np.ndarray:
    return np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)


def _resample(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return samples.astype(np.float32)
    g = math.gcd(src_sr, dst_sr)
    up = dst_sr // g
    down = src_sr // g
    return resample_poly(samples, up, down).astype(np.float32)


def _to_wav_bytes(samples_int16: np.ndarray, sr: int) -> bytes:
    """RIFF/WAVE PCM 16-bit mono header + data。Asterisk Playback() 可直接吃。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples_int16.tobytes())
    return buf.getvalue()


def _to_pcm_raw(samples_int16: np.ndarray) -> bytes:
    """16-bit PCM LE 原始 bytes，無 header。"""
    return samples_int16.tobytes()


def _to_pcm8_raw(samples_int16: np.ndarray) -> bytes:
    """8-bit unsigned PCM 原始 bytes（Cyberon PDF 的 pcm8(8K) 規格的猜測）。"""
    scaled = ((samples_int16.astype(np.int32) + 32768) >> 8).astype(np.uint8)
    return scaled.tobytes()


def _encode(samples_f32_24k: np.ndarray, outfmt: str) -> tuple[bytes, str]:
    """F5-TTS 輸出（24kHz f32）→ outfmt 指定的 bytes。回 (bytes, actual_fmt)。

    支援 outfmt: wav(default) / pcm / pcm8 / mp3(fallback to wav)。
    """
    fmt = (outfmt or "wav").lower().strip()
    if fmt in {"wav", ""}:
        s16 = _f32_to_int16(_resample(samples_f32_24k, 24000, 16000))
        return _to_wav_bytes(s16, 16000), "wav"
    if fmt == "pcm":
        s16 = _f32_to_int16(_resample(samples_f32_24k, 24000, 16000))
        return _to_pcm_raw(s16), "pcm"
    if fmt == "pcm8":
        s16 = _f32_to_int16(_resample(samples_f32_24k, 24000, 8000))
        return _to_pcm8_raw(s16), "pcm8"
    if fmt == "mp3":
        # 沒實作 mp3 編碼器；fallback wav
        s16 = _f32_to_int16(_resample(samples_f32_24k, 24000, 16000))
        return _to_wav_bytes(s16, 16000), "wav(mp3-fallback)"
    # 不認的 fmt → fallback wav
    s16 = _f32_to_int16(_resample(samples_f32_24k, 24000, 16000))
    return _to_wav_bytes(s16, 16000), f"wav(unknown-fmt={fmt!r})"


# ── gRPC servicer ────────────────────────────────────────
class StreamServiceServicer(pb_grpc.StreamServiceServicer):
    def TTS(self, request, context):
        req_id = uuid.uuid4().hex[:8]
        try:
            # proto3 未帶的 float 欄位值是 0 → 視為預設 1；範圍依 Cyberon 規格 clamp
            speed = min(max(request.speed, 0.5), 2.0) if request.speed else 1.0
            gain = min(max(request.gain, 0.5), 4.0) if request.gain else 1.0

            print(
                f"[TTS {req_id}] req: serviceName={request.serviceName!r}, "
                f"lang={request.language!r}, speaker={request.speaker!r}, "
                f"outfmt={request.outfmt!r}, speed={speed}, gain={gain}, "
                f"text={request.text!r}",
                flush=True,
            )

            if TOKEN_REQUIRED and request.token != EXPECTED_TOKEN:
                context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                context.set_details("invalid token")
                print(f"[TTS {req_id}] ⚠️  invalid token", flush=True)
                return

            text = (request.text or "").strip()
            if not text:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("empty text")
                return

            # F5-TTS inference (serialize - single GPU model instance)
            t0 = time.time()
            gen_text, eff_speed = _prep_short_text(text, speed)
            if gen_text != text:
                print(
                    f"[TTS {req_id}] short-text: gen_text={gen_text!r}, speed {speed}→{eff_speed}",
                    flush=True,
                )
            ref_file, ref_text, used_speaker = _resolve_speaker(request.speaker)
            if used_speaker != request.speaker:
                print(
                    f"[TTS {req_id}] speaker {request.speaker!r} 未註冊 → 用預設聲紋",
                    flush=True,
                )
            with _model_lock:
                wav_f32, sr, _ = _model.infer(
                    ref_file=ref_file,
                    ref_text=ref_text,
                    gen_text=gen_text,
                    seed=42,
                    speed=eff_speed,
                )
            infer_dur = time.time() - t0
            audio_dur = len(wav_f32) / sr if sr else 0.0
            print(
                f"[TTS {req_id}] infer: {infer_dur:.2f}s for {audio_dur:.2f}s audio "
                f"(RTF {infer_dur / max(audio_dur, 0.001):.2f})",
                flush=True,
            )

            # encode to requested format（gain 在 float 域套用，_f32_to_int16 會 clip 防爆音）
            samples = np.asarray(wav_f32, dtype=np.float32) * gain
            samples, trimmed_sec = _trim_leading_silence(samples, sr)
            if trimmed_sec > 0.1:
                print(f"[TTS {req_id}] trimmed {trimmed_sec:.2f}s leading silence", flush=True)
            audio_bytes, actual_fmt = _encode(samples, request.outfmt)
            print(
                f"[TTS {req_id}] encode: {len(audio_bytes)} bytes as {actual_fmt}, "
                f"streaming in {CHUNK_BYTES} byte chunks",
                flush=True,
            )

            # stream chunks
            n_chunks = 0
            for i in range(0, len(audio_bytes), CHUNK_BYTES):
                yield pb.TtsResponse(data=audio_bytes[i : i + CHUNK_BYTES])
                n_chunks += 1
            print(f"[TTS {req_id}] sent {n_chunks} chunks, done", flush=True)

        except Exception as exc:  # noqa: BLE001
            print(f"[TTS {req_id}] ⚠️  例外: {type(exc).__name__}: {exc}", flush=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"internal error: {exc}")


# ── server bootstrap ─────────────────────────────────────
def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_StreamServiceServicer_to_server(StreamServiceServicer(), server)

    with open(KEY_FILE, "rb") as f:
        key = f.read()
    with open(CERT_FILE, "rb") as f:
        cert = f.read()
    creds = grpc.ssl_server_credentials([(key, cert)])

    addr = f"{HOST}:{PORT}"
    server.add_secure_port(addr, creds)
    server.start()
    print(f"✅ TTS gRPC server (TLS, self-signed) listening on {addr}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
