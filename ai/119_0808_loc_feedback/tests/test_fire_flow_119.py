from __future__ import annotations

import re
import unittest

from handlers.火警通用 import HuoJingGenericHandler
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


class FireExtractor:
    def __init__(self):
        self.general_calls: list[tuple[str, str | None]] = []

    def extract_general_fields(
        self, caller_text: str, question: str | None = None
    ) -> dict:
        self.general_calls.append((caller_text, question))
        text = caller_text.strip()
        question = question or ""
        out: dict = {}

        if any(word in text for word in ("煙", "烟")):
            out["fire_or_smoke"] = "煙"
        elif "味" in text:
            out["fire_or_smoke"] = "氣味"
        elif "火" in text:
            out["fire_or_smoke"] = "火"
        if "黑煙" in text:
            out["smoke_color"] = "黑煙"
        elif "白煙" in text:
            out["smoke_color"] = "白煙"

        if "什麼在燒" in question or "燃燒標的" in question:
            category_terms = (
                ("工廠", "工廠"),
                ("廠房", "工廠"),
                ("車", "車輛"),
                ("山林", "露天野外"),
                ("雜草", "露天野外"),
                ("垃圾", "露天野外"),
                ("房子", "建築物"),
                ("住宅", "建築物"),
                ("建築物", "建築物"),
            )
            for term, category in category_terms:
                if term in text:
                    out["burning_object"] = term
                    out["fire_category"] = category
                    break

        if any(word in text for word in ("變大", "越来越大", "越來越大")):
            out["fire_trend"] = "變大"
        elif "消退" in text:
            out["fire_trend"] = "消退"
        extent = re.search(r"(約)?([一二三四五六七八九十\d]+坪)", text)
        if extent:
            out["fire_extent"] = extent.group(0)

        if "住戶、鄰居" in question:
            out["caller_position"] = "裡面" if "裡面" in text else "外面"
            if "住戶" in text:
                out["caller_role"] = "住戶"
            elif "鄰居" in text:
                out["caller_role"] = "鄰居"
            elif "路過" in text:
                out["caller_role"] = "路過民眾"

        if "受困" in question or "裡面有沒有人" in question:
            out["people_trapped"] = not any(
                word in text for word in ("沒有", "無人", "没人")
            )
            count = re.search(r"(\d+|[一二三四五六七八九十]+)\s*個?人", text)
            if count:
                out["trapped_count"] = count.group(1)
        if "廠內有沒有人" in question:
            out["factory_people_present"] = not any(
                word in text for word in ("沒有人", "無人", "没人")
            )
        if "總共幾層樓" in question:
            values = re.findall(r"(\d+)\s*樓", text)
            if values:
                out["building_total_floors"] = values[0] + "樓"
            if len(values) > 1:
                out["fire_floor"] = values[1] + "樓"
        if "延燒" in question:
            out["fire_spread"] = "沒有" not in text
            if "連棟" in text:
                out["building_layout"] = "連棟"
            elif "頂樓加蓋" in text:
                out["building_layout"] = "頂樓加蓋"

        if "小型工廠" in question:
            out["factory_scale_type"] = text
        if "化學品或危險物品" in question:
            out["hazardous_materials"] = "無" if "沒有" in text else text

        if "什麼車種" in question:
            out["vehicle_type"] = "小客車" if "小客車" in text else "貨車"
            count = re.search(r"(\d+|一|兩|二|三)\s*台", text)
            if count:
                out["vehicle_count"] = count.group(1) + "台"
        if "車內有沒有人" in question:
            out["vehicle_occupants"] = "沒有" not in text
            count = re.search(r"(\d+|一|兩|二|三)\s*個?人", text)
            if count:
                out["vehicle_occupant_count"] = count.group(1)
        if "一般道路還是高速公路" in question:
            out["road_type"] = "高速公路" if "高速" in text else "一般道路"

        if "燒雜草垃圾、山林" in question:
            out["outdoor_fire_type"] = text
        if "水源或是消防栓" in question:
            out["nearby_water_source"] = text
        if "波及到建築物" in question:
            out["people_trapped"] = (
                "受困" in text
                and "沒有" not in text
                and "沒有人" not in text
            )
            out["affected_targets"] = "無" if "沒有" in text else text

        phone = re.search(r"09\d{8}", text)
        if phone:
            out["caller_contact"] = phone.group(0)
        if "先生" in text:
            out["caller_salutation"] = "先生"
        elif "小姐" in text:
            out["caller_salutation"] = "小姐"
        return out

    def extract_address(self, caller_text: str, use_question: bool = False) -> dict:
        return {}

    def extract_caller_info(
        self, question: str, caller_text: str, include_address: bool = False
    ) -> dict:
        phone = re.search(r"09\d{8}", caller_text)
        salutation = None
        if "先生" in caller_text:
            salutation = "先生"
        elif "小姐" in caller_text:
            salutation = "小姐"
        return {
            "caller_name": None,
            "caller_contact": phone.group(0) if phone else None,
            "caller_salutation": salutation,
        }

    def check_fire_trigger_scenarios(
        self, caller_text: str, already_triggered: list[int]
    ) -> list[int]:
        return []

    def generate_summary(
        self, transcript_texts: list[str], filled_fields: dict
    ) -> str:
        return "火災測試摘要"


class FireFlowTests(unittest.TestCase):
    def _run_flow(self, answers: list[str]) -> tuple[SopEngine119, ScriptedIO, FireExtractor]:
        io = ScriptedIO(answers)
        llm = FireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        handler = HuoJingGenericHandler()
        handler.run_generic_flow(engine)
        handler.collect_caller_info(engine)
        self.assertFalse(io.answers)
        transcript_answers = engine.case.caller_texts()
        self.assertEqual(len(transcript_answers), len(answers))
        self.assertEqual(
            [call[0] for call in llm.general_calls],
            transcript_answers,
        )
        return engine, io, llm

    def test_building_flow_and_indoor_guidance(self) -> None:
        engine, io, _ = self._run_flow([
            "看到火",
            "房子在燒",
            "火越來越大，大約10坪",
            "我在裡面，是住戶",
            "有2個人受困",
            "總共5樓，3樓在燒",
            "有延燒，是連棟",
            "電話0912345678，我是先生",
        ])
        self.assertEqual(engine.case.fire_category, "建築物")
        self.assertEqual(engine.case.trapped_count, "2")
        self.assertEqual(engine.case.fire_floor, "3樓")
        self.assertIs(engine.case.fire_spread, True)
        self.assertTrue(any("不要往上逃生" in message for message in io.messages))
        self.assertEqual(engine.case.result, "dispatched")

    def test_factory_flow_skips_smoke_color(self) -> None:
        engine, io, _ = self._run_flow([
            "只看到火",
            "工廠在燒",
            "火正在消退，大約3坪",
            "大型鐵皮工廠",
            "廠內沒有人，沒有受困",
            "沒有化學品或危險物品",
            "電話0922333444，我是小姐",
        ])
        self.assertEqual(engine.case.fire_category, "工廠")
        self.assertEqual(engine.case.factory_scale_type, "大型鐵皮工廠")
        self.assertEqual(engine.case.hazardous_materials, "無")
        self.assertFalse(any("黑煙還是白煙" in message for message in io.messages))

    def test_vehicle_flow(self) -> None:
        engine, _, _ = self._run_flow([
            "看到火",
            "小客車在燒",
            "火越來越大，大約2坪",
            "小客車，1台",
            "車內沒有人",
            "在高速公路",
            "電話0933555777，我是先生",
        ])
        self.assertEqual(engine.case.fire_category, "車輛")
        self.assertEqual(engine.case.vehicle_type, "小客車")
        self.assertIs(engine.case.vehicle_occupants, False)
        self.assertEqual(engine.case.road_type, "高速公路")

    def test_outdoor_flow_with_smoke_color_and_safety_message(self) -> None:
        engine, io, _ = self._run_flow([
            "只看到煙",
            "是黑煙",
            "山林在燒",
            "火越來越大，大約20坪",
            "是山林",
            "附近沒有水源或消防栓",
            "沒有波及建築物車輛，也沒有人受困",
            "電話0944666888，我是小姐",
        ])
        self.assertEqual(engine.case.smoke_color, "黑煙")
        self.assertEqual(engine.case.fire_category, "露天野外")
        self.assertEqual(engine.case.affected_targets, "無")
        self.assertTrue(any("注意山林或雜草火勢蔓延" in message for message in io.messages))

    def test_previously_supplied_fields_are_not_asked_again(self) -> None:
        io = ScriptedIO([])
        llm = FireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine._apply_extracted_fields({
            "fire_or_smoke": "火",
            "burning_object": "住宅",
            "fire_trend": "變大",
            "fire_extent": "5坪",
            "fire_category": "建築物",
            "caller_position": "外面",
            "caller_role": "鄰居",
            "people_trapped": False,
            "building_total_floors": "4樓",
            "fire_floor": "2樓",
            "fire_spread": False,
            "building_layout": "獨棟",
        })
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertFalse(io.answers)
        self.assertFalse(any("請問" in message for message in io.messages))

    def test_explicit_fire_field_correction_overwrites_old_value(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine._apply_extracted_fields({
            "fire_category": "車輛",
            "vehicle_count": "1台",
            "road_type": "一般道路",
        })
        engine._apply_extracted_fields({
            "vehicle_count": "2台",
            "road_type": "高速公路",
        })
        self.assertEqual(engine.case.vehicle_count, "2台")
        self.assertEqual(engine.case.road_type, "高速公路")

    def test_existing_callback_number_is_confirmed_at_end(self) -> None:
        io = ScriptedIO(["對，我是先生"])
        llm = FireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.caller_contact = "0911222333"

        HuoJingGenericHandler().collect_caller_info(engine)

        self.assertEqual(engine.case.caller_contact, "0911222333")
        self.assertEqual(engine.case.caller_salutation, "先生")
        self.assertTrue(any("0911222333" in message for message in io.messages))
        self.assertEqual(len(llm.general_calls), 1)
        self.assertEqual(engine.case.result, "dispatched")


if __name__ == "__main__":
    unittest.main()
