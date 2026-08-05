"""case_field_labels_119.py — 119 CaseInfo119 欄位 key → 中文 label 對照表。

供 sop_api_server.py 的 `/schema/case-fields/labels` endpoint 使用。

Source: case_info_119.py 的 CaseInfo119 dataclass 欄位註解（119_0724_add_2maincategory）
- `transcript` 是對話紀錄，**故意不放 label**（跟 110LLM 慣例一致）
- 欄位順序與 CaseInfo119 dataclass 定義一致
- 相對 0721_v2 新增「火警 SOP 要素」6 欄位（fire_or_smoke ... fire_floor）
"""

from __future__ import annotations

from typing import Dict

# ── CaseInfo119 對外欄位 label（不含 transcript） ──────────────────────────
LABELS: Dict[str, str] = {
    # 分類結果
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
    # 患者基本資訊（救護專用）
    "patient_count": "傷病患人數",
    "patient_gender": "性別",
    "patient_age": "年齡",
    "incident_description": "發生了什麼事",
    "current_condition": "目前狀況",
    "injury_cause": "受傷原因",
    "injury_location": "受傷部位",
    "injury_severity": "傷勢",
    "tocc": "TOCC（旅遊/職業/接觸/群聚史）",
    "medical_history": "過去病史",
    "collapse_cause": "路倒原因",
    "ingested_substance": "服藥種類與數量",
    # 孕婦急產專用
    "pregnancy_week": "胎次與孕週",
    "due_date": "預產期",
    "multiple_pregnancy": "單或雙胞胎",
    "water_broken_bleeding": "破水/出血狀況",
    "contractions": "宮縮情況",
    "prenatal_history": "產檢異常史",
    "prenatal_clinic": "產檢醫院/診所",
    # 火警 SOP 要素
    "fire_or_smoke": "看到火還是煙",
    "smoke_color": "煙的顏色",
    "smoke_trend": "煙的變化趨勢",
    "flame_observation": "火舌/火花觀察",
    "burning_object": "燃燒物",
    "fire_floor": "起火樓層",
    # 觸發情境（急病 / 火警通用）
    "triggered_scenarios": "已觸發情境編號",
    "blood_glucose": "血糖值",
    "blood_pressure": "血壓值",
    "seizure_info": "抽搐相關",
    # 報案人訊息
    "caller_name": "報案人姓名",
    "caller_contact": "報案人聯繫方式",
    "caller_address": "報案人住址",
    # 元資訊
    "case_summary": "案情摘要",
    "flow_stage": "流程階段",
    "result": "結果",
}
