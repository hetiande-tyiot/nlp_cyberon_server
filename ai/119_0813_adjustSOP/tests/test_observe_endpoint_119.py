"""
tests/test_observe_endpoint_119.py

覆蓋 POST /session/{id}/observe（轉真人後續聽對話、只更新 case_summary）。

重點守四件事：
  1. session 已 done 仍可呼叫（不回 409）——AI 自己判斷轉真人時引擎就結束了
  2. 真人受理員（role="agent"）講的話真的會進到摘要輸入裡
  3. 連續多句只會觸發少數幾次 LLM（節流有效）
  4. /observe 不會把 session 設成 done / closed（否則 SSE 會提早關掉）
"""

from __future__ import annotations

import os
import threading
import time
import unittest

# 必須在 import sop_api_server 之前設好：避免測試去載 GGUF / BERT，
# 並把節流間隔縮到毫秒級讓測試跑得完。
os.environ.setdefault("GGUF_MODEL_PATH", "/nonexistent")
os.environ.setdefault("ENABLE_MAIN_CLASSIFIER", "0")
os.environ.setdefault("ENABLE_SUB_CLASSIFIER", "0")
os.environ.setdefault("OBSERVE_DEBOUNCE_S", "0.2")
os.environ.setdefault("OBSERVE_MIN_INTERVAL_S", "0.3")
os.environ.setdefault("OBSERVE_GRACE_S", "0.5")
os.environ.setdefault("OBSERVE_IDLE_CLOSE_S", "1.0")

import sop_api_server as api  # noqa: E402
from case_info_119 import CaseInfo119  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from llm_extractor_119 import format_transcript_for_report  # noqa: E402


class FakeSummaryLLM:
    """只實作 generate_summary，記下每次拿到的逐字稿。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._lock = threading.Lock()

    def generate_summary(self, transcript_texts: list[str], filled_fields: dict) -> str:
        with self._lock:
            self.calls.append(list(transcript_texts))
            n = len(self.calls)
        return f"摘要第{n}版：現場情況已由真人受理員接手釐清中。"


class FakeEngine:
    """只提供 /observe 會用到的三個東西：case、_case_lock、_llm。"""

    def __init__(self, llm=None) -> None:
        self.case = CaseInfo119()
        self._case_lock = threading.Lock()
        self._llm = llm


def _make_session(llm=None, *, done: bool = False) -> api.Session:
    sess = api.Session("11111111-2222-3333-4444-555555555555")
    sess.engine = FakeEngine(llm)
    sess.case = sess.engine.case
    if done:
        sess.done.set()
    with api._sessions_lock:
        api._sessions[sess.sess_id] = sess
    return sess


class ObserveEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._sessions: list[api.Session] = []

    def tearDown(self) -> None:
        for sess in self._sessions:
            sess.closed.set()
            sess.summary_dirty.set()
            with api._sessions_lock:
                api._sessions.pop(sess.sess_id, None)

    def _session(self, llm=None, *, done: bool = False) -> api.Session:
        sess = _make_session(llm, done=done)
        self._sessions.append(sess)
        return sess

    # ── 1. done 之後仍可呼叫 ──────────────────────────────────────────────

    def test_observe_accepted_after_session_done(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)

        resp = api.observe_session(
            sess.sess_id,
            api.ObservePayload(text="病患現在還有呼吸嗎？", role="agent"),
        )

        self.assertTrue(resp["accepted"])
        self.assertEqual(resp["transcript_size"], 1)

    def test_observe_does_not_end_session(self) -> None:
        sess = self._session(FakeSummaryLLM())

        api.observe_session(
            sess.sess_id, api.ObservePayload(text="有，會喘", role="caller")
        )

        self.assertFalse(sess.done.is_set())
        self.assertFalse(sess.closed.is_set())

    # ── 2. transcript 與參數驗證 ─────────────────────────────────────────

    def test_observe_appends_both_roles_to_transcript(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)

        api.observe_session(
            sess.sess_id, api.ObservePayload(text="請問是幾樓？", role="agent")
        )
        api.observe_session(
            sess.sess_id, api.ObservePayload(text="中山路三十二號五樓", role="caller")
        )

        self.assertEqual(
            sess.engine.case.transcript,
            [
                {"role": "agent", "text": "請問是幾樓？"},
                {"role": "caller", "text": "中山路三十二號五樓"},
            ],
        )

    def test_observe_rejects_unknown_role(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)

        with self.assertRaises(HTTPException) as ctx:
            api.observe_session(
                sess.sess_id, api.ObservePayload(text="嗨", role="assistant")
            )

        self.assertEqual(ctx.exception.status_code, 400)

    def test_observe_unknown_session_is_404(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            api.observe_session(
                "no-such-session", api.ObservePayload(text="嗨", role="caller")
            )

        self.assertEqual(ctx.exception.status_code, 404)

    # ── 3. 摘要取材：真人受理員的話必須進得去 ────────────────────────────

    def test_summary_input_includes_agent_speech(self) -> None:
        llm = FakeSummaryLLM()
        sess = self._session(llm, done=True)
        api.observe_session(
            sess.sess_id, api.ObservePayload(text="患者意識清楚嗎？", role="agent")
        )
        api.observe_session(
            sess.sess_id, api.ObservePayload(text="叫他有反應", role="caller")
        )

        api._flush_summary(sess)

        self.assertEqual(len(llm.calls), 1)
        self.assertIn("真人受理員：患者意識清楚嗎？", llm.calls[0])
        self.assertIn("報警人：叫他有反應", llm.calls[0])
        self.assertTrue(sess.engine.case.case_summary.startswith("摘要第1版"))

    def test_summary_lines_are_truncated_to_max_turns(self) -> None:
        case = CaseInfo119()
        for i in range(10):
            case.transcript.append({"role": "agent", "text": f"第{i}句"})

        lines = api._transcript_lines_for_summary(case, max_turns=3)

        self.assertEqual(
            lines, ["真人受理員：第7句", "真人受理員：第8句", "真人受理員：第9句"]
        )

    def test_summary_lines_skip_empty_and_unknown_roles(self) -> None:
        case = CaseInfo119()
        case.transcript.extend(
            [
                {"role": "assistant", "text": "119 您好"},
                {"role": "caller", "text": "   "},
                {"role": "system", "text": "內部訊息"},
                {"role": "agent", "text": "我接手了"},
            ]
        )

        lines = api._transcript_lines_for_summary(case, max_turns=0)

        self.assertEqual(lines, ["受理員：119 您好", "真人受理員：我接手了"])

    def test_fallback_never_quotes_assistant_or_agent_lines(self) -> None:
        """沒欄位可用時規則備援會拿「最後一句」——那句必須是報警人講的。"""
        sess = self._session(None, done=True)
        api.observe_session(
            sess.sess_id, api.ObservePayload(text="樓下有濃煙", role="caller")
        )
        api.observe_session(
            sess.sess_id, api.ObservePayload(text="請問是幾樓？", role="agent")
        )

        api._flush_summary(sess)

        summary = sess.engine.case.case_summary
        self.assertIn("樓下有濃煙", summary)
        self.assertNotIn("請問是幾樓", summary)
        self.assertNotIn("真人受理員", summary)

    def test_summary_falls_back_to_rules_without_llm(self) -> None:
        sess = self._session(None, done=True)
        sess.engine.case.address = "板橋區中山路32號"
        api.observe_session(
            sess.sess_id, api.ObservePayload(text="有人昏倒", role="caller")
        )

        api._flush_summary(sess)

        self.assertIn("板橋區中山路32號", sess.engine.case.case_summary)

    # ── 4. 背景 worker 與節流 ────────────────────────────────────────────

    def test_worker_coalesces_burst_of_utterances(self) -> None:
        llm = FakeSummaryLLM()
        sess = self._session(llm, done=True)

        for i in range(5):
            api.observe_session(
                sess.sess_id, api.ObservePayload(text=f"第{i}句話", role="caller")
            )

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not llm.calls:
            time.sleep(0.05)
        time.sleep(0.6)

        self.assertGreaterEqual(len(llm.calls), 1)
        self.assertLess(len(llm.calls), 5, "5 句話不該觸發 5 次 LLM（節流失效）")
        self.assertIn("報警人：第4句話", llm.calls[-1])

    def test_worker_starts_only_once(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)

        api.observe_session(sess.sess_id, api.ObservePayload(text="一", role="caller"))
        first = sess.summary_worker
        api.observe_session(sess.sess_id, api.ObservePayload(text="二", role="caller"))

        self.assertIs(sess.summary_worker, first)

    # ── 5. SSE 收線時機 ──────────────────────────────────────────────────

    def test_stream_stays_open_when_engine_done_but_not_hung_up(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)

        self.assertFalse(api._stream_should_close(sess, done_seen_at=time.monotonic()))

    def test_stream_closes_on_hangup(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)
        sess.closed.set()

        self.assertTrue(api._stream_should_close(sess, done_seen_at=None))

    def test_stream_closes_after_grace_when_no_observe_arrives(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)
        stale = time.monotonic() - (api.OBSERVE_GRACE_S + 1.0)

        self.assertTrue(api._stream_should_close(sess, done_seen_at=stale))

    def test_stream_survives_grace_once_observing(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)
        stale = time.monotonic() - (api.OBSERVE_GRACE_S + 1.0)
        sess.last_observe_at = time.monotonic()

        self.assertFalse(api._stream_should_close(sess, done_seen_at=stale))

    def test_stream_closes_after_idle_limit_while_observing(self) -> None:
        sess = self._session(FakeSummaryLLM(), done=True)
        sess.last_observe_at = time.monotonic() - (api.OBSERVE_IDLE_CLOSE_S + 1.0)

        self.assertTrue(
            api._stream_should_close(sess, done_seen_at=time.monotonic())
        )


class TranscriptReportTests(unittest.TestCase):
    def test_report_formatter_keeps_agent_turns(self) -> None:
        text = format_transcript_for_report(
            [
                {"role": "assistant", "text": "119 您好"},
                {"role": "caller", "text": "有人昏倒"},
                {"role": "agent", "text": "我是受理員，請問地址"},
            ]
        )

        self.assertIn("真人受理員：我是受理員，請問地址", text)


if __name__ == "__main__":
    unittest.main()
