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
    location_type:     Optional[str]  = None  # address/intersection/landmark/highway/mrt
    address_district:  Optional[str]  = None  # 行政區（如「板橋區」）
    address_road:      Optional[str]  = None  # 道路（含段、巷、弄）
    address_number:    Optional[str]  = None  # 門牌號（如「32號」）
    intersection_road1: Optional[str] = None  # 交叉路口第一條路/巷
    intersection_road2: Optional[str] = None  # 交叉路口第二條路/巷
    highway_name:       Optional[str] = None  # 國道/高速公路名稱
    highway_direction:  Optional[str] = None  # 南向/北向
    highway_kilometer:  Optional[str] = None  # 公里數
    address_validation_status: Optional[str] = None  # pending/valid/invalid/error
    jurisdiction_office: Optional[str] = None  # 地址 API 回傳之管轄單位
    address_suspect_error: bool = False  # 抽取、校驗或確認失敗
    address_error_reason: Optional[str] = None  # 供前端顯示的錯誤原因

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
    caller_is_patient:    Optional[bool] = None  # True=報案人即患者
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
    fire_or_smoke:       Optional[str] = None  # 看到火、煙或僅聞到氣味
    smoke_color:         Optional[str] = None  # 黑煙/白煙/其他顏色
    burning_object:      Optional[str] = None  # 燒什麼（房子/車子/雜草…）
    fire_trend:          Optional[str] = None  # 變大/消退/穩定
    fire_extent:         Optional[str] = None  # 火勢大約範圍
    fire_category:       Optional[str] = None  # 舊四分類：建築物/工廠/車輛/露天野外

    # 火警垂片代碼（0 為合法已填值）
    fire_tab:              Optional[str] = None  # A / B1 / B2 / C
    fire_incident_type:    Optional[int] = None  # 0=建築物火警；1=非建築物火警
    building_type_code:    Optional[str] = None  # 00/10–12/20–29
    has_flame:             Optional[int] = None  # 0=無火焰；1=有火焰
    smoke_color_code:      Optional[int] = None  # 0=無煙；1=黑；2=白；3=其他
    has_explosion:         Optional[int] = None  # 0=無；1=有
    spread_risk:           Optional[int] = None  # 0=低；1=極可能或已延燒
    people_trapped_code:   Optional[int] = None  # 0=無人受困；1=有人受困
    building_floors_code:  Optional[int] = None  # 0未知；1=1~3；2=4~10；3=11~15；4=16+
    fire_floor_code:       Optional[int] = None  # 0未知；1地下室；2=1~3；3=4~10；4=11~15；5=16+
    building_structure:    Optional[int] = None  # 0其他；1木造；2鐵皮；3連造鐵皮；4磚；5RC；6SRC
    burn_area_code:        Optional[int] = None  # 0未知；1=0~50坪…5=500坪以上
    access_water_info:     Optional[int] = None  # 0一般；1小巷；2缺水；3小巷且缺水
    non_building_fire:     Optional[int] = None  # 0=交通工具及山林；1=輕微火警
    vehicle_wildfire_code: Optional[int] = None  # 0~6交通工具；7平地；8山地
    minor_fire_code:       Optional[int] = None  # 0垃圾；1電線桿；2瓦斯；3警報；4查看

    # 建築物火災
    caller_position:      Optional[str] = None  # 報案人在建物內/外
    caller_role:          Optional[str] = None  # 住戶/鄰居/路過民眾
    people_trapped:       Optional[bool] = None  # 是否有人受困
    trapped_count:        Optional[str] = None  # 受困人數
    building_total_floors: Optional[str] = None  # 建築物總樓層
    fire_floor:           Optional[str] = None  # 起火樓層
    fire_spread:          Optional[bool] = None  # 是否有延燒
    building_layout:      Optional[str] = None  # 連棟/頂樓加蓋等

    # 工廠火災
    factory_scale_type:     Optional[str] = None  # 小型/大型鐵皮/連棟工廠
    factory_people_present: Optional[bool] = None  # 廠內是否有人
    hazardous_materials:    Optional[str] = None  # 化學品或危險物品狀況

    # 車輛火災
    vehicle_type:           Optional[str] = None  # 車種
    vehicle_count:          Optional[str] = None  # 起火車輛數
    vehicle_occupants:      Optional[bool] = None  # 車內是否有人
    vehicle_occupant_count: Optional[str] = None  # 車內人數
    road_type:              Optional[str] = None  # 一般道路/高速公路

    # 露天野外火災
    outdoor_fire_type:  Optional[str] = None  # 雜草垃圾/山林/高速公路
    nearby_water_source: Optional[str] = None  # 水源或消防栓狀況
    affected_targets:   Optional[str] = None  # 波及建物/車輛/人員

    # ── 觸發情境（急病 / 火警通用）────────────────────────────────────────────
    triggered_scenarios: List[int]  = field(default_factory=list)  # 已觸發情境編號清單
    blood_glucose:       Optional[str] = None  # 血糖值（回應11）
    blood_pressure:      Optional[str] = None  # 血壓值（回應16）
    seizure_info:        Optional[str] = None  # 抽搐相關（回應14）

    # ── 報案人訊息 ──────────────────────────────────────────────────────────
    caller_name:       Optional[str] = None  # 報案人姓名
    caller_contact:    Optional[str] = None  # 報案人聯繫方式（電話/手機）
    caller_salutation: Optional[str] = None  # 報案人明確選擇的稱呼（先生/小姐）
    caller_address:    Optional[str] = None  # 報案人住址（急病等次類別專用）

    # ── 全類型通用標記 ──────────────────────────────────────────────────────
    ImportantCase: int = 0  # 0=預設, 1=一般處理, 2=緊急處理
    ImportantTag: List[str] = field(default_factory=list)  # AI 標籤（白名單、去重）
    NeedPolice: Optional[bool] = None  # 是否需要警察

    # ── 局內同仁回報 ────────────────────────────────────────────────────────
    call_type: Optional[str] = None  # 局內回報 / 一般案件
    report_request_type: Optional[str] = None  # 現場回報 / 支援請求
    field_report_content: Optional[str] = None  # 本次現場回報案情
    support_vehicle_type: Optional[str] = None  # 支援車輛類型
    support_vehicle_count: Optional[int] = None  # 支援車輛數量
    support_request_confirmed: Optional[bool] = None  # 車型與數量覆誦結果
    has_additional_request: Optional[bool] = None  # 是否尚有其他協助需求

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
    #   火警：火警_location → 火警_location_confirm → 火警_route_1 / 火警_route_2
    #   → 火警_A_* | 火警_B1_* | 火警_B2_* | 火警_C_* → 火警_safety
    #   → 火警_summary_confirm → 火警_caller_info → completed
    #   緊急救援：緊急救援_location → 緊急救援_location_confirm
    #   → 緊急救援_incident → 緊急救援_summary_confirm → 緊急救援_caller_info → completed
    #   局內回報：局內回報_need → 局內回報_location
    #   → 局內回報_field_content | 局內回報_support_detail
    #   → 局內回報_support_confirm → 局內回報_more → completed

    result: Optional[str] = None
    # result 取值：
    #   "dispatched"      — 救護車/消防車/救援人員已派出，流程正常完成
    #   "ohca_transfer"   — 判斷為 OHCA，已轉人工
    #   "human_transfer"  — 報案人等必要資訊無法確認，已轉人工
    #   "manual_end"      — 操作員主動結束流程
    #   "error"           — 流程異常終止
    #   "report_recorded" — 局內現場回報已記錄（示範模式）
    #   "support_dispatched" — 局內支援車輛已派遣（示範模式）

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
        if field == "ImportantCase" and val == 0:
            return False
        if isinstance(val, str):
            return bool(val.strip())
        if isinstance(val, list):
            return bool(val)
        return True

    def filled_fields_for_summary(self) -> Dict[str, Any]:
        """
        返回適合傳給摘要 prompt 的已填欄位（排除 False 布林、None、
        transcript、flow_stage 等技術欄位）。
        """
        exclude = {
            "transcript", "flow_stage", "result",
            "main_conf", "sub_conf", "address_confirmed",
            "address_validation_status", "address_suspect_error",
            "address_error_reason",
            "is_ohca", "caller_name", "caller_contact", "caller_salutation",
            "caller_address",
            "triggered_scenarios",
        }
        out: Dict[str, Any] = {}
        for k, v in self.to_dict().items():
            if k in exclude:
                continue
            if v is None or v is False:
                continue
            if k == "ImportantCase" and v == 0:
                continue
            if isinstance(v, list) and len(v) == 0:
                continue
            out[k] = v
        return out
