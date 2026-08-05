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
    main_category: Optional[str]  = None   # 主類別（火警/救護/緊急救援/災害/...）
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
    patient_count:        Optional[str] = None  # 傷病患人數
    patient_gender:       Optional[str] = None  # 性別
    patient_age:          Optional[str] = None  # 年齡
    incident_description: Optional[str] = None  # 發生了什麼事
    current_condition:    Optional[str] = None  # 目前狀況
    injury_cause:         Optional[str] = None  # 受傷原因（一般受傷專用）
    injury_location:      Optional[str] = None  # 受傷部位（一般受傷專用）
    injury_severity:      Optional[str] = None  # 傷勢（一般受傷專用）
    tocc:                 Optional[str] = None  # TOCC（旅遊/職業/接觸/群聚史）
    medical_history:      Optional[str] = None  # 過去病史（路倒專用）
    collapse_cause:       Optional[str] = None  # 路倒原因（路倒專用）
    ingested_substance:   Optional[str] = None  # 服藥種類與數量（吞食藥物專用）

    # ── 孕婦急產專用 ─────────────────────────────────────────────────────────────
    pregnancy_week:        Optional[str] = None  # 胎次與孕週（如「第1胎32週」）
    due_date:              Optional[str] = None  # 預產期
    multiple_pregnancy:    Optional[str] = None  # 單或雙胞胎
    water_broken_bleeding: Optional[str] = None  # 破水/出血狀況
    contractions:          Optional[str] = None  # 宮縮情況（如「5分鐘一次」）
    prenatal_history:      Optional[str] = None  # 產檢異常史
    prenatal_clinic:       Optional[str] = None  # 產檢醫院/診所

    # ── 火警 SOP 要素 ────────────────────────────────────────────────────────
    fire_or_smoke:      Optional[str] = None  # 看到火還是煙（火/煙/兩者）
    smoke_color:        Optional[str] = None  # 黑煙/白煙
    smoke_trend:        Optional[str] = None  # 持續冒/變大/消散
    flame_observation:  Optional[str] = None  # 火舌/火花/無
    burning_object:     Optional[str] = None  # 燒什麼（房子/車子/雜草…）
    fire_floor:         Optional[str] = None  # 幾樓在燒

    # ── 觸發情境（急病 / 火警通用）────────────────────────────────────────────
    triggered_scenarios: List[int]  = field(default_factory=list)  # 已觸發情境編號清單
    blood_glucose:       Optional[str] = None  # 血糖值（回應11）
    blood_pressure:      Optional[str] = None  # 血壓值（回應16）
    seizure_info:        Optional[str] = None  # 抽搐相關（回應14）

    # ── 報案人訊息 ──────────────────────────────────────────────────────────
    caller_name:    Optional[str] = None  # 報案人姓名
    caller_contact: Optional[str] = None  # 報案人聯繫方式（電話/手機）
    caller_address: Optional[str] = None  # 報案人住址（急病等次類別專用）

    # ── 元資訊 ──────────────────────────────────────────────────────────────
    transcript:   List[Dict[str, str]] = field(default_factory=list)
    # transcript 格式：[{"role": "assistant"|"caller", "text": "..."}, ...]

    case_summary: Optional[str] = None   # LLM 每輪更新的案情摘要
    flow_stage:   str           = "initial"
    # flow_stage 取值：
    #   initial → main_classified → 救護_location → 救護_location_confirm
    #   → 救護_sub_classified → 救護_vital_1 → 救護_vital_2 → 救護_vital_3
    #   → 救護_patient_1 → 救護_patient_2 → 救護_patient_3
    #   → 救護_summary_confirm → 急病_S0 → 急病_S1 → 急病_S2 → 急病_S6（急病專用）
    #   → 一般受傷_injury_cause → 一般受傷_injury_detail → 一般受傷_tocc（一般受傷專用）
    #   → 路倒_medical_history → 路倒_collapse_cause → 路倒_tocc（路倒專用）
    #   → 救護_caller_info → completed | ohca_transfer
    #   火警：火警_location → 火警_location_confirm → 火警_phone
    #   → 火警_smoke_1..6 → 火警_summary_confirm → 火警_caller_info → completed
    #   緊急救援：緊急救援_location → 緊急救援_location_confirm
    #   → 緊急救援_incident → 緊急救援_summary_confirm → 緊急救援_caller_info → completed

    result: Optional[str] = None
    # result 取值：
    #   "dispatched"      — 救護車/消防車/救援人員已派出，流程正常完成
    #   "ohca_transfer"   — 判斷為 OHCA，已轉人工
    #   "human_transfer"  — 地址/報案人等必要資訊無法確認，已轉人工
    #   "manual_end"      — 操作員主動結束流程
    #   "error"           — 流程異常終止

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
            "is_ohca", "caller_name", "caller_contact", "caller_address",
            "triggered_scenarios",
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
