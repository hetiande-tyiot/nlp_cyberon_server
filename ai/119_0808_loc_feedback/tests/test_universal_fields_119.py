from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from case_info_119 import CaseInfo119
from important_tags_119 import (
    IMPORTANT_TAGS,
    match_important_tags,
    merge_important_tags,
    normalize_important_tags,
)
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, SopEngine119


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)

    def say(self, text: str) -> None:
        pass

    def hear_text(self) -> str:
        return self.answers.pop(0)


class FakeExtractor:
    def __init__(self, outputs: list[dict]):
        self.outputs = list(outputs)
        self.general_calls: list[tuple[str, str | None]] = []

    def extract_general_fields(
        self,
        caller_text: str,
        question: str | None = None,
    ) -> dict:
        self.general_calls.append((caller_text, question))
        return self.outputs.pop(0)

    def extract_address(self, caller_text: str, use_question: bool = False) -> dict:
        return {}

    def generate_summary(self, transcript_texts: list[str], filled_fields: dict) -> str:
        return "測試摘要"


class UniversalFieldTests(unittest.TestCase):
    def test_defaults_and_exact_serialized_keys(self) -> None:
        case = CaseInfo119()

        data = case.to_dict()

        self.assertEqual(data["ImportantCase"], 0)
        self.assertEqual(data["ImportantTag"], [])
        self.assertIsNone(data["NeedPolice"])
        self.assertIsNone(data["call_type"])
        self.assertIsNone(data["report_request_type"])
        self.assertIsNone(data["support_vehicle_count"])
        self.assertIsNone(data["fire_category"])
        self.assertIsNone(data["people_trapped"])
        self.assertIsNone(data["caller_salutation"])
        self.assertNotIn("important_case", data)
        self.assertFalse(case.is_field_filled("ImportantCase"))
        self.assertFalse(case.is_field_filled("ImportantTag"))

    def test_all_configured_tags_match_and_unknown_tags_are_rejected(self) -> None:
        text = "，".join(IMPORTANT_TAGS)

        self.assertEqual(match_important_tags(text), list(IMPORTANT_TAGS))
        self.assertEqual(
            normalize_important_tags(["持刀", "未知標籤", "持刀", "槍聲"]),
            ["持刀", "槍聲"],
        )

    def test_tag_merge_appends_in_turn_order_without_duplicates(self) -> None:
        merged = merge_important_tags(["持刀"], ["槍聲", "持刀", "砍人"])

        self.assertEqual(merged, ["持刀", "槍聲", "砍人"])

    def test_engine_updates_from_new_evidence_and_ignores_nulls(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._apply_extracted_fields({
            "ImportantCase": 2,
            "ImportantTag": ["持刀"],
            "NeedPolice": True,
        })
        engine._apply_extracted_fields({
            "ImportantCase": None,
            "ImportantTag": None,
            "NeedPolice": None,
        })
        self.assertEqual(engine.case.ImportantCase, 2)
        self.assertIs(engine.case.NeedPolice, True)

        engine._apply_extracted_fields({
            "ImportantCase": 1,
            "ImportantTag": ["持刀", "賭博"],
            "NeedPolice": False,
        })

        # ImportantCase 可依本輪明確證據降級（更正誤聽的關鍵詞）
        self.assertEqual(engine.case.ImportantCase, 1)
        self.assertEqual(engine.case.ImportantTag, ["持刀", "賭博"])
        self.assertIs(engine.case.NeedPolice, False)

    def test_important_case_accepts_upgrade_and_downgrade(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))

        engine._apply_extracted_fields({"ImportantCase": 1})
        self.assertEqual(engine.case.ImportantCase, 1)

        engine._apply_extracted_fields({"ImportantCase": 2})
        self.assertEqual(engine.case.ImportantCase, 2)

        # 更正誤聽關鍵詞時必須能降回來
        engine._apply_extracted_fields({"ImportantCase": 1})
        self.assertEqual(engine.case.ImportantCase, 1)
        engine._apply_extracted_fields({"ImportantCase": 0})
        self.assertEqual(engine.case.ImportantCase, 0)

    def test_important_case_rejects_bool_and_out_of_range(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._apply_extracted_fields({"ImportantCase": 2})

        # True 在 Python 中等於 1，若無 bool 防護會被誤當成「一般」降級
        engine._apply_extracted_fields({"ImportantCase": True})
        self.assertEqual(engine.case.ImportantCase, 2)

        engine._apply_extracted_fields({"ImportantCase": 3})
        self.assertEqual(engine.case.ImportantCase, 2)

    def test_internal_report_fields_accept_explicit_corrections(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._apply_extracted_fields({
            "call_type": "局內回報",
            "report_request_type": "支援請求",
            "support_vehicle_type": "救護車",
            "support_vehicle_count": 2,
            "support_request_confirmed": False,
        })
        engine._apply_extracted_fields({
            "call_type": "一般案件",
            "support_vehicle_type": "消防車",
            "support_vehicle_count": 3,
            "support_request_confirmed": True,
        })

        self.assertEqual(engine.case.call_type, "局內回報")
        self.assertEqual(engine.case.support_vehicle_type, "消防車")
        self.assertEqual(engine.case.support_vehicle_count, 3)
        self.assertIs(engine.case.support_request_confirmed, True)

    def test_every_answer_runs_general_extraction_and_updates_fields(self) -> None:
        llm = FakeExtractor([
            {
                "ImportantCase": 2,
                "ImportantTag": ["持刀"],
                "NeedPolice": True,
            },
            {
                "ImportantCase": 1,
                "ImportantTag": ["賭博"],
                "NeedPolice": False,
            },
        ])
        engine = SopEngine119(
            io=ScriptedIO([
                "有人持刀，要幫我報警",
                "更正，不是持刀，只是賭博",
            ]),
            llm_extractor=llm,  # type: ignore[arg-type]
        )

        engine._ask_and_extract("發生什麼事？")
        engine._ask_and_extract("還有其他情況嗎？")

        self.assertEqual(len(llm.general_calls), 2)
        self.assertEqual(engine.case.ImportantCase, 1)
        self.assertEqual(engine.case.ImportantTag, ["持刀", "賭博"])
        self.assertIs(engine.case.NeedPolice, False)

    def test_llm_general_field_postprocessing_enforces_types_and_whitelist(self) -> None:
        extractor = LLMExtractor119.__new__(LLMExtractor119)

        def extract_slots(_text, schema, _rules, **_kwargs):
            if "ImportantCase" in schema:
                return {
                    "ImportantCase": "2",
                    "ImportantTag": ["持刀", "未知標籤", "槍聲", "持刀"],
                    "NeedPolice": "true",
                }
            if "caller_salutation" in schema:
                return {"caller_salutation": "先生"}
            if "fire_category" in schema:
                return {
                    "fire_category": "建築物",
                    "people_trapped": "false",
                    "fire_spread": "true",
                    "road_type": "不適用",
                }
            if "call_type" in schema:
                return {
                    "call_type": "局內回報",
                    "report_request_type": "支援請求",
                    "support_vehicle_type": "救護車",
                    "support_vehicle_count": "2",
                    "support_request_confirmed": "true",
                    "has_additional_request": "false",
                }
            return {}

        extractor.extract_slots = MagicMock(side_effect=extract_slots)
        extractor.extract_patient_info = MagicMock(return_value={})

        result = extractor.extract_general_fields(
            "現場有人持刀，聽到槍聲，需要救護車",
            question="請問發生什麼事？",
        )

        self.assertEqual(result["ImportantCase"], 2)
        self.assertEqual(result["ImportantTag"], ["持刀", "槍聲"])
        self.assertIs(result["NeedPolice"], True)
        self.assertEqual(result["caller_salutation"], "先生")
        self.assertEqual(result["fire_category"], "建築物")
        self.assertIs(result["people_trapped"], False)
        self.assertIs(result["fire_spread"], True)
        self.assertNotIn("road_type", result)
        self.assertEqual(result["call_type"], "局內回報")
        self.assertEqual(result["report_request_type"], "支援請求")
        self.assertEqual(result["support_vehicle_type"], "救護車")
        self.assertEqual(result["support_vehicle_count"], 2)
        self.assertIs(result["support_request_confirmed"], True)
        self.assertIs(result["has_additional_request"], False)


if __name__ == "__main__":
    unittest.main()
