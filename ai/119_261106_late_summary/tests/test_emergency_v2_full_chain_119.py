"""
緊急救援 v2 的八個類別，各走一遍線上流程。

開場原文來自公開通話，先用 v2 模型判對，而且硬規則不會把它判成別的子類。
後面的短回答不再改判，好讓這一類的題目能問完。
"""

from __future__ import annotations

import json
import os
import types
import unittest

from emergency_accident_119 import (
    ACCIDENT_QUESTIONS,
    DISPATCH_LINE,
    RELATION_QUESTION,
)
from emergency_rescue_subs_119 import (
    DIVE_QUESTIONS,
    FALL_QUESTIONS,
    GAS_QUESTIONS,
    LIFT_QUESTIONS,
    MOUNTAIN_QUESTIONS,
    asked_questions,
)
from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler
from hard_subcategory_rules_119 import match_hard_subcategory
from sop_119_engine import DialogueIO, SopEngine119

MODEL_DIR = "/home/cvmax/autodl-tmp/models/TW-119-BERT-sub_緊急救援_v2"
JSONL = "/home/cvmax/autodl-tmp/119_20260609stt_case_public.jsonl"
V2_LABELS = (
    "其他",
    "山難",
    "瓦斯漏氣(建築物)",
    "跳樓",
    "跳水",
    "車禍救助",
    "開瓦斯自殺",
    "電梯受困",
)
SIGNATURE = {
    "車禍救助": ACCIDENT_QUESTIONS[0].question,
    "山難": asked_questions(MOUNTAIN_QUESTIONS)[0].question,
    "瓦斯漏氣(建築物)": asked_questions(GAS_QUESTIONS)[0].question,
    "跳樓": asked_questions(FALL_QUESTIONS)[0].question,
    "跳水": asked_questions(DIVE_QUESTIONS)[0].question,
    "電梯受困": asked_questions(LIFT_QUESTIONS)[0].question,
    "其他": RELATION_QUESTION,
    "開瓦斯自殺": RELATION_QUESTION,
}


def _torch_ready() -> bool:
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
        if self.heard > 40:
            raise AssertionError("題目超過 40 句：" + self.messages[-1])
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
        return "v2 全流程測試"


class _LockOpening:
    """第一句用真模型。後面維持這個子類，避免短回答把 128 字以後的內容截掉前又被改判。"""

    def __init__(self, real):
        self.real = real
        self.locked: str | None = None
        self.first = None

    def predict(self, text, main_cat):
        if self.locked is None:
            self.first = self.real.predict(text)
            self.locked = self.first.final_label
            return self.first
        return types.SimpleNamespace(
            final_label=self.locked,
            classifier_conf=0.95,
            all_probs={self.locked: 0.95, "其他": 0.02},
        )


def _margin(probs: dict) -> float:
    ordered = sorted(probs.values(), reverse=True)
    if len(ordered) < 2:
        return 1.0
    return ordered[0] - ordered[1]


@unittest.skipUnless(_torch_ready(), "需要 torch 與緊急救援 v2 模型")
class EmergencyV2FullChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from classifier_with_llm import SubCategoryClassifier

        cls.real = SubCategoryClassifier(
            main_category="緊急救援",
            model_dir=MODEL_DIR,
            llm_model_path=None,
            device="cuda" if __import__("torch").cuda.is_available() else "cpu",
        )
        best: dict[str, tuple[int, str]] = {}
        batch_text: list[str] = []
        batch_gold: list[str] = []

        def _consume():
            if not batch_text:
                return
            preds = cls.real.predict_batch(batch_text)
            for gold, text, pred in zip(batch_gold, batch_text, preds):
                if pred.final_label != gold or pred.classifier_conf < 0.35:
                    continue
                if _margin(pred.all_probs) < 0.15:
                    continue
                hard, _kw = match_hard_subcategory(text, "緊急救援")
                if hard not in (None, gold):
                    continue
                prev = best.get(gold)
                if prev is None or len(text) > prev[0]:
                    best[gold] = (len(text), text)
            batch_text.clear()
            batch_gold.clear()

        with open(JSONL, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if (rec.get("main_category") or "").strip() != "緊急救援":
                    continue
                gold = (rec.get("sub_category") or "").strip()
                text = (rec.get("stt_text") or "").strip()
                if gold not in V2_LABELS or len(text) < 40:
                    continue
                batch_text.append(text)
                batch_gold.append(gold)
                if len(batch_text) >= 32:
                    _consume()
        _consume()
        missing = [label for label in V2_LABELS if label not in best]
        if missing:
            raise AssertionError(f"v2 沒有夠有把握的樣本：{missing}")
        cls.examples = {label: best[label][1] for label in V2_LABELS}

    def test_each_v2_label_finishes_its_call(self) -> None:
        for label in V2_LABELS:
            with self.subTest(label=label):
                opening = self.examples[label]
                checked = self.real.predict(opening)
                self.assertEqual(checked.final_label, label)
                self.assertGreaterEqual(checked.classifier_conf, 0.35)
                io = _FillIO()
                wrapper = _LockOpening(self.real)
                engine = SopEngine119(
                    io=io, llm_extractor=_NameLLM(), sub_classifiers=wrapper,
                )
                engine.case.main_category = "緊急救援"
                engine.case.main_conf = 0.95
                engine.case.incident_description = "報案人已說明經過"
                engine.case.address = "板橋區文化路一段10號"
                engine.case.address_confirmed = True
                engine.case.transcript = [{"role": "caller", "text": opening}]
                handler = JinJiJiuYuanGenericHandler()
                handler.run_generic_flow(engine)
                handler.collect_caller_info(engine)
                self.assertEqual(engine.case.sub_category, label)
                self.assertEqual(engine.case.result, "dispatched")
                self.assertEqual(engine.case.caller_name, "王先生")
                self.assertIn(DISPATCH_LINE, io.messages)
                self.assertIn(SIGNATURE[label], io.messages)
                self.assertLess(
                    io.messages.index(DISPATCH_LINE),
                    io.messages.index(SIGNATURE[label]),
                )


if __name__ == "__main__":
    unittest.main()
