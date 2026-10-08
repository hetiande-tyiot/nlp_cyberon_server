"""
救護追問（例如「是不是有明顯外傷、大出血？外觀是否變形？」）回答後，engine 不可卡死。

背景：2026-10-08 通話 abb1fa2f（墜落傷）報案人回答「欸有明顯。」後 AI 再也不回話，
最後報案人掛斷、整通案件 json 沒寫出來。原因是 handler 在已經拿著 engine._case_lock
的狀態下，又呼叫 engine._is_field_filled()，而它內部要再拿同一把鎖；
這把鎖（threading.Lock）不能重複拿，engine 執行緒就自己等自己、永遠停住。
墜落傷、一般受傷、吞食藥物、精神異常四個 handler 都有同樣寫法。

本測試在另一條執行緒裡跑追問，5 秒內沒跑完就判定為卡死，
避免測試本身被卡住；同時確認回答的傷勢有寫進案件。

執行：
  cd ai/119_0904_addrflow && python -m unittest tests.test_trigger_question_no_deadlock_119 -v
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock

from sop_119_engine import DialogueIO, SopEngine119
from handlers.墜落傷 import ZhuiLuoShangHandler
from handlers.一般受傷 import GeneralInjuryHandler
from handlers.吞食藥物 import TunShiYaoWuHandler
from handlers.精神異常 import JingShenYiChangHandler


class SilentIO(DialogueIO):
    def say(self, text: str) -> None:
        pass

    def hear_text(self) -> str:
        raise AssertionError("本測試不應該向報案人要回答")


_QUESTION = "是不是有明顯外傷、大出血？外觀是否變形？"
_ANSWER = "欸有明顯。"


class TriggerQuestionNoDeadlockTests(unittest.TestCase):

    def _engine(self) -> SopEngine119:
        engine = SopEngine119(io=SilentIO(), main_classifier=None,
                              sub_classifiers=None, llm_extractor=None)
        engine.case.main_category = "救護"
        # 報案人的回答直接給定，不經過一般欄位抽取（那段與本問題無關）。
        engine._ask_and_extract = lambda question: _ANSWER  # type: ignore[method-assign]
        # 假的 LLM：把回答抽成一段傷勢文字（這正是會走進鎖內那段程式的情況）。
        engine._llm = MagicMock()
        engine._llm.extract_slots.return_value = {"injury_severity": "有明顯外傷"}
        return engine

    def _run_with_timeout(self, handler, engine: SopEngine119) -> None:
        def run() -> None:
            handler._ask_trigger_question(
                _QUESTION, "injury_severity",
                schema={"injury_severity": "string|null"},
                rules="- injury_severity：傷勢描述",
                engine=engine,
            )

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(
            worker.is_alive(),
            f"{type(handler).__name__} 追問後卡住超過 5 秒（engine._case_lock 死結）",
        )

    def test_each_handler_finishes_and_saves_injury(self) -> None:
        for handler_cls in (ZhuiLuoShangHandler, GeneralInjuryHandler,
                            TunShiYaoWuHandler, JingShenYiChangHandler):
            with self.subTest(handler=handler_cls.__name__):
                engine = self._engine()
                self._run_with_timeout(handler_cls(), engine)
                self.assertEqual(engine.case.injury_severity, "有明顯外傷")


if __name__ == "__main__":
    unittest.main()
