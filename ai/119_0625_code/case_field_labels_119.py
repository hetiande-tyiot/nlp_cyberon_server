"""case_field_labels_119.py — 119 CaseInfo119 欄位 key → 中文 label 對照表。

供 sop_api_server_119.py 的 `/schema/case-fields/labels` endpoint 使用。

Source: case_info_119.py 的 CaseInfo119 dataclass 註解（vendor 內無對應 SLOT_LABELS）
- `transcript` 是對話紀錄，**故意不放 label**（跟 110LLM 慣例一致）
"""

from __future__ import annotations

from typing import Dict

# ── CaseInfo119 對外欄位 label（17 條，不含 transcript） ──────────────────
LABELS: Dict[str, str] = {
    # 分類
    "main_category": "主類別",
    "main_conf": "主類置信度",
    "sub_category": "子類別",
    "sub_conf": "子類置信度",
    # 地址
    "address": "完整地址",
    "address_confirmed": "地址已確認",
    # 生命征象（救護專用）
    "consciousness": "是否有意識",
    "breathing": "是否有呼吸",
    "abdomen_rise": "肚子是否有起伏",
    "is_ohca": "是否判斷為 OHCA",
    # 患者基本資訊
    "patient_gender": "性別",
    "patient_age": "年齡",
    "incident_description": "發生了什麼事",
    "current_condition": "目前狀況",
    # 元資訊
    "case_summary": "案情摘要",
    "flow_stage": "流程階段",
    "result": "結果",
}
