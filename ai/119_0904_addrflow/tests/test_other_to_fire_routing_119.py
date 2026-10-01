"""
主案類模型把明確的火警判成「其他案類」時，第一句話已經明確有火 → 直接進火警，不追問。

背景：主案類 BERT 會把「有機車燒起來」「這邊有火燒車」判成其他案類，
系統就先問「請問現場有沒有人受傷、身體不適，或是有火、有人受困需要救護或消防？」，
報案人答「有火」才進火警，多問了一題。
規則：用原本追問後判斷答案的同一個判斷（救護優先），改成在追問前先看第一句話；
結果是火警才跳過追問。同時講到有人受傷、或跟火無關的，照舊先追問。

這裡的主案類模型是假的（固定回傳其他案類），也不載入 LLM。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sop_119_engine import DialogueIO, SopEngine119

CLARIFY_Q = "請問現場有沒有人受傷、身體不適，或是有火、有人受困需要救護或消防？"


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
    """固定判成其他案類（信心夠高，不會觸發主案類的重問）。"""

    def predict(self, text: str):
        return {
            "main_category": "其他案類",
            "main_conf": 0.95,
            "main_probs": {"其他案類": 0.95, "火警": 0.03},
        }


def _run(answers: list[str]):
    io = ScriptedIO(answers)
    engine = SopEngine119(io=io, main_classifier=FakeMainClf(),
                          sub_classifiers=None, llm_extractor=None)
    with patch.object(engine, "_run_火警") as run_fire, \
            patch.object(engine, "_run_救護") as run_rescue:
        engine._run_main_flow()
    return engine, io, run_fire, run_rescue


class FireOpeningSkipsClarifyTests(unittest.TestCase):

    def test_clear_fire_openings_go_straight_to_fire(self) -> None:
        for opening in ("有機車燒起來", "這邊有火燒車", "那邊失火了", "報火災 摩托車相撞起火"):
            with self.subTest(opening=opening):
                engine, io, run_fire, run_rescue = _run([opening])
                self.assertEqual(engine.case.main_category, "火警")
                self.assertNotIn(CLARIFY_Q, io.messages)
                run_fire.assert_called_once()
                run_rescue.assert_not_called()


class NonFireStillClarifiesTests(unittest.TestCase):
    """跟火無關、或同時有人受傷的，維持原本的做法：先追問。"""

    def test_car_crash_with_injury_and_smoke_goes_to_rescue_not_fire(self) -> None:
        # 「車禍」是明確救護關鍵詞：原本的 E1 會在追問之前就直接改派救護，不會進火警
        engine, io, run_fire, run_rescue = _run(["車禍有人受傷，車子冒煙"])
        self.assertEqual(engine.case.main_category, "救護")
        run_rescue.assert_called_once()
        run_fire.assert_not_called()

    def test_fight_still_asks(self) -> None:
        engine, io, run_fire, run_rescue = _run(["有人打架", "沒有人受傷"])
        self.assertIn(CLARIFY_Q, io.messages)
        run_fire.assert_not_called()

    def test_negated_fire_still_asks(self) -> None:
        engine, io, run_fire, run_rescue = _run(["沒有火，是有人在吵架", "沒有"])
        self.assertIn(CLARIFY_Q, io.messages)
        run_fire.assert_not_called()

    def test_clarify_answer_with_fire_still_routes_to_fire(self) -> None:
        # 第一句話看不出是火警 → 照樣追問，追問答案有火才進火警（原本的行為）
        engine, io, run_fire, run_rescue = _run(["我要報案", "有東西燒起來了"])
        self.assertIn(CLARIFY_Q, io.messages)
        self.assertEqual(engine.case.main_category, "火警")
        run_fire.assert_called_once()


if __name__ == "__main__":
    unittest.main()
