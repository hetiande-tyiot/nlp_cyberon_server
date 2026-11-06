"""
其他案類的安全網與釐清改派（E1 / E2 / D2）。

背景：BERT 會把明確救護案（吞藥自殺、鬥毆傷…）誤送「其他案類」而靜默轉人工、
不跑任何 SOP。
  E1：命中「明確救護」高貼合關鍵詞 → 直接改派救護（治安模糊的打架除外）。
  E2：其他案類轉出前追問一次，依『答案』（不重跑主 BERT）改派救護/火警/緊急救援。
  D2：補「安眠藥／打起來」等 STT 常見詞，讓關鍵詞比得到。

執行：
  cd ai/119_0904_addrflow && python -m unittest tests.test_other_category_routing_119 -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from sop_119_engine import DialogueIO, SopEngine119
from handlers.base import SubCategoryHandler


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
    """固定回傳同一主類別，模擬 BERT 對某些案型的固執誤判。"""

    def __init__(self, main_category: str, conf: float, *, other_prob: float = 0.2):
        self.main_category = main_category
        self.conf = conf
        self.other_prob = other_prob
        self.calls: list[str] = []

    def predict(self, text: str):
        self.calls.append(text)
        return {
            "main_category": self.main_category,
            "main_conf": self.conf,
            "main_probs": {
                self.main_category: self.conf,
                "救護": self.other_prob,
            },
        }


def _engine(answers: list[str], main_cat: str, conf: float) -> SopEngine119:
    engine = SopEngine119(
        io=ScriptedIO(answers),
        main_classifier=FakeMainClf(main_cat, conf),
        sub_classifiers=None,
        llm_extractor=None,
    )
    return engine


class E1KeywordOverrideTests(unittest.TestCase):
    """E1：明確救護關鍵詞把『其他案類』強制轉回救護。"""

    def test_overdose_suicide_misrouted_to_other_is_forced_to_rescue(self) -> None:
        # conf 0.688 < 0.7 → 觸發一次主追問；重問後 BERT 仍固執其他案類。
        io_answers = ["我女朋友剛剛吞了很多安眠藥", "我剛剛講，我女朋友吞了很多安眠藥"]
        engine = _engine(io_answers, "其他案類", 0.688)

        with patch.object(engine, "_run_救護") as run_rescue:
            engine._run_main_flow()

        self.assertEqual(engine.case.main_category, "救護")
        run_rescue.assert_called_once()

    def test_ambiguous_fight_is_not_forced_by_e1(self) -> None:
        # 「打起來」屬治安模糊子類 → E1 不直接轉救護，維持其他案類交給 E2。
        engine = _engine(["有很多人打起來了"], "其他案類", 0.95)
        # 高信心不追問；攔住 E2 的釐問只驗 E1 沒有直接轉救護。
        with patch.object(engine, "_clarify_other_category", return_value=False):
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "其他案類")

    def test_confident_other_category_still_gets_e1_override(self) -> None:
        # 即使 BERT 高信心（0.95）判其他案類，明確救護詞仍應覆寫（吞藥不追問就轉救護）。
        engine = _engine(["他喝農藥了快來"], "其他案類", 0.95)
        with patch.object(engine, "_run_救護") as run_rescue:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "救護")
        run_rescue.assert_called_once()

    def test_hanging_misrouted_to_emergency_is_forced_to_rescue(self) -> None:
        # 「有人上吊」被 BERT 判成緊急救援（細類空白）→ 自傷類應搶回救護。見 9/10 上吊×2。
        engine = _engine(["有人上吊了快來"], "緊急救援", 0.95)
        with patch.object(engine, "_run_救護") as run_rescue:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "救護")
        run_rescue.assert_called_once()

    def test_genuine_emergency_is_not_stolen_to_rescue(self) -> None:
        # 正牌緊急救援（電梯受困）不含自傷類關鍵詞 → 不應被搶成救護。
        engine = _engine(["有人被困在電梯裡"], "緊急救援", 0.9)
        with patch.object(engine, "_run_緊急救援") as run_emerg:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "緊急救援")
        run_emerg.assert_called_once()

    def test_plain_fall_misrouted_to_emergency_is_forced_to_rescue(self) -> None:
        # 單純墜落（未受困）預設救護墜落傷 → 誤送緊急救援時搶回。
        engine = _engine(["有人從高處墜落受傷了"], "緊急救援", 0.9)
        with patch.object(engine, "_run_救護") as run_rescue:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "救護")
        run_rescue.assert_called_once()

    def test_trapped_fall_stays_emergency(self) -> None:
        # 墜落且卡住/搆不到 → 正牌緊急救援，不搶回救護。
        engine = _engine(["有人墜樓卡在夾層動彈不得"], "緊急救援", 0.9)
        with patch.object(engine, "_run_緊急救援") as run_emerg:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "緊急救援")
        run_emerg.assert_called_once()

    def test_hanging_always_starts_in_rescue_even_if_forced_entry_mentioned(self) -> None:
        # 上吊一律先走救護上吊流程（即使提到破門）；破門→緊急救援是下游 mid-flow 轉換，
        # 不在分類階段判斷。故分類階段仍搶回救護。
        engine = _engine(["有人上吊了門反鎖進不去要破門"], "緊急救援", 0.9)
        with patch.object(engine, "_run_救護") as run_rescue:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "救護")
        run_rescue.assert_called_once()


class E2ClarifyRoutingTests(unittest.TestCase):
    """E2：其他案類轉出前追問一次，依答案改派。"""

    def test_fight_with_injury_in_clarify_routes_to_rescue(self) -> None:
        # 首句純打架（治安模糊）→ 高信心其他案類不追主問 → E2 釐問 → 答有傷 → 救護。
        engine = _engine(["有很多人打起來了", "有啦有人被打傷流血了"], "其他案類", 0.92)
        with patch.object(engine, "_run_救護") as run_rescue:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "救護")
        run_rescue.assert_called_once()
        self.assertTrue(any("有沒有人受傷" in m for m in engine._io.messages))

    def test_fight_without_injury_transfers_to_human(self) -> None:
        # 釐問後報案人明確說沒人受傷 → 維持其他案類、轉人工。
        engine = _engine(["有很多人打起來了", "沒有人受傷啦就是在吵架"], "其他案類", 0.92)
        with patch.object(engine, "_run_救護") as run_rescue:
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "其他案類")
        run_rescue.assert_not_called()
        self.assertTrue(
            any("轉接專人" in m for m in engine._io.messages)
        )
        self.assertEqual(engine.case.result, "dispatched")

    def test_clarify_reveals_fire_routes_to_fire(self) -> None:
        engine = _engine(["這裡怪怪的", "有啦有東西著火了冒好多煙"], "其他案類", 0.92)
        with patch.object(engine, "_run_火警") as run_fire, patch.object(
            engine, "_refresh_fire_subtype_from_bert"
        ):
            engine._run_main_flow()
        self.assertEqual(engine.case.main_category, "火警")
        run_fire.assert_called_once()


class BreakInEscalationTests(unittest.TestCase):
    """上吊流程中發現需破門 → 改判緊急救援、加派消防車（分類階段仍走救護）。"""

    def _eng(self):
        engine = SopEngine119(io=ScriptedIO([]), main_classifier=None,
                              sub_classifiers=None, llm_extractor=None)
        engine.case.main_category = "救護"
        engine.case.sub_category = "上吊"
        engine._sub_reclassify_enabled = True
        return engine

    def test_escalate_flips_main_and_adds_fire_truck(self) -> None:
        engine = self._eng()
        self.assertTrue(engine._escalate_main_to_emergency())
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertTrue(any("消防車" in m for m in engine._io.messages))
        self.assertFalse(engine._sub_reclassify_enabled)  # 改判後停用救護子類重分類
        self.assertFalse(engine._escalate_main_to_emergency())  # 已緊急救援→不重複

    def test_break_in_text_escalates(self) -> None:
        engine = self._eng()
        h = SubCategoryHandler()
        self.assertTrue(h._maybe_escalate_break_in(engine, "他反鎖在裡面進不去，要破門"))
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_negated_or_open_door_does_not_escalate(self) -> None:
        h = SubCategoryHandler()
        for txt in ("門是開的進得去", "沒有反鎖，進得去"):
            engine = self._eng()
            self.assertFalse(h._maybe_escalate_break_in(engine, txt))
            self.assertEqual(engine.case.main_category, "救護")

    def test_llm_vetoes_keyword_false_positive(self) -> None:
        # 關鍵字命中「反鎖」但語意是假設/已解決 → LLM 判 false → 不升級。
        from unittest.mock import MagicMock
        engine = self._eng()
        engine._llm = MagicMock()
        engine._llm.extract_slots.return_value = {"need_break_in": False}
        h = SubCategoryHandler()
        self.assertFalse(h._maybe_escalate_break_in(engine, "我怕他等下反鎖，但現在門是開的"))
        self.assertEqual(engine.case.main_category, "救護")
        engine._llm.extract_slots.assert_called_once()

    def test_llm_confirms_break_in(self) -> None:
        from unittest.mock import MagicMock
        engine = self._eng()
        engine._llm = MagicMock()
        engine._llm.extract_slots.return_value = {"need_break_in": True}
        h = SubCategoryHandler()
        self.assertTrue(h._maybe_escalate_break_in(engine, "他反鎖在房間裡，門打不開"))
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_no_keyword_skips_llm(self) -> None:
        # 沒有破門關鍵字 → 連 LLM 都不呼叫（便宜預篩）。
        from unittest.mock import MagicMock
        engine = self._eng()
        engine._llm = MagicMock()
        h = SubCategoryHandler()
        self.assertFalse(h._maybe_escalate_break_in(engine, "他還吊在上面沒有呼吸"))
        engine._llm.extract_slots.assert_not_called()


if __name__ == "__main__":
    unittest.main()
