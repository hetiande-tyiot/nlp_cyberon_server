"""指定次案類硬規則：詞表比對、雙欄寫入、分類器不寫疑似欄。"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from classification_badges_119 import classification_badges_html
from emergency_accident_119 import SUBCATEGORY as ACCIDENT
from emergency_rescue_subs_119 import SUB_QUESTIONS
from hard_subcategory_rules_119 import (
    keywords_for,
    match_hard_subcategory,
    normalize_hard_keyword,
)
from sop_119_engine import DialogueIO, SopEngine119


class ScriptedIO(DialogueIO):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        raise AssertionError("這個測試不應再向報案人提問")


class BoomClassifier:
    def predict(self, text: str, main_category: str):
        raise AssertionError(f"硬規則命中後不該呼叫分類器：{main_category} {text}")


class FixedClassifier:
    def __init__(self, label: str, conf: float = 0.9, second_label: str = "路樹傾倒", second: float = 0.04):
        self.label = label
        self.conf = conf
        self.second_label = second_label
        self.second = second
        self.calls = 0

    def predict(self, text: str, main_category: str):
        self.calls += 1
        return SimpleNamespace(
            final_label=self.label,
            classifier_conf=self.conf,
            all_probs={self.label: self.conf, self.second_label: self.second},
        )


class HardKeywordTableTests(unittest.TestCase):
    def test_strips_grade_marks(self) -> None:
        self.assertEqual(normalize_hard_keyword("喝農藥(D)"), "喝農藥")
        self.assertEqual(normalize_hard_keyword("路塌陷B)"), "路塌陷")
        self.assertEqual(normalize_hard_keyword("要救護車後斷線（D)"), "要救護車後斷線")

    def test_longer_keyword_wins(self) -> None:
        sub, keyword = match_hard_subcategory("他喝農藥了", "救護")
        self.assertEqual(sub, "喝農藥")
        self.assertEqual(keyword, "喝農藥")

    def test_rescue_drowning_does_not_use_emergency_row(self) -> None:
        self.assertEqual(match_hard_subcategory("游泳游不回岸上", "救護"), (None, None))
        self.assertEqual(match_hard_subcategory("有人溺水了", "救護")[0], "溺水")

    def test_other_break_in_uses_only_that_main(self) -> None:
        self.assertEqual(match_hard_subcategory("門打不開", "其他案類")[0], "破門")
        self.assertEqual(match_hard_subcategory("房內自殺", "其他案類"), (None, None))

    def test_complaint_rows_have_no_keywords(self) -> None:
        for sub in ("其它", "消防安全", "救護", "檢舉投訴", "危險物品", "服勤紀律", "救災"):
            self.assertEqual(keywords_for("檢舉投訴", sub), ())
        self.assertEqual(match_hard_subcategory("救護車趕快來", "檢舉投訴"), (None, None))

    def test_collapsed_road_typo_keyword_still_matches(self) -> None:
        self.assertEqual(match_hard_subcategory("路塌陷了", "災害")[0], "道路中斷")

    def test_emergency_three_sops_match_only_in_that_main(self) -> None:
        self.assertEqual(match_hard_subcategory("游泳游不回岸上", "緊急救援")[0], "溺水")
        self.assertEqual(match_hard_subcategory("要破門", "緊急救援")[0], "破門")
        self.assertEqual(match_hard_subcategory("手指卡住", "緊急救援")[0], "其他(卡住夾住)")
        self.assertEqual(match_hard_subcategory("汽油味", "緊急救援"), (None, None))
        self.assertEqual(match_hard_subcategory("手指卡住", "救護"), (None, None))
        self.assertEqual(match_hard_subcategory("要破門", "其他案類"), (None, None))


class HardRuleEngineTests(unittest.TestCase):
    def test_disaster_hard_rule_writes_both_slots_and_skips_bert(self) -> None:
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=BoomClassifier())
        engine.case.main_category = "災害"
        engine.case.transcript = [{"role": "caller", "text": "電線掉了"}]
        engine._refresh_disaster_subtype_from_bert()
        self.assertEqual(engine.case.sub_category, "電線掉落")
        self.assertEqual(engine.case.suspected_sub_category, "電線掉落")
        self.assertEqual(engine.case.sub_conf, 1.0)

    def test_classifier_does_not_fill_suspected_slot(self) -> None:
        clf = FixedClassifier("路樹傾倒")
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=clf)
        engine.case.main_category = "災害"
        engine.case.transcript = [{"role": "caller", "text": "現場還在確認中"}]
        engine._refresh_disaster_subtype_from_bert()
        self.assertEqual(engine.case.sub_category, "路樹傾倒")
        self.assertIsNone(engine.case.suspected_sub_category)
        self.assertEqual(clf.calls, 1)

    def test_fire_hard_rule_writes_subtype(self) -> None:
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=BoomClassifier())
        engine.case.main_category = "火警"
        engine.case.transcript = [{"role": "caller", "text": "高鐵燒起來"}]
        engine._refresh_fire_subtype_from_bert()
        self.assertEqual(engine.case.sub_category, "軌道型交通工具")
        self.assertEqual(engine.case.suspected_sub_category, "軌道型交通工具")

    def test_rescue_hard_rule_beats_old_poison_keyword(self) -> None:
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=BoomClassifier())
        sub, conf, source, margin = engine._do_sub_classify("他喝農藥", "救護")
        self.assertEqual((sub, conf, source, margin), ("喝農藥", 1.0, "hard_rule", 1.0))

    def test_reclassify_does_not_let_bert_override_hard_rule(self) -> None:
        clf = FixedClassifier("急病", second_label="車禍")
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=clf)
        engine.case.main_category = "救護"
        engine.case.sub_category = "喝農藥"
        engine.case.suspected_sub_category = "喝農藥"
        engine.case.sub_conf = 1.0
        engine.case.transcript = [{"role": "caller", "text": "他喝農藥"}]
        engine._sub_reclassify_enabled = True
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(engine.case.sub_category, "喝農藥")
        self.assertEqual(engine.case.suspected_sub_category, "喝農藥")
        self.assertEqual(clf.calls, 0)

    def test_other_category_hard_rule_writes_both_slots(self) -> None:
        engine = SopEngine119(io=ScriptedIO())
        engine.case.main_category = "其他案類"
        engine.case.transcript = [{"role": "caller", "text": "門打不開"}]
        engine._refresh_hard_subcategory_only()
        self.assertEqual(engine.case.sub_category, "破門")
        self.assertEqual(engine.case.suspected_sub_category, "破門")

    def test_stuck_hard_rule_uses_the_trap_sop_name(self) -> None:
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=BoomClassifier())
        engine.case.main_category = "緊急救援"
        engine.case.transcript = [{"role": "caller", "text": "手指卡住"}]
        sub, _conf, source, _margin = engine._do_sub_classify("手指卡住", "緊急救援")
        self.assertEqual((sub, source), ("其他(卡住夾住)", "hard_rule"))
        engine._refresh_hard_subcategory_only()
        self.assertEqual(engine.case.sub_category, "其他(卡住夾住)")
        self.assertEqual(engine.case.suspected_sub_category, "其他(卡住夾住)")

    def test_main_switch_clears_suspected_slot(self) -> None:
        engine = SopEngine119(io=ScriptedIO())
        engine.case.main_category = "災害"
        engine.case.sub_category = "電線掉落"
        engine.case.suspected_sub_category = "電線掉落"
        engine.case.sub_conf = 1.0
        engine._migrate_case_for_main_switch("災害", "救護")
        self.assertIsNone(engine.case.sub_category)
        self.assertIsNone(engine.case.suspected_sub_category)
        self.assertIsNone(engine.case.sub_conf)


class ClassificationBadgeTests(unittest.TestCase):
    def test_hard_rule_and_classifier_are_separate_reminders(self) -> None:
        hard = classification_badges_html({
            "main": "救護",
            "main_conf": 0.9,
            "sub": "喝農藥",
            "sub_conf": 1.0,
            "sub_source": "hard_rule",
            "suspected_sub_category": "喝農藥",
        })
        self.assertIn("硬規則", hard)
        self.assertIn("疑似喝農藥類", hard)
        self.assertNotIn("分類器", hard)
        self.assertNotIn("關鍵詞直判", hard)

        clf = classification_badges_html({
            "main": "災害",
            "main_conf": 0.8,
            "sub": "路樹傾倒",
            "sub_conf": 0.9,
            "sub_source": "classifier",
            "suspected_sub_category": None,
        })
        self.assertIn("分類器", clf)
        self.assertNotIn("疑似", clf)
        self.assertNotIn("硬規則", clf)

        keyword = classification_badges_html({
            "main": "救護",
            "sub": "上吊",
            "sub_conf": 1.0,
            "sub_source": "keyword",
        })
        self.assertIn("關鍵詞直判", keyword)
        self.assertNotIn("疑似", keyword)


class ClassifierCoverageTests(unittest.TestCase):
    def test_made_sops_missing_from_v2_are_exactly_the_three_hard_rules(self) -> None:
        label_map = Path(
            "/home/cvmax/autodl-tmp/models/TW-119-BERT-sub_緊急救援_v2/label_map.json"
        )
        if not label_map.is_file():
            self.skipTest("沒有緊急救援 v2 的 label_map")
        v2 = set(json.loads(label_map.read_text(encoding="utf-8"))["label2id"])
        made = set(SUB_QUESTIONS) | {ACCIDENT}
        missing = made - v2
        self.assertEqual(missing, {"溺水", "破門", "其他(卡住夾住)"})
        for label in missing:
            self.assertTrue(keywords_for("緊急救援", label), label)


if __name__ == "__main__":
    unittest.main()
