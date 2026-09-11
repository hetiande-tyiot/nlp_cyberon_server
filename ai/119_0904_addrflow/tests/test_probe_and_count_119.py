"""
C 探問後續的兩項資料品質修補。

背景（見 90642da6，吞身心科藥自殺案，C 探問成功切到吞食藥物）：
  修1：C 探問問句列了「吃錯藥/吃太多藥/中毒」示範詞，抽取器把問句示範當答案灌進
       collapse_cause → _reset_probe_question_echo 偵測回聲並還原。
  修2：非外傷案（急病/吞食藥物…）人數題不再問「幾個人受傷」（會被答成 0 人、與患者
       性別年齡矛盾），改中性問法。

執行：
  cd ai/119_0904_addrflow && python -m unittest tests.test_probe_and_count_119 -v
"""

from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace

from handlers.base import SubCategoryHandler


class _FakeEngine:
    def __init__(self, **case_kw):
        self.case = SimpleNamespace(
            collapse_cause=case_kw.get("collapse_cause"),
            sub_category=case_kw.get("sub_category"),
            incident_description=case_kw.get("incident_description"),
        )
        self._case_lock = threading.Lock()
        self.updates = 0

    def _notify_case_update(self) -> None:
        self.updates += 1

    def _debug_print(self, *a) -> None:
        pass


_PROBE_Q = "知道是什麼原因嗎？有沒有可能吃錯藥、吃太多藥、或是中毒？"


class ResetProbeEchoTests(unittest.TestCase):
    """修1：collapse_cause 若只是探問問句的回聲 → 還原。"""

    def test_question_echo_is_reset(self) -> None:
        h = SubCategoryHandler()
        eng = _FakeEngine(collapse_cause="吃錯藥、吃太多藥、或是中毒")
        h._reset_probe_question_echo(eng, _PROBE_Q, None)
        self.assertIsNone(eng.case.collapse_cause)
        self.assertGreaterEqual(eng.updates, 1)

    def test_partial_question_echo_is_reset(self) -> None:
        h = SubCategoryHandler()
        eng = _FakeEngine(collapse_cause="吃太多藥")
        h._reset_probe_question_echo(eng, _PROBE_Q, None)
        self.assertIsNone(eng.case.collapse_cause)

    def test_real_answer_is_kept(self) -> None:
        h = SubCategoryHandler()
        eng = _FakeEngine(collapse_cause="吞了整排身心科的藥")
        h._reset_probe_question_echo(eng, _PROBE_Q, None)
        self.assertEqual(eng.case.collapse_cause, "吞了整排身心科的藥")

    def test_unchanged_value_is_left_alone(self) -> None:
        h = SubCategoryHandler()
        eng = _FakeEngine(collapse_cause="原本就有的原因")
        h._reset_probe_question_echo(eng, _PROBE_Q, "原本就有的原因")
        self.assertEqual(eng.case.collapse_cause, "原本就有的原因")
        self.assertEqual(eng.updates, 0)


class PatientCountQuestionTests(unittest.TestCase):
    """修2：非外傷案人數題改中性問法。"""

    def test_trauma_subcats_ask_injury_count(self) -> None:
        h = SubCategoryHandler()
        for sub in ("一般受傷", "打架受傷", "車禍", "墜落傷", "燒燙傷"):
            with self.subTest(sub=sub):
                eng = _FakeEngine(sub_category=sub)
                self.assertEqual(
                    h._patient_count_question(eng), "現場有幾個人受傷？"
                )

    def test_non_trauma_subcats_ask_neutral_count(self) -> None:
        h = SubCategoryHandler()
        for sub in ("吞食藥物", "急病", "精神異常", "路倒", None):
            with self.subTest(sub=sub):
                eng = _FakeEngine(sub_category=sub)
                self.assertEqual(
                    h._patient_count_question(eng), "現場有幾位需要救護？"
                )


class IncidentVagueTests(unittest.TestCase):
    """Fix2：急病含糊病情判定（含糊 → 仍問 S0 逼出細類）。"""

    def test_vague_incidents(self) -> None:
        h = SubCategoryHandler()
        for inc in ("有人身體不舒服", "身體不適", "", "不太舒服", None):
            with self.subTest(inc=inc):
                self.assertTrue(h._incident_is_vague(_FakeEngine(incident_description=inc)))

    def test_specific_incidents_not_vague(self) -> None:
        h = SubCategoryHandler()
        for inc in ("手被熱水燙傷", "快要生了", "他吞了很多安眠藥", "胸口很痛喘不過氣", "從三樓摔下來"):
            with self.subTest(inc=inc):
                self.assertFalse(h._incident_is_vague(_FakeEngine(incident_description=inc)))


if __name__ == "__main__":
    unittest.main()
