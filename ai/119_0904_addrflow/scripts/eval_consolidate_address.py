"""評測 `LLMExtractor119.consolidate_address` 對真實通話的地址判讀。

用法（**會載入 gguf，必須先確認 VRAM**）：
    # 用 CPU 跑，不影響線上服務（慢，18 通約數分鐘）
    LLM_DEVICE=cpu ADDRCHECK_API_URL=… ADDRCHECK_API_TOKEN=… \
      PYTHONPATH=. python scripts/eval_consolidate_address.py

    # 或停掉線上服務後用 GPU
    N_GPU_LAYERS=-1 … python scripts/eval_consolidate_address.py

⚠️ 線上服務佔約 24GB/32GB VRAM，**不要在服務運行時用 GPU 跑**（runbook §7 雙開 OOM）。

比較三個來源對同一通話的地址判讀：
    regex     現行的規則抽取（跑完整地址流程，無 LLM）
    LLM       consolidate_address 吃全部報案人發話
    人工      log 裡的 case.address ＋ 人工判讀的正解

判準是「送 addrCheck 是否 valid」與「是否等於人工正解」，
不是誰的字串比較長。
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from location_validation_119 import verify_address_detail  # noqa: E402
from sop_utils_119 import (  # noqa: E402
    build_street_address,
    extract_street_address_components,
)

LOG_DIR = "/home/cyberon2/nlp_cyberon_server/log_119"
FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "data", "real_calls_119.json",
)

# 人工判讀的正解（報案人實際要表達的地址）。None 代表該通本來就沒有有效地址。
GROUND_TRUTH = {
    "case119_20260906_031238_0d315b49": "板橋區大觀路1段28巷6弄4號9樓",
    "case119_20260906_032031_57083a74": "新北市新莊區新豐街20巷6號1樓",
    "case119_20260906_031810_0da9f51f": "新北市板橋區實踐路132號",
    "case119_20260906_031549_3ca772b3": "新北市淡水區淡金路1段551號1樓",
    "case119_20260906_003354_bbee02e4": "新北市板橋區光武街136巷8弄16號",
    "case119_20260906_003709_575f6cf4": "新北市中和區景平路431巷27號",
    "case119_20260906_003050_e2236f44": None,          # 報案人前後改區，無定論
    "case119_20260906_011911_fa60d893": "新北市汐止區橫科路351巷31號1樓",
    "case119_20260905_105417_26455048": "新北市板橋區國光路31巷11號",
    "case119_20260905_105142_cf78b6aa": "新北市新莊區中港路648巷6號",
    "case119_20260905_104526_3bd6c9f4": "新北市瑞芳區明里路14號",
    "case119_20260904_205512_8b3744e3": "新北市三重區仁愛街283巷28號5樓",
    "case119_20260904_195416_de7f3a53": "新北市五股區明德路12巷28號",
    "case119_20260902_133949_4540ae40": "土城區中央路3段61巷2號4樓",
    "case119_20260904_094500_df9769a8": "土城區亞洲路3號2樓",
}


def caller_lines(path):
    data = json.load(open(path, encoding="utf-8"))
    return data, [
        t["text"] for t in (data.get("transcript") or [])
        if t.get("role") == "caller" and (t.get("text") or "").strip()
    ]


def regex_address(texts):
    """現行規則抽取：逐輪累積元件，取最完整的一組。"""
    best = {}
    for text in texts:
        for key, value in extract_street_address_components(text).items():
            best.setdefault(key, value)
    return build_street_address(
        best.get("address_district"), best.get("address_road"),
        best.get("address_number"), existing=" ".join(texts),
    )


def check(address):
    if not address:
        return "—", None
    try:
        status, hint, reason = verify_address_detail(address, "address")
    except Exception as exc:
        return f"error: {exc}", None
    return reason or ("valid" if status else "?"), hint


def main():
    from llm_extractor_119 import LLMExtractor119

    model = os.getenv("GGUF_MODEL_PATH",
                      "/home/cyberon2/nlp_cyberon_server/models/TW-119-Model.gguf")
    n_gpu = 0 if os.getenv("LLM_DEVICE", "").lower() == "cpu" else int(
        os.getenv("N_GPU_LAYERS", "-1"))
    print(f"載入模型（n_gpu_layers={n_gpu}）…", flush=True)
    llm = LLMExtractor119(model_path=model, n_gpu_layers=n_gpu, verbose=False)

    fixture_ids = {c["id"] for c in json.load(open(FIXTURE, encoding="utf-8"))["cases"]}
    rows = []
    for case_id in sorted(set(GROUND_TRUTH) | fixture_ids):
        path = os.path.join(LOG_DIR, f"{case_id}.json")
        if not os.path.exists(path):
            continue
        data, texts = caller_lines(path)
        truth = GROUND_TRUTH.get(case_id)

        rx = regex_address(texts)
        out = llm.consolidate_address(texts, current_address=data.get("address"))
        lm = out.get("address")

        rows.append({
            "id": case_id,
            "truth": truth,
            "logged": data.get("address"),
            "regex": rx, "regex_api": check(rx)[0],
            "llm": lm, "llm_api": check(lm)[0],
            "llm_confidence": out.get("confidence"),
            "llm_need_ask": out.get("need_ask"),
        })
        print(f"  ✓ {case_id[7:22]}", flush=True)

    out_path = os.path.join(os.path.dirname(FIXTURE), "consolidate_eval.json")
    json.dump(rows, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    def norm(a):
        return (a or "").replace("新北市", "").replace(" ", "")

    hit_r = sum(1 for r in rows if r["truth"] and norm(r["regex"]) == norm(r["truth"]))
    hit_l = sum(1 for r in rows if r["truth"] and norm(r["llm"]) == norm(r["truth"]))
    n = sum(1 for r in rows if r["truth"])
    print(f"\n{'='*66}\n對照人工正解（{n} 通有正解）")
    print(f"  regex 命中 {hit_r}/{n}")
    print(f"  LLM   命中 {hit_l}/{n}")
    ok_r = sum(1 for r in rows if r["regex_api"] == "valid")
    ok_l = sum(1 for r in rows if r["llm_api"] == "valid")
    print(f"\naddrCheck 判 valid：regex {ok_r}/{len(rows)}　LLM {ok_l}/{len(rows)}")
    print(f"\n→ {out_path}")


if __name__ == "__main__":
    main()
