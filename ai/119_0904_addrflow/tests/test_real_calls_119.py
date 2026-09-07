"""以真實通話為資料的地址測試（2026-09-04 新增）。

資料來源 `tests/data/real_calls_119.json`，由
`scripts/build_real_call_fixture.py` 從 `log_119/case119_*.json` 產生。
每筆都對應一起真實事故或一種真實的報案講法。

三層斷言，都刻意避開「問句順序」：
  1. 原話 → 地址元件（不受流程影響）
  2. 組出的地址 → addrCheck 判定（用快照離線回放）
  3. 流程健全性（不崩、不超預算、已鎖地址不被改寫）

⚠️ 不斷言「完整流程的最終 status」：報案人的回答序列固定、問句會隨版本變，
兩者錯位會讓報案人回答「哪一區」的那句被當成對覆誦的回答，測出來的
status 是錯位造成的假回歸。
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from location_validation_119 import JurisdictionResult
from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import (
    build_address_ask_questions,
    build_street_address,
    extract_street_address_components,
    is_usable_address,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "real_calls_119.json")


def load_fixture() -> dict:
    with open(FIXTURE, encoding="utf-8") as handle:
        return json.load(handle)


class ScriptedIO(DialogueIO):
    def __init__(self, answers):
        self.answers = list(answers)
        self.questions = []

    def say(self, text):
        self.questions.append(text)

    def hear_text(self):
        return self.answers.pop(0) if self.answers else "不知道"


class RealCallComponentTests(unittest.TestCase):
    """第一層：報案人原話 → 地址元件。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()

    def test_fixture_is_present(self) -> None:
        self.assertTrue(self.fixture["cases"], "fixture 沒有案例")
        self.assertTrue(self.fixture["api_snapshots"], "fixture 沒有 API 快照")

    def test_components_match_expectation(self) -> None:
        for case in self.fixture["cases"]:
            for row in case["utterances"]:
                with self.subTest(case=case["id"], text=row["text"][:24]):
                    parts = extract_street_address_components(row["text"])
                    self.assertEqual(
                        parts.get("address_district"),
                        row["expect_district"],
                        f'{case["note"]}｜區',
                    )
                    self.assertEqual(
                        parts.get("address_road"),
                        row["expect_road"],
                        f'{case["note"]}｜路',
                    )
                    self.assertEqual(
                        parts.get("address_number"),
                        row["expect_number"],
                        f'{case["note"]}｜號',
                    )

    def test_narrative_lines_yield_no_address(self) -> None:
        """派遣後的閒聊不得被當成地址（三項期望皆 None 的那些句子）。"""
        checked = 0
        for case in self.fixture["cases"]:
            for row in case["utterances"]:
                if any((row["expect_district"], row["expect_road"],
                        row["expect_number"])):
                    continue
                checked += 1
                with self.subTest(text=row["text"][:24]):
                    parts = extract_street_address_components(row["text"])
                    self.assertFalse(
                        parts,
                        f'不該從敘述句抽出地址元件：{parts}',
                    )
        self.assertGreater(checked, 0, "fixture 應含敘述句樣本")


class RealCallApiSnapshotTests(unittest.TestCase):
    """第二層：組出的地址 → addrCheck 判定（離線回放快照）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshots = load_fixture()["api_snapshots"]

    def test_known_valid_addresses(self) -> None:
        for address in (
            "新北市五股區明德路12巷28號",
            "蘆洲區長安街31號",
            "土城區中央路3段61巷2號",
            "新北市瑞芳區明里路14號",
            "新北市新莊區中港路648巷6號",
            "新北市板橋區國光路31巷11號",
            "新北市板橋區光武街136巷8弄16號",
            "新北市中和區景平路431巷27號",
        ):
            with self.subTest(address=address):
                self.assertTrue(
                    self.snapshots[address]["valid"],
                    f"{address} 應為有效地址（快照過期可重跑產生腳本）",
                )

    def test_known_invalid_addresses(self) -> None:
        expected = {
            "新北市三重區正義南路12號": "road_only",
            "土城區亞洲路3號": "road_only",
            "板橋區大華街2號": "road_only",
            "土城區中央路3段二十六11巷2號": "not_found",
            # 汐止沒有後德路（API 建議福德路）、淡水沒有明德路
            "汐止區後德路18號": "not_found",
            "淡水區明德路18號": "not_found",
        }
        for address, reason in expected.items():
            with self.subTest(address=address):
                snap = self.snapshots[address]
                self.assertFalse(snap["valid"])
                self.assertEqual(snap["reason"], reason)

    def test_first_spoken_address_of_0902_was_valid_all_along(self) -> None:
        """09-02 事故的核心：報案人第一次講的地址本來就是有效的。"""
        self.assertTrue(self.snapshots["土城區中央路3段61巷2號"]["valid"])
        self.assertFalse(
            self.snapshots["土城區中央路3段二十六11巷2號"]["valid"]
        )


class RealCallFlowTests(unittest.TestCase):
    """第三層：流程健全性（不看 status，只看不崩／不失控／不被改寫）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()

    def _replay(self, answers, snapshots):
        def fake_jurisdiction(address, **_kwargs):
            snap = snapshots.get(address)
            if snap is None:
                return JurisdictionResult(False, api_reason="not_found")
            return JurisdictionResult(
                snap["valid"], error=snap["hint"], api_reason=snap["reason"]
            )

        io = ScriptedIO(answers)
        engine = SopEngine119(io=io)
        with patch("sop_119_engine.query_jurisdiction", fake_jurisdiction):
            engine._run_address_flow(
                stage_ask="replay_ask",
                stage_confirm="replay_confirm",
                dispatch_line="已確認地址，救護車已派出了喔。",
                ask_questions=build_address_ask_questions(flow="救護"),
            )
        return engine, io

    def test_every_case_completes_within_budget(self) -> None:
        snapshots = self.fixture["api_snapshots"]
        for case in self.fixture["cases"]:
            answers = [row["text"] for row in case["utterances"]]
            with self.subTest(case=case["id"]):
                engine, _io = self._replay(answers, snapshots)
                self.assertLessEqual(
                    engine._address_asks_used,
                    engine._ADDRESS_ASK_BUDGET,
                    case["note"],
                )

    def test_dispatched_address_survives_later_narrative(self) -> None:
        """地址定案後，通話後段的敘述句不得改寫它。"""
        narratives = [
            row["text"]
            for case in self.fixture["cases"]
            for row in case["utterances"]
            if not any((row["expect_district"], row["expect_road"],
                        row["expect_number"]))
        ]
        self.assertTrue(narratives, "fixture 應含敘述句樣本")

        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.address = "五股區明德路12巷28號"
        engine.case.location_type = "address"
        engine.case.address_district = "五股區"
        engine.case.address_road = "明德路12巷"
        engine.case.address_number = "28號"
        engine._address_locked = True

        for text in narratives:
            engine._apply_location_rules(text)
            self.assertEqual(engine.case.address, "五股區明德路12巷28號", text)

    def test_no_whole_utterance_becomes_address(self) -> None:
        """整段話（含案情描述）不得成為 case.address。"""
        for case in self.fixture["cases"]:
            for row in case["utterances"]:
                if len(row["text"]) < 45:
                    continue
                with self.subTest(text=row["text"][:24]):
                    self.assertFalse(
                        is_usable_address(row["text"]),
                        "整段話不該被當成可用地址",
                    )


class LaneAlleyFromRealCallsTests(unittest.TestCase):
    """巷弄要在第一次就抽到——報案人講話有停頓，STT 轉成標點。

    2026-09-06 00:33 實測：「光武街。136巷。8弄16號」原本只抽到「光武街」，
    覆誦唸成「光武街16號」，報案人連講三次才被接住（12 句 AI 發話）。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()

    def test_lane_captured_despite_punctuation(self) -> None:
        expectations = {
            "那個欸光武街，啊，那個板橋區光武街。136巷。8弄16號。": "光武街136巷8弄",
            "五股區明德路。12巷28號這個地址。": "明德路12巷",
        }
        for case in self.fixture["cases"]:
            for row in case["utterances"]:
                want = expectations.get(row["text"])
                if not want:
                    continue
                with self.subTest(text=row["text"][:24]):
                    parts = extract_street_address_components(row["text"])
                    self.assertEqual(parts.get("address_road"), want)

    def test_punctuation_does_not_glue_unrelated_text(self) -> None:
        """反面：只有「路名↔段/巷/弄」之間的標點可以去掉。

        第一版做成「全部去標點」，把地標描述和路名連成一個候選
        （蘆洲成功國小旁邊長安街），由這批真實通話的 fixture 抓到。
        """
        from sop_utils_119 import extract_address_road

        cases = {
            "那個。蘆洲成功國小旁邊。長安街。三十一三十一。好。": "長安街",
            "光武街。我家在16號": "光武街",
            "中山路。旁邊的3巷": "中山路",
        }
        for text, want in cases.items():
            with self.subTest(text=text[:20]):
                self.assertEqual(extract_address_road(text), want)


class RealCallRebuildTests(unittest.TestCase):
    """元件重建出的地址要能對上 API 快照。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = load_fixture()

    def test_0902_first_utterance_rebuilds_to_valid_address(self) -> None:
        text = "欸我住在那個辦土城區中央路3段61巷2號4樓。"
        parts = extract_street_address_components(text)
        rebuilt = build_street_address(
            parts.get("address_district"),
            parts.get("address_road"),
            parts.get("address_number"),
            existing=text,
        )
        self.assertEqual(rebuilt, "土城區中央路3段61巷2號4樓")
        # 去掉樓層後即為 API 快照裡的有效地址
        self.assertTrue(
            self.fixture["api_snapshots"]["土城區中央路3段61巷2號"]["valid"]
        )

    def test_city_filler_does_not_pollute_rebuild(self) -> None:
        text = "嗯，在那個新北市五股區明德路12巷28號"
        parts = extract_street_address_components(text)
        rebuilt = build_street_address(
            parts.get("address_district"),
            parts.get("address_road"),
            parts.get("address_number"),
            existing=text,
        )
        self.assertEqual(rebuilt, "新北市五股區明德路12巷28號")
        self.assertTrue(self.fixture["api_snapshots"][rebuilt]["valid"])


if __name__ == "__main__":
    unittest.main()
