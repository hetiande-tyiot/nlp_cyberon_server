"""
address_mapper_119.py
━━━━━━━━━━━━━━━━━━━━
三輪地址歸一化：行政區 → 街路 → 其他地址。

映射表放在本專案 scripts/ 目錄（map_city.json / map_street.json /
map_other_road.json）。若臺語相似度模組 ese.py 可用，則啟用行政區模糊備援。
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, Optional

_THIS_DIR = Path(__file__).resolve().parent
_TW_UTILS_DIR = _THIS_DIR / "scripts"

try:
    _ese_utils_dir = str(_TW_UTILS_DIR)
    if _ese_utils_dir not in sys.path:
        sys.path.insert(0, _ese_utils_dir)
    from ese import (  # type: ignore
        chinese_to_tl as _chinese_to_tl,
        similarity_score as _similarity_score,
    )
except Exception:
    _chinese_to_tl = None  # type: ignore[assignment]
    _similarity_score = None  # type: ignore[assignment]

_DISTRICT_CANDIDATES_FOR_NORM: list[str] = [
    "八里區", "三芝區", "三重區", "三峽區", "土城區", "中和區", "五股區",
    "平溪區", "永和區", "石門區", "石碇區", "汐止區", "坪林區", "林口區",
    "板橋區", "金山區", "泰山區", "烏來區", "貢寮區", "淡水區", "深坑區",
    "新店區", "新莊區", "瑞芳區", "萬裡區", "樹林區", "雙溪區", "蘆洲區",
    "鶯歌區",
]


def _addr_build_regex_from_keys(mapping: Dict[str, str]) -> re.Pattern:
    keys = [k for k in mapping.keys() if k]
    keys.sort(key=len, reverse=True)
    pattern = "|".join(re.escape(k) for k in keys)
    return re.compile(pattern)


class ThreeStageLocationMapper:
    """
    三輪地址歸一化：
      1. 行政區映射（含臺語模糊備援匹配）
      2. 街路映射
      3. 其它地址映射
    """

    def __init__(
        self,
        utils_dir: Path = _TW_UTILS_DIR,
        district_mapping_path: Optional[str] = None,
        street_mapping_path: Optional[str] = None,
        other_mapping_path: Optional[str] = None,
    ) -> None:
        def _load_json(p: Path) -> Dict[str, str]:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)

        dp = Path(district_mapping_path) if district_mapping_path else utils_dir / "map_city.json"
        sp = Path(street_mapping_path) if street_mapping_path else utils_dir / "map_street.json"
        op = Path(other_mapping_path) if other_mapping_path else utils_dir / "map_other_road.json"

        self.district_mapping: Dict[str, str] = _load_json(dp)
        self.street_mapping: Dict[str, str] = _load_json(sp)
        self.other_mapping: Dict[str, str] = _load_json(op)

        self._district_pattern = _addr_build_regex_from_keys(self.district_mapping)
        self._street_pattern = _addr_build_regex_from_keys(self.street_mapping)
        self._other_pattern = _addr_build_regex_from_keys(self.other_mapping)

        if callable(_chinese_to_tl):
            self._district_tl: Dict[str, str] = {
                name: _chinese_to_tl(name) for name in _DISTRICT_CANDIDATES_FOR_NORM
            }
        else:
            self._district_tl = {}

    def _apply_simple_mapping(
        self,
        text: str,
        mapping: Dict[str, str],
        pattern: re.Pattern,
    ) -> str:
        if not isinstance(text, str) or not text:
            return text

        def _sub(m: re.Match) -> str:
            return mapping.get(m.group(0), m.group(0))

        return pattern.sub(_sub, text)

    def _fuzzy_match_district_by_tl(self, wrong_name: str) -> Optional[str]:
        if not self._district_tl:
            return None
        if not isinstance(wrong_name, str) or not wrong_name:
            return None
        wrong_tl = _chinese_to_tl(wrong_name)  # type: ignore[call-arg]
        if not wrong_tl:
            return None
        best_name: Optional[str] = None
        best_score: float = -1.0
        for name, tl in self._district_tl.items():
            if not tl:
                continue
            score = _similarity_score(wrong_tl, tl)  # type: ignore[call-arg]
            if score > best_score:
                best_score = score
                best_name = name
        return best_name

    def _apply_district_with_fallback(self, text: str) -> str:
        if not isinstance(text, str) or not text:
            return text
        replaced = self._apply_simple_mapping(
            text, self.district_mapping, self._district_pattern,
        )
        if replaced != text:
            return replaced
        try:
            idx = text.index("區")
        except ValueError:
            return text
        if idx < 2:
            return text
        wrong_segment = text[idx - 2: idx + 1]
        best_district = self._fuzzy_match_district_by_tl(wrong_segment)
        if not best_district:
            return text
        return text.replace(wrong_segment, best_district, 1)

    def map_location(self, location: str) -> str:
        """依序執行三輪映射：行政區 → 街路 → 其他地址。"""
        if not isinstance(location, str):
            return location
        text = location.strip()
        if not text:
            return location
        s1 = self._apply_district_with_fallback(text)
        s2 = self._apply_simple_mapping(s1, self.street_mapping, self._street_pattern)
        s3 = self._apply_simple_mapping(s2, self.other_mapping, self._other_pattern)
        return s3


_LOCATION_MAPPER_INSTANCE: Optional[ThreeStageLocationMapper] = None


def get_location_mapper() -> Optional[ThreeStageLocationMapper]:
    """進程內單例；載入失敗時回傳 None，呼叫端應跳過歸一化。"""
    global _LOCATION_MAPPER_INSTANCE
    if _LOCATION_MAPPER_INSTANCE is not None:
        return _LOCATION_MAPPER_INSTANCE
    try:
        _LOCATION_MAPPER_INSTANCE = ThreeStageLocationMapper()
        return _LOCATION_MAPPER_INSTANCE
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "[ThreeStageLocationMapper] 初始化失敗，地址歸一化將跳過。原因：%s",
            exc,
        )
        return None
