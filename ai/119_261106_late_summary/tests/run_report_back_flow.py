"""回報流程腳本。不載入 LLM，只把對話走完並印出案件 JSON 與案情摘要。

在專案目錄執行：

    python tests/run_report_back_flow.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sop_119_engine
from sop_119_engine import DialogueIO, SopEngine119

# 空號就不會把市話預填地址寫進槽位。
sop_119_engine.fetch_incoming_caller = lambda: {"phone": "", "address": ""}

ANSWERS = [
    "我要回報，剛剛那個燙傷",
    "板橋文化路，案號119，燒燙傷",
    "是",
    "左手被熱油燙到，起了大水泡",
    "患者是男生，大概40歲",
    "我是他家人",
    "人還清醒，叫他有反應",
    "我人在現場",
    "沒有其他的了",
]


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)
        print(f"系統：{text}", flush=True)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError("回答已用盡")
        text = self.answers.pop(0)
        print(f"報案人：{text}", flush=True)
        return text


def main() -> None:
    io = ScriptedIO(ANSWERS)
    engine = SopEngine119(io=io)
    engine.run()

    case = engine.case.to_dict()
    kept = {
        key: value
        for key, value in case.items()
        if key not in {"transcript", "sop_element_ids"}
        and value not in (None, "", [], {}, False)
        and not (key == "ImportantCase" and value == 0)
        and not (key == "level" and value == 0)
    }
    print("\n案件 JSON：")
    print(json.dumps(kept, ensure_ascii=False, indent=2))
    print("\n案情摘要：")
    print(case.get("case_summary") or "（空）")


if __name__ == "__main__":
    main()
