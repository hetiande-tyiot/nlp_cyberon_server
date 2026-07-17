"""
case_info_119.py
━━━━━━━━━━━━━━━━
119 報案受理系統 — 案件資訊容器

所有欄位均為 Optional，預設 None，代表「尚未抽取」。
布林欄位語意：True=是/有, False=否/無, None=不確定/未提及。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CaseInfo119:
    # ── 分類結果 ────────────────────────────────────────────────────────────
    main_category: Optional[str]  = None   # 主類別（火警/救護/災害/...）
    main_conf:     Optional[float] = None  # 主類置信度
    sub_category:  Optional[str]  = None   # 子類別（急病/車禍/...）
    sub_conf:      Optional[float] = None  # 子類置信度

    # ── 地址 ────────────────────────────────────────────────────────────────
    address:           Optional[str]  = None  # 完整事發地址（含樓層）
    address_confirmed: Optional[bool] = None  # 報警人是否已確認地址

    # ── 生命征象（救護專用）────────────────────────────────────────────────
    # True=有/是, False=沒有/否, None=不確定/未提及
    consciousness: Optional[bool] = None  # 是否有意識
    breathing:     Optional[bool] = None  # 是否有呼吸
    abdomen_rise:  Optional[bool] = None  # 肚子是否有起伏
    is_ohca:       bool           = False  # 是否判斷為 OHCA

    # ── 患者基本資訊（救護專用）────────────────────────────────────────────
    patient_gender:      Optional[str] = None  # 性別
    patient_age:         Optional[str] = None  # 年齡
    incident_description: Optional[str] = None  # 發生了什麼事
    current_condition:   Optional[str] = None  # 目前狀況

    # ── 元資訊 ──────────────────────────────────────────────────────────────
    transcript:   List[Dict[str, str]] = field(default_factory=list)
    # transcript 格式：[{"role": "assistant"|"caller", "text": "..."}, ...]

    case_summary: Optional[str] = None   # LLM 每輪更新的案情摘要
    flow_stage:   str           = "initial"
    # flow_stage 取值：
    #   initial → main_classified → 救護_location → 救護_location_confirm
    #   → 救護_sub_classified → 救護_vital_1 → 救護_vital_2 → 救護_vital_3
    #   → 救護_patient_1 → 救護_patient_2 → 救護_patient_3
    #   → 救護_summary_confirm → completed | ohca_transfer

    result: Optional[str] = None
    # result 取值：
    #   "dispatched"    — 救護車已派出，流程正常完成
    #   "ohca_transfer" — 判斷為 OHCA，已轉人工
    #   "error"         — 流程異常終止

    # ── 工具方法 ──────────────────────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        """序列化為純 Python dict（供 JSON 或 Streamlit 顯示）。"""
        d = asdict(self)
        return d

    def caller_texts(self) -> List[str]:
        """返回所有報警人輸入文本的列表。"""
        return [t["text"] for t in self.transcript if t.get("role") == "caller"]

    def full_caller_text(self) -> str:
        """拼接所有報警人輸入，以換行分隔。"""
        return "\n".join(self.caller_texts())

    def display_address(self) -> str:
        """返回完整地址，用於複讀確認。"""
        return self.address if self.address else "（未知）"

    def vital_signs_ok(self) -> bool:
        """三項生命征象是否全部確認（True）。"""
        return (
            self.consciousness is True
            and self.breathing is True
            and self.abdomen_rise is True
        )

    def vital_signs_ohca(self) -> bool:
        """任一生命征象為 False 或 None → 判斷為 OHCA。"""
        return not self.vital_signs_ok()

    def is_field_filled(self, field: str) -> bool:
        """欄位是否已有抽取結果（非空）。"""
        val = getattr(self, field, None)
        if val is None:
            return False
        if isinstance(val, str):
            return bool(val.strip())
        return True

    def filled_fields_for_summary(self) -> Dict[str, Any]:
        """
        返回適合傳給摘要 prompt 的已填欄位（排除 False 布林、None、
        transcript、flow_stage 等技術欄位）。
        """
        exclude = {
            "transcript", "flow_stage", "result",
            "main_conf", "sub_conf", "address_confirmed",
            "is_ohca",
        }
        out: Dict[str, Any] = {}
        for k, v in self.to_dict().items():
            if k in exclude:
                continue
            if v is None or v is False:
                continue
            if isinstance(v, list) and len(v) == 0:
                continue
            out[k] = v
        return out
