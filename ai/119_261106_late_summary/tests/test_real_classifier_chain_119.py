"""
用真實的主分類器和子分類器，從開場白跑到 SOP。

不預設大類、不預設子類，也不把後面的回答鎖成第一次的結果。
地址和姓名用固定回答，其餘回答「不清楚狀況」，避免假抽取改寫分類。
"""

from __future__ import annotations

import json
import os
import unittest

from disaster_flow_119 import SPARK_SUBTYPES
from emergency_accident_119 import ACCIDENT_QUESTIONS, RELATION_QUESTION
from emergency_rescue_subs_119 import (
    DIVE_QUESTIONS,
    FALL_QUESTIONS,
    GAS_QUESTIONS,
    LIFT_QUESTIONS,
    MOUNTAIN_QUESTIONS,
    asked_questions,
)
from hard_subcategory_rules_119 import match_hard_subcategory
from sop_119_engine import DialogueIO, SopEngine119

MODELS = "/home/cvmax/autodl-tmp/models"
JSONL = "/home/cvmax/autodl-tmp/119_20260609stt_case_public.jsonl"
ADDRESS = "新北市板橋區文化路一段10號"
TRAP_QUESTION = "哪裡卡住了？"

EMERGENCY_MARK = {
    "車禍救助": ACCIDENT_QUESTIONS[0].question,
    "山難": asked_questions(MOUNTAIN_QUESTIONS)[0].question,
    "瓦斯漏氣(建築物)": asked_questions(GAS_QUESTIONS)[0].question,
    "跳樓": asked_questions(FALL_QUESTIONS)[0].question,
    "跳水": asked_questions(DIVE_QUESTIONS)[0].question,
    "電梯受困": asked_questions(LIFT_QUESTIONS)[0].question,
    "其他": RELATION_QUESTION,
    "開瓦斯自殺": RELATION_QUESTION,
}
DISASTER_MARK = "有人被壓到受傷或受困嗎？"
SPARK_MARK = "電線有沒有冒火花或冒煙？"


def _ready() -> bool:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return os.path.isdir(os.path.join(MODELS, "TW-119-BERT_main")) and os.path.isfile(JSONL)


def _margin(probs: dict) -> float:
    ordered = sorted(probs.values(), reverse=True)
    return (ordered[0] - ordered[1]) if len(ordered) > 1 else 1.0


class _LiveIO(DialogueIO):
    def __init__(self, opening: str):
        self.opening = opening
        self.messages: list[str] = []
        self.heard = 0
        self._given_opening = False

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        self.heard += 1
        if self.heard > 30:
            raise AssertionError("題目超過 30 句：" + (self.messages[-1] if self.messages else ""))
        if not self._given_opening:
            self._given_opening = True
            return self.opening
        question = self.messages[-1] if self.messages else ""
        if "姓名" in question:
            return "王先生 0912345678"
        if "地址" in question or "幾樓" in question or "路燈" in question:
            return ADDRESS
        if question.startswith("確定是") or "行政區" in question:
            return "對"
        return "不清楚狀況"


class _LiveLLM:
    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        question = question or ""
        if "姓名" in question:
            return {"caller_name": "王先生", "caller_contact": "0912345678"}
        if "地址" in question or "幾樓" in question:
            return {"address": ADDRESS}
        return {}

    def extract_caller_info(self, question, text, include_address=False):
        return {"caller_name": "王先生", "caller_contact": "0912345678"}

    def extract_confirmation(self, question, caller_text, current_address):
        return {"confirmed": True, "new_address": None}

    def generate_summary(self, transcript_texts, filled_fields):
        return "真實分類測試"


@unittest.skipUnless(_ready(), "需要 torch、主分類器與公開通話資料")
class RealClassifierChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from classifier_with_llm import build_classifiers
        from inference_pipeline import HierarchicalClassifier

        device = "cuda" if torch.cuda.is_available() else "cpu"
        cls.main = HierarchicalClassifier(models_base=MODELS, device=device)
        cls.subs = build_classifiers(models_base=MODELS, enable_llm=False, device=device)
        cls._scan()

    @classmethod
    def _scan(cls):
        wanted_main = {"緊急救援", "災害"}
        best_em: dict[str, tuple[float, str]] = {}
        best_dis: dict[str, tuple[float, str]] = {}
        buf_text: list[str] = []
        buf_main: list[str] = []
        buf_sub: list[str] = []

        def consume():
            if not buf_text:
                return
            mains = cls.main.predict_batch(buf_text)
            keep_text = []
            keep_main = []
            keep_sub = []
            for text, gold_main, gold_sub, result in zip(buf_text, buf_main, buf_sub, mains):
                if result["main_category"] != gold_main or result["main_conf"] < 0.7:
                    continue
                if _margin(result.get("main_probs") or {}) < 0.15:
                    continue
                keep_text.append(text)
                keep_main.append(gold_main)
                keep_sub.append(gold_sub)
            by_main: dict[str, list[int]] = {}
            for i, main_name in enumerate(keep_main):
                by_main.setdefault(main_name, []).append(i)
            for main_name, idxs in by_main.items():
                texts = [keep_text[i] for i in idxs]
                # one predict at a time; these subsets are small after the main filter
                for text, gold_sub in zip(texts, (keep_sub[i] for i in idxs)):
                    pred = cls.subs.predict(text, main_name)
                    if pred is None or pred.final_label != gold_sub:
                        continue
                    hard, _kw = match_hard_subcategory(text, main_name)
                    if hard is not None:
                        continue
                    margin = _margin(pred.all_probs or {})
                    threshold = 0.35 if main_name == "緊急救援" else 0.5
                    if pred.classifier_conf <= threshold or margin < 0.15:
                        continue
                    bucket = best_em if main_name == "緊急救援" else best_dis
                    prev = bucket.get(gold_sub)
                    if prev is None or pred.classifier_conf > prev[0]:
                        bucket[gold_sub] = (pred.classifier_conf, text)
            buf_text.clear()
            buf_main.clear()
            buf_sub.clear()

        with open(JSONL, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                main_name = (rec.get("main_category") or "").strip()
                if main_name not in wanted_main:
                    continue
                text = (rec.get("stt_text") or "").strip()
                sub = (rec.get("sub_category") or "").strip()
                if len(text) < 40 or not sub:
                    continue
                buf_text.append(text)
                buf_main.append(main_name)
                buf_sub.append(sub)
                if len(buf_text) >= 32:
                    consume()
        consume()
        cls.emergency = {label: item[1] for label, item in best_em.items()}
        cls.disaster = {label: item[1] for label, item in best_dis.items()}

    def _run(self, opening: str) -> tuple[SopEngine119, _LiveIO]:
        io = _LiveIO(opening)
        engine = SopEngine119(
            io=io,
            llm_extractor=_LiveLLM(),
            main_classifier=self.main,
            sub_classifiers=self.subs,
        )
        engine.run()
        return engine, io

    def test_main_classifier_reaches_both_categories_and_their_sops(self) -> None:
        self.assertTrue(self.emergency, "沒有任何緊急救援通話同時過了主分類和 v2 子分類門檻")
        self.assertTrue(self.disaster, "沒有任何災害通話同時過了主分類和子分類門檻")
        for label in ("車禍救助", "山難", "瓦斯漏氣(建築物)", "跳樓", "跳水", "電梯受困", "其他"):
            self.assertIn(label, self.emergency, label)
        for label, opening in self.emergency.items():
            with self.subTest(main="緊急救援", label=label):
                engine, io = self._run(opening)
                self.assertEqual(engine.case.main_category, "緊急救援")
                self.assertEqual(engine.case.sub_category, label)
                self.assertIsNone(engine.case.suspected_sub_category)
                self.assertIn(EMERGENCY_MARK[label], io.messages)
                if label == "其他":
                    self.assertNotIn(TRAP_QUESTION, io.messages)
                self.assertEqual(engine.case.result, "dispatched")
        for label, opening in self.disaster.items():
            with self.subTest(main="災害", label=label):
                engine, io = self._run(opening)
                self.assertEqual(engine.case.main_category, "災害")
                self.assertEqual(engine.case.sub_category, label)
                self.assertIn(DISASTER_MARK, io.messages)
                if label in SPARK_SUBTYPES:
                    self.assertIn(SPARK_MARK, io.messages)
                else:
                    self.assertNotIn(SPARK_MARK, io.messages)
                self.assertEqual(engine.case.result, "dispatched")


if __name__ == "__main__":
    unittest.main()
