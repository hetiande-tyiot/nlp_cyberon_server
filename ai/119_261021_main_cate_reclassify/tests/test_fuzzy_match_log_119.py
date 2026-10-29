"""模糊比對取樣的測試（2026-09-04 新增）。

地址判斷有兩處猜測都沒有可靠門檻——addrCheck 的地標比對（API 端）與
address_mapper 的行政區音近比對（本地，門檻 0.6 是估的）。
取樣的目的是累積「報案人到底接不接受這個猜測」，作為日後調參依據。
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from fuzzy_match_log_119 import (
    KIND_DISTRICT,
    KIND_LANDMARK,
    OUTCOME_CONFIRMED,
    OUTCOME_DENIED,
    OUTCOME_UNCONFIRMED,
    fuzzy_log_path,
    load_samples,
    record_fuzzy_match,
    summarize,
)


class FuzzyLogPathTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("FUZZY_LOG_PATH", None)
        os.environ.pop("LOG_DIR", None)

    def test_explicit_path_wins(self) -> None:
        os.environ["FUZZY_LOG_PATH"] = "/tmp/somewhere/fz.jsonl"
        self.assertEqual(fuzzy_log_path(), "/tmp/somewhere/fz.jsonl")

    def test_defaults_next_to_case_logs(self) -> None:
        """與 case JSON 同目錄，時間戳才能對照回完整通話。"""
        os.environ["LOG_DIR"] = "/tmp/logdir"
        self.assertEqual(fuzzy_log_path(), "/tmp/logdir/fuzzy_matches.jsonl")

    def test_disabled_when_no_env(self) -> None:
        """沒設任何輸出位置就停用取樣，不寫死路徑。

        否則跑測試會把測試資料混進正式樣本，而那份樣本是要拿來調
        API 門檻的，混進假資料就失去分析價值。
        """
        self.assertIsNone(fuzzy_log_path())
        self.assertFalse(record_fuzzy_match(KIND_DISTRICT, spoken="X"))


class RecordAndLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "fuzzy_matches.jsonl")
        os.environ["FUZZY_LOG_PATH"] = self.path

    def tearDown(self) -> None:
        os.environ.pop("FUZZY_LOG_PATH", None)
        self._tmp.cleanup()

    def test_record_writes_one_json_line(self) -> None:
        self.assertTrue(record_fuzzy_match(
            KIND_LANDMARK,
            spoken="捷運頂埔站出口1",
            matched="捷運新埔站",
            resolved="新北市板橋區民生路三段2號B1",
            outcome=OUTCOME_DENIED,
            alternatives=["捷運板橋站1號出口"],
            api_hint="（模糊比對）地標比對成功…",
            location_type="mrt",
            session="abcd1234",
        ))
        with open(self.path, encoding="utf-8") as handle:
            lines = handle.read().strip().splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["spoken"], "捷運頂埔站出口1")
        self.assertEqual(row["matched"], "捷運新埔站")
        self.assertEqual(row["outcome"], OUTCOME_DENIED)
        self.assertIn("ts", row)

    def test_raw_hint_is_kept_for_later_reparsing(self) -> None:
        """API 日後改 hint 格式時，舊樣本仍要能重新解析。"""
        record_fuzzy_match(
            KIND_LANDMARK, spoken="X", api_hint="（模糊比對）原始字串"
        )
        self.assertEqual(load_samples()[0]["api_hint"], "（模糊比對）原始字串")

    def test_write_failure_never_raises(self) -> None:
        """取樣是附帶功能，寫不進去也不能影響報案流程。"""
        os.environ["FUZZY_LOG_PATH"] = "/proc/cannot/write/here.jsonl"
        self.assertFalse(record_fuzzy_match(KIND_DISTRICT, spoken="X"))

    def test_corrupt_line_is_skipped(self) -> None:
        record_fuzzy_match(KIND_DISTRICT, spoken="好的那筆")
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write("{壞掉的行\n")
        self.assertEqual(len(load_samples()), 1)

    def test_missing_file_returns_empty(self) -> None:
        os.environ["FUZZY_LOG_PATH"] = os.path.join(self._tmp.name, "nope.jsonl")
        self.assertEqual(load_samples(), [])


class SummarizeTests(unittest.TestCase):
    def test_accept_rate_and_max_denied_score(self) -> None:
        """denied 的最高分是關鍵：門檻至少要拉到它之上才擋得掉已知錯誤。"""
        samples = [
            {"kind": KIND_DISTRICT, "outcome": OUTCOME_CONFIRMED, "score": 0.9},
            {"kind": KIND_DISTRICT, "outcome": OUTCOME_DENIED, "score": 0.62},
            {"kind": KIND_DISTRICT, "outcome": OUTCOME_DENIED, "score": 0.71},
            {"kind": KIND_DISTRICT, "outcome": OUTCOME_UNCONFIRMED},
            {"kind": KIND_LANDMARK, "outcome": OUTCOME_CONFIRMED},
        ]
        result = summarize(samples)
        self.assertEqual(result["total"], 5)
        district = result["by_kind"][KIND_DISTRICT]
        self.assertEqual(district["total"], 4)
        self.assertEqual(district["accept_rate"], round(1 / 3, 3))
        self.assertEqual(district["max_denied_score"], 0.71)
        self.assertIsNone(result["by_kind"][KIND_LANDMARK]["max_denied_score"])

    def test_no_answered_samples_gives_none_rate(self) -> None:
        result = summarize([
            {"kind": KIND_DISTRICT, "outcome": OUTCOME_UNCONFIRMED},
        ])
        self.assertIsNone(result["by_kind"][KIND_DISTRICT]["accept_rate"])

    def test_empty(self) -> None:
        self.assertEqual(summarize([]), {"total": 0, "by_kind": {}})


if __name__ == "__main__":
    unittest.main()
