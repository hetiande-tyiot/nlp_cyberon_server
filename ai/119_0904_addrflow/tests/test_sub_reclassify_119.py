"""
子類動態重分類與 SOP 遷移。

執行：
  cd /root/work/119 && python -m unittest tests.test_sub_reclassify_119 -v
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fire_tab_map_119 import (
    TAB_A,
    TAB_B1,
    TAB_A_QUESTIONS,
    apply_bert_subtype_to_case,
    apply_subtype_identity_codes,
    subtype_name_from_identity_codes,
)
from handlers import sop_slots_for
from handlers.火警通用 import HuoJingGenericHandler
from handlers.車禍 import CheHuoHandler
from handlers.急病 import JiBingHandler
from sop_119_engine import DialogueIO, SopEngine119, SubCategorySwitched


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


class FakeSubClf:
    def __init__(self, all_probs: dict[str, float]):
        self.all_probs = dict(all_probs)
        self.calls: list[tuple[str, str]] = []

    def predict(self, text: str, main_category: str):
        self.calls.append((text, main_category))
        label = max(self.all_probs, key=self.all_probs.get)
        conf = self.all_probs[label]
        return SimpleNamespace(
            final_label=label,
            classifier_conf=conf,
            all_probs=dict(self.all_probs),
        )


class RemapLLM:
    def __init__(self, remapped: dict | None = None):
        self.remapped = remapped or {}
        self.remap_calls: list[dict] = []

    def remap_sop_fields_for_subcategory(self, **kwargs):
        self.remap_calls.append(kwargs)
        return dict(self.remapped)

    def extract_general_fields(self, *args, **kwargs):
        return {}

    def generate_summary(self, *args, **kwargs):
        return ""


def _probs(**kwargs: float) -> dict[str, float]:
    base = {
        "急病": 0.02,
        "一般受傷": 0.02,
        "路倒": 0.02,
        "精神異常": 0.02,
        "打架受傷": 0.02,
        "吞食藥物": 0.02,
        "割腕": 0.02,
        "車禍": 0.02,
        "其它": 0.02,
    }
    base.update(kwargs)
    return base


class MaybeReclassifyTests(unittest.TestCase):
    def _engine(self, *, probs: dict[str, float], llm=None) -> SopEngine119:
        engine = SopEngine119(
            io=ScriptedIO([]),
            sub_classifiers=FakeSubClf(probs),
            llm_extractor=llm,
        )
        engine.case.main_category = "救護"
        engine.case.sub_category = "急病"
        engine.case.sub_conf = 0.7
        engine.case.transcript = [{"role": "caller", "text": "有人不舒服"}]
        engine._sub_reclassify_enabled = True
        return engine

    def test_same_subcategory_does_not_switch(self) -> None:
        engine = self._engine(probs=_probs(急病=0.81, 車禍=0.05))
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(engine.case.sub_category, "急病")

    def test_lower_or_equal_confidence_does_not_switch(self) -> None:
        engine = self._engine(probs=_probs(車禍=0.40, 急病=0.40))
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(engine.case.sub_category, "急病")

        engine = self._engine(probs=_probs(車禍=0.39, 急病=0.41))
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(engine.case.sub_category, "急病")

    def test_higher_confidence_switches_and_updates_sub_category(self) -> None:
        llm = RemapLLM({"injury_cause": "兩車碰撞"})
        engine = self._engine(probs=_probs(車禍=0.72, 急病=0.18), llm=llm)
        engine.case.incident_description = "人突然倒下"
        engine.case.consciousness = True

        result = engine._maybe_reclassify_sub()
        self.assertEqual(result, ("急病", "車禍"))
        self.assertEqual(engine.case.sub_category, "車禍")
        self.assertAlmostEqual(engine.case.sub_conf or 0, 0.72)
        self.assertEqual(engine.case.incident_description, "人突然倒下")
        self.assertEqual(engine.case.injury_cause, "兩車碰撞")
        self.assertTrue(llm.remap_calls)
        self.assertEqual(llm.remap_calls[0]["old_sub"], "急病")
        self.assertEqual(llm.remap_calls[0]["new_sub"], "車禍")

    def test_keyword_only_kept_when_keyword_still_matches(self) -> None:
        engine = self._engine(probs=_probs(急病=0.88, 車禍=0.04))
        engine.case.sub_category = "上吊"
        engine.case.transcript = [{"role": "caller", "text": "有人上吊了快來"}]
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(engine.case.sub_category, "上吊")

    def test_keyword_only_switches_when_keyword_gone(self) -> None:
        engine = self._engine(probs=_probs(急病=0.77, 車禍=0.05))
        engine.case.sub_category = "上吊"
        engine.case.transcript = [{"role": "caller", "text": "他只是肚子痛"}]
        result = engine._maybe_reclassify_sub()
        self.assertEqual(result, ("上吊", "急病"))
        self.assertEqual(engine.case.sub_category, "急病")

    def test_disabled_flag_skips(self) -> None:
        engine = self._engine(probs=_probs(車禍=0.9, 急病=0.05))
        engine._sub_reclassify_enabled = False
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(engine.case.sub_category, "急病")


class SwitchClearsExclusiveSlotsTests(unittest.TestCase):
    def test_clears_old_exclusive_keeps_shared_semantic(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]), llm_extractor=RemapLLM())
        engine.case.main_category = "救護"
        engine.case.sub_category = "孕婦急產"
        engine.case.incident_description = "快生了"
        engine.case.consciousness = True
        engine.case.pregnancy_week = "32週"
        engine.case.due_date = "下週"
        engine._switch_subcategory("孕婦急產", "急病", 0.8)

        self.assertEqual(engine.case.sub_category, "急病")
        self.assertEqual(engine.case.incident_description, "快生了")
        self.assertIs(engine.case.consciousness, True)
        self.assertIsNone(engine.case.pregnancy_week)
        self.assertIsNone(engine.case.due_date)
        self.assertIn("pregnancy_week", sop_slots_for("孕婦急產"))
        self.assertNotIn("pregnancy_week", sop_slots_for("急病"))

    def test_ambiguous_same_name_slot_cleared_without_llm(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]), llm_extractor=RemapLLM())
        engine.case.main_category = "救護"
        engine.case.sub_category = "車禍"
        engine.case.medical_history = "路過現場"
        engine.case.incident_description = "兩車相撞"
        engine._switch_subcategory("車禍", "路倒", 0.75)
        self.assertIsNone(engine.case.medical_history)
        self.assertEqual(engine.case.incident_description, "兩車相撞")


class RescueHandlerRestartTests(unittest.TestCase):
    def test_switch_restarts_new_handler_and_asks_empty_slots(self) -> None:
        class StopAfterChehuoS0(Exception):
            pass

        # incident_description 預先填好：模擬 A 的初問已在重問迴圈完成（重問迴圈的
        # sub-reclassify 尚未啟用），車禍訊號改在後續生命征象問答才吐露，藉此驗證
        # handler 執行中切類會重入新 handler（C 探問揭露服藥時走的正是這條路）。
        io = ScriptedIO(["他昏過去了，其實是兩台車對撞"])
        clf = FakeSubClf(_probs(車禍=0.86, 急病=0.10))
        engine = SopEngine119(io=io, sub_classifiers=clf, llm_extractor=RemapLLM())
        engine.case.main_category = "救護"
        # 具體病情（非含糊）→ 急病 S0 跳過（Fix2 不觸發），切類改在 S1 生命征象問答發生。
        engine.case.incident_description = "有人突然倒下昏迷"

        def stop_on_chehuo(self, eng):
            eng._set_stage("車禍_S0")
            if not eng._is_field_filled("incident_description"):
                eng._say("請問發生什麼事呢？")
            raise StopAfterChehuoS0()

        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(
                engine,
                "_do_sub_classify",
                return_value=("急病", 0.9, "classifier", 0.5),
            ),
            patch.object(CheHuoHandler, "run_subtype_flow", stop_on_chehuo),
            self.assertRaises(StopAfterChehuoS0),
        ):
            engine._run_救護()

        self.assertEqual(engine.case.sub_category, "車禍")
        # incident_description 已填 → 급病 S0 不再問，切類後由重入的車禍 handler 接手。
        self.assertTrue(any("清醒" in m for m in io.messages))
        self.assertGreaterEqual(len(clf.calls), 1)


class NoSymptomReaskTests(unittest.TestCase):
    """A 閘門：incident_description 只是「要救護車」這類請求（非病情）時，即使 BERT
    高信心，也要在鎖定細類前先追問「發生什麼狀況」。驅動案例 4c012163。"""

    def test_request_only_incident_triggers_reask_before_locking(self) -> None:
        class StopAtHandler(Exception):
            pass

        # 兩次 no_symptom_yet 追問的回答（仍未給具體病情，維持請求式）。
        io = ScriptedIO(["就是要救護車", "麻煩快點"])
        clf = FakeSubClf(_probs(急病=0.98))  # 高信心、高 margin
        engine = SopEngine119(io=io, sub_classifiers=clf, llm_extractor=RemapLLM())
        engine.case.main_category = "救護"
        engine.case.incident_description = "需要救護車"  # 純請求，非病情

        def stop_here(self, eng):
            raise StopAtHandler()

        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(JiBingHandler, "run_subtype_flow", stop_here),
            self.assertRaises(StopAtHandler),
        ):
            engine._run_救護()

        # 應至少追問一次「發生什麼狀況」，而非直接鎖定急病。
        self.assertTrue(any("發生什麼狀況" in m for m in io.messages))
        # 初判 + 追問後重判 → 分類器被呼叫多次。
        self.assertGreaterEqual(len(clf.calls), 2)

    def test_real_symptom_incident_does_not_reask(self) -> None:
        """對照組：已有具體病情（非請求）時，高信心即可定案、不應多問。"""
        class StopAtHandler(Exception):
            pass

        io = ScriptedIO([])
        clf = FakeSubClf(_probs(急病=0.98))
        engine = SopEngine119(io=io, sub_classifiers=clf, llm_extractor=RemapLLM())
        engine.case.main_category = "救護"
        engine.case.incident_description = "阿公突然胸口悶喘不過氣"  # 具體病情

        def stop_here(self, eng):
            raise StopAtHandler()

        with (
            patch.object(engine, "_run_address_flow"),
            patch.object(JiBingHandler, "run_subtype_flow", stop_here),
            self.assertRaises(StopAtHandler),
        ):
            engine._run_救護()

        self.assertFalse(any("發生什麼狀況" in m for m in io.messages))
        self.assertEqual(engine.case.sub_category, "急病")


class FireTabSwitchTests(unittest.TestCase):
    def test_apply_bert_allow_tab_switch_updates_tab(self) -> None:
        case = SimpleNamespace(
            fire_tab=TAB_A,
            fire_incident_type=0,
            building_type_code="10",
            has_flame=1,
            non_building_fire=None,
            vehicle_wildfire_code=None,
            minor_fire_code=None,
            sub_category="透天厝",
            sub_conf=0.7,
        )
        apply_bert_subtype_to_case(case, "汽車", 0.88, allow_tab_switch=True)
        self.assertEqual(case.fire_tab, TAB_B1)
        self.assertEqual(case.sub_category, "汽車")
        self.assertEqual(case.fire_incident_type, 1)
        self.assertEqual(case.vehicle_wildfire_code, 0)
        self.assertIsNone(case.building_type_code)
        self.assertIsNone(case.has_flame)

    def test_apply_bert_locked_tab_still_blocks_cross_tab_without_flag(self) -> None:
        case = SimpleNamespace(
            fire_tab=TAB_A,
            fire_incident_type=0,
            building_type_code="11",
            non_building_fire=None,
            vehicle_wildfire_code=None,
            minor_fire_code=None,
            sub_category="集合住宅",
            sub_conf=0.7,
        )
        apply_bert_subtype_to_case(case, "汽車", 0.99)
        self.assertEqual(case.fire_tab, TAB_A)
        self.assertEqual(case.sub_category, "集合住宅")
        self.assertIsNone(case.vehicle_wildfire_code)

    def test_engine_switches_fire_tab_when_new_conf_higher(self) -> None:
        clf = FakeSubClf({"汽車": 0.82, "透天厝": 0.12, "垃圾": 0.06})
        engine = SopEngine119(
            io=ScriptedIO([]),
            sub_classifiers=clf,
            llm_extractor=RemapLLM(),
        )
        engine.case.main_category = "火警"
        engine.case.sub_category = "透天厝"
        engine.case.sub_conf = 0.6
        engine.case.fire_tab = TAB_A
        engine.case.fire_incident_type = 0
        engine.case.building_type_code = "10"
        engine.case.has_flame = 1
        engine.case.transcript = [{"role": "caller", "text": "是車子在燒不是房子"}]
        engine._sub_reclassify_enabled = True

        result = engine._maybe_reclassify_sub()
        self.assertEqual(result, ("透天厝", "汽車"))
        self.assertEqual(engine.case.sub_category, "汽車")
        self.assertEqual(engine.case.fire_tab, TAB_B1)
        self.assertEqual(engine.case.fire_incident_type, 1)
        self.assertEqual(engine.case.vehicle_wildfire_code, 0)
        self.assertIsNone(engine.case.building_type_code)
        self.assertIsNone(engine.case.has_flame)

    def test_locked_tab_empty_sub_writes_same_tab_label(self) -> None:
        clf = FakeSubClf({"透天厝": 0.81, "汽車": 0.10, "垃圾": 0.05})
        engine = SopEngine119(
            io=ScriptedIO([]),
            sub_classifiers=clf,
            llm_extractor=RemapLLM(),
        )
        engine.case.main_category = "火警"
        engine.case.sub_category = None
        engine.case.fire_tab = TAB_A
        engine.case.fire_incident_type = 0
        engine.case.transcript = [{"role": "caller", "text": "透天厝著火了"}]
        engine._sub_reclassify_enabled = True

        result = engine._maybe_reclassify_sub()
        self.assertIsNone(result)
        self.assertEqual(engine.case.sub_category, "透天厝")
        self.assertEqual(engine.case.building_type_code, "10")
        self.assertEqual(engine.case.fire_tab, TAB_A)

    def test_identity_code_extract_writes_sub_category(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]), llm_extractor=RemapLLM())
        engine.case.main_category = "火警"
        engine.case.fire_tab = TAB_A
        engine.case.fire_incident_type = 0
        engine._apply_extracted_fields({"building_type_code": "11"})
        self.assertEqual(engine.case.sub_category, "集合住宅")
        self.assertEqual(
            subtype_name_from_identity_codes(engine.case), "集合住宅",
        )

    def test_same_tab_switch_updates_building_type_code(self) -> None:
        clf = FakeSubClf({"集合住宅": 0.84, "透天厝": 0.12, "垃圾": 0.04})
        engine = SopEngine119(
            io=ScriptedIO([]),
            sub_classifiers=clf,
            llm_extractor=RemapLLM(),
        )
        engine.case.main_category = "火警"
        engine.case.sub_category = "透天厝"
        engine.case.sub_conf = 0.6
        engine.case.fire_tab = TAB_A
        engine.case.fire_incident_type = 0
        engine.case.building_type_code = "10"
        engine.case.has_flame = 1
        engine.case.transcript = [{"role": "caller", "text": "是公寓大樓不是透天"}]
        engine._sub_reclassify_enabled = True

        result = engine._maybe_reclassify_sub()
        self.assertEqual(result, ("透天厝", "集合住宅"))
        self.assertEqual(engine.case.sub_category, "集合住宅")
        self.assertEqual(engine.case.building_type_code, "11")
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.has_flame, 1)

    def test_same_tab_b1_switch_updates_vehicle_code(self) -> None:
        clf = FakeSubClf({"機車": 0.85, "汽車": 0.10, "垃圾": 0.02})
        engine = SopEngine119(
            io=ScriptedIO([]),
            sub_classifiers=clf,
            llm_extractor=RemapLLM(),
        )
        engine.case.main_category = "火警"
        engine.case.sub_category = "汽車"
        engine.case.fire_tab = TAB_B1
        engine.case.fire_incident_type = 1
        engine.case.non_building_fire = 0
        engine.case.vehicle_wildfire_code = 0
        engine.case.transcript = [{"role": "caller", "text": "是機車在燒"}]
        engine._sub_reclassify_enabled = True

        result = engine._maybe_reclassify_sub()
        self.assertEqual(result, ("汽車", "機車"))
        self.assertEqual(engine.case.sub_category, "機車")
        self.assertEqual(engine.case.vehicle_wildfire_code, 1)
        self.assertEqual(engine.case.fire_tab, TAB_B1)

    def test_entering_tab_writes_sub_before_questions(self) -> None:
        clf = FakeSubClf({"透天厝": 0.81, "汽車": 0.10, "垃圾": 0.05})
        engine = SopEngine119(
            io=ScriptedIO([]),
            sub_classifiers=clf,
            llm_extractor=RemapLLM(),
        )
        engine.case.main_category = "火警"
        engine.case.fire_incident_type = 0
        engine.case.fire_tab = TAB_A
        engine.case.has_flame = 1
        engine.case.smoke_color_code = 1
        engine.case.has_explosion = 0
        engine.case.spread_risk = 0
        engine.case.people_trapped_code = 0
        engine.case.building_floors_code = 1
        engine.case.fire_floor_code = 2
        engine.case.building_structure = 5
        engine.case.burn_area_code = 1
        engine.case.access_water_info = 0
        engine.case.transcript = [{"role": "caller", "text": "透天厝著火了"}]
        self.assertEqual(len(TAB_A_QUESTIONS), 11)

        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.sub_category, "透天厝")
        self.assertEqual(engine.case.building_type_code, "10")
        self.assertEqual(engine.case.fire_tab, TAB_A)

    def test_apply_identity_codes_same_tab_overwrites_number(self) -> None:
        case = SimpleNamespace(
            fire_tab=TAB_A,
            fire_incident_type=0,
            building_type_code="10",
            has_flame=1,
            non_building_fire=None,
            vehicle_wildfire_code=None,
            minor_fire_code=None,
            sub_category="透天厝",
        )
        self.assertTrue(apply_subtype_identity_codes(case, "集合住宅"))
        self.assertEqual(case.building_type_code, "11")
        self.assertEqual(case.fire_incident_type, 0)
        self.assertEqual(case.has_flame, 1)
        self.assertIsNone(case.vehicle_wildfire_code)

    def test_fire_below_threshold_does_not_switch_tab(self) -> None:
        clf = FakeSubClf({"汽車": 0.48, "透天厝": 0.20, "垃圾": 0.10})
        engine = SopEngine119(io=ScriptedIO([]), sub_classifiers=clf)
        engine.case.main_category = "火警"
        engine.case.sub_category = "透天厝"
        engine.case.fire_tab = TAB_A
        engine.case.transcript = [{"role": "caller", "text": "好像是車子"}]
        engine._sub_reclassify_enabled = True
        self.assertIsNone(engine._maybe_reclassify_sub())
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.sub_category, "透天厝")


class SubCategorySwitchedExceptionTests(unittest.TestCase):
    def test_after_caller_input_raises_when_switched(self) -> None:
        clf = FakeSubClf(_probs(車禍=0.9, 急病=0.05))
        engine = SopEngine119(io=ScriptedIO([]), sub_classifiers=clf)
        engine.case.main_category = "救護"
        engine.case.sub_category = "急病"
        engine.case.transcript = [
            {"role": "assistant", "text": "請問現場發生什麼事？"},
            {"role": "caller", "text": "兩車相撞"},
        ]
        engine._sub_reclassify_enabled = True
        with self.assertRaises(SubCategorySwitched) as raised:
            engine._after_caller_input("兩車相撞", question="請問現場發生什麼事？")
        self.assertEqual(raised.exception.old, "急病")
        self.assertEqual(raised.exception.new, "車禍")


if __name__ == "__main__":
    unittest.main()
