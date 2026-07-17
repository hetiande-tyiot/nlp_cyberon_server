"""STT WebSocket adapter — 用 Faster-Whisper 模擬 Cyberon /SttProxy/recognition protocol。

跑法（測試）:
    cd /home/aitop4/nlp_cyberon_server/ai/STT-Whisper
    /home/aitop4/nlp_cyberon_server/aienv/bin/python stt_whisper_server.py

跑法（systemd 推薦）:
    uvicorn stt_whisper_server:app --host 0.0.0.0 --port 8891 --workers 1

協議（client-side 視角，跟 Cyberon 相容）:
    1. ws.connect → server: {"state": "listening"}
    2. client → {"token":"...","action":"start","domain":"...","platform":"...","uid":"...","type":"audio/L16; rate=16000"}
    3. client → 多個 binary PCM frames（16-bit signed LE）
    4. client → {"action":"stop"}
    5. server → {"state":"result","err_code":0,"recog_result":"...","isFinish":true,"recog_index":N,...}
    6. server → {"state":"listening"}（準備下一輪；client 可直接送新的 start，或 close）

注意:
- 不實作 server-side EPD（機器 A 已用 client-side VAD + 主動 stop）
- 不實作 partial 結果（isGetPartial 收到也忽略；只在 stop 後回 isFinish=true 的 final result）
- 不實作 SD / gender / NLU 等延伸欄位（回空 list）
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

# ── 設定 ───────────────────────────────────────────────────
MODEL_DIR = os.environ.get(
    "WHISPER_MODEL_DIR",
    os.path.dirname(os.path.abspath(__file__)),
)
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
PORT = int(os.environ.get("STT_PORT", "8891"))
DEFAULT_LANG = os.environ.get("WHISPER_LANG", "zh")
# beam_size：1=greedy（最快、短句準確度差異小），5=原本（最準但慢 3-5x）
BEAM_SIZE = int(os.environ.get("WHISPER_BEAM", "1"))
# VAD filter：跳掉錄音內的靜音 chunk、減少送進 Whisper 的工作量（明顯降低 stop → FINAL 延遲）
VAD_FILTER = os.environ.get("WHISPER_VAD_FILTER", "1") == "1"
# INITIAL_PROMPT 預設空字串（避免短音被 prompt 內容「鸚鵡學舌」污染）
# 要試 prompt 效果可設 env var：WHISPER_INITIAL_PROMPT="..."
INITIAL_PROMPT = os.environ.get("WHISPER_INITIAL_PROMPT", "")
EXPECTED_TOKEN = os.environ.get(
    "STT_TOKEN",
    "yGFJ1D5HcTXaysVMc_GEfQto-lWfjjgruiqdAhEh0fw4YKbJ1TkYFYOOQ80nuXuv"
    "imoRqtzr99iqXE8KN5_Cxj6ksGV1uVLilv1ERRp0Je_B4MhASKJmX5evRd0VMdPf",
)
# token 驗證可關（STT_TOKEN_REQUIRED=0），預設要驗以跟 Cyberon 行為一致
TOKEN_REQUIRED = os.environ.get("STT_TOKEN_REQUIRED", "1") == "1"

# ── 載入模型 ───────────────────────────────────────────────
print(
    f"⏳ 載入 Faster-Whisper from {MODEL_DIR} "
    f"(device={DEVICE}, compute={COMPUTE_TYPE})…",
    flush=True,
)
_model = WhisperModel(MODEL_DIR, device=DEVICE, compute_type=COMPUTE_TYPE)
print("✅ Whisper 就緒", flush=True)

app = FastAPI(title="STT-Whisper (Cyberon-compat)", version="1.0")


# ── helpers ──────────────────────────────────────────────
def _parse_audio_type(t: str) -> tuple[int, int]:
    """解析 'audio/L16; rate=8000' / 'audio/L16; rate=16000' 之類。

    回 (sample_rate_hz, sample_width_bytes)。Cyberon 規格只支援 L16（16-bit signed PCM, LE）。
    """
    s = (t or "").lower().replace(" ", "")
    rate = 16000
    if "rate=8000" in s:
        rate = 8000
    elif "rate=16000" in s:
        rate = 16000
    return rate, 2


def _pcm_bytes_to_float32(audio_bytes: bytes, sample_rate: int) -> np.ndarray:
    """16-bit signed PCM bytes → float32 16kHz ndarray（faster-whisper 吃這個）。"""
    if not audio_bytes:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    if sample_rate != 16000:
        # 線性 resample（簡單夠用，要求高品質可換 scipy.signal.resample_poly）
        new_len = int(len(samples) * 16000 / sample_rate)
        if new_len > 0:
            samples = np.interp(
                np.linspace(0, len(samples), new_len, endpoint=False),
                np.arange(len(samples)),
                samples,
            ).astype(np.float32)
    return samples


def _do_transcribe(samples: np.ndarray) -> tuple[str, float]:
    """sync transcribe；call via loop.run_in_executor。回 (text, duration_seconds)。"""
    if len(samples) == 0:
        return "", 0.0
    segments, info = _model.transcribe(
        samples,
        language=DEFAULT_LANG,
        beam_size=BEAM_SIZE,
        initial_prompt=INITIAL_PROMPT if INITIAL_PROMPT else None,
        vad_filter=VAD_FILTER,                  # 跳靜音 chunk，降低 stop→FINAL 延遲
        without_timestamps=True,                # 不需要 segment timestamp、省解碼 token
        condition_on_previous_text=False,       # 避免上輪 hallucination 級聯到下一句
    )
    text = "".join(s.text for s in segments).strip()
    return text, float(info.duration)


# ── 端點 ─────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "model_dir": MODEL_DIR, "device": DEVICE}


@app.websocket("/SttProxy/recognition")
async def stt_recognition(ws: WebSocket):
    await ws.accept()
    sess = uuid.uuid4().hex[:8]
    print(f"[STT {sess}] 連線", flush=True)

    try:
        while True:
            await ws.send_text(json.dumps({"state": "listening"}))

            # 等 start action（或 client close）
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                print(f"[STT {sess}] client close（listening 階段）", flush=True)
                return

            text = msg.get("text")
            if not text:
                # listening 階段收到 binary：忽略，繼續等
                continue

            try:
                start = json.loads(text)
            except json.JSONDecodeError as e:
                await ws.send_text(
                    json.dumps({"err_code": -2, "err_msg": f"invalid JSON: {e}"})
                )
                continue

            if start.get("action") != "start":
                await ws.send_text(
                    json.dumps({"err_code": -2, "err_msg": "expected action=start"})
                )
                continue

            if TOKEN_REQUIRED and start.get("token") != EXPECTED_TOKEN:
                await ws.send_text(
                    json.dumps({"err_code": -5, "err_msg": "invalid token"})
                )
                continue

            audio_type = start.get("type", "audio/L16; rate=16000")
            sample_rate, _ = _parse_audio_type(audio_type)
            domain = start.get("domain", "freeSTT-zh-TW")
            uid = start.get("uid", "unknown")
            print(
                f"[STT {sess}] start: domain={domain}, rate={sample_rate}, uid={uid}",
                flush=True,
            )

            # 收 audio frames 直到 stop
            audio_buffer = bytearray()
            recog_index = 0
            t_first_frame: Optional[float] = None
            t_recog_start = time.time()

            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    print(
                        f"[STT {sess}] client close（recog 階段，buffered "
                        f"{len(audio_buffer)} bytes 丟棄）",
                        flush=True,
                    )
                    return

                # binary audio frame
                if msg.get("bytes") is not None:
                    if t_first_frame is None:
                        t_first_frame = time.time()
                    audio_buffer.extend(msg["bytes"])
                    continue

                # text → action
                if msg.get("text"):
                    try:
                        action_msg = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue

                    act = (action_msg.get("action") or "").lower()
                    if act == "stop":
                        audio_dur_s = len(audio_buffer) / max(sample_rate * 2, 1)
                        print(
                            f"[STT {sess}] stop received: audio_bytes={len(audio_buffer)} "
                            f"(~{audio_dur_s:.2f}s)",
                            flush=True,
                        )
                        samples = _pcm_bytes_to_float32(bytes(audio_buffer), sample_rate)
                        loop = asyncio.get_event_loop()
                        t_infer_start = time.time()
                        try:
                            recog_text, recog_dur = await loop.run_in_executor(
                                None, _do_transcribe, samples
                            )
                        except Exception as e:  # noqa: BLE001
                            print(
                                f"[STT {sess}] ⚠️ transcribe failed: {type(e).__name__}: {e}",
                                flush=True,
                            )
                            await ws.send_text(
                                json.dumps(
                                    {
                                        "err_code": -4,
                                        "err_msg": f"transcribe error: {e}",
                                        "state": "result",
                                        "isFinish": True,
                                        "recog_index": recog_index,
                                        "recog_result": "",
                                        "recog_nbest": [],
                                    },
                                    ensure_ascii=False,
                                )
                            )
                            break

                        infer_elapsed = time.time() - t_infer_start
                        print(
                            f"[STT {sess}] transcribe: {recog_dur:.2f}s audio → "
                            f"{infer_elapsed:.2f}s inference, text={recog_text!r}",
                            flush=True,
                        )

                        await ws.send_text(
                            json.dumps(
                                {
                                    "err_code": 0,
                                    "err_msg": "",
                                    "state": "result",
                                    "isFinish": True,
                                    "recog_index": recog_index,
                                    "sen_base_ms": 0,
                                    "sen_start_ms": 0,
                                    "sen_end_ms": int(recog_dur * 1000),
                                    "recog_result": recog_text,
                                    "recog_nbest": [recog_text] if recog_text else [],
                                    "recog_word": [],
                                },
                                ensure_ascii=False,
                            )
                        )
                        recog_index += 1
                        break  # back to outer while → 再送一次 listening

                    if act == "cancel":
                        print(f"[STT {sess}] cancel received, drop buffer", flush=True)
                        break  # back to outer → listening

                    # 其他 action 忽略

    except WebSocketDisconnect:
        print(f"[STT {sess}] WebSocketDisconnect", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[STT {sess}] ⚠️ 例外: {type(e).__name__}: {e}", flush=True)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
