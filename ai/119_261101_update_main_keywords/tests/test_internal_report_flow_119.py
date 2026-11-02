from __future__ import annotations

import re
import unittest

from sop_119_engine import DialogueIO, SopEngine119


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


class InternalReportExtractor:
    def __init__(self):
        self.general_calls: list[tuple[str, str | None]] = []

    def extract_general_fields(
        self,
        caller_text: str,
        question: str | None = None,
        *,
        main_category: str | None = None,
        call_type: str | None = None,
    ) -> dict:
        self.general_calls.append((caller_text, question))
        text = caller_text.strip()
        question = question or ""
        out: dict = {}

        if "分隊回報" in text:
            out["call_type"] = "局內回報"
        if any(word in text for word in ("現場狀況", "現場回報", "回報案情")):
            out["report_request_type"] = "現場回報"
        if any(word in text for word in ("支援", "要車", "增派", "加派")):
            out["report_request_type"] = "支援請求"
        if "完整地址" in question and "號" in text:
            out["address"] = text
        if "回報的內容" in question:
            out["field_report_content"] = text

        vehicle_match = re.search(r"(\d+)\s*台\s*([^，。,\s]+車)", text)
        if vehicle_match:
            out["support_vehicle_count"] = int(vehicle_match.group(1))
            out["support_vehicle_type"] = vehicle_match.group(2)
        if "是否要" in question:
            if any(word in text for word in ("不是", "不對", "有誤")):
                out["support_request_confirmed"] = False
            elif text in ("是", "對", "正確", "沒錯"):
                out["support_request_confirmed"] = True
        if "其他需要" in question or "其他需要中心協助" in question:
            if any(word in text for word in ("沒有", "不用", "沒了")):
                out["has_additional_request"] = False
            elif text.startswith("有"):
                out["has_additional_request"] = True
        return out

    def extract_address(
        self,
        caller_text: str,
        use_question: bool = False,
        include_floor: bool = True,
    ) -> dict:
        return {}

    def generate_summary(self, transcript_texts: list[str], filled_fields: dict) -> str:
        return "局內回報測試摘要"


class InternalReportFlowTests(unittest.TestCase):
    def test_ordinary_incident_does_not_enter_internal_report_flow(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._apply_extracted_fields({"call_type": "一般案件"})

        self.assertFalse(engine._is_internal_report("有人受傷，需要救護車"))

    def test_field_report_is_detected_recorded_and_closed(self) -> None:
        io = ScriptedIO([
            "板橋分隊回報",
            "我要回報現場狀況",
            "新北市板橋區文化路100號",
            "現場火勢已撲滅，無人受傷",
            "沒有其他需求",
        ])
        llm = InternalReportExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]

        engine.run()

        self.assertEqual(engine.case.main_category, "局內回報")
        self.assertEqual(engine.case.report_request_type, "現場回報")
        self.assertEqual(engine.case.field_report_content, "現場火勢已撲滅，無人受傷")
        self.assertEqual(engine.case.result, "report_recorded")
        self.assertEqual(engine.case.flow_stage, "completed")
        self.assertIn("收到，為您記錄。", io.messages)
        self.assertIn("好的，已為您記錄，謝謝回報。", io.messages)
        self.assertFalse(io.answers)
        # 首輪分類為局內回報後，會以局內 schema 補抽一次。
        self.assertEqual(len(llm.general_calls), 6)

    def test_support_request_reasks_after_correction_then_dispatches(self) -> None:
        io = ScriptedIO([
            "中和分隊回報",
            "現場需要支援車輛",
            "新北市中和區中正路200號",
            "2台救護車",
            "不是，要3台消防車",
            "3台消防車",
            "是",
            "沒有",
        ])
        llm = InternalReportExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]

        engine.run()

        self.assertEqual(engine.case.report_request_type, "支援請求")
        self.assertEqual(engine.case.support_vehicle_count, 3)
        self.assertEqual(engine.case.support_vehicle_type, "消防車")
        self.assertIs(engine.case.support_request_confirmed, True)
        self.assertEqual(engine.case.result, "support_dispatched")
        self.assertEqual(
            io.messages.count("現場需要什麼車？幾台？"),
            2,
        )
        self.assertIn("好的，中心將為您派遣 3 台 消防車。", io.messages)
        self.assertFalse(io.answers)

    def test_additional_request_is_reclassified_in_same_call(self) -> None:
        io = ScriptedIO([
            "新店分隊回報",
            "先回報現場狀況",
            "新北市新店區北新路300號",
            "現場已完成疏散",
            "有，還要2台救護車支援",
            "新北市新店區北新路300號",
            "2台救護車",
            "是",
            "沒有",
        ])
        llm = InternalReportExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]

        engine.run()

        self.assertEqual(engine.case.report_request_type, "支援請求")
        self.assertEqual(engine.case.support_vehicle_count, 2)
        self.assertEqual(engine.case.support_vehicle_type, "救護車")
        self.assertEqual(engine.case.result, "support_dispatched")
        self.assertIn("收到，為您記錄。", io.messages)
        self.assertIn("好的，中心將為您派遣 2 台 救護車。", io.messages)
        self.assertFalse(io.answers)


if __name__ == "__main__":
    unittest.main()
