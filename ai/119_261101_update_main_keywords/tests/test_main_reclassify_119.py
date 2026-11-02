"""進細類前每輪重跑主分類：救護暫定後改判火警。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from location_validation_119 import JurisdictionResult
from sop_119_engine import DialogueIO, MainCategorySwitched, SopEngine119


FIRE_WORDS = ("火灾", "火災", "消防車", "消防车", "有煙", "有烟")


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError("測試回答已用盡")
        return self.answers.pop(0)


class FakeMainClf:
    """沒有火災詞就回救護 0.89；含火災／消防車／有煙就回火警 0.9。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def predict(self, text: str):
        self.calls.append(text)
        if any(w in (text or "") for w in FIRE_WORDS):
            return {
                "main_category": "火警",
                "main_conf": 0.9,
                "main_probs": {"火警": 0.9, "救護": 0.08},
            }
        return {
            "main_category": "救護",
            "main_conf": 0.89,
            "main_probs": {"救護": 0.89, "火警": 0.06},
        }


class FakeLLM:
    def extract_general_fields(
        self,
        caller_text: str,
        question: str | None = None,
        *,
        main_category: str | None = None,
        call_type: str | None = None,
        **_kwargs,
    ) -> dict:
        text = caller_text or ""
        out: dict = {}
        if any(w in text for w in ("火災", "火灾", "有煙", "有烟")):
            out["incident_description"] = "有煙有火災"
            if main_category == "火警":
                out["fire_or_smoke"] = "有煙有火"
        return out


def _engine(answers: list[str], *, llm=None) -> SopEngine119:
    return SopEngine119(
        io=ScriptedIO(answers),
        main_classifier=FakeMainClf(),
        sub_classifiers=None,
        llm_extractor=llm,
    )


def _stop_after_fire_address(engine: SopEngine119):
    return patch.multiple(
        "handlers.火警通用.HuoJingGenericHandler",
        run_generic_flow=lambda self, eng: None,
        collect_caller_info=lambda self, eng: None,
    )


class MainReclassifyDuringAddressTests(unittest.TestCase):
    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_vague_opening_then_fire_switches_main(self, _query) -> None:
        engine = _engine([
            "欸，我那個。",
            "板橋區府中路32號，有煙有火災。需要消防車。",
            "是的。",
        ])
        with _stop_after_fire_address(engine):
            engine._run_main_flow()

        self.assertEqual(engine.case.main_category, "火警")
        self.assertIn("板橋區府中路32號", engine.case.address or "")
        self.assertTrue(engine.case.address_confirmed)
        spoken = "\n".join(engine._io.messages)
        self.assertNotIn("救護車已派出", spoken)
        self.assertIn("消防車已派出", spoken)
        first_q = engine._io.messages[0]
        self.assertTrue(
            any(k in first_q for k in ("火災", "消防車", "救護")),
            first_q,
        )
        loc_qs = [q for q in engine._io.messages if "地址" in q]
        self.assertTrue(loc_qs)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_incident_description_survives_switch_to_fire(self, _query) -> None:
        engine = _engine(
            [
                "欸，我那個。",
                "板橋區府中路32號，有煙有火災。需要消防車。",
                "是的。",
            ],
            llm=FakeLLM(),
        )
        with _stop_after_fire_address(engine):
            engine._run_main_flow()

        self.assertEqual(engine.case.main_category, "火警")
        self.assertEqual(engine.case.incident_description, "有煙有火災")
        self.assertEqual(engine.case.fire_or_smoke, "有煙有火")

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "板橋分局"),
    )
    def test_yes_confirm_does_not_switch_fire_back_to_rescue(self, _query) -> None:
        engine = _engine([
            "欸，我那個。",
            "板橋區府中路32號，有煙有火災。需要消防車。",
            "是的。",
        ])
        with _stop_after_fire_address(engine):
            engine._run_main_flow()

        self.assertEqual(engine.case.main_category, "火警")
        last_predict = engine._main_clf.calls[-1]
        self.assertIn("是的。", last_predict)
        self.assertTrue(any(w in last_predict for w in FIRE_WORDS))


class MainReclassifyWindowTests(unittest.TestCase):
    def test_confirm_short_reply_alone_does_not_leave_fire(self) -> None:
        engine = _engine([])
        engine.case.main_category = "火警"
        engine.case.main_conf = 0.9
        engine.case.transcript = [
            {"role": "caller", "text": "板橋區府中路32號，有煙有火災。需要消防車。"},
            {"role": "assistant", "text": "確定是板橋區府中路32號這個地址嗎？"},
            {"role": "caller", "text": "是的。"},
        ]
        engine._main_reclassify_enabled = True
        engine._maybe_reclassify_main()
        self.assertEqual(engine.case.main_category, "火警")

    def test_after_sub_handler_does_not_switch_main(self) -> None:
        engine = _engine([])
        engine.case.main_category = "救護"
        engine.case.sub_category = "急病"
        engine.case.transcript = [
            {"role": "caller", "text": "有人昏倒"},
            {"role": "caller", "text": "有煙有火災。需要消防車。"},
        ]
        engine._main_reclassify_enabled = False
        engine._after_caller_input("有煙有火災。需要消防車。")
        self.assertEqual(engine.case.main_category, "救護")
        self.assertEqual(engine.case.sub_category, "急病")


class MainSwitchMigrateTests(unittest.TestCase):
    def test_keeps_shared_slots_clears_rescue_exclusive(self) -> None:
        engine = _engine([])
        engine.case.main_category = "救護"
        engine.case.address = "板橋區府中路32號"
        engine.case.address_district = "板橋區"
        engine.case.address_road = "府中路"
        engine.case.address_number = "32號"
        engine.case.address_confirmed = True
        engine.case.incident_description = "有人昏倒"
        engine.case.consciousness = True
        engine.case.sub_category = "急病"
        engine.case.sub_conf = 0.9

        engine._migrate_case_for_main_switch("救護", "火警")

        self.assertEqual(engine.case.address, "板橋區府中路32號")
        self.assertEqual(engine.case.address_district, "板橋區")
        self.assertEqual(engine.case.incident_description, "有人昏倒")
        self.assertIsNone(engine.case.consciousness)
        self.assertIsNone(engine.case.sub_category)
        self.assertIsNone(engine.case.sub_conf)

    def test_reextracts_fire_fields_from_history(self) -> None:
        engine = _engine([], llm=FakeLLM())
        engine.case.main_category = "救護"
        engine.case.consciousness = True
        engine.case.incident_description = "有人昏倒"
        engine.case.transcript = [
            {"role": "assistant", "text": "請先告訴我地址？幾樓？"},
            {"role": "caller", "text": "板橋區府中路32號，有煙有火災。需要消防車。"},
        ]
        engine._apply_main_switch("救護", "火警", 0.9)
        self.assertEqual(engine.case.main_category, "火警")
        self.assertIsNone(engine.case.consciousness)
        self.assertEqual(engine.case.fire_or_smoke, "有煙有火")
        self.assertEqual(engine.case.incident_description, "有人昏倒")

    def test_maybe_reclassify_raises_when_enabled(self) -> None:
        engine = _engine([])
        engine.case.main_category = "救護"
        engine.case.transcript = [
            {"role": "caller", "text": "欸，我那個。"},
            {"role": "caller", "text": "有煙有火災。需要消防車。"},
        ]
        engine._main_reclassify_enabled = True
        with self.assertRaises(MainCategorySwitched) as ctx:
            engine._maybe_reclassify_main()
        self.assertEqual(ctx.exception.old, "救護")
        self.assertEqual(ctx.exception.new, "火警")
        self.assertEqual(engine.case.main_category, "火警")


if __name__ == "__main__":
    unittest.main()
