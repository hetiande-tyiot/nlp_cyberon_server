"""119 地址类别的数据加载与外部辖区校验。"""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JURISDICTION_API_URL = (
    "http://61.216.64.19:8055/Template/Office/data"
)
DEFAULT_MRT_CSV = BASE_DIR / "scripts" / "MRTstation.csv"
DEFAULT_LANDMARK_XLSX = BASE_DIR / "scripts" / "landmarks.xlsx"


@dataclass(frozen=True)
class JurisdictionResult:
    """辖区 API 结果；valid=None 表示网络或响应格式异常。"""

    valid: Optional[bool]
    office_name: Optional[str] = None
    error: Optional[str] = None


def _extract_office_name(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        value = payload.get("officeName")
        if value is not None and str(value).strip():
            return str(value).strip()
        for key in ("data", "result"):
            nested = payload.get(key)
            found = _extract_office_name(nested)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_office_name(item)
            if found:
                return found
    return None


def query_jurisdiction(
    address: str,
    *,
    url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> JurisdictionResult:
    """查询地址辖区；仅非空 officeName 代表地址有效。"""
    api_url = url or os.getenv(
        "JURISDICTION_API_URL", DEFAULT_JURISDICTION_API_URL
    )
    if timeout is None:
        try:
            timeout = float(os.getenv("JURISDICTION_API_TIMEOUT", "2.5"))
        except ValueError:
            timeout = 2.5
    request_url = f"{api_url}?{urlencode({'addr': address})}"
    request = Request(request_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return JurisdictionResult(None, error=str(exc))
    office_name = _extract_office_name(payload)
    return JurisdictionResult(bool(office_name), office_name=office_name)


def _normalized_name(value: str) -> str:
    return re.sub(r"[\s　，,。．、;；/／()（）]+", "", str(value or "")).lower()


def _split_aliases(value: str) -> Iterable[str]:
    for item in re.split(r"[、,，;；/／]+", str(value or "")):
        item = item.strip()
        if item:
            yield item


@lru_cache(maxsize=4)
def load_landmark_names(path: str = str(DEFAULT_LANDMARK_XLSX)) -> tuple[str, ...]:
    """读取地标名称与别名；模板为空时返回空集合。"""
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
    """读取 cp950 CSV 第二列，并补充不含出口编号的站名。"""
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


def contains_known_name(location: str, names: Iterable[str]) -> bool:
    """地点文字是否包含名单名称，忽略空白与常见标点。"""
    target = _normalized_name(location)
    return bool(target) and any(
        normalized and normalized in target
        for normalized in (_normalized_name(name) for name in names)
    )


def validate_landmark(
    location: str,
    *,
    path: str = str(DEFAULT_LANDMARK_XLSX),
) -> bool:
    return contains_known_name(location, load_landmark_names(path))


def validate_mrt(
    location: str,
    *,
    path: str = str(DEFAULT_MRT_CSV),
) -> bool:
    return contains_known_name(location, load_mrt_location_names(path))
