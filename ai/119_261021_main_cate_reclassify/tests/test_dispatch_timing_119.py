"""
派車那句（「XX 已派出了喔」）講的時間點。

承辦的受理順序：主案類、次案類都確定了才講派車。所以：
  - 地址確認後只講「已確認地址。」，不講派車
  - 救護：次案類判斷完才講「救護車已派出了喔。」
  - 火警：案類分析完（決定垂片）才講「消防車已派出了喔。」
  - 緊急救援：還不判斷次案類，問完發生什麼事才講「救援人員已派出了喔。」
  - 派車整通只講一次；地址沒確認成功就不講（跟改之前一樣）
  - 轉人工、問姓名電話、救護次案類的觸發回應都不再提派車

這裡的模型、LLM、地址驗證 API 都是假的，不會連到線上服務：
每一句回答要抽出什麼欄位，都由測試事先指定。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fire_tab_map_119 import TAB_A, TAB_A_QUESTIONS, TRAPPED_YES
from handlers import _REGISTRY
from handlers.火警通用 import HuoJingGenericHandler
from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler
from location_validation_119 import JurisdictionResult
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

AMBULANCE_LINE = "救護車已派出了喔。"
FIRE_TRUCK_LINE = "消防車已派出了喔。"
RESCUE_LINE = "救援人員已派出了喔。"
ADDRESS_CONFIRMED_LINE = "已確認地址。"
ADDRESS = "新北市板橋區府中路32號3樓"
ADDRESS_FIELDS = {
    "address": ADDRESS, "location_type": "address",
    "address_district": "板橋區", "address_road": "府中路",
    "address_number": "32號", "address_floor": "3樓",
}


class StopCall(Exception):
    """測試準備的回答用完了：只想看到某一句為止，後面的流程不跑。"""


class ScriptedIO(DialogueIO):
    """依序回答；把 AI 說的話和報案人的回答照順序記下來。"""

    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.lines: list[tuple[str, str]] = []

    @property
    def ai_lines(self) -> list[str]:
        return [text for who, text in self.lines if who == "AI"]

    def say(self, text: str) -> None:
        self.lines.append(("AI", text))

    def hear_text(self) -> str:
        if not self.answers:
            raise StopCall
        text = self.answers.pop(0)
        self.lines.append(("報案人", text))
        return text


class FakeMainClassifier:
    """主案類一律很有把握地判成救護。"""

    def predict(self, text):
        return {"main_category": "救護", "main_conf": 0.99,
                "main_probs": {"救護": 0.99, "火警": 0.01}}


class FakeSubClassifier:
    """次案類模型：一律很有把握地判成指定的次案類（用來測沒有關鍵字直接命中的情況）。"""

    def __init__(self, label: str):
        self.label = label

    def predict(self, text, main_cat):
        import types
        return types.SimpleNamespace(
            final_label=self.label, classifier_conf=0.95,
            all_probs={self.label: 0.95, "急病": 0.03},
        )


class FakeLLM:
    """每句回答只抽事先指定的欄位；其他功能一律回空。"""

    def __init__(self, extracted: dict[str, dict]):
        self.extracted = extracted

    def extract_general_fields(self, caller_text, question=None, **_):
        return dict(self.extracted.get((caller_text or "").strip(), {}))

    def extract_caller_info(self, question, text, include_address=False):
        return dict(self.extracted.get((text or "").strip(), {}))

    def generate_summary(self, transcript_texts, filled_fields):
        return "測試摘要"

    def __getattr__(self, name):
        def _empty(*args, **kwargs):
            return {}
        return _empty


def _fake_address_api(address, **_):
    return JurisdictionResult(True, "板橋分局")


def _run_call(steps: list[tuple[str, dict]], sub_classifier=None) -> tuple[SopEngine119, ScriptedIO]:
    """從「119 您好」開始跑一整通電話。steps：(報案人回答, 假 LLM 抽出的欄位)。"""
    io = ScriptedIO([text for text, _ in steps])
    engine = SopEngine119(
        io=io,
        main_classifier=FakeMainClassifier(),
        sub_classifiers=sub_classifier,
        llm_extractor=FakeLLM({text: fields for text, fields in steps}),  # type: ignore[arg-type]
    )
    with patch("sop_119_engine.query_jurisdiction", _fake_address_api):
        try:
            engine._run_main_flow()
        except StopCall:
            pass
    return engine, io


# 一通燒炭電話（第一句就講出燒炭，關鍵字直接定次案類），依被問的順序排。
# 燒炭照 xlsx 題目表問（見 test_ems_shaotan_119）；第一句已經講出是朋友，報案身分不再問。
SHAO_TAN_CALL = [
    ("我朋友在房間燒炭，快叫救護車",
     {"incident_description": "朋友在房間燒炭", "caller_relation": "朋友"}),
    (ADDRESS, ADDRESS_FIELDS),
    ("對", {}),
    ("我在現場", {"caller_location": "在現場"}),
    ("炭盆我已經拿出去了，熄了", {"charcoal_status": "已滅火"}),
    ("我把他拖出來了", {"patient_location": "已在外面"}),
    ("男生，大概三十歲", {"patient_gender": "男性", "patient_age": "30歲"}),
    ("他現在醒著，可以講話", {"consciousness_level": "意識清醒"}),
    ("我叫王小明，0912345678", {"caller_name": "王小明", "caller_contact": "0912345678"}),
]


class AnnounceDispatchTests(unittest.TestCase):
    """派車那句的共用函式 _announce_dispatch。"""

    def _engine(self, *, address_confirmed: bool) -> tuple[SopEngine119, ScriptedIO]:
        io = ScriptedIO([])
        engine = SopEngine119(io=io)
        engine.case.address_confirmed = address_confirmed
        return engine, io

    def test_only_said_once(self) -> None:
        """中途換次案類、換垂片會再呼叫一次，不能重講。"""
        engine, io = self._engine(address_confirmed=True)
        engine._announce_dispatch(AMBULANCE_LINE)
        engine._announce_dispatch(AMBULANCE_LINE)
        self.assertEqual(io.ai_lines, [AMBULANCE_LINE])

    def test_not_said_when_address_not_confirmed(self) -> None:
        """地址沒確認成功就不講（跟改之前一樣）。"""
        engine, io = self._engine(address_confirmed=False)
        engine._announce_dispatch(AMBULANCE_LINE)
        self.assertEqual(io.ai_lines, [])
        self.assertFalse(engine._dispatch_announced)


class RescueCallTests(unittest.TestCase):
    """救護：整通電話跑一次，看派車講在哪裡。"""

    def test_shao_tan_full_call_order(self) -> None:
        engine, io = _run_call(SHAO_TAN_CALL)
        lines = io.ai_lines
        self.assertEqual(engine.case.sub_category, "燒炭")
        self.assertEqual(engine.case.result, "dispatched")
        # 地址確認那句只講地址，緊接著（次案類已由第一句的關鍵字確定）講派車
        confirmed = lines.index(ADDRESS_CONFIRMED_LINE)
        self.assertEqual(lines[confirmed + 1], AMBULANCE_LINE)
        # 派車整通只講一次，而且在燒炭的第一題之前
        self.assertEqual(lines.count(AMBULANCE_LINE), 1)
        self.assertLess(lines.index(AMBULANCE_LINE), lines.index("您現在人還在現場嗎？"))
        # 其他句子都不再提派車
        others = [line for line in lines if line != AMBULANCE_LINE]
        self.assertFalse([line for line in others if "已派出" in line or "已經派" in line])
        self.assertIn("請問你的姓名與聯繫方式？", lines)

    def test_dispatch_after_asking_what_happened(self) -> None:
        """第一句沒講出次案類：先問發生什麼狀況、判斷完次案類，才講派車。"""
        engine, io = _run_call(
            [
                ("我要叫救護車", {}),
                (ADDRESS, ADDRESS_FIELDS),
                ("對", {}),
                ("我爸突然倒在路邊叫不太醒", {"incident_description": "父親倒在路邊叫不太醒"}),
            ],
            sub_classifier=FakeSubClassifier("路倒"),
        )
        lines = io.ai_lines
        asked = lines.index("請問現場發生什麼狀況？")
        self.assertLess(lines.index(ADDRESS_CONFIRMED_LINE), asked)
        self.assertGreater(lines.index(AMBULANCE_LINE), asked)
        self.assertEqual(engine.case.sub_category, "路倒")


class FireTests(unittest.TestCase):
    """火警：案類分析完才講派車。"""

    def _fire_engine(self, answers: list[str], **prefilled) -> tuple[SopEngine119, ScriptedIO]:
        io = ScriptedIO(answers)
        engine = SopEngine119(io=io, llm_extractor=FakeLLM({}))  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        engine.case.address_confirmed = True
        engine.case.fire_tab = TAB_A  # 已經知道是建築物火警
        for key, value in prefilled.items():
            setattr(engine.case, key, value)
        return engine, io

    def test_dispatch_before_first_tab_question(self) -> None:
        engine, io = self._fire_engine([])
        with self.assertRaises(StopCall):
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.ai_lines, [FIRE_TRUCK_LINE, TAB_A_QUESTIONS[0].question])

    def test_trapped_before_analysis_no_dispatch_claim(self) -> None:
        """報地址時就講出有人受困：立刻轉人工，不說消防車已派出。"""
        engine, io = self._fire_engine([], trapped_status=TRAPPED_YES)
        with self.assertRaises(TransferToHumanError):
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.ai_lines, ["請不要掛斷電話，我馬上幫您轉給專人。"])


class EmergencyRescueTests(unittest.TestCase):
    """緊急救援：問完發生什麼事才講派車；問姓名電話不提派車。"""

    def _engine(self, answers: list[str], **prefilled) -> tuple[SopEngine119, ScriptedIO]:
        io = ScriptedIO(answers)
        engine = SopEngine119(io=io)
        engine.case.main_category = "緊急救援"
        engine.case.address_confirmed = True
        for key, value in prefilled.items():
            setattr(engine.case, key, value)
        return engine, io

    def test_incident_known_dispatch_right_away(self) -> None:
        engine, io = self._engine([], incident_description="有人被困在電梯")
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.ai_lines, [RESCUE_LINE])

    def test_ask_incident_then_dispatch(self) -> None:
        engine, io = self._engine(["電梯卡住，裡面有人"])
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.ai_lines, ["請問發生什麼事情。", RESCUE_LINE])

    def test_caller_info_question_no_dispatch(self) -> None:
        engine, io = self._engine(["我叫王小明"], caller_name="王小明")
        JinJiJiuYuanGenericHandler().collect_caller_info(engine)
        self.assertEqual(io.ai_lines[0], "請問你的姓名與聯繫方式？")


class NoDispatchClaimElsewhereTests(unittest.TestCase):
    """轉人工、救護次案類的觸發回應都不再提派車。"""

    def test_ohca_transfer_line(self) -> None:
        io = ScriptedIO([])
        engine = SopEngine119(io=io)
        with self.assertRaises(TransferToHumanError):
            engine._check_ohca_and_transfer(False, "breathing")
        self.assertEqual(io.ai_lines, ["請不要掛斷電話，我立即為您轉接專人。"])

    def test_trigger_responses_never_say_dispatched(self) -> None:
        """還有觸發情境的救護 handler，每個情境都跑一次，回應裡不能有派車。
        照 OK 表重寫的次案類（例如燒炭）已經沒有觸發情境，跳過。"""
        for name, handler in _REGISTRY.items():
            if not hasattr(handler, "_send_trigger_responses"):
                continue
            for scenario_id in range(1, 13):
                with self.subTest(handler=name, scenario=scenario_id):
                    io = ScriptedIO(["不知道"] * 10)
                    engine = SopEngine119(io=io)
                    engine.case.main_category = "救護"
                    engine.case.sub_category = name
                    try:
                        handler._send_trigger_responses(scenario_id, engine)
                    except (StopCall, TransferToHumanError):
                        pass
                    said = [line for line in io.ai_lines if "已派出" in line or "已經派" in line]
                    self.assertEqual(said, [])


if __name__ == "__main__":
    unittest.main()
