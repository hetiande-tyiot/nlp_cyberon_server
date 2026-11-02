"""分類結果徽章。硬規則、分類器、舊關鍵詞直判分開顯示。"""

from __future__ import annotations

import html
from typing import Any, Dict


def classification_badges_html(clf: Dict[str, Any]) -> str:
    """硬規則另顯示「疑似XXXX類」；分類器與舊關鍵詞直判不顯示疑似。"""
    badges = ""
    if clf.get("main"):
        conf = clf.get("main_conf")
        conf_str = f" {conf:.0%}" if isinstance(conf, (int, float)) else ""
        badges += (
            f'<span class="badge badge-main">🔹 {html.escape(str(clf["main"]))}'
            f"{conf_str}</span>"
        )
    source = clf.get("sub_source")
    if clf.get("sub"):
        conf = clf.get("sub_conf")
        conf_str = f" {conf:.0%}" if isinstance(conf, (int, float)) else ""
        label = html.escape(str(clf["sub"]))
        if source == "hard_rule":
            suffix = " · 硬規則"
        elif source == "classifier":
            suffix = " · 分類器"
        else:
            suffix = ""
        badges += (
            f'<span class="badge badge-sub">🔸 {label}{conf_str}{suffix}</span>'
        )
    suspected = clf.get("suspected_sub_category")
    if source == "hard_rule" and suspected:
        badges += (
            '<span class="badge badge-suspect">疑似'
            f"{html.escape(str(suspected))}類</span>"
        )
    if source == "keyword":
        badges += '<span class="badge badge-kw">🔑 關鍵詞直判</span>'
    return badges
