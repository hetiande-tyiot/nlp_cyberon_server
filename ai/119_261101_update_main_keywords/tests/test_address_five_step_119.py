"""一般門牌地址五步流程的測試（2026-09-04 新增）。

第一步 歷史對話補抽
第二步 缺什麼問什麼（模糊猜測先核對），非建築物不問樓層
第三步 addrCheck 驗證，用 hint 決定下一句問話，只清該重問的元件
第四步 引導式逐級（必問 區→路→號）
第五步 候選與提示回報給受理員，流程繼續
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from address_hint_119 import (
    build_hint_question,
    floor_suppress_reason,
    parse_address_hint,
)
from location_validation_119 import JurisdictionResult
from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import build_address_ask_questions

NEARBY_HINT = (
    "「新北市板橋區大華街2號」查無此門牌；同路段鄰近門牌為 "
    "新北市板橋區大華街1號、新北市板橋區大華街5號、新北市板橋區大華街7號，"
    "請向報案人確認號碼。"
)
SECTION_HINT = "「土城區中央路」分成 一段、二段、三段、四段，請追問是哪一段以及門牌號碼。"
NEED_NUMBER_HINT = "已確認路名「新北市板橋區大華街」，請追問門牌號碼。"
SUGGEST_HINT = "查無「中央路三段二十六」，是否為 新北市土城區中央路？"
MULTI_DISTRICT_HINT = (
    "查無「中央路三段」，是否為 新北市土城區中央路、新北市新店區中央路、"
    "新北市新莊區中央路？"
)
ROAD_UNKNOWN_HINT = "查無「不存在路」這條路，請向報案人重新確認路名。"


class ScriptedIO(DialogueIO):
    """回答用完後一律回「不知道」，讓流程自行收斂而非拋錯。"""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.questions: list[str] = []

    def say(self, text: str) -> None:
        self.questions.append(text)

    def hear_text(self) -> str:
        return self.answers.pop(0) if self.answers else "不知道"


_TMP_FUZZY_LOG: "tempfile.TemporaryDirectory | None" = None


def setUpModule() -> None:
    """模糊比對取樣改寫到臨時檔，別污染正式的 log_119/fuzzy_matches.jsonl。"""
    global _TMP_FUZZY_LOG
    _TMP_FUZZY_LOG = tempfile.TemporaryDirectory()
    os.environ["FUZZY_LOG_PATH"] = os.path.join(
        _TMP_FUZZY_LOG.name, "fuzzy_matches.jsonl"
    )


def tearDownModule() -> None:
    os.environ.pop("FUZZY_LOG_PATH", None)
    if _TMP_FUZZY_LOG is not None:
        _TMP_FUZZY_LOG.cleanup()


def run_address_flow(engine: SopEngine119) -> None:
    engine._run_address_flow(
        stage_ask="救護_location",
        stage_confirm="救護_location_confirm",
        dispatch_line="已確認地址，救護車已派出了喔。",
        ask_questions=build_address_ask_questions(flow="救護"),
    )


class HintParsingTests(unittest.TestCase):
    """hint 是 API 端決定的自然語言，解析失敗必須退回泛用問句。"""

    def test_nearby_numbers(self) -> None:
        advice = parse_address_hint(NEARBY_HINT)
        self.assertEqual(advice.kind, "nearby_numbers")
        self.assertEqual(advice.numbers, ("1號", "5號", "7號"))
        self.assertEqual(
            build_hint_question(advice, spoken_number="2號"),
            "這條路好像沒有2號欸，麻煩再幫我看一下門牌？",
        )

    def test_need_section(self) -> None:
        advice = parse_address_hint(SECTION_HINT)
        self.assertEqual(advice.kind, "need_section")
        self.assertEqual(advice.road, "中央路")
        self.assertIn("哪一段", build_hint_question(advice))

    def test_need_number(self) -> None:
        advice = parse_address_hint(NEED_NUMBER_HINT)
        self.assertEqual(advice.kind, "need_number")
        self.assertEqual(build_hint_question(advice), "請問是幾號？")

    def test_road_suggestions(self) -> None:
        advice = parse_address_hint(SUGGEST_HINT)
        self.assertEqual(advice.kind, "road_suggestions")
        self.assertEqual(advice.suggestions, ("中央路",))

    def test_same_road_in_many_districts_asks_district(self) -> None:
        """同名路分佈多區時該問「哪一區」，不是唸三次同樣的路名。"""
        advice = parse_address_hint(MULTI_DISTRICT_HINT)
        self.assertEqual(advice.kind, "road_in_districts")
        self.assertEqual(advice.districts, ("土城區", "新店區", "新莊區"))
        question = build_hint_question(advice)
        self.assertIn("土城區", question)
        self.assertIn("新店區", question)

    def test_road_unknown(self) -> None:
        self.assertEqual(parse_address_hint(ROAD_UNKNOWN_HINT).kind, "road_unknown")

    def test_unparsable_hint_falls_back(self) -> None:
        for hint in (None, "", "某個以後才會出現的新格式"):
            with self.subTest(hint=hint):
                advice = parse_address_hint(hint)
                self.assertEqual(advice.kind, "generic")
                self.assertFalse(advice.is_parsed)
                self.assertIn("再說一次", build_hint_question(advice))


class FloorSuppressRuleTests(unittest.TestCase):
    """規則表要能直接加一列擴充，不必改流程碼。"""

    class _Case:
        def __init__(self, **kwargs):
            self.location_type = None
            self.non_building_fire = None
            for key, value in kwargs.items():
                setattr(self, key, value)

    def test_non_building_location_types(self) -> None:
        for location_type in ("intersection", "highway", "mrt"):
            with self.subTest(location_type=location_type):
                case = self._Case(location_type=location_type)
                self.assertEqual(floor_suppress_reason(case), "非建築地點型態")

    def test_fire_non_building(self) -> None:
        case = self._Case(non_building_fire=0)
        self.assertEqual(floor_suppress_reason(case), "火警非建築物")

    def test_landmark_still_asks_floor(self) -> None:
        """地標多為大樓、醫院，仍需要樓層。"""
        self.assertIsNone(floor_suppress_reason(self._Case(location_type="landmark")))

    def test_extra_rule_can_be_appended(self) -> None:
        case = self._Case(location_type="address")
        extra = (("工地", lambda c: True),)
        self.assertEqual(floor_suppress_reason(case, extra_rules=extra), "工地")


class HintDrivenReaskTests(unittest.TestCase):
    @patch("sop_119_engine.query_jurisdiction")
    def test_wrong_number_keeps_district_and_road(self, query) -> None:
        """第三步核心：門牌號錯只重問號，已驗證的區和路不清掉。

        09-04 事故就是只有門牌號錯，卻要報案人整段重報。
        """
        query.side_effect = [
            JurisdictionResult(False, error=NEARBY_HINT, api_reason="road_only"),
            JurisdictionResult(True, "板橋分局"),
        ]
        io = ScriptedIO(["板橋區大華街2號", "5號", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertEqual(engine.case.address_district, "板橋區")
        self.assertEqual(engine.case.address_road, "大華街")
        self.assertTrue(
            any("好像沒有2號" in q for q in io.questions),
            io.questions,
        )

    @patch("sop_119_engine.query_jurisdiction")
    def test_generic_retry_when_hint_unparsable(self, query) -> None:
        """hint 格式變了不能弄壞流程，要退回泛用問句。"""
        query.return_value = JurisdictionResult(
            False, error="全新的格式 XYZ", api_reason="not_found"
        )
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertTrue(
            any("再說一次事發地點" in q for q in io.questions), io.questions
        )


class AskBudgetTests(unittest.TestCase):
    @patch("sop_119_engine.query_jurisdiction")
    def test_flow_never_exceeds_ask_budget(self, query) -> None:
        """五步流程疊起來最壞會問二十幾次，必須受總預算約束。"""
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertLessEqual(
            engine._address_asks_used, engine._ADDRESS_ASK_BUDGET
        )


class CandidateAndReportTests(unittest.TestCase):
    @patch("sop_119_engine.query_jurisdiction")
    def test_candidates_survive_reasks(self, query) -> None:
        """候選累積：重問不清空，09-02 那通講對過的地址不該消失。"""
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        io = ScriptedIO(["板橋區大華街2號", "板橋區大華街9號"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        texts = [item["text"] for item in engine._address_candidates]
        self.assertIn("板橋區大華街2號", texts)

    @patch("sop_119_engine.query_jurisdiction")
    def test_failure_report_carries_candidates_and_hint(self, query) -> None:
        """第五步：受理員要看到報案人講過什麼，不只一句失敗原因。"""
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        reason = engine.case.address_error_reason or ""
        self.assertIn("查無此門牌", reason)
        self.assertIn("報案人講過", reason)
        self.assertIn("板橋區大華街2號", reason)
        self.assertIn("系統提示", reason)
        self.assertEqual(engine.case.ImportantCase, 1)
        self.assertIn("地址搜尋失敗", engine.case.ImportantTag)

    @patch("sop_119_engine.query_jurisdiction")
    def test_guided_failure_restores_address(self, query) -> None:
        """引導式收集失敗要還原地址，別讓受理員接到一片空白。"""
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertTrue(engine.case.address)


if __name__ == "__main__":
    unittest.main()


FUZZY_LANDMARK_HINT = (
    "（模糊比對）地標比對成功（共 5 個相近，已取最相符的）：地標：捷運新埔站 → "
    "新北市板橋區民生路三段2號B1。若不確定請向報案人確認是否為此處，"
    "其他可能：地標：捷運板橋站1號出口、地標：捷運板橋站2號出口。"
)
EXACT_LANDMARK_HINT = "地標比對成功：地標：大觀市場 → 新北市板橋區大觀市場"


class LandmarkFuzzyMatchTests(unittest.TestCase):
    """addrCheck 地標比對沒有相似度門檻，模糊配出來的一律要確認。

    實測：「捷運不存在站出口9」→ 捷運亞東醫院站2號出口（status=true）、
    「未知市場旁邊」→ 市場 → 文山區景隆街2號附近（跨到臺北市）。
    API hint 自己就寫「若不確定請向報案人確認是否為此處」。
    """

    def test_parse_marks_fuzzy(self) -> None:
        from address_hint_119 import parse_landmark_hint

        match = parse_landmark_hint(FUZZY_LANDMARK_HINT)
        self.assertTrue(match.is_fuzzy)
        self.assertEqual(match.matched, "捷運新埔站")
        self.assertEqual(match.resolved, "新北市板橋區民生路三段2號B1")
        self.assertEqual(
            match.alternatives, ("捷運板橋站1號出口", "捷運板橋站2號出口")
        )

    def test_exact_match_is_not_fuzzy(self) -> None:
        from address_hint_119 import parse_landmark_hint

        match = parse_landmark_hint(EXACT_LANDMARK_HINT)
        self.assertFalse(match.is_fuzzy)
        self.assertEqual(match.matched, "大觀市場")

    @patch("sop_119_engine.verify_address_detail")
    def test_fuzzy_landmark_must_be_confirmed(self, verify) -> None:
        verify.return_value = (True, FUZZY_LANDMARK_HINT, "valid")
        io = ScriptedIO(["捷運頂埔站出口1", "對", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertTrue(
            any("是這裡嗎" in q for q in io.questions), io.questions
        )
        self.assertEqual(engine.case.address_validation_status, "valid")

    @patch("sop_119_engine.verify_address_detail")
    def test_denied_fuzzy_landmark_is_not_used(self, verify) -> None:
        """報案人否認就不能採用——這是配錯站直接派過去的防線。"""
        verify.return_value = (True, FUZZY_LANDMARK_HINT, "valid")
        io = ScriptedIO(["捷運頂埔站出口1", "不是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertNotEqual(engine.case.address, "新北市板橋區民生路三段2號B1")
        self.assertFalse(engine.case.address_confirmed)

    @patch("sop_119_engine.verify_address_detail")
    def test_exact_landmark_needs_no_extra_question(self, verify) -> None:
        verify.return_value = (True, EXACT_LANDMARK_HINT, "valid")
        io = ScriptedIO(["大觀市場", "是"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertFalse(
            any("是這裡嗎" in q for q in io.questions), io.questions
        )
        self.assertEqual(engine.case.address_validation_status, "valid")


class BasementFloorTests(unittest.TestCase):
    """地標驗測回的地址常寫成「…2號B1」，地下樓層不可在重建時被丟掉。"""

    def test_basement_floor_survives_rebuild(self) -> None:
        from sop_utils_119 import (
            compose_street_address,
            extract_street_address_components,
        )

        for text in (
            "新北市板橋區民生路三段2號B1",
            "板橋區文化路一段10號b2f",
            "板橋區大華街5號地下2樓",
        ):
            with self.subTest(text=text):
                parts = extract_street_address_components(text)
                rebuilt = compose_street_address(
                    parts.get("address_district"),
                    parts.get("address_road"),
                    parts.get("address_number"),
                    existing=text,
                )
                self.assertEqual(rebuilt, text)


class StubLLM:
    """模擬 LLM extractor，讓五步流程走到 self._llm 不是 None 的分支。

    地址流程的抽取是兩層：規則（regex）先跑，抽不到才叫 LLM。
    不給 llm_extractor 時 `self._llm is None`，engine 裡十處 LLM 分支
    全部跳過——等於只驗證了規則路徑。線上服務 llm_loaded=true，
    走的是這裡模擬的那一半。
    """

    def __init__(self, addresses: dict[str, str] | None = None):
        self.addresses = addresses or {}
        self.address_calls: list[str] = []
        self.confirm_calls: list[str] = []

    def extract_general_fields(self, caller_text, question=None, **_kwargs) -> dict:
        return {}

    def extract_address(self, caller_text, use_question=False, include_floor=True) -> dict:
        self.address_calls.append(caller_text)
        for key, value in self.addresses.items():
            if key in (caller_text or ""):
                return {"address": value}
        return {"address": None}

    def extract_confirmation(self, question, caller_text, current_address) -> dict:
        self.confirm_calls.append(caller_text)
        return {"confirmed": None, "new_address": None}

    def extract_patient_info(self, *_args, **_kwargs) -> dict:
        return {}

    def extract_vital_sign(self, *_args, **_kwargs) -> dict:
        return {}

    def generate_summary(self, *_args, **_kwargs) -> str:
        return ""


class FiveStepWithLLMTests(unittest.TestCase):
    """有 LLM 時的五步流程；純規則版在上面各類別已覆蓋。"""

    @patch("sop_119_engine.query_jurisdiction")
    def test_llm_branch_is_reached(self, query) -> None:
        query.return_value = JurisdictionResult(True, "板橋分局")
        llm = StubLLM({"大華街": "板橋區大華街5號"})
        io = ScriptedIO(["就是那個大華街那邊啦", "是"])
        engine = SopEngine119(io=io, llm_extractor=llm)

        run_address_flow(engine)

        self.assertTrue(llm.address_calls, "應該有走到 LLM 抽取分支")

    @patch("sop_119_engine.query_jurisdiction")
    def test_known_limit_rule_fragment_overwrites_llm_address(self, query) -> None:
        """已知限制（**既有行為，0903 線上版亦同**，非五步流程引入）：

        `_apply_location_rules` 判為 address 型態時，會用規則從本輪原話
        抽出的元件重組地址並覆寫。若規則只抽到路名（沒有區、號），
        組出來的「大華街」會蓋掉 LLM 抽到的完整「板橋區大華街5號」。

        真實影響取決於 LLM 是否比單句 regex 抽得更完整——LLM 有整段對話
        上下文，確實可能。留此測試記錄現況；日後若改成「資訊更少就不覆寫」，
        這裡會紅，屆時改斷言即可。
        """
        query.return_value = JurisdictionResult(True, "板橋分局")
        llm = StubLLM({"大華街": "板橋區大華街5號"})
        io = ScriptedIO(["就是那個大華街那邊啦", "是"])
        engine = SopEngine119(io=io, llm_extractor=llm)

        run_address_flow(engine)

        self.assertEqual(engine.case.address, "大華街")

    @patch("sop_119_engine.query_jurisdiction")
    def test_hint_reask_still_works_with_llm(self, query) -> None:
        """第三步的 hint 導向補問在有 LLM 時仍要正確。"""
        query.side_effect = [
            JurisdictionResult(False, error=NEARBY_HINT, api_reason="road_only"),
            JurisdictionResult(True, "板橋分局"),
        ]
        llm = StubLLM({"大華街2號": "板橋區大華街2號"})
        io = ScriptedIO(["板橋區大華街2號", "5號", "是"])
        engine = SopEngine119(io=io, llm_extractor=llm)

        run_address_flow(engine)

        self.assertTrue(
            any("好像沒有2號" in q for q in io.questions), io.questions
        )
        self.assertEqual(engine.case.address_district, "板橋區")
        self.assertEqual(engine.case.address_road, "大華街")

    @patch("sop_119_engine.query_jurisdiction")
    def test_ask_budget_respected_with_llm(self, query) -> None:
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        engine = SopEngine119(
            io=ScriptedIO(["板橋區大華街2號"]), llm_extractor=StubLLM()
        )

        run_address_flow(engine)

        self.assertLessEqual(
            engine._address_asks_used, engine._ADDRESS_ASK_BUDGET
        )

    @patch("sop_119_engine.verify_address_detail")
    def test_fuzzy_landmark_confirm_with_llm(self, verify) -> None:
        verify.return_value = (True, FUZZY_LANDMARK_HINT, "valid")
        io = ScriptedIO(["捷運頂埔站出口1", "不是"])
        engine = SopEngine119(io=io, llm_extractor=StubLLM())

        run_address_flow(engine)

        self.assertTrue(any("是這裡嗎" in q for q in io.questions), io.questions)
        self.assertNotEqual(engine.case.address, "新北市板橋區民生路三段2號B1")


class UncertainAnswerTests(unittest.TestCase):
    """「不知道」不等於「對」。

    parse_yes_no("不知道") 回 None（既非肯定也非否定）。猜測的確認若採用
    「不是明確否認就當確認」，報案人一句「不知道」就會讓系統把猜測當成事實。
    離線重放 226 通真實通話時，回答用盡後補「不知道」，模糊比對到的地標
    全被當成確認採用——地址攸關派遣，這種模稜兩可一律不採用。
    """

    def test_uncertain_tokens_detected(self) -> None:
        from address_hint_119 import is_uncertain_answer

        for text in ("不知道", "不清楚", "不確定", "沒印象", "不太確定", "我不曉得欸"):
            with self.subTest(text=text):
                self.assertTrue(is_uncertain_answer(text))

    def test_clear_answers_are_not_uncertain(self) -> None:
        from address_hint_119 import is_uncertain_answer

        for text in ("對", "是", "不是", "板橋區", "5號", "", None):
            with self.subTest(text=text):
                self.assertFalse(is_uncertain_answer(text))

    @patch("sop_119_engine.verify_address_detail")
    def test_uncertain_answer_does_not_accept_fuzzy_landmark(self, verify) -> None:
        verify.return_value = (True, FUZZY_LANDMARK_HINT, "valid")
        io = ScriptedIO(["捷運頂埔站出口1", "不知道"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        self.assertNotEqual(engine.case.address, "新北市板橋區民生路三段2號B1")
        self.assertFalse(engine.case.address_confirmed)


class BestCandidateRestoreTests(unittest.TestCase):
    """失敗時要回到資訊最完整的候選。

    hint 導向補問會清掉該重問的元件；補問沒問到時 case.address 會停在
    殘缺狀態。離線重放發現「土城區要走路1段2號」被削成「土城區」，
    19 通如此——候選都累積著，卻沒用上。
    """

    @patch("sop_119_engine.query_jurisdiction")
    def test_failure_keeps_most_complete_candidate(self, query) -> None:
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io)

        run_address_flow(engine)

        # 不該只剩「板橋區」或「大華街」這種被削過的殘骸
        self.assertIn("大華街", engine.case.address or "")
        self.assertIn("板橋區", engine.case.address or "")

    def test_valid_candidate_wins_over_longer_text(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._record_address_candidate("土城區中央路3段61巷2號4樓一直講", source="x")
        engine._record_address_candidate(
            "土城區中央路3段61巷2號", source="y", api_status="valid"
        )
        self.assertEqual(
            engine._best_candidate_address(), "土城區中央路3段61巷2號"
        )


class CandidateComponentMergeTests(unittest.TestCase):
    """hint 導向一次只重問一格，同一地址的元件會散在不同候選。

    真實通話（case119_20260901_142234）：報案人先講「吳鳳路90號」，
    被 API 打回後補「吳鳳路2段」，門牌號那格已被清掉。兩個候選
    merge_address 兩個方向都會丟一邊，得按元件各取最完整。
    """

    def _engine_with(self, texts):
        engine = SopEngine119(io=ScriptedIO([]))
        for text in texts:
            engine._record_address_candidate(text, source="replay")
        return engine

    def test_same_road_components_are_merged(self) -> None:
        engine = self._engine_with(["板橋區吳鳳路90號", "板橋區吳鳳路2段"])
        self.assertEqual(engine._best_candidate_address(), "板橋區吳鳳路2段90號")

    def test_different_addresses_are_not_merged(self) -> None:
        """報案人改報別的地址時硬合併會拼出不存在的門牌。"""
        engine = self._engine_with(["板橋區大華街2號", "土城區中央路5號"])
        self.assertIn(
            engine._best_candidate_address(),
            {"板橋區大華街2號", "土城區中央路5號"},
        )

    def test_different_districts_are_not_merged(self) -> None:
        engine = self._engine_with(["板橋區文化路1號", "中和區文化路2段"])
        self.assertNotIn("2段1號", engine._best_candidate_address() or "")

    def test_api_valid_candidate_wins(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._record_address_candidate("板橋區吳鳳路2段", source="x")
        engine._record_address_candidate(
            "板橋區吳鳳路91號", source="y", api_status="valid"
        )
        self.assertEqual(engine._best_candidate_address(), "板橋區吳鳳路91號")


AMBIGUOUS_HINT = (
    "「重陽路」的 一段、二段、四段 都有 1 號，是不同的地點，"
    "請追問報案人是哪一段。"
)


class AmbiguousSectionTests(unittest.TestCase):
    """reason=ambiguous：同一門牌號在多個路段都存在。

    2026-09-04 20:57 那通查證時發現的第六種 hint 格式。
    不追問段別就會派到錯的路段——API 已經明講該問什麼。
    """

    def test_ambiguous_hint_asks_for_section(self) -> None:
        advice = parse_address_hint(AMBIGUOUS_HINT)
        self.assertEqual(advice.kind, "need_section")
        self.assertEqual(advice.road, "重陽路")
        self.assertEqual(advice.sections, ("一段", "二段", "四段"))
        question = build_hint_question(advice)
        self.assertIn("哪一段", question)
        self.assertIn("重陽路", question)

    def test_ambiguous_reason_has_readable_text(self) -> None:
        from location_validation_119 import addrcheck_failure_reason

        text = addrcheck_failure_reason("ambiguous")
        self.assertIn("段", text)
        self.assertNotIn("管轄", text)

    def test_section_hints_do_not_collide(self) -> None:
        """「分成」與「都有」兩種段別提示都要解析成 need_section。"""
        for hint in (AMBIGUOUS_HINT, SECTION_HINT):
            with self.subTest(hint=hint[:20]):
                self.assertEqual(parse_address_hint(hint).kind, "need_section")


class UnconfirmedButValidTests(unittest.TestCase):
    """API 查無 vs 報案人沒確認，是兩件事。

    2026-09-04 20:55 那通地址其實有效（API 回「地址有效：新北市三重區
    仁愛街283巷28號」），只是覆誦沒得到確認，卻被標成「地址搜尋失敗」，
    受理員會誤以為地址查不到。
    """

    def _fail_with(self, status: str) -> SopEngine119:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.address = "三重區仁愛街283巷28號5樓"
        engine.case.address_validation_status = status
        engine._mark_address_failure("報警人未能明確確認地址")
        return engine

    def test_api_valid_but_unconfirmed(self) -> None:
        engine = self._fail_with("valid")
        self.assertEqual(engine.case.address_validation_status, "valid")
        self.assertIn("地址未確認", engine.case.ImportantTag)
        self.assertNotIn("地址搜尋失敗", engine.case.ImportantTag)
        self.assertFalse(engine.case.address_confirmed)
        self.assertTrue(engine.case.address_suspect_error)

    def test_api_invalid_keeps_search_failure_tag(self) -> None:
        engine = self._fail_with("invalid")
        self.assertEqual(engine.case.address_validation_status, "invalid")
        self.assertIn("地址搜尋失敗", engine.case.ImportantTag)
        self.assertNotIn("地址未確認", engine.case.ImportantTag)


class LLMConsolidateTests(unittest.TestCase):
    """第三步半：規則走不通時讓 LLM 讀整段對話重新判讀。

    離線評測 14 通真實通話（scripts/eval_consolidate_address.py）：
    規則命中 5、LLM 命中 13。規則錯的全是漏掉補述的類型
    （國光路11號缺31巷、橫科路31號缺351巷、大觀路1段4號缺28巷6弄）。

    LLM 不直接定案：輸出送 addrCheck，通過才採用，之後還要覆誦確認。
    """

    class StubConsolidator(StubLLM):
        def __init__(self, address, raise_error=False):
            super().__init__()
            self.address = address
            self.raise_error = raise_error
            self.calls = 0

        def consolidate_address(self, caller_texts, **_kwargs):
            self.calls += 1
            if self.raise_error:
                raise RuntimeError("模型爆炸")
            return {"address": self.address, "confidence": "high",
                    "need_ask": None}

    @staticmethod
    def _api_only_valid_for(good: str):
        """依地址回應，不依呼叫次數——流程的 API 呼叫數會隨版本改變。"""
        def fake(address, **_kwargs):
            if address and good in address:
                return JurisdictionResult(
                    True, "板橋分局", error=f"地址有效：{good}"
                )
            return JurisdictionResult(
                False, error=NEARBY_HINT, api_reason="road_only"
            )
        return fake

    @patch("sop_119_engine.query_jurisdiction")
    def test_llm_result_adopted_when_api_valid(self, query) -> None:
        query.side_effect = self._api_only_valid_for("國光路31巷11號")
        llm = self.StubConsolidator("新北市板橋區國光路31巷11號")
        io = ScriptedIO(["板橋區國光路11號", "是"])
        engine = SopEngine119(io=io, llm_extractor=llm)

        run_address_flow(engine)

        self.assertTrue(llm.calls, "規則失敗後應該叫 LLM")
        self.assertIn("31巷", engine.case.address or "")
        self.assertEqual(engine.case.address_validation_status, "valid")

    @patch("sop_119_engine.query_jurisdiction")
    def test_llm_result_rejected_when_api_invalid(self, query) -> None:
        """LLM 判讀沒通過 addrCheck 就不採用，流程照原本走。"""
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        llm = self.StubConsolidator("板橋區不存在路999號")
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io, llm_extractor=llm)

        run_address_flow(engine)

        self.assertNotIn("不存在路", engine.case.address or "")

    @patch("sop_119_engine.query_jurisdiction")
    def test_llm_failure_does_not_break_flow(self, query) -> None:
        """模型出錯時要安靜退回規則路徑，不能中斷報案。"""
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        llm = self.StubConsolidator(None, raise_error=True)
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io, llm_extractor=llm)

        run_address_flow(engine)   # 不應拋例外
        self.assertTrue(engine.case.address_suspect_error)

    @patch("sop_119_engine.query_jurisdiction")
    def test_no_llm_falls_back_to_guided(self, query) -> None:
        query.return_value = JurisdictionResult(
            False, error=NEARBY_HINT, api_reason="road_only"
        )
        io = ScriptedIO(["板橋區大華街2號"])
        engine = SopEngine119(io=io)          # 沒有 llm_extractor

        run_address_flow(engine)
        self.assertLessEqual(
            engine._address_asks_used, engine._ADDRESS_ASK_BUDGET
        )

    @patch("sop_119_engine.query_jurisdiction")
    def test_consolidation_costs_no_ask_budget(self, query) -> None:
        """LLM 整合不問報案人，不該消耗提問預算。"""
        query.side_effect = self._api_only_valid_for("大華街5號")
        llm = self.StubConsolidator("新北市板橋區大華街5號")
        io = ScriptedIO(["板橋區大華街2號", "是"])
        engine = SopEngine119(io=io, llm_extractor=llm)

        run_address_flow(engine)

        # 整合本身不問話；此處只驗證沒有超出預算，且 LLM 有被呼叫
        self.assertTrue(llm.calls)
        self.assertLessEqual(
            engine._address_asks_used, engine._ADDRESS_ASK_BUDGET
        )
