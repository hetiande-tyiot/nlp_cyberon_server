"""
從歷史案件記錄挖出地址語料，產生測試用的真實語句集。

用途
────
人工編的測試句子講得太漂亮。真實報案人（經過 STT）會有語助詞、句號碎片、
同音錯字、無關噪音。這支腳本把 log_119/*.json 裡「受理員問地址 → 報案人回答」
的問答對抽出來，依講話方式分類，輸出成 tests/data/address_corpus_119.json。

用法
────
    cd ai/119_0813_adjustSOP
    PYTHONPATH=. ../../llmenv/bin/python scripts/mine_address_corpus.py
    PYTHONPATH=. ../../llmenv/bin/python scripts/mine_address_corpus.py --log-dir /path/to/logs

輸出的 category 是用規則粗分的，只是方便人工複核時分組看，不是標準答案。
語料裡的 system_* 欄位是「當時系統跑出來的結果」，其中有錯的（例如地址查無
管轄單位那幾筆），不可當成 golden，要人工看過才算數。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List

DEFAULT_LOG_DIR = Path("/home/cyberon2/nlp_cyberon_server/log_119")
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "data" / "address_corpus_119.json"

# 受理員的地址類問句（排除覆誦確認句，那類回答多半只是是/否）
ADDRESS_QUESTION_RE = re.compile(r"地址|哪裡|那一區|哪一區|什麼路|幾號|路口|公里")
CONFIRM_QUESTION_RE = re.compile(r"確定是")

# 講話方式分類（依序比對，取第一個命中的）
FILLER_HEAD_RE = re.compile(r"^(?:呃|嗯|欸|喔|唉|啊|哦)[，,、。\.\s]*")
ACK_HEAD_RE = re.compile(r"^(?:是|對|好|沒錯|謝謝|不錯|嘿|快)[。\.，,、\s]+")
DEICTIC_RE = re.compile(r"我(?:們)?(?:這邊|這裡)|那個|在那個|這邊是")
UNKNOWN_RE = re.compile(r"不知道|不清楚|不曉得|路過|不是這附近|沒注意")
FRAGMENTED_RE = re.compile(r"[。\.]\s*\S")          # 句中還有句號 → STT 把停頓斷開
ADDRESS_TOKEN_RE = re.compile(r"[路街道段巷弄號樓區]")
DIGIT_RE = re.compile(r"\d")


def classify_utterance(text: str) -> str:
    """粗分報案人這句話的講話方式，方便分組複核。"""
    s = (text or "").strip()
    if not s:
        return "empty"
    if UNKNOWN_RE.search(s):
        return "不知道地址"
    has_addr = bool(ADDRESS_TOKEN_RE.search(s))
    if not has_addr:
        return "無地址內容"
    if FRAGMENTED_RE.search(s):
        return "句號碎片"
    if DEICTIC_RE.search(s):
        return "指示詞開頭"
    if FILLER_HEAD_RE.match(s) or ACK_HEAD_RE.match(s):
        return "語助詞開頭"
    if not DIGIT_RE.search(s) and "號" not in s:
        return "只到路名"
    return "乾淨完整"


def iter_cases(log_dir: Path) -> Iterator[Dict[str, Any]]:
    for path in sorted(log_dir.glob("*.json")):
        try:
            yield path.stem, json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue


def mine(log_dir: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for case_id, case in iter_cases(log_dir):
        last_question = None
        for turn in case.get("transcript") or []:
            role = turn.get("role")
            text = (turn.get("text") or "").strip()
            if role == "assistant" and text:
                last_question = text
                continue
            if role != "caller" or not text or not last_question:
                continue
            if not ADDRESS_QUESTION_RE.search(last_question):
                continue
            if CONFIRM_QUESTION_RE.search(last_question):
                continue

            key = (last_question, text)
            if key in seen:
                continue
            seen.add(key)

            records.append({
                "case_id": case_id,
                "question": last_question,
                "utterance": text,
                "category": classify_utterance(text),
                # 當時系統跑出來的結果，供人工複核用，不是標準答案
                "system_address": case.get("address"),
                "system_location_type": case.get("location_type"),
                "system_status": case.get("address_validation_status"),
                "system_error_reason": case.get("address_error_reason"),
            })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    records = mine(args.log_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    counts = Counter(r["category"] for r in records)
    print(f"來源 {args.log_dir}")
    print(f"挖出 {len(records)} 筆地址問答，寫入 {args.out}\n")
    for category, count in counts.most_common():
        print(f"  {count:4}  {category}")


if __name__ == "__main__":
    main()
