"""火警等級：次案類初始值，語意標籤只升不降。"""

from __future__ import annotations

import unittest

from case_info_119 import CaseInfo119
from fire_level_119 import (
    accepted_signals,
    highest_signal_level,
    initial_level,
    raise_fire_level,
)
from sop_119_engine import DialogueIO, SopEngine119


class _SilentIO(DialogueIO):
    def say(self, text: str) -> None:
        return None

    def hear_text(self) -> str:
        return ""


class FireLevelTests(unittest.TestCase):
    def test_initial_levels_from_the_sheet(self) -> None:
        self.assertEqual(initial_level("透天厝"), 0)
        self.assertEqual(initial_level("旅館、百貨商場用途建築物"), 2)
        self.assertEqual(initial_level("隧道"), 2)
        self.assertEqual(initial_level("船舶"), 3)
        self.assertEqual(initial_level("瓦斯漏氣"), 0)
        self.assertEqual(initial_level("巷弄狹小"), 0)
        self.assertEqual(initial_level("不存在的次案類"), 0)

    def test_signals_upgrade_and_never_downgrade(self) -> None:
        case = CaseInfo119(main_category="火警", sub_category="隧道", fire_level=2)

        raise_fire_level(case, ["無煙"])
        self.assertEqual(case.fire_level, 2)

        raise_fire_level(case, ["有人受困"])
        self.assertEqual(case.fire_level, 3)

        raise_fire_level(case, ["無火焰", "白煙"])
        self.assertEqual(case.fire_level, 3)

    def test_unknown_signals_are_dropped(self) -> None:
        self.assertEqual(accepted_signals(["有爆炸", "有火焰", "無火焰"]), ["有火焰"])
        self.assertEqual(highest_signal_level(["有爆炸"]), 0)
        self.assertEqual(highest_signal_level("黑煙"), 2)

    def test_rescue_case_is_left_unset(self) -> None:
        case = CaseInfo119(main_category="救護", sub_category="車禍")

        raise_fire_level(case, ["有人受困"])

        self.assertIsNone(case.fire_level)

    def test_engine_apply_uses_signals_not_a_direct_level(self) -> None:
        engine = SopEngine119(io=_SilentIO())
        engine.case.main_category = "救護"
        engine._apply_extracted_fields({
            "fire_level_signals": ["有人受困"],
            "fire_level": 3,
        })
        self.assertIsNone(engine.case.fire_level)

        engine.case.main_category = "火警"
        engine.case.sub_category = "機車"
        engine.case.fire_level = 2
        engine._apply_extracted_fields({
            "fire_level_signals": ["無煙"],
            "fire_level": 1,
        })
        self.assertEqual(engine.case.fire_level, 2)
        self.assertFalse(hasattr(engine.case, "fire_level_signals"))

        engine._apply_extracted_fields({"fire_level_signals": ["有人受困", "亂寫"]})
        self.assertEqual(engine.case.fire_level, 3)

    def test_subtype_floor_raises_a_zero_level(self) -> None:
        case = CaseInfo119(main_category="火警", sub_category="化學、毒劑交通工具")

        raise_fire_level(case)

        self.assertEqual(case.fire_level, 3)

    def test_summary_omits_unset_and_zero(self) -> None:
        unset = CaseInfo119(main_category="火警", sub_category="透天厝", fire_level=0)
        raised = CaseInfo119(main_category="火警", sub_category="透天厝", fire_level=2)

        self.assertNotIn("fire_level", unset.filled_fields_for_summary())
        self.assertEqual(raised.filled_fields_for_summary()["fire_level"], 2)


if __name__ == "__main__":
    unittest.main()
