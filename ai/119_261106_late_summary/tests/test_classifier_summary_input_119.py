"""地址問完的下一輪起，進大類、子類模型前拼接當前案情摘要；空白也讀取。硬規則與關鍵詞仍用原話。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from sop_119_engine import DialogueIO, SopEngine119


class ScriptedIO(DialogueIO):
    def say(self, text: str) -> None:
        return None

    def hear_text(self) -> str:
        raise AssertionError("這個測試不應再向報案人提問")


class AnswerIO(DialogueIO):
    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.said: list[str] = []

    def say(self, text: str) -> None:
        self.said.append(text)

    def hear_text(self) -> str:
        return self.answers.pop(0)


class RecordingMain:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def predict(self, text: str):
        self.calls.append(text)
        return {
            "main_category": "救護",
            "main_conf": 0.91,
            "main_probs": {"救護": 0.91, "火警": 0.04},
        }


class RecordingSub:
    def __init__(self, label: str = "急病") -> None:
        self.label = label
        self.calls: list[tuple[str, str]] = []

    def predict(self, text: str, main_category: str):
        self.calls.append((text, main_category))
        return SimpleNamespace(
            final_label=self.label,
            classifier_conf=0.9,
            all_probs={self.label: 0.9, "路倒": 0.04},
        )


class BoomClassifier:
    def predict(self, *args):
        raise AssertionError(f"不該呼叫分類器：{args}")


class ClassifierSummaryInputTests(unittest.TestCase):
    def _mark_address_already_passed(self, engine: SopEngine119) -> None:
        """地址環節已經過去，目前這些輪算下一輪。"""
        engine._address_done_caller_count = engine._caller_turn_count() - 1

    def test_summary_is_appended_before_main_and_sub_models(self) -> None:
        caller = "現場狀況還在了解"
        summary = "有人受困在車內"
        main = RecordingMain()
        sub = RecordingSub()
        engine = SopEngine119(
            io=ScriptedIO(), main_classifier=main, sub_classifiers=sub,
        )
        engine.case.case_summary = f"  {summary}  "
        self._mark_address_already_passed(engine)

        cat, conf, _margin = engine._do_main_classify(caller)
        sub_cat, sub_conf, source, _sub_margin = engine._do_sub_classify(caller, "救護")

        self.assertEqual(cat, "救護")
        self.assertEqual(conf, 0.91)
        self.assertEqual(main.calls, [caller + summary])
        self.assertEqual((sub_cat, sub_conf, source), ("急病", 0.9, "classifier"))
        self.assertEqual(sub.calls, [(caller + summary, "救護")])

    def test_blank_summary_is_still_read_and_model_text_unchanged(self) -> None:
        caller = "現場狀況還在了解"
        for blank in (None, "", "   \n"):
            with self.subTest(blank=blank):
                main = RecordingMain()
                sub = RecordingSub()
                engine = SopEngine119(
                    io=ScriptedIO(), main_classifier=main, sub_classifiers=sub,
                )
                engine.case.case_summary = blank
                self._mark_address_already_passed(engine)
                engine._do_main_classify(f"  {caller}  ")
                engine._do_sub_classify(caller, "災害")
                self.assertEqual(main.calls, [caller])
                self.assertEqual(sub.calls, [(caller, "災害")])

    def test_reclassify_models_also_receive_summary(self) -> None:
        caller = "現場還在確認"
        summary = "有人受困在車內"
        sub = RecordingSub("急病")
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=sub)
        engine.case.case_summary = summary
        engine.case.main_category = "救護"
        engine.case.sub_category = "急病"
        engine.case.transcript = [{"role": "caller", "text": caller}]
        self._mark_address_already_passed(engine)
        engine._sub_reclassify_enabled = True

        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(sub.calls, [(caller + summary, "救護")])

        sub.label = "瓦斯外洩"
        engine.case.main_category = "緊急救援"
        engine.case.sub_category = "瓦斯外洩"
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(sub.calls[-1], (caller + summary, "緊急救援"))

    def test_hard_rule_and_keywords_ignore_summary(self) -> None:
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=BoomClassifier())
        engine.case.case_summary = "手被燙傷"

        sub, conf, source, margin = engine._do_sub_classify("他喝農藥", "救護")
        self.assertEqual((sub, conf, source, margin), ("喝農藥", 1.0, "hard_rule", 1.0))

        engine.case.case_summary = "他喝農藥"
        sub, conf, source, margin = engine._do_sub_classify("手被燙傷", "救護")
        self.assertEqual((sub, conf, source, margin), ("燒燙傷", 1.0, "keyword", 1.0))

        bare = SopEngine119(io=ScriptedIO())
        bare.case.case_summary = "現場火災"
        self.assertEqual(
            bare._do_main_classify("請趕快過來"),
            ("救護", 0.5, 0.0),
        )

    def test_address_and_reask_replies_skip_classifier(self) -> None:
        engine = SopEngine119(io=AnswerIO([
            "板橋區文化路100號",
            "三重區",
            "對",
            "有人昏倒",
        ]))
        engine._ask_address_and_extract("請先告訴我地址？")
        engine._ask_address_and_extract("請問是哪一區？")
        engine._ask_and_extract("確定是板橋區文化路100號這個地址嗎？")
        engine._ask_and_extract("請問現場發生什麼狀況？")

        callers = [t for t in engine.case.transcript if t.get("role") == "caller"]
        self.assertEqual(
            [t["text"] for t in callers],
            ["板橋區文化路100號", "三重區", "對", "有人昏倒"],
        )
        self.assertTrue(callers[0].get("skip_classifier"))
        self.assertTrue(callers[1].get("skip_classifier"))
        self.assertNotIn("skip_classifier", callers[2])
        self.assertNotIn("skip_classifier", callers[3])
        self.assertFalse(engine._asking_address)
        self.assertIn("板橋區文化路100號", engine.case.full_caller_text())
        self.assertEqual(
            engine.case.classifier_caller_text(),
            "對\n有人昏倒",
        )

    def test_models_omit_address_replies_but_keep_summary(self) -> None:
        symptom = "現場狀況還在了解"
        summary = "有人受困在車內"
        main = RecordingMain()
        sub = RecordingSub()
        engine = SopEngine119(
            io=ScriptedIO(), main_classifier=main, sub_classifiers=sub,
        )
        engine.case.case_summary = summary
        engine.case.transcript = [
            {"role": "caller", "text": symptom},
            {"role": "caller", "text": "板橋區文化路100號", "skip_classifier": True},
            {"role": "caller", "text": "三重區", "skip_classifier": True},
        ]
        self._mark_address_already_passed(engine)
        full = engine.case.full_caller_text()
        expected = symptom + summary

        engine._do_main_classify(full)
        sub_cat, sub_conf, source, _margin = engine._do_sub_classify(full, "救護")
        self.assertEqual(main.calls, [expected])
        self.assertEqual((sub_cat, sub_conf, source), ("急病", 0.9, "classifier"))
        self.assertEqual(sub.calls, [(expected, "救護")])

        engine._do_main_classify("請趕快過來")
        self.assertEqual(main.calls[-1], "請趕快過來" + summary)

        engine.case.main_category = "救護"
        engine.case.sub_category = "急病"
        engine._sub_reclassify_enabled = True
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(sub.calls[-1], (expected, "救護"))

        sub.label = "瓦斯外洩"
        engine.case.main_category = "緊急救援"
        engine.case.sub_category = "瓦斯外洩"
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(sub.calls[-1], (expected, "緊急救援"))

    def test_hard_rule_still_reads_address_reply(self) -> None:
        engine = SopEngine119(io=ScriptedIO(), sub_classifiers=BoomClassifier())
        engine.case.case_summary = "手被燙傷"
        engine.case.transcript = [
            {"role": "caller", "text": "現場狀況還在了解"},
            {"role": "caller", "text": "他喝農藥", "skip_classifier": True},
        ]

        sub, conf, source, margin = engine._do_sub_classify(
            engine.case.full_caller_text(), "救護",
        )
        self.assertEqual((sub, conf, source, margin), ("喝農藥", 1.0, "hard_rule", 1.0))

    def test_summary_starts_on_the_turn_after_address(self) -> None:
        symptom = "現場狀況還在了解"
        summary = "有人受困在車內"
        main = RecordingMain()
        sub = RecordingSub()
        engine = SopEngine119(
            io=ScriptedIO(), main_classifier=main, sub_classifiers=sub,
        )
        engine.case.case_summary = summary
        engine.case.transcript = [
            {"role": "caller", "text": symptom},
            {"role": "caller", "text": "板橋區文化路100號", "skip_classifier": True},
        ]
        full = engine.case.full_caller_text()

        engine._do_main_classify(full)
        engine._do_sub_classify(full, "救護")
        self.assertEqual(main.calls, [symptom])
        self.assertEqual(sub.calls, [(symptom, "救護")])

        engine._address_done_caller_count = engine._caller_turn_count()
        engine._do_main_classify(full)
        engine._do_sub_classify(full, "救護")
        self.assertEqual(main.calls[-1], symptom)
        self.assertEqual(sub.calls[-1], (symptom, "救護"))

        engine.case.transcript.append({"role": "caller", "text": "請再說明一下"})
        later = engine.case.full_caller_text()
        expected = "現場狀況還在了解\n請再說明一下" + summary
        engine._do_main_classify(later)
        sub_cat, sub_conf, source, _margin = engine._do_sub_classify(later, "救護")
        self.assertEqual(main.calls[-1], expected)
        self.assertEqual((sub_cat, sub_conf, source), ("急病", 0.9, "classifier"))
        self.assertEqual(sub.calls[-1], (expected, "救護"))
        self.assertNotIn("板橋區文化路100號", main.calls[-1])
        self.assertNotIn("板橋區文化路100號", sub.calls[-1][0])
