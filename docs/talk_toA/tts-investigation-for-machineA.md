# Cyberon TTS 調查結果（給機器 A 開發者）

> **2026-05-09 更新**：Python 範例已實測通過。原本草稿用 `grpcio` 的版本不能用（cert 沒 SAN，hostname verify 過不去），**Python 必須改用 `grpclib`**。

## TL;DR

- **協定**：**gRPC**（Protocol Buffers），**不是 HTTP，不是 WebSocket**
- **端點**：`192.168.5.204:8088`
- **Service**：`streamservice.StreamService`
- **RPC method**：`TTS(TtsRequest) returns (stream TtsResponse)` — **Server streaming**
- **TLS**：自簽 cert（沒 CN/SAN），**必須跳過憑證驗證**（Cyberon 官方 PDF 的 Go sample 也是 `InsecureSkipVerify: true`）
- **認證**：透過 request body 內的 `token` 欄位
- **輸出格式選項**：mp3 / wav / pcm / pcm8（8kHz，**最適合 Asterisk**）
- **已實測**：機器 B 端 Python PoC 跑通，0.66 秒合成 5.3 秒語音

---

## 端點與認證

| 項目 | 值 |
|---|---|
| Host | `192.168.5.204` |
| Port | `8088` |
| Proto package | `streamservice` |
| Service | `StreamService` |
| RPC method | `TTS` |
| TLS | 自簽 cert，要跳過驗證 |
| Token | `yGFJ1D5HcTXaysVMc_GEfQto-lWfjjgruiqdAhEh0fw4YKbJ1TkYFYOOQ80nuXuvimoRqtzr99iqXE8KN5_Cxj6ksGV1uVLilv1ERRp0Je_B4MhASKJmX5evRd0VMdPf` |

> Token 不要 commit 進 public repo。

---

## .proto 檔案

直接附上完整 schema：

```proto
syntax = "proto3";

package streamservice;

message TtsRequest {
  string serviceName    = 1;  // 必要：固定填 "e2e"
  string text           = 2;  // 必要：要合成的文字
  string outfmt         = 3;  // 輸出聲音格式，預設 mp3，支援 mp3, wav, pcm, pcm8(8K)
  int64  vbr_quality    = 4;  // outfmt=mp3 時音質，預設 4，0(好) ~ 9(差)
  string language       = 5;  // 主要語言，預設 zh-TW
  bool   phrbrk         = 8;  // 是否自動斷詞，預設 false
  string speaker        = 10; // 主要語言語者，預設 Sharon
  float  speed          = 12; // 語速，預設 1，範圍 0.5 ~ 2
  float  gain           = 14; // 音量，預設 1，範圍 0.5 ~ 4
  string token          = 23; // 必要：認證 token
  string uid            = 24; // user unique id（可選）
}

message TtsResponse {
  bytes data = 1;
}

service StreamService {
  rpc TTS(TtsRequest) returns (stream TtsResponse) {};
}
```

機器 B 端原始檔路徑：
```
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/proto/service.proto
```

---

## 必填欄位

最少要傳這 3 個，其餘都有預設：

- `serviceName = "e2e"`
- `text = "..."`
- `token = "..."`

---

## 語言 / 語者

| `language` | 預設 `speaker` |
|---|---|
| `zh-TW`（台灣國語）| `Sharon` |
| `zh-NAN`（閩南語）| `YiChuen` |
| `en-US`（美式英語）| `Zero` |

---

## 輸出格式選項

| `outfmt` | 規格 | 適合場景 |
|---|---|---|
| `mp3`（預設）| 壓縮，需解碼 | 一般用途 |
| `wav` | 16-bit PCM, 16kHz, 含 RIFF header | 寫檔做後處理 |
| `pcm` | 16-bit PCM raw（無 header）, 16kHz | 餵給 16kHz 音訊管線 |
| `pcm8` | 8-bit PCM, **8kHz** | **電話線品質，最適合 Asterisk** |

→ **建議用 `pcm8`**，省一次轉檔，可以直接 stream 給 Asterisk。

---

## Python 客戶端：必須用 `grpclib`，不能用 `grpcio`

### 為什麼不能用 `grpcio`

Cyberon 的 server cert 是 **2019 年簽的自簽 cert，Subject 只有 `C=TW, ST=..., O=Cyberon`，沒有 CN 也沒有 SAN**。`grpcio` 的 hostname 驗證強制檢查 cert 的 CN 或 SAN 是否符合 servername，**完全不可能過驗證**，會看到：

```
StatusCode.UNAVAILABLE
Custom verification check failed with error: UNAUTHENTICATED:
Hostname Verification Check failed.
```

任何 `ssl_target_name_override` 值都救不了（試過 "Cyberon"、空字串等）。

### 用 `grpclib`（pure-Python gRPC，吃自訂 SSL context）

#### 環境準備

```bash
pip install grpclib protobuf grpcio-tools
```

> `grpcio-tools` 只是用它的 `protoc` 編譯 proto，不需要裝 `grpcio` 本身。

#### 編譯 proto

```bash
mkdir -p ./proto && cp service.proto ./proto/

# 注意是 --python_grpc_out（grpclib 的 plugin），不是 --grpc_python_out（grpcio 的）
PATH=$(python -c "import sys, os; print(os.path.dirname(sys.executable))"):$PATH \
python -m grpc_tools.protoc \
  -I./proto \
  --python_out=. \
  --python_grpc_out=. \
  service.proto
```

產出：
- `service_pb2.py` — message 定義（共用）
- `service_grpc.py` — grpclib 的 stub（用這個）

#### Client 範例

```python
"""TTS client using grpclib + custom SSL context (skip cert verify)."""

import asyncio
import ssl

from grpclib.client import Channel

import service_pb2 as pb
import service_grpc as pb_grpc

TOKEN = (
    "yGFJ1D5HcTXaysVMc_GEfQto-lWfjjgruiqdAhEh0fw4YKbJ1TkYFYOOQ80nuXuv"
    "imoRqtzr99iqXE8KN5_Cxj6ksGV1uVLilv1ERRp0Je_B4MhASKJmX5evRd0VMdPf"
)
HOST = "192.168.5.204"
PORT = 8088


def make_insecure_tls_context() -> ssl.SSLContext:
    """跳過憑證驗證的 TLS context，等效於 Go 的 InsecureSkipVerify=true。"""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2"])  # gRPC 走 HTTP/2，必須 ALPN 協商 h2
    return ctx


async def tts_to_bytes(text: str, outfmt: str = "pcm8") -> bytes:
    """合成一句文字，回傳完整音訊 bytes。"""
    ssl_ctx = make_insecure_tls_context()
    channel = Channel(HOST, PORT, ssl=ssl_ctx)
    try:
        stub = pb_grpc.StreamServiceStub(channel)
        req = pb.TtsRequest(
            serviceName="e2e",
            text=text,
            outfmt=outfmt,
            language="zh-TW",
            speaker="Sharon",
            token=TOKEN,
        )
        chunks: list[bytes] = []
        async with stub.TTS.open() as stream:
            await stream.send_message(req, end=True)
            async for resp in stream:
                chunks.append(resp.data)
        return b"".join(chunks)
    finally:
        channel.close()


async def main():
    audio = await tts_to_bytes("新北市警局 110 您好", outfmt="pcm8")
    with open("out.pcm", "wb") as f:
        f.write(audio)
    print(f"OK, {len(audio)} bytes")


if __name__ == "__main__":
    asyncio.run(main())
```

→ 這份 client 在機器 B 端已實測通過，可以直接搬。

---

## Go 客戶端

依 Cyberon 官方 PDF 第 11 頁範例（節錄）：

```go
import (
    "crypto/tls"
    "google.golang.org/grpc"
    "google.golang.org/grpc/credentials"
)

// Bypass SSL certificate secure verify
config := &tls.Config{
    InsecureSkipVerify: true,
}
conn, err := grpc.Dial(
    "192.168.5.204:8088",
    grpc.WithTransportCredentials(credentials.NewTLS(config)),
)
```

完整 sample（含完整 main + recv loop）見 PDF 第 11 頁，路徑：
```
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/Document/Cyberon_TTS_Protocol_Document.pdf
```

---

## 重要 caveats

1. **是 gRPC 不是 HTTP** — 不能用 curl / requests。Python 用戶要裝 `grpclib`（看上面）；Go 用戶用標準 `google.golang.org/grpc`。

2. **Python 不能用 `grpcio`** — 已經試過。改用 `grpclib`（不同套件名、不同 API、是 asyncio）。詳見上方 grpclib 章節。

3. **TLS 必須跳過憑證驗證** — Cyberon 自簽 cert 且沒 SAN，這是官方建議的做法（PDF 第 10 頁）。**Token 機制本身已經提供認證**，TLS 只是傳輸加密。

4. **Stream 處理** — response 是 server streaming，要全部收完才能拼成完整音檔。grpclib 用 `async for resp in stream`，Go 用 `stream.Recv()` 直到 `io.EOF`。

5. **取樣率注意** — `mp3`/`wav`/`pcm` 是 16kHz；`pcm8` 是 **8kHz, 8-bit**。Asterisk 通常用 8kHz，所以 `pcm8` 可以直接餵不用轉檔。

6. **Token 不要外流** — 上面的 token 是 production 用的，不要 commit 進公開 repo、不要寫進 client-side 程式碼。

---

## 機器 B 端的實測結果（驗證上面的 spec 正確）

- 用上面 grpclib 的 sample 跑「新北市警局 110 您好，請問哪裡發生什麼事？」outfmt=wav
- 收到 167 個 chunk，每個 1024 bytes（最後一個 322 bytes），共 170,284 bytes
- WAV header 解析：RIFF magic OK, sample_rate=16000Hz, bits=16, channels=1
- 整體耗時 0.66 秒（合成 5.3 秒語音），吞吐 ~258 KB/s

→ spec 跟實際 server 行為**完全一致**。

機器 B 端 PoC 檔案位置（如果要直接 copy 來改）：
```
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/test_tts.py        ← grpclib + asyncio client
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/service_pb2.py     ← message 定義
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/service_grpc.py    ← grpclib stub
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/cyberon-server.crt ← 抽出來的 server cert（非必要，純參考）
```

---

## 完整參考文件

機器 B 上 Cyberon 官方 TTS 規格 PDF（11 頁，含 Scalar Value Types 對應、Golang client sample、發展注意事項）：
```
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/Document/Cyberon_TTS_Protocol_Document.pdf
```

API 端點與 token 原始檔（已 inline 在上面）：
```
/home/aitop4/nlp_cyberon_server/ai/cyberon/TTS_gRPC/API_Info.txt
```

---

## 有問題請傳訊息

任何欄位語意不清、實際 call 失敗（請附 client 程式、request 內容、錯誤訊息），我這邊重新查 PDF 或實測。
