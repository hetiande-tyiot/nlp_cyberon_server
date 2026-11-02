"""
災害整通對話，以及先前加上的硬規則疑似分類。

災害走線上那一支：地址已確認後辨子類、派車、五題、姓名電話。
硬規則用各子類最長的關鍵詞當報案人原話，再走引擎實際會呼叫的寫入路徑。
"""

from __future__ import annotations

import types
import unittest

from classification_badges_119 import classification_badges_html
from disaster_flow_119 import (
    DISASTER_QUESTIONS,
    DISPATCH_LINE,
    INJURY_HURT,
    INJURY_TRAPPED,
    ROLE_OWNER,
    TRAFFIC_PARTIAL,
)
from hard_subcategory_rules_119 import HARD_RULE_TARGETS, keywords_for, match_hard_subcategory
from sop_119_engine import DialogueIO, SopEngine119

SPARK_QUESTION = next(
    item.question for item in DISASTER_QUESTIONS if item.field == "electrical_hazard"
)
COUNT_QUESTION = next(
    item.question for item in DISASTER_QUESTIONS if item.field == "disaster_trapped_count"
)


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError(
                "回答用完了，下一句是：" + (self.messages[-1] if self.messages else "")
            )
        return self.answers.pop(0)


class AnswerLLM:
    def __init__(self, by_answer: dict[str, dict]):
        self.by_answer = by_answer

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        return dict(self.by_answer.get((caller_text or "").strip(), {}))

    def extract_caller_info(self, question, text, include_address=False):
        return dict(self.by_answer.get((text or "").strip(), {}))

    def generate_summary(self, transcript_texts, filled_fields):
        return "災害測試摘要"


class FixedBert:
    def __init__(self, label: str, conf: float = 0.92, second: float = 0.04):
        self.label = label
        self.conf = conf
        self.second = second
        self.calls = 0

    def predict(self, text, main_cat):
        self.calls += 1
        return types.SimpleNamespace(
            final_label=self.label,
            classifier_conf=self.conf,
            all_probs={self.label: self.conf, "其他": self.second},
        )


class BoomBert:
    def predict(self, text, main_cat):
        raise AssertionError(f"硬規則不該再呼叫分類器：{main_cat} {text}")


def _badge(engine: SopEngine119, source: str) -> str:
    return classification_badges_html({
        "main": engine.case.main_category,
        "main_conf": engine.case.main_conf or 1.0,
        "sub": engine.case.sub_category,
        "sub_conf": engine.case.sub_conf,
        "sub_source": source,
        "suspected_sub_category": engine.case.suspected_sub_category,
    })


class DisasterFullCallTests(unittest.TestCase):
    def _run(self, opening: str, steps: list[tuple[str, dict]], bert=None):
        io = ScriptedIO([answer for answer, _ in steps])
        llm = AnswerLLM({answer: fields for answer, fields in steps})
        engine = SopEngine119(io=io, llm_extractor=llm, sub_classifiers=bert)  # type: ignore[arg-type]
        engine.case.main_category = "災害"
        engine.case.main_conf = 0.95
        engine.case.address = "板橋區文化路一段10號"
        engine.case.address_confirmed = True
        engine._address_locked = True
        engine.case.transcript = [{"role": "caller", "text": opening}]
        engine._run_災害()
        return engine, io

    def test_hard_rule_wire_down_asks_spark_and_marks_suspected(self) -> None:
        engine, io = self._run("電線掉了", [
            ("有人被壓住出不來", {"disaster_injury_or_trapped": INJURY_TRAPPED}),
            ("兩個人", {"disaster_trapped_count": "兩個人"}),
            ("擋到一部分還過得去", {"traffic_impact": TRAFFIC_PARTIAL}),
            ("有冒火花", {"electrical_hazard": "有火花或冒煙"}),
            ("我住這裡", {"disaster_caller_role": ROLE_OWNER}),
            ("王小明 0912345678", {"caller_name": "王小明", "caller_contact": "0912345678"}),
        ], bert=BoomBert())
        self.assertIn(DISPATCH_LINE, io.messages)
        self.assertIn(COUNT_QUESTION, io.messages)
        self.assertIn(SPARK_QUESTION, io.messages)
        self.assertLess(io.messages.index(DISPATCH_LINE), io.messages.index(SPARK_QUESTION))
        self.assertEqual(engine.case.sub_category, "電線掉落")
        self.assertEqual(engine.case.suspected_sub_category, "電線掉落")
        self.assertEqual(engine.case.sub_conf, 1.0)
        self.assertEqual(engine.case.disaster_injury_or_trapped, INJURY_TRAPPED)
        self.assertEqual(engine.case.disaster_trapped_count, "兩個人")
        self.assertEqual(engine.case.traffic_impact, TRAFFIC_PARTIAL)
        self.assertEqual(engine.case.electrical_hazard, "有火花或冒煙")
        self.assertEqual(engine.case.disaster_caller_role, ROLE_OWNER)
        self.assertEqual(engine.case.caller_name, "王小明")
        self.assertEqual(engine.case.caller_contact, "0912345678")
        self.assertEqual(engine.case.result, "dispatched")
        badge = _badge(engine, "hard_rule")
        self.assertIn("硬規則", badge)
        self.assertIn("疑似電線掉落類", badge)
        self.assertNotIn("分類器", badge)

    def test_classifier_tree_does_not_ask_spark_or_suspect(self) -> None:
        bert = FixedBert("路樹傾倒")
        engine, io = self._run("路樹倒在文化路", [
            ("有人受傷但已經出來", {"disaster_injury_or_trapped": INJURY_HURT}),
            ("沒擋到路", {"traffic_impact": "未影響交通"}),
            ("我路過", {"disaster_caller_role": "路過"}),
            ("林小姐 0922333444", {"caller_name": "林小姐", "caller_contact": "0922333444"}),
        ], bert=bert)
        self.assertNotIn(COUNT_QUESTION, io.messages)
        self.assertNotIn(SPARK_QUESTION, io.messages)
        self.assertEqual(engine.case.sub_category, "路樹傾倒")
        self.assertIsNone(engine.case.suspected_sub_category)
        self.assertEqual(engine.case.disaster_injury_or_trapped, INJURY_HURT)
        self.assertIsNone(engine.case.disaster_trapped_count)
        self.assertEqual(engine.case.traffic_impact, "未影響交通")
        self.assertIsNone(engine.case.electrical_hazard)
        self.assertEqual(engine.case.disaster_caller_role, "路過")
        self.assertEqual(engine.case.caller_name, "林小姐")
        self.assertGreater(bert.calls, 0)
        self.assertEqual(engine.case.result, "dispatched")
        badge = _badge(engine, "classifier")
        self.assertIn("分類器", badge)
        self.assertNotIn("疑似", badge)
        self.assertNotIn("硬規則", badge)


class HardRuleSuspectedTests(unittest.TestCase):
    def _apply(self, main: str, text: str) -> SopEngine119:
        engine = SopEngine119(io=ScriptedIO([]), sub_classifiers=BoomBert())
        engine.case.main_category = main
        engine.case.main_conf = 0.9
        engine.case.transcript = [{"role": "caller", "text": text}]
        if main == "火警":
            engine._refresh_fire_subtype_from_bert()
        elif main == "災害":
            engine._refresh_disaster_subtype_from_bert()
        elif main in ("緊急救援", "其他案類", "檢舉投訴"):
            engine._refresh_hard_subcategory_only()
        elif main == "救護":
            sub, conf, source, _margin = engine._do_sub_classify(text, "救護")
            engine.case.sub_category = sub
            engine.case.sub_conf = conf
            engine.case.suspected_sub_category = sub if source == "hard_rule" else None
        return engine

    def test_every_listed_subtype_with_keywords_sets_both_slots(self) -> None:
        seen = 0
        for main, subs in HARD_RULE_TARGETS.items():
            for sub in subs:
                keywords = keywords_for(main, sub)
                if not keywords:
                    engine = self._apply(main, "這句沒有任何關鍵詞")
                    self.assertIsNone(engine.case.suspected_sub_category, (main, sub))
                    continue
                keyword = max(keywords, key=len)
                hit, matched = match_hard_subcategory(keyword, main)
                self.assertEqual(hit, sub, (main, keyword, matched))
                engine = self._apply(main, keyword)
                self.assertEqual(engine.case.sub_category, sub, (main, keyword))
                self.assertEqual(engine.case.suspected_sub_category, sub, (main, keyword))
                self.assertEqual(engine.case.sub_conf, 1.0)
                badge = _badge(engine, "hard_rule")
                self.assertIn("硬規則", badge)
                self.assertIn(f"疑似{sub}類", badge)
                self.assertNotIn("分類器", badge)
                self.assertNotIn("關鍵詞直判", badge)
                seen += 1
        # 救護 6、火警 7、緊急救援 4、災害 16、其他案類 7。
        # 其他案類本身與檢舉投訴七列沒有關鍵詞，不會命中。
        self.assertEqual(seen, 40)

    def test_classifier_path_does_not_fill_suspected_slot(self) -> None:
        bert = FixedBert("急病", 0.88, 0.05)
        engine = SopEngine119(io=ScriptedIO([]), sub_classifiers=bert)
        engine.case.main_category = "救護"
        text = "有人突然不舒服"
        self.assertEqual(match_hard_subcategory(text, "救護"), (None, None))
        sub, conf, source, _margin = engine._do_sub_classify(text, "救護")
        engine.case.sub_category = sub
        engine.case.sub_conf = conf
        engine.case.suspected_sub_category = sub if source == "hard_rule" else None
        self.assertEqual(source, "classifier")
        self.assertEqual(engine.case.sub_category, "急病")
        self.assertIsNone(engine.case.suspected_sub_category)
        badge = _badge(engine, "classifier")
        self.assertIn("分類器", badge)
        self.assertNotIn("疑似", badge)

    def test_leaving_the_main_category_clears_the_suspected_slot(self) -> None:
        engine = self._apply("災害", "電線掉了")
        self.assertEqual(engine.case.suspected_sub_category, "電線掉落")
        engine._migrate_case_for_main_switch("災害", "救護")
        self.assertIsNone(engine.case.suspected_sub_category)
        self.assertIsNone(engine.case.sub_category)


if __name__ == "__main__":
    unittest.main()
