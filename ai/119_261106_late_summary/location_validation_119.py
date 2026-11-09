"""119 地址类别的数据加载与外部辖区校验。"""

from __future__ import annotations

import csv
import json
import time
import os
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import timing_119
from addrcheck_log_119 import log_addrcheck


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JURISDICTION_API_URL = (
    "http://100.107.145.7:8088/api/AddrCheck/Verify"
)
DEFAULT_MRT_CSV = BASE_DIR / "scripts" / "MRTstation.csv"
DEFAULT_LANDMARK_XLSX = BASE_DIR / "scripts" / "landmarks.xlsx"

# ── addrCheck 地址驗測（地址確認全面改走 addrCheck /Verify）──
# env：ADDRCHECK_API_URL / ADDRCHECK_API_TOKEN（Bearer，與 ACRC 共用 Ingest__Token）
#      / ADDRCHECK_API_TIMEOUT（預設 2.5）
#      / ADDRCHECK_API_FALLBACK_URL（備用位址：主位址連線被拒、HTTP 錯誤或回應格式不對時改打這個；
#        主位址等滿逾時秒數都沒回應就直接放棄，不再打備用位址，免得通話多等一輪）
DEFAULT_ADDRCHECK_BASE_URL = "http://192.168.5.85:8088"
DEFAULT_ADDRCHECK_FALLBACK_URL = "http://100.107.145.7:8088"
ADDRCHECK_VERIFY_PATH = "/api/AddrCheck/Verify"

# 內部地點型態 → addrCheck API 的 type（帶 type 只查該層；None 讓後端自動判斷）
LOCATION_TYPE_TO_API_TYPE = {
    "address": "House",
    "intersection": "Crossroad",
    "highway": "Freeway",
    "landmark": "Landmark",
    "mrt": "Landmark",
}


@dataclass(frozen=True)
class JurisdictionResult:
    """辖区 API 结果；valid=None 表示网络或响应格式异常。"""

    valid: Optional[bool]
    office_name: Optional[str] = None
    error: Optional[str] = None
    api_reason: Optional[str] = None  # addrCheck 回傳之 reason（road_only/not_found…）


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


def _addrcheck_token() -> str:
    """addrCheck Bearer token（與 ACRC 共用 Ingest__Token）。"""
    for key in ("ADDRCHECK_API_TOKEN", "INGEST_TOKEN", "Ingest__Token"):
        value = os.getenv(key)
        if value:
            return value
    return ""


# addrCheck 失敗分類 → 值班看板上的錯誤說明
ADDRCHECK_REASON_TEXT = {
    "road_only": "查無此門牌",
    "not_found": "查無此路段",
    "invalid_format": "地址格式無法解析",
    "ambiguous": "同一門牌在多個路段都有，需確認段別",
}
DEFAULT_ADDRCHECK_FAILURE_TEXT = "地址驗測查無此地點"


def addrcheck_failure_reason(api_reason: Optional[str]) -> str:
    """把 addrCheck 的 reason 轉成可讀的錯誤說明。"""
    return ADDRCHECK_REASON_TEXT.get(
        (api_reason or "").strip(), DEFAULT_ADDRCHECK_FAILURE_TEXT
    )


def verify_address_detail(
    address: str,
    location_type: Optional[str] = None,
    *,
    url: Optional[str] = None,
    timeout: Optional[float] = None,
    call_uuid: Optional[str] = None,
) -> tuple[Optional[bool], Optional[str], Optional[str]]:
    """地址驗測核心：POST addrCheck /Verify，回 (status, hint, reason)。

    status True=有效 / False=查無 / None=網路或回應異常（API 無法使用）。
    location_type 轉成 API 的 type 只查該層；None 讓後端自動判斷。
    連不上時隔 1 秒再查一次，還是不行才回 None（所有地點型態都一樣）。
    每打一次 API 都寫一筆到資料庫 addrcheck_log；call_uuid 是哪一通電話，引擎以外呼叫時為 None。
    """
    address = (address or "").strip()
    if not address:
        return False, "尚未取得地址", None
    result = _verify_once(address, location_type, url, timeout, call_uuid)
    if result[0] is None:
        time.sleep(1)
        result = _verify_once(address, location_type, url, timeout, call_uuid)
    return result


def _verify_once(
    address: str,
    location_type: Optional[str],
    url: Optional[str],
    timeout: Optional[float],
    call_uuid: Optional[str],
) -> tuple[Optional[bool], Optional[str], Optional[str]]:
    """打一輪 addrCheck：主位址連線被拒等失敗時換備用位址。每打一次都寫一筆紀錄。"""
    base = (url or os.getenv("ADDRCHECK_API_URL", DEFAULT_ADDRCHECK_BASE_URL)).rstrip("/")
    bases = [base]
    # 呼叫端自己指定 url（測試、離線腳本）時只打那一個，不用備用位址
    fallback = os.getenv("ADDRCHECK_API_FALLBACK_URL", DEFAULT_ADDRCHECK_FALLBACK_URL).rstrip("/")
    if not url and fallback and fallback != base:
        bases.append(fallback)
    if timeout is None:
        try:
            timeout = float(os.getenv("ADDRCHECK_API_TIMEOUT", "2.5"))
        except ValueError:
            timeout = 2.5
    body: dict[str, object] = {"address": address}
    api_type = LOCATION_TYPE_TO_API_TYPE.get(location_type) if location_type else None
    if api_type:
        body["type"] = api_type
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = _addrcheck_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for base in bases:
        request = Request(
            f"{base}{ADDRCHECK_VERIFY_PATH}",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        called_at = datetime.now()
        _t0 = time.perf_counter()
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("回應格式非物件")
        except Exception as exc:
            # 逾時/連不上的耗時照樣記——外部 API 慢是常見的延遲來源
            elapsed_ms = (time.perf_counter() - _t0) * 1000.0
            timing_119.emit("addrcheck", api_type or "address", elapsed_ms, extra="error=1")
            log_addrcheck(call_uuid, address, api_type, None, None, None,
                          elapsed_ms, str(exc), called_at)
            # 等滿逾時秒數都沒回應：直接當 API 無法使用，不再打備用位址；
            # 其他失敗（連線被拒、HTTP 錯誤、回應格式不對）才換下一個位址
            timed_out = isinstance(exc, TimeoutError) or isinstance(
                getattr(exc, "reason", None), TimeoutError
            )
            if timed_out or base == bases[-1]:
                return None, str(exc), None
            continue
        elapsed_ms = (time.perf_counter() - _t0) * 1000.0
        timing_119.emit("addrcheck", api_type or "address", elapsed_ms)
        status, hint, reason = (
            bool(payload.get("status")),
            payload.get("hint"),
            payload.get("reason"),
        )
        log_addrcheck(call_uuid, address, api_type, status, reason, hint,
                      elapsed_ms, None, called_at)
        return status, hint, reason


def verify_address_status(
    address: str,
    location_type: Optional[str] = None,
    *,
    url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> tuple[Optional[bool], Optional[str]]:
    """verify_address_detail 的薄包裝，回 (status, hint)。"""
    status, hint, _reason = verify_address_detail(
        address, location_type, url=url, timeout=timeout
    )
    return status, hint


def query_jurisdiction(
    address: str,
    *,
    url: Optional[str] = None,
    timeout: Optional[float] = None,
    call_uuid: Optional[str] = None,
) -> JurisdictionResult:
    """一般地址（address 型態）驗測 → addrCheck House。

    回傳沿用 JurisdictionResult 維持引擎介面：valid=status，office_name 固定 None
    （119 不需管轄分局），valid=None 表示 API 無法使用。
    """
    status, hint, reason = verify_address_detail(
        address, "address", url=url, timeout=timeout, call_uuid=call_uuid
    )
    return JurisdictionResult(
        status, office_name=None, error=hint, api_reason=reason
    )


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
def load_landmark_alias_map(
    path: str = str(DEFAULT_LANDMARK_XLSX),
) -> dict:
    """讀地標「別名→正名」對映，供 STT 同音誤認正規化（南亞夜市→南雅夜市）。

    資料來源同 load_landmark_names（landmarks.xlsx：地標名稱 / 別名 / 地址）。
    addrCheck 地標比對無相似度門檻，會把同音誤認硬配到別處；查詢前先用這張表
    把口語名改寫成正名，再送 addrCheck。
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("讀取 landmarks.xlsx 需要安裝 openpyxl") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    next(rows, ())  # 跳過表頭
    mapping: dict = {}
    for row in rows:
        primary = str(row[0] or "").strip() if len(row) > 0 else ""
        aliases = str(row[1] or "").strip() if len(row) > 1 else ""
        if not primary:
            continue
        for alias in _split_aliases(aliases):
            key = re.sub(r"\s+", "", alias)
            if key:
                mapping[key] = primary
    workbook.close()
    return mapping


def normalize_landmark_alias(
    name: Optional[str], path: str = str(DEFAULT_LANDMARK_XLSX)
) -> Optional[str]:
    """已知同音誤認的地標名改寫成正名；無對映或讀表失敗時原樣回傳。"""
    if not name:
        return name
    try:
        mapping = load_landmark_alias_map(path)
    except Exception:
        return name
    return mapping.get(re.sub(r"\s+", "", str(name)), name)


@lru_cache(maxsize=4)
def load_landmark_table(
    path: str = str(DEFAULT_LANDMARK_XLSX),
) -> tuple[tuple[str, tuple[str, ...], str], ...]:
    """讀地標表每一列：(地標名稱, (名稱與別名…), 地址)。地址空白的列不收（沒有地址就不能直接定位）。"""
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    next(rows, ())  # 跳過表頭
    table = []
    for row in rows:
        primary = str(row[0] or "").strip() if len(row) > 0 else ""
        aliases = str(row[1] or "").strip() if len(row) > 1 else ""
        address = str(row[2] or "").strip() if len(row) > 2 else ""
        if primary and address:
            table.append((primary, (primary, *_split_aliases(aliases)), address))
    workbook.close()
    return tuple(table)


def lookup_landmark_table(
    location: Optional[str], path: str = str(DEFAULT_LANDMARK_XLSX)
) -> Optional[tuple[str, str]]:
    """報案人講的地點有包含地標表上的名稱或別名，就回傳 (地標名稱, 地址)；沒有或讀表失敗回 None。"""
    target = _normalized_name(location or "")
    if not target:
        return None
    try:
        table = load_landmark_table(path)
    except Exception:
        return None
    for primary, names, address in table:
        if any(_normalized_name(n) and _normalized_name(n) in target for n in names):
            return primary, address
    return None


# 機場線各站（交通部鐵道局「機場捷運車站位置座標」），addrCheck 只認「○○站」，不帶出口
AIRPORT_MRT_STATIONS = frozenset((
    "台北車", "三重", "新北產業園區", "新莊副都心", "泰山", "泰山貴和", "體育大學",
    "長庚醫院", "林口", "山鼻", "坑口", "機場第一航廈", "機場第二航廈", "機場第三航廈",
    "機場旅館", "大園", "橫山", "領航", "高鐵桃園", "桃園體育園區", "興南", "環北",
))
# 機場線和其他線都有的站：報案人有講「機捷」「機場捷運」才算機場線
AIRPORT_MRT_SHARED = frozenset(("台北車", "三重", "新北產業園區"))


def _mrt_station_core(raw: str) -> str:
    """名單上的名稱去掉出口和「站」，留下站名本體（「頂埔站出口1」→「頂埔」、「台北車站M1」→「台北車」）。"""
    return re.sub(r"站?(?:出口\w*|M\d+)?$", "", raw.replace("臺", "台")).strip()


@lru_cache(maxsize=4)
def load_mrt_exits(path: str = str(DEFAULT_MRT_CSV)) -> dict:
    """捷運名單整理成 {站名本體: {出口編號: 名單上的寫法}}；沒有出口編號的列記在空字串底下。"""
    stations: dict = {}
    with open(path, "r", encoding="cp950", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            raw = str(row[1] or "").strip() if len(row) > 1 else ""
            if not raw:
                continue
            exit_no = str(row[2] or "").strip() if len(row) > 2 else ""
            exit_no = "" if exit_no == "0" else exit_no.upper()
            stations.setdefault(_mrt_station_core(raw), {})[exit_no] = raw
    return stations


def mrt_query_candidates(spoken: Optional[str]) -> Optional[tuple[str, ...]]:
    """把報案人講的捷運站改成 addrCheck 認得的寫法，依序列出要試的幾種（第一個完全比對到的就採用）。

    addrCheck 的捷運資料寫法不一：多數是「府中捷運站2號出口」，也有名單原本的「南港展覽館站出口2A」
    「台北車站M1」，機場線只認「泰山貴和站」。名單上找不到站名就回 None，照原話查。
    """
    from sop_utils_119 import chinese_numerals_to_digits

    # 不先轉整句中文數字：站名裡也有數字（三重、七張、十四張）
    text = re.sub(r"\s+", "", (spoken or "").replace("臺", "台"))
    try:
        stations = load_mrt_exits()
    except Exception:
        return None
    found = [core for core in stations if core and core in text]
    if not found:
        return None
    core = max(found, key=len)
    airport_said = "機捷" in text or "機場捷運" in text
    if core in AIRPORT_MRT_STATIONS and (core not in AIRPORT_MRT_SHARED or airport_said):
        return (f"{core}站",)
    exit_token = r"([A-Za-z]?(?:\d+|[一二兩三四五六七八九十]+)[A-Za-z]?)"
    m = (re.search(exit_token + r"號?出口", text.replace(core, "", 1))
         or re.search(r"出口" + exit_token, text))
    exit_no = chinese_numerals_to_digits(m.group(1)).upper() if m else ""
    candidates = []
    if exit_no:
        candidates.append(f"{core}捷運站{exit_no}號出口")
        if exit_no in stations[core]:
            candidates.append(stations[core][exit_no])
    candidates += [f"{core}捷運站", f"{core}站"]
    return tuple(dict.fromkeys(candidates))


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
    """地標驗測改走 addrCheck type=Landmark；path 參數保留相容。"""
    return verify_address_status(location, "landmark")[0] is True


def validate_mrt(
    location: str,
    *,
    path: str = str(DEFAULT_MRT_CSV),
) -> bool:
    """捷運驗測改走 addrCheck type=Landmark；path 參數保留相容。"""
    return verify_address_status(location, "mrt")[0] is True
