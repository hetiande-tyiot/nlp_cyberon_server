"""119 地址驗測與地點名單載入。

分兩件事：

1. 驗測（地址確認）：全部類別走同一個 MapaddrCheck `/api/AddrCheck/Verify`
   端點（見 API.md）。一個端點吃五種定位方式，帶 `type` 只查那一層，回傳
   status / reason / address / hint。座標（lon/lat/x/y）目前用不到，只看
   status 判斷有效與否。取代了原本三套各自為政的校驗：門牌舊 jurisdiction
   API、地標比對 landmarks.xlsx、捷運比對 MRTstation.csv。

2. 分類（判斷地點類別）：`_refresh_location_type` 仍用本地的捷運站名、地標
   名單餵給 classify_location_type，協助把地址歸到正確的 location_type
   （再轉成 API 的 type）。這部分的資料載入保留在下方。

驗測設定（環境變數）：
  ADDRCHECK_API_URL      Base URL，預設 http://localhost:8060
  ADDRCHECK_API_TOKEN    Bearer token（與 ACRC 共用 Ingest__Token）
  ADDRCHECK_API_TIMEOUT  逾時秒數，預設 2.5
"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MRT_CSV = BASE_DIR / "scripts" / "MRTstation.csv"
DEFAULT_LANDMARK_XLSX = BASE_DIR / "scripts" / "landmarks.xlsx"

DEFAULT_ADDRCHECK_BASE_URL = "http://localhost:8060"
VERIFY_PATH = "/api/AddrCheck/Verify"

# 內部 location_type → MapaddrCheck API 的 type（只查該層，不會退到其他層）。
# 捷運沒有專屬 type，當地標查。
LOCATION_TYPE_TO_API_TYPE = {
    "address": "House",
    "intersection": "Crossroad",
    "highway": "Freeway",
    "landmark": "Landmark",
    "mrt": "Landmark",
}


# ───────────────────────── 驗測：MapaddrCheck /Verify ─────────────────────────


@dataclass(frozen=True)
class AddrCheckResult:
    """`/Verify` 結果；status=None 代表網路或 API 例外，不是「查無」。"""

    status: Optional[bool]
    reason: Optional[str] = None   # valid / ambiguous / road_only / not_found / unparsable
    address: Optional[str] = None  # 命中的正規化地址；status=False 時為 None
    hint: Optional[str] = None     # 可直接轉成追問話術的中文提示
    error: Optional[str] = None    # 網路／解析例外訊息（status=None 時才有）


def _base_url() -> str:
    return os.getenv("ADDRCHECK_API_URL", DEFAULT_ADDRCHECK_BASE_URL).rstrip("/")


def _token() -> str:
    for key in ("ADDRCHECK_API_TOKEN", "INGEST_TOKEN", "Ingest__Token"):
        value = os.getenv(key)
        if value:
            return value
    return ""


def _timeout() -> float:
    try:
        return float(os.getenv("ADDRCHECK_API_TIMEOUT", "2.5"))
    except ValueError:
        return 2.5


def verify_address(
    address: str,
    *,
    location_type: Optional[str] = None,
    town: Optional[str] = None,
    url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: Optional[float] = None,
) -> AddrCheckResult:
    """把報案地址原文 POST 到 `/api/AddrCheck/Verify`。

    location_type 為內部類別（address/intersection/highway/landmark/mrt），
    會轉成 API 的 `type` 只查該層；判斷不出類別時傳 None，省略 `type` 讓後端
    自動判斷。
    """
    address = (address or "").strip()
    if not address:
        return AddrCheckResult(False, reason="unparsable", hint="尚未取得地址")

    body: dict[str, object] = {"address": address}
    api_type = LOCATION_TYPE_TO_API_TYPE.get(location_type) if location_type else None
    if api_type:
        body["type"] = api_type
    if town:
        body["town"] = town

    endpoint = f"{url or _base_url()}{VERIFY_PATH}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    bearer = token if token is not None else _token()
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"

    request = Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    call_timeout = timeout if timeout is not None else _timeout()
    try:
        with urlopen(request, timeout=call_timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # 400（body/type 不合法）、401（token 錯）等：盡量帶出後端的 hint
        hint = None
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            if isinstance(detail, dict):
                hint = detail.get("hint")
        except Exception:
            pass
        return AddrCheckResult(None, error=f"HTTP {exc.code}", hint=hint)
    except Exception as exc:
        return AddrCheckResult(None, error=str(exc))

    if not isinstance(payload, dict):
        return AddrCheckResult(None, error="回應格式非物件")

    return AddrCheckResult(
        status=bool(payload.get("status")),
        reason=payload.get("reason"),
        address=payload.get("address"),
        hint=payload.get("hint"),
    )


# ───────────────────── 分類：捷運／地標名單載入（本地檔） ─────────────────────


def _split_aliases(value: str) -> Iterable[str]:
    for item in re.split(r"[、,，;；/／]+", str(value or "")):
        item = item.strip()
        if item:
            yield item


@lru_cache(maxsize=4)
def load_landmark_names(path: str = str(DEFAULT_LANDMARK_XLSX)) -> tuple[str, ...]:
    """讀取地標名稱與別名；模板為空時回傳空集合。供地點類別分類使用。"""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("讀取 landmarks.xlsx 需要安裝 openpyxl") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    headers = [str(v or "").strip() for v in next(rows, ())]
    required = ["地標名稱", "別名", "地址"]
    if headers[:3] != required:
        workbook.close()
        raise ValueError(f"地標 Excel 欄位必須為：{', '.join(required)}")

    names: list[str] = []
    for row in rows:
        primary = str(row[0] or "").strip() if len(row) > 0 else ""
        aliases = str(row[1] or "").strip() if len(row) > 1 else ""
        if primary:
            names.append(primary)
        names.extend(_split_aliases(aliases))
    workbook.close()
    return tuple(dict.fromkeys(names))


@lru_cache(maxsize=4)
def load_mrt_location_names(path: str = str(DEFAULT_MRT_CSV)) -> tuple[str, ...]:
    """讀取 cp950 CSV 第二列，並補充不含出口編號的站名。供地點類別分類使用。"""
    names: list[str] = []
    with open(path, "r", encoding="cp950", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            raw = str(row[1] or "").strip()
            if not raw:
                continue
            names.append(raw)
            station = re.sub(r"(?:出口.*|[A-Za-z]\d+)$", "", raw).strip()
            if station:
                names.append(station)
    return tuple(dict.fromkeys(names))
