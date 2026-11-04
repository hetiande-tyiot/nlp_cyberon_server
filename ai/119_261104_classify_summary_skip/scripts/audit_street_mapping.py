"""檢查 map_street.json：找出「把真實路名映射掉」的條目。

用法（需要 addrCheck env）：
    ADDRCHECK_API_URL=… ADDRCHECK_API_TOKEN=… \
    PYTHONPATH=. python scripts/audit_street_mapping.py [模式] [上限]

模式：
    suspect  只查結構上可疑的（key 同時是某條 value、或連鎖映射）。預設，約 600 條
    all      查整張表（25439 條，很慢，會打大量 API）
    targets  查所有**映射目標**是否真的存在（1707 條，較快）

targets 模式檢查的是另一種問題：目標本身不存在的映射毫無價值，還會誤導。
實例（2026-09-06 01:21 真實通話）：`"桃園街": "厚德街"`，三重區兩條路都查無，
系統問「是三德街、後埔街、明德街嗎」——那是針對「厚德街」的建議；
不映射的話 API 會針對報案人講的「桃園街」建議「公園街」。

背景：映射表的用途是修正 STT 聽錯的路名。但若 **key 本身就是真實存在的路名**，
這條映射就會把報案人講對的路改成別條路。實例（2026-09-04 20:57 真實通話）：

    重陽路      → 三和路    兩條都真實存在，三重區同時有這兩條
    新北大道路  → 思源路    新北大道真實存在；此條目標疑似寫錯（應為「新北大道」）

addrCheck 可以不帶行政區查路名（回 valid / ambiguous 即代表該路存在），
所以能逐條驗證。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from location_validation_119 import verify_address_detail  # noqa: E402

MAP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "map_street.json"
)
MODE = sys.argv[1] if len(sys.argv) > 1 else "suspect"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 600

def road_exists(key: str, hint: str | None) -> bool | None:
    """從 hint 判斷「來源路名本身」是否真的存在。

    ⚠️ 不能只看 reason：`ambiguous` 多半是「你講的查無，但同音的有好幾條」，
    `valid` 也可能是 API 模糊比對到別條路——
        「中小街1號」查無此路。同音的「忠孝街」在 三峽區…都有        → 中小街不存在
        「加新村街」→ 地址有效：新北市金山區金包里街1號              → 加新村街不存在
        「「重陽路」的 一段、二段、四段 都有 1 號」                   → 重陽路存在
    判準是「API 回的地址裡有沒有原路名」。回 None 表示無法判定，需人工看。
    """
    text = hint or ""
    if not text:
        return None
    if "查無此路" in text or f"查無「{key}" in text:
        # 不帶行政區查詢時，有些路名 API 找不到，但會出現在建議裡：
        #   「查無「區運路」，是否為 新北市板橋區區運路、…」← 區運路其實存在
        # 建議項去掉區前綴後要「等於」原路名才算——用包含會把
        # 「建三路」誤判成「三路」存在。
        match = re.search(r"是否為\s*([^？?。]+)", text)
        if match:
            for item in re.split(r"[、,，]", match.group(1)):
                # 非貪婪：貪婪會把「板橋區區運路」吃成「板橋區區」，
                # 剩下「運路」對不上原路名
                stripped = re.sub(
                    r"^(?:[一-鿿]{2,3}[市縣])?[一-鿿]{1,4}?區", "", item.strip()
                )
                if stripped == key:
                    return True
        return False
    if "已依讀音修正" in text:      # 原路名查無，靠讀音找到別條
        return False
    match = re.search(r"「([^」]+)」\s*的\s*[^，。]+?\s*都有", text)
    if match:
        return key in match.group(1)
    match = re.search(r"地址有效：\s*([^\s，。]+)", text)
    if match:
        return key in match.group(1)
    match = re.search(r"「([^」]+?)」查無此門牌", text)
    if match:
        return key in match.group(1)
    match = re.search(r"最接近的是\s*([^\s，。（(]+)", text)
    if match:
        return key in match.group(1)
    return None

mapping = json.load(open(MAP_PATH, encoding="utf-8"))
keys = set(mapping)
values = set(mapping.values())

if MODE == "all":
    targets = sorted(keys)
elif MODE == "targets":
    targets = sorted(values)
else:
    both = keys & values                                    # 自相矛盾
    chained = {k for k, v in mapping.items() if v in mapping and mapping[v] != v}
    targets = sorted(both | chained)
targets = targets[:LIMIT]

print(f"檢查 {len(targets)} 條（模式 {MODE}，全表 {len(mapping)} 條）\n")

bad, ok, unknown = [], [], []
for index, key in enumerate(targets, 1):
    try:
        _status, hint, reason = verify_address_detail(f"{key}1號", "address")
    except Exception as exc:
        unknown.append((key, "", f"error: {exc}"))
        continue
    if MODE == "targets":
        # 目標模式：存在=好，不存在才是問題（與其他模式相反）
        exists = road_exists(key, hint)
        srcs = [k for k, v in mapping.items() if v == key]
        if exists is False:
            bad.append((key, f"{len(srcs)} 條來源指向它", reason, (hint or "")[:80]))
        elif exists is True:
            ok.append(key)
        else:
            unknown.append((key, "", f"無法判定：{(hint or '')[:60]}"))
        if index % 50 == 0:
            print(f"  …{index}/{len(targets)}")
        time.sleep(0.05)
        continue
    exists = road_exists(key, hint)
    if exists is True:
        bad.append((key, mapping[key], reason, (hint or "")[:80]))
    elif exists is False:
        ok.append(key)
    else:
        unknown.append((key, mapping[key], f"無法判定：{(hint or '')[:60]}"))
    if index % 50 == 0:
        print(f"  …{index}/{len(targets)}")
    time.sleep(0.05)   # 別把 API 打爆

print()
if unknown and not bad and not ok:
    print("⚠⚠ 所有查詢都失敗——多半是沒帶 ADDRCHECK_API_URL / ADDRCHECK_API_TOKEN。")
    print(f"   失敗 {len(unknown)} 筆，第一筆：{unknown[0]}")
    print("   這份結果不可用，請帶 env 重跑。")
print(f"⚠ key 本身就是真實路名（這些映射會把正確路名改掉）：{len(bad)} 條")
for key, target, reason, hint in bad:
    print(f'   "{key}": "{target}"   ← {key} 存在（{reason}）')
    if hint:
        print(f"        {hint}")
print()
print(f"key 確實查無（映射合理）：{len(ok)} 條")
if unknown:
    print(f"無法判定／查詢失敗：{len(unknown)} 條（需人工看）")
    for key, target, note in unknown[:10]:
        print(f'   "{key}": "{target}"  {note}')

out = os.path.join(os.path.dirname(MAP_PATH), "map_street_audit.json")
json.dump(
    {
        "mode": MODE,
        "checked": len(targets),
        "total_entries": len(mapping),
        "suspicious": [
            {"key": k, "maps_to": t, "reason": r, "hint": h} for k, t, r, h in bad
        ],
        "ok_keys": ok,
        "failed": [{"key": k, "maps_to": t, "error": e} for k, t, e in unknown],
        "usable": bool(bad or ok),
    },
    open(out, "w", encoding="utf-8"),
    ensure_ascii=False,
    indent=1,
)
print(f"\n→ {out}")
