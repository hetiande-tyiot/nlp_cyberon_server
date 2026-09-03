"""case_field_labels_119.py — 119 CaseInfo119 欄位 key → 中文 label 對照表。

供 sop_api_server.py 的 `/schema/case-fields/labels` endpoint 使用。

Source: case_info_119.py 的 CaseInfo119 dataclass 欄位註解（119_0813_adjustSOP）
- `transcript` 是對話紀錄，**故意不放 label**（跟 110LLM 慣例一致）
- 欄位順序與 CaseInfo119 dataclass 定義一致
- 相對 0808 的變動：欄位 87 → 90（含 transcript），label 86 → 89
  - 地址拆得更細：新增 address_road（道路含段巷弄）、address_number（門牌號）
  - 新增 caller_is_patient（報案人是否即患者）
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
    "location_type": "地點型態",
    "address_district": "行政區",
    "address_road": "道路（含段、巷、弄）",
    "address_number": "門牌號",
    "intersection_road1": "路口第一條路",
    "intersection_road2": "路口第二條路",
    "highway_name": "國道/高速公路名稱",
    "highway_direction": "行駛方向",
    "highway_kilometer": "公里數",
    "address_validation_status": "地址校驗狀態",
    "jurisdiction_office": "管轄單位",
    "address_suspect_error": "地址疑似有誤",
    "address_error_reason": "地址錯誤原因",
    # 生命征象（救護專用）
    "consciousness": "是否有意識",
    "breathing": "是否有呼吸",
    "abdomen_rise": "肚子是否有起伏",
    "is_ohca": "是否判斷為 OHCA",
    # 患者基本資訊（救護專用）
    "patient_count": "傷病患人數",
    "patient_gender": "性別",
    "patient_age": "年齡",
    "caller_is_patient": "報案人是否即患者",
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
    # 火警 SOP 要素（通用）
    "fire_or_smoke": "看到火還是煙",
    "smoke_color": "煙的顏色",
    "burning_object": "燃燒物",
    "fire_trend": "火勢變化趨勢",
    "fire_extent": "火勢範圍",
    "fire_category": "火災類型",
    # 火警 — 建築物火災
    "caller_position": "報案人在建物內/外",
    "caller_role": "報案人身分",
    "people_trapped": "是否有人受困",
    "trapped_count": "受困人數",
    "building_total_floors": "建築物總樓層",
    "fire_floor": "起火樓層",
    "fire_spread": "是否有延燒",
    "building_layout": "建築物形式",
    # 火警 — 工廠火災
    "factory_scale_type": "工廠規模與型態",
    "factory_people_present": "廠內是否有人",
    "hazardous_materials": "危險物品狀況",
    # 火警 — 車輛火災
    "vehicle_type": "車種",
    "vehicle_count": "起火車輛數",
    "vehicle_occupants": "車內是否有人",
    "vehicle_occupant_count": "車內人數",
    "road_type": "道路類型",
    # 火警 — 露天野外火災
    "outdoor_fire_type": "露天火災型態",
    "nearby_water_source": "附近水源狀況",
    "affected_targets": "波及對象",
    # 觸發情境（急病 / 火警通用）
    "triggered_scenarios": "已觸發情境編號",
    "blood_glucose": "血糖值",
    "blood_pressure": "血壓值",
    "seizure_info": "抽搐相關",
    # 報案人訊息
    "caller_name": "報案人姓名",
    "caller_contact": "報案人聯繫方式",
    "caller_salutation": "報案人稱呼",
    "caller_address": "報案人住址",
    # 全類型通用標記
    "ImportantCase": "案件重要程度",
    "ImportantTag": "AI 重要標籤",
    "NeedPolice": "是否需轉介110",
    # 局內同仁回報
    "call_type": "來電類型",
    "report_request_type": "回報/請求類型",
    "field_report_content": "現場回報案情",
    "support_vehicle_type": "支援車輛類型",
    "support_vehicle_count": "支援車輛數量",
    "support_request_confirmed": "車型數量已覆誦確認",
    "has_additional_request": "是否尚有其他需求",
    # 火警派遣卡（FireDispatchCard 編碼）
    "fire_tab": "派遣卡分頁（A/B1/B2/C）",
    "fire_incident_type": "火警類型（0建築/1非建築）",
    "building_type_code": "建物類別代碼",
    "has_flame": "是否有火焰",
    "smoke_color_code": "煙霧顏色代碼",
    "has_explosion": "是否有爆炸",
    "spread_risk": "延燒風險",
    "people_trapped_code": "受困人員",
    "building_floors_code": "建物總樓層代碼",
    "fire_floor_code": "起火樓層代碼",
    "building_structure": "建物構造",
    "burn_area_code": "燃燒面積代碼",
    "access_water_info": "通道與水源",
    "non_building_fire": "非建築火警類型",
    "vehicle_wildfire_code": "交通工具/山林代碼",
    "minor_fire_code": "輕微火警代碼",
    # 元資訊
    "case_summary": "案情摘要",
    "flow_stage": "流程階段",
    "result": "結果",
}
