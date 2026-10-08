"""追問「之幾」之後，門牌子號與樓層的組合。

2026-10-06 8d211dc0 那通：報案人說「25號之23樓」，追問「25號之幾呢？」
答「之二。13樓。」，覆誦卻唸成「25號之二二23樓」；答「是」之後又變成
「25號二二二23樓」、門牌的「之二」整個掉了。原因是重組地址時從整串找
樓層，把子號的「二」連同「23樓」當成樓層；答案裡的「13樓」也沒被採用。
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from location_validation_119 import JurisdictionResult
from sop_119_engine import SopEngine119
from sop_utils_119 import compose_street_address
from tests.test_address_mapper_119 import ScriptedIO, run_address_flow


class ComposeFloorTests(unittest.TestCase):
    def test_sub_number_digit_is_not_taken_as_floor(self) -> None:
        """「25號之二23樓」重組後樓層是「23樓」，不是「二23樓」。"""
        self.assertEqual(
            compose_street_address(
                "永和區", "環河西路2段", "25號之二",
                existing="永和區環河西路2段25號之二23樓",
            ),
            "永和區環河西路2段25號之二23樓",
        )

    def test_rebuild_twice_is_stable(self) -> None:
        """同一個地址重組兩次結果不變（舊做法每次多一個「二」）。"""
        once = compose_street_address(
            "永和區", "環河西路2段", "25號之二",
            existing="永和區環河西路2段25號之二23樓",
        )
        twice = compose_street_address(
            "永和區", "環河西路2段", "25號之二", existing=once,
        )
        self.assertEqual(once, twice)


class ConfirmedSubFlowTests(unittest.TestCase):
    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "永和分局"),
    )
    def test_answer_with_floor_replaces_old_floor(self, _query) -> None:
        """答「之二。13樓。」→ 門牌補上之二、樓層改用答案的 13 樓；答「是」後不變。"""
        io = ScriptedIO(["永和區環河西路2段25號之23樓。", "之二。13樓。", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.address, "永和區環河西路2段25號之二13樓")
        self.assertEqual(engine.case.address_number, "25號之二")
        self.assertIn("25號之二13樓", io.questions[2])
        self.assertTrue(engine.case.address_confirmed)

    def test_answer_without_floor_keeps_old_split(self) -> None:
        """只答「之十二」時照舊：用子號把糊在一起的「十二三樓」切回「三樓」。"""
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.address = "板橋區文化路51號十二三樓"
        engine.case.address_number = "51號"

        engine._apply_confirmed_sub("之十二")

        self.assertEqual(engine.case.address, "板橋區文化路51號之十二三樓")
        self.assertEqual(engine.case.address_number, "51號之十二")


if __name__ == "__main__":
    unittest.main()
