"""
災害子類模型接上通用流程。

只跑模型自己判得過門檻的類別：信心大於 0.5，而且比第二名至少高 0.15。
這和線上寫入災害子類的條件相同。電線掉落會多問火花，其他類別不問。
"""

from __future__ import annotations

import json
import os
import types
import unittest

from disaster_flow_119 import DISPATCH_LINE, SPARK_SUBTYPES
from handlers.災害通用 import ZaiHaiGenericHandler
from hard_subcategory_rules_119 import match_hard_subcategory
from sop_119_engine import DialogueIO, SopEngine119

MODEL_DIR = "/home/cvmax/autodl-tmp/models/TW-119-BERT-sub_災害"
JSONL = "/home/cvmax/autodl-tmp/119_sub_disaster_data/災害.jsonl"
INJURY_QUESTION = "有人被壓到受傷或受困嗎？"
SPARK_QUESTION = "電線有沒有冒火花或冒煙？"


def _ready() -> bool:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return os.path.isdir(MODEL_DIR) and os.path.isfile(JSONL)


class _FillIO(DialogueIO):
    def __init__(self):
        self.messages: list[str] = []
        self.heard = 0

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        self.heard += 1
        if self.heard > 20:
            raise AssertionError("題目超過 20 句：" + self.messages[-1])
        if "姓名" in (self.messages[-1] if self.messages else ""):
            return "王先生 0912345678"
        return "不清楚狀況"


class _NameLLM:
    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        if "姓名" in (question or ""):
            return {"caller_name": "王先生", "caller_contact": "0912345678"}
        return {}

    def extract_caller_info(self, question, text, include_address=False):
        return {"caller_name": "王先生", "caller_contact": "0912345678"}

    def generate_summary(self, transcript_texts, filled_fields):
        return "災害模型測試"


class _LockOpening:
    def __init__(self, real):
        self.real = real
        self.locked = None

    def predict(self, text, main_cat):
        if self.locked is None:
            self.locked = self.real.predict(text)
            return self.locked
        label = self.locked.final_label
        return types.SimpleNamespace(
            final_label=label,
            classifier_conf=0.9,
            all_probs={label: 0.9, "其他": 0.02},
        )


def _margin(probs: dict) -> float:
    ordered = sorted(probs.values(), reverse=True)
    return (ordered[0] - ordered[1]) if len(ordered) > 1 else 1.0


@unittest.skipUnless(_ready(), "需要 torch 與災害子類模型")
class DisasterModelFullChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from classifier_with_llm import SubCategoryClassifier

        cls.real = SubCategoryClassifier(
            main_category="災害",
            model_dir=MODEL_DIR,
            llm_model_path=None,
            device="cuda" if __import__("torch").cuda.is_available() else "cpu",
        )
        rows = []
        with open(JSONL, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        best: dict[str, tuple] = {}
        texts = [row["stt_text"] for row in rows]
        golds = [row["sub_category"] for row in rows]
        for start in range(0, len(texts), 32):
            preds = cls.real.predict_batch(texts[start:start + 32])
            for gold, text, pred in zip(golds[start:start + 32], texts[start:start + 32], preds):
                if pred.final_label != gold or pred.classifier_conf <= 0.5:
                    continue
                if _margin(pred.all_probs) < 0.15:
                    continue
                hard, _kw = match_hard_subcategory(text, "災害")
                if hard not in (None, gold):
                    continue
                prev = best.get(gold)
                if prev is None or pred.classifier_conf > prev[0]:
                    best[gold] = (pred.classifier_conf, text)
        if not best:
            raise AssertionError("災害模型沒有任何過門檻的類別")
        cls.examples = {label: item[1] for label, item in best.items()}

    def test_each_accepted_label_finishes_the_disaster_call(self) -> None:
        self.assertIn("路樹傾倒", self.examples)
        self.assertIn("電線掉落", self.examples)
        for label, opening in self.examples.items():
            with self.subTest(label=label):
                checked = self.real.predict(opening)
                self.assertEqual(checked.final_label, label)
                io = _FillIO()
                engine = SopEngine119(
                    io=io,
                    llm_extractor=_NameLLM(),
                    sub_classifiers=_LockOpening(self.real),
                )
                engine.case.main_category = "災害"
                engine.case.main_conf = 0.95
                engine.case.address = "板橋區文化路一段10號"
                engine.case.address_confirmed = True
                engine._address_locked = True
                engine.case.transcript = [{"role": "caller", "text": opening}]
                engine._run_災害()
                self.assertEqual(engine.case.sub_category, label)
                self.assertEqual(engine.case.result, "dispatched")
                self.assertIn(DISPATCH_LINE, io.messages)
                self.assertIn(INJURY_QUESTION, io.messages)
                if label in SPARK_SUBTYPES:
                    self.assertIn(SPARK_QUESTION, io.messages)
                else:
                    self.assertNotIn(SPARK_QUESTION, io.messages)


if __name__ == "__main__":
    unittest.main()
