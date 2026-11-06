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
    # 硬規則命中時與 sub_category 同值，提醒受理員「疑似XXXX類」。
    # 分類器或舊的高貼合關鍵詞直判不填。
    suspected_sub_category: Optional[str] = None
    level:         int            = 0      # 派遣等級：0 未分級，1 一級，2 二級，3 三級。火警依次案類與報案人描述只升不降；救護依傷病患人數（2 人以上 2，其他包含沒講人數都是 1）；其他大類目前固定 0

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
    # addrCheck 依讀音把地址改過時的提示。API 自己會警告「兩者讀音相同，
    # 向報案人複述路名無法分辨」——覆誦得到的「對」不具鑑別力，所以要讓
    # 受理員知道這個路名是系統改的，不是報案人講的。
    address_corrected_note: Optional[str] = None

    # ── 生命征象（救護專用）────────────────────────────────────────────────
    # True=有/是, False=沒有/否, None=不確定/未提及
    consciousness: Optional[bool] = None  # 是否有意識
    breathing:     Optional[bool] = None  # 是否有呼吸
    abdomen_rise:  Optional[bool] = None  # 肚子是否有起伏
    is_ohca:       bool           = False  # 是否判斷為 OHCA

    # ── 患者基本資訊（救護專用）────────────────────────────────────────────
    patient_count:        Optional[str] = None  # 患者人數
    patient_gender:       Optional[str] = None  # 性別
    patient_age:          Optional[str] = None  # 年齡
    caller_is_patient:    Optional[bool] = None  # True=報案人即患者
    incident_description: Optional[str] = None  # 發生了什麼事（緊急救援用；救護的病徵、主訴各有自己的欄位）
    current_condition:    Optional[str] = None  # 目前狀況
    injury_cause:         Optional[str] = None  # 受傷原因（一般受傷專用）
    injury_location:      Optional[str] = None  # 受傷部位（一般受傷專用）
    injury_severity:      Optional[str] = None  # 傷勢（一般受傷專用）
    injury_place:         Optional[str] = None  # 發生場所（一般受傷）：住家室內、戶外等，照報案人說的記
    crash_vehicles:       Optional[str] = None  # 事故車種（救護-車禍）：照報案人說的記，例：汽車撞機車
    crash_trapped:        Optional[str] = None  # 人員受困（救護-車禍）：未知/無人受困/有人受困
    conflict_status:      Optional[str] = None  # 衝突狀況（打架受傷）：已停止/進行中
    weapon_held:          Optional[str] = None  # 持械（打架受傷）：沒有/不確定/刀/棍棒/酒瓶/玻璃/其他照原話
    tocc:                 Optional[str] = None  # TOCC（旅遊/職業/接觸/群聚史）
    medical_history:      Optional[str] = None  # 過去病史（路倒專用）
    collapse_cause:       Optional[str] = None  # 路倒原因（路倒專用）
    ingested_substance:   Optional[str] = None  # 服用藥物（吞食藥物）
    # 救護垂片 1018 xlsx 新增的文字欄位（急病、燒燙傷照題目表問）
    consciousness_level:  Optional[str] = None  # 意識：未知/清醒/迷迷糊糊/沒有反應
    caller_relation:      Optional[str] = None  # 報案身分：本人/家人/朋友/路過/不認識…
    caller_location:      Optional[str] = None  # 報案人位置：在現場/在患者旁邊/在遠處/不敢靠近/不在現場…
    drinking_status:      Optional[str] = None  # 是否飲酒：有喝酒/沒有喝酒/不清楚（被動）
    collapse_status:      Optional[str] = None  # 路倒狀況：喝醉/睡著/身體不舒服/跌倒受傷/不清楚
    patient_appearance:   Optional[str] = None  # 外觀特徵（路倒）：照報案人說的記，讓救護人員找得到人
    companion_present:    Optional[str] = None  # 身旁親友（路倒舊欄位）：1106 xlsx 起路倒改問家屬陪同，這格沒有題目在用，要不要刪待決定
    mobility:             Optional[str] = None  # 平常行動能力：平常可以自己走/平常需要人扶/長期臥床或坐輪椅（被動）
    symptom_onset:        Optional[str] = None  # 症狀發生時間（被動）
    scene_access:         Optional[str] = None  # 現場進入條件：有沒有人開門、管理員、電梯（被動）
    # 救護垂片 1028 xlsx 燒炭OK 的文字欄位
    charcoal_status:      Optional[str] = None  # 炭盆狀況：尚未熄滅/已滅火
    patient_location:     Optional[str] = None  # 患者位置（燒炭）：還在裡面/已在外面
    # 救護垂片 1028 xlsx 墜落傷OK
    fall_status:          Optional[str] = None  # 墜落狀況：尚未跳下/已跳下/卡住/已勸導離開
    fall_height:          Optional[str] = None  # 墜落高度：幾樓或多高
    fall_position:        Optional[str] = None  # 患者位置：地面(一樓)/卡住/不清楚
    stuck_location:       Optional[str] = None  # 卡住位置：遮雨棚/女兒牆/屋頂或鐵皮屋/陽台/鷹架…
    # 救護垂片 1028 xlsx 上吊OK
    hanging_status:       Optional[str] = None  # 上吊狀況：已解開繩子/還沒解開
    break_in_need:        Optional[str] = None  # 破門需求：需要破門/不需要破門
    hanging_location:     Optional[str] = None  # 患者位置：住家/橋墩/山上電塔
    # 救護垂片 1104 xlsx 割腕OK（傷勢沿用 injury_severity）
    cutting_tool:         Optional[str] = None  # 工具（割腕、刀傷）：美工刀/菜刀/玻璃…
    tool_status:          Optional[str] = None  # 工具移除：已移除/還在身上/不清楚
    # 救護垂片 1028 xlsx 吞食藥物OK（服用藥物沿用 ingested_substance、病史沿用 medical_history）
    drug_amount:          Optional[str] = None  # 藥物數量：一整罐、大概 20 顆…
    medicine_bag:         Optional[str] = None  # 藥袋：有/無
    # 救護垂片 1028 xlsx 精神異常OK（病史沿用 medical_history）
    aggression:           Optional[str] = None  # 攻擊傾向：攻擊他人/自傷/無
    injured_count:        Optional[str] = None  # 受傷人數
    forced_admission:     Optional[str] = None  # 強制送醫：需要/不需要/不清楚
    forced_admission_reason: Optional[str] = None  # 強制送醫原因：大吼罵人/摔丟東西/胡言亂語…
    family_accompany:     Optional[str] = None  # 家屬陪同：有/沒有/家屬在路上
    # 救護垂片 1102 xlsx 電擊傷、溺水
    electric_type:        Optional[str] = None  # 電擊種類：高壓電/雷擊/家用電/其他
    power_off:            Optional[str] = None  # 現場是否已斷電：已斷電/未斷電
    patient_identity:     Optional[str] = None  # 傷患身分（電擊傷）：照報案人說的記，例：工地工人、外籍移工
    drowning_status:      Optional[str] = None  # 溺水狀況：還在水裡/看不到人/已拉上岸
    # 救護垂片名稱不同的關鍵要素各自一格（11/04 使用者決定）
    symptoms:             Optional[str] = None  # 病徵：全身無力/昏倒/喘/頭暈…
    chief_complaint:      Optional[str] = None  # 主訴（其它）：身體不舒服/受傷/想自殺…
    burn_cause:           Optional[str] = None  # 燒燙傷原因：熱水/熱油/火燒/化學藥劑/電
    burn_severity:        Optional[str] = None  # 燙傷傷勢：燙到哪裡、範圍多大、有沒有起水泡
    drowning_cause:       Optional[str] = None  # 溺水原因（救護、緊急救援共用）：照報案人說的記，例：失足落水/游泳抽筋/翻船
    pesticide_type:       Optional[str] = None  # 農藥種類：除草劑/巴拉刈/清潔劑…
    pesticide_amount:     Optional[str] = None  # 農藥劑量：半瓶/一整瓶…

    # ── 孕婦急產專用 ─────────────────────────────────────────────────────────────
    # 下面幾個欄位照 1028 xlsx「12-孕婦待產」的關鍵要素記（題目表見 ems_tab_map_119）
    pregnancy_week:        Optional[str] = None  # 懷孕週數（如「39週」）
    due_date:              Optional[str] = None  # 預產期
    multiple_pregnancy:    Optional[str] = None  # 胎次與胎數（如「第2胎、單胞胎」）
    water_broken_bleeding: Optional[str] = None  # 破水/出血狀況
    contractions:          Optional[str] = None  # 陣痛狀況：沒有陣痛/不規則陣痛/規則陣痛/已經破水/落紅
    prenatal_history:      Optional[str] = None  # 產檢狀況：產檢正常/產檢有異常/沒產檢或不知道
    prenatal_clinic:       Optional[str] = None  # 產檢醫院/診所

    # ── 火警 SOP 要素 ────────────────────────────────────────────────────────
    fire_or_smoke:       Optional[str] = None  # 火煙狀況：只記 只有火花/有火有煙/有火無煙/無火有煙/無火無煙/不確定
    smoke_color:         Optional[str] = None  # 黑煙/白煙/其他顏色
    burning_object:      Optional[str] = None  # 燒什麼（房子/車子/雜草…）
    fire_trend:          Optional[str] = None  # 變大/消退/穩定
    fire_category:      Optional[str] = None  # 舊四分類：建築物/工廠/車輛/露天野外

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

    # 垂片 A（建築物火警）照 xlsx 新增的欄位，存文字（參考範圍不是選擇題）。
    # 其他 A 的關鍵要素沿用既有文字欄位：fire_or_smoke（火煙狀況）、
    # smoke_color、fire_floor、building_total_floors、caller_role、hazardous_materials、
    # nearby_water_source（水源狀況）。
    place_usage:           Optional[str] = None  # 場所用途：住宅/店家/工廠/辦公室…
    # 建築物類型（1013 xlsx，A、C 都問）：透天厝、集合住宅、倉庫…
    # 在 A 跟次案類相同；在 C 另外記，次案類仍是警報器作響等
    building_type:         Optional[str] = None
    trapped_status:        Optional[str] = None  # 人員受困（A、B1、C）：只記 未知/無人受困/有人受困；有人受困就轉人工
    door_response:         Optional[str] = None  # 起火戶應門（A、C）：有人應門/無人應門/已聯絡上/聯絡不上
    building_construction: Optional[str] = None  # 建物構造：木造屋/鐵皮屋/磚造屋/RC…
    odor:                  Optional[str] = None  # 氣味：燒焦味/塑膠味/瓦斯味…
    explosion_status:      Optional[str] = None  # 有無爆炸（被動，報案人講到才記）

    # 垂片 B1（交通工具火警）照 xlsx 新增的欄位，存文字。起火車輛數量沿用 vehicle_count。
    vehicle_kind:          Optional[str] = None  # 交通工具（1013）：聯結車/大小貨車/小客車/汽車/機車/腳踏車…
    vehicle_model:         Optional[str] = None  # 車型（1013）：1104 xlsx 拿掉，不問也不抽
    vehicle_power:         Optional[str] = None  # 車輛動力(汽車)：不確定/油車/油電車/電動車(Tesla)
    vehicle_power_motorcycle: Optional[str] = None  # 車輛動力(機車)：不確定/油車/電動車(GOGORO)
    bicycle_type:          Optional[str] = None  # 腳踏車車型（1013）：一般腳踏車/UBIKE/電輔車
    fire_origin_part:     Optional[str] = None  # 起火部位：車頭或引擎/車廂或車斗/車底/電瓶…
    engine_off_status:     Optional[str] = None  # 熄火狀態：已熄火/未熄火
    injury_status:         Optional[str] = None  # 患者人數：記人數，例如 1 人、2 人
    cargo:                 Optional[str] = None  # 載運物：易燃物/化學品/鋰電池…
    extinguish_status:     Optional[str] = None  # 滅火狀況：無人/有人在場/已在自行滅火…（B2 也用）
    vehicle_motion:        Optional[str] = None  # 車輛行駛狀況：停放路邊/行駛中起火/停車場內
    plate_number:          Optional[str] = None  # 車牌號碼（被動）

    # 垂片 C（輕微火警）照 0929 xlsx 新增的欄位，存文字。
    # 氣味類型沿用 odor（跟 A 共用）。
    alarm_status:          Optional[str] = None  # 警報器狀態：已停止/仍在響/疑似誤報…
    source_located:        Optional[str] = None  # 來源確認：已確認位置/聞得到但找不到來源…
    target_object:         Optional[str] = None  # 標的物：電線桿或電纜/電表/電箱/人孔蓋/招牌…（被動）
    # 各垂片共用（1106 xlsx），參考範圍不同的依垂片給抽取規則
    spread_reached:        Optional[str] = None  # 是否延燒（A、B1、B2、C）：無/是/可能性高
    burning_area:          Optional[str] = None  # 燃燒面積（A 坪數、B2 停車格或籃球場、C 照報案人說的記）

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
    vehicle_count:         Optional[str] = None  # 起火車輛數
    vehicle_occupants:      Optional[bool] = None  # 車內是否有人
    vehicle_occupant_count: Optional[str] = None  # 車內人數
    road_type:              Optional[str] = None  # 一般道路/高速公路

    # 露天野外火災
    outdoor_fire_type:  Optional[str] = None  # 雜草垃圾/山林/高速公路
    nearby_water_source: Optional[str] = None  # 水源狀況（A：一般情況/小巷/缺水/小巷且缺水；B2：無或未知/有）
    affected_targets:   Optional[str] = None  # 波及建物/車輛/人員

    # ── 災害通用流程（所有子類同一套題）──────────────────────────────────────
    # 人員受困、火煙狀況、報案人位置、報案身分跟火警、救護共用欄位
    #（trapped_status、fire_or_smoke、caller_location、caller_relation）
    disaster_injury:        Optional[str] = None  # 人員受傷：未知/無人受傷/有人受傷
    disaster_trapped_count: Optional[str] = None  # 受困人數（照報案人的話記）
    traffic_impact:         Optional[str] = None  # 交通影響：未影響交通/佔用部分車道/完全無法通行

    # ── 緊急救援（1106 xlsx）自己的關鍵要素 ──────────────────────────────────
    # 跟救護、火警、災害名稱一樣的關鍵要素共用那邊的欄位（見 emergency_tab_map_119.EMERGENCY_SHARED_FIELDS）
    drown_distance:       Optional[str] = None  # 離岸距離（照報案人說的記）
    drown_flotation:      Optional[str] = None  # 救生裝備：有/沒有
    drown_group:          Optional[str] = None  # 團體帶隊（被動）：個人/公司/社團（溺水、山難共用）
    dive_status:          Optional[str] = None  # 跳水狀況：尚未跳下/已跳下/已勸導離開
    fall_intent:          Optional[str] = None  # 輕生意圖（照報案人說的記）
    fall_floor:           Optional[str] = None  # 所在樓層
    mountain_cause:       Optional[str] = None  # 山難原因：迷路/受傷/身體不舒服/失聯沒下山/其他照報案人說的記
    mountain_location:    Optional[str] = None  # 位置座標
    mountain_entry:       Optional[str] = None  # 入山資訊
    mountain_route:       Optional[str] = None  # 登山路線
    mountain_supplies:    Optional[str] = None  # 隨身物資
    trap_body_part:       Optional[str] = None  # 卡住部位
    trap_object:          Optional[str] = None  # 卡住物品
    trap_freed:           Optional[str] = None  # 是否脫困：還卡著/已經出來了
    gas_smell_place:      Optional[str] = None  # 聞到位置
    gas_smell_strength:   Optional[str] = None  # 味道濃淡：很濃/淡淡的/一陣一陣
    gas_type:             Optional[str] = None  # 瓦斯種類：天然氣/瓦斯桶
    gas_adjacent:         Optional[str] = None  # 鄰接建物（被動）
    gas_discomfort:       Optional[str] = None  # 身體不適（被動）：有/沒有/不知道（瓦斯漏氣、電梯受困共用）
    lift_building:        Optional[str] = None  # 社區棟別
    lift_floor:           Optional[str] = None  # 受困樓層
    lift_count:           Optional[str] = None  # 受困人數（照報案人說的記）
    lift_company:         Optional[str] = None  # 電梯公司：已經聯絡/還沒聯絡
    door_reason:          Optional[str] = None  # 擔心原因
    knock_response:       Optional[str] = None  # 有無回應：有回應/沒有回應/有聲音但叫不應
    door_kind:            Optional[str] = None  # 門的種類：大門/房門/浴室門/鐵門
    door_locksmith:       Optional[str] = None  # 鑰匙鎖匠：有鑰匙但打不開/沒有鑰匙/已找鎖匠
    door_consent:         Optional[str] = None  # 同意破門：同意/不同意/家屬或屋主還沒到

    # ── 觸發情境（急病 / 火警通用）────────────────────────────────────────────
    triggered_scenarios: List[int]  = field(default_factory=list)  # 已觸發情境編號清單
    blood_glucose:       Optional[str] = None  # 血糖值（回應11）
    blood_pressure:      Optional[str] = None  # 血壓值（回應16）
    seizure_info:        Optional[str] = None  # 抽搐相關（回應14）

    # ── 報案人訊息 ──────────────────────────────────────────────────────────
    caller_name:       Optional[str] = None  # 報案人姓名
    caller_contact:    Optional[str] = None  # 報案人聯繫方式（電話/手機）
    # 號碼格式檢查結果：None=未提供（未知不算錯），True=合格，False=碼數/格式不對。
    # STT 可能把尾碼聽成別的字（實測「444」→「是是是」），殘缺號碼會讓回撥失敗，
    # 所以照實記錄原值、另外標記，不追問也不竄改。
    caller_contact_valid:  Optional[bool] = None
    caller_contact_reason: Optional[str] = None   # valid=False 時的原因說明
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
    #   火警：火警_location → 火警_location_confirm → 火警-案類分析
    #   → 火警_A_* | 火警_B1_* | 火警_B2_* | 火警_C_* → 火警_safety
    #   → 火警_summary_confirm → 火警_caller_info → completed
    #   緊急救援：緊急救援_location → 緊急救援_location_confirm
    #   → 緊急救援_incident → 緊急救援_summary_confirm → 緊急救援_caller_info → completed
    #   災害：災害_location → 災害_location_confirm → 災害-人員受傷 → 災害-受困人數
    #   → 災害-交通影響 → 災害-火煙狀況 → 災害-報案人位置
    #   → 災害_summary_confirm → 災害_caller_info → completed
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
        # 系統內部用的次案類代號，不放進送出去的 JSON
        for name in ("building_type_code", "vehicle_wildfire_code", "minor_fire_code"):
            d.pop(name, None)
        # 已填 SOP 欄位多帶「次案類編號-題號」和該欄位的值。槽位本身不變。
        from sop_element_id_119 import sop_element_ids

        d["sop_element_ids"] = sop_element_ids(d)
        # 救護的派遣等級跟著目前的傷病患人數算：報案人改口人數時，等級也跟著改（可以往下降）
        if d.get("main_category") == "救護":
            from sop_utils_119 import rescue_level

            d["level"] = rescue_level(d.get("patient_count"))
        return d

    def caller_texts(self) -> List[str]:
        """返回所有報警人輸入文本的列表。"""
        return [t["text"] for t in self.transcript if t.get("role") == "caller"]

    def full_caller_text(self) -> str:
        """拼接所有報警人輸入，以換行分隔。"""
        return "\n".join(self.caller_texts())

    def classifier_caller_text(self) -> str:
        """拼接報警人輸入，問地址與重問地址的回復不進來。"""
        return "\n".join(
            t["text"]
            for t in self.transcript
            if t.get("role") == "caller" and not t.get("skip_classifier")
        )

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
            "main_conf", "sub_conf", "suspected_sub_category", "address_confirmed",
            "address_validation_status", "address_suspect_error",
            "address_error_reason", "address_corrected_note",
            "is_ohca", "caller_name", "caller_contact", "caller_salutation",
            "caller_contact_valid", "caller_contact_reason",
            "caller_address",
            "triggered_scenarios",
            "sop_element_ids",
        }
        out: Dict[str, Any] = {}
        for k, v in self.to_dict().items():
            if k in exclude:
                continue
            if v is None or v is False:
                continue
            if k == "ImportantCase" and v == 0:
                continue
            if k == "level" and v == 0:
                continue
            if isinstance(v, list) and len(v) == 0:
                continue
            out[k] = v
        return out
