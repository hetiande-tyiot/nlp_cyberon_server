from __future__ import annotations

import re
import unittest
from types import SimpleNamespace

from fire_tab_map_119 import SAFETY_MESSAGE, apply_bert_subtype_to_case
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


class FakeFireBert:
    def __init__(self, label: str | None = None, conf: float = 0.0):
        self.label = label
        self.conf = conf
        self.calls: list[tuple[str, str]] = []

    def predict(self, text: str, main_category: str):
        self.calls.append((text, main_category))
        if not self.label:
            return None
        # 模擬真實 PredictionResult：含 all_probs，讓 margin 閘門有分布可算。
        # 預測標籤取 conf，其餘機率平均分給兩個佔位類別（確保預測標籤為 top-1）。
        rest = max(0.0, 1.0 - self.conf) / 2
        all_probs = {self.label: self.conf, "_o1": rest, "_o2": rest}
        return SimpleNamespace(
            final_label=self.label,
            classifier_conf=self.conf,
            all_probs=all_probs,
        )


class FireExtractor:
    def __init__(self):
        self.general_calls: list[tuple[str, str | None]] = []
        self.route_calls: list[tuple[str, str]] = []

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

        if "房子在燒嗎" in question:
            if any(k in text for k in ("不是", "其他", "其它", "車子", "草木", "垃圾")):
                out["fire_incident_type"] = 1
            elif any(k in text for k in ("是", "房子", "房屋", "透天", "公寓", "大樓")):
                out["fire_incident_type"] = 0
        if "車子在燒，還是山上" in question:
            if any(k in text for k in ("車", "汽車", "機車")):
                out["non_building_fire"] = 0
                if "機車" in text:
                    out["vehicle_wildfire_code"] = 1
                elif "汽車" in text:
                    out["vehicle_wildfire_code"] = 0
            elif any(k in text for k in ("山", "草", "林", "田")):
                out["non_building_fire"] = 0
            elif any(k in text for k in ("垃圾", "電線", "瓦斯", "警報", "都不是", "查看")):
                out["non_building_fire"] = 1
                if "垃圾" in text:
                    out["minor_fire_code"] = 0
                elif "電線" in text or "電纜" in text:
                    out["minor_fire_code"] = 1
                elif "瓦斯" in text:
                    out["minor_fire_code"] = 2
                elif "警報" in text:
                    out["minor_fire_code"] = 3
                elif "查看" in text:
                    out["minor_fire_code"] = 4

        if "哪一種建築物" in question:
            if "透天" in text:
                out["building_type_code"] = "10"
            elif "公寓" in text or "集合" in text:
                out["building_type_code"] = "11"
            elif "倉庫" in text or "仓库" in text:
                out["building_type_code"] = "12"
            else:
                out["building_type_code"] = "00"
        if "火苗竄出來" in question:
            out["has_flame"] = 0 if any(k in text for k in ("沒", "只有煙", "只有烟")) else 1
        if "煙是什麼顏色" in question:
            if "黑" in text:
                out["smoke_color_code"] = 1
            elif "白" in text:
                out["smoke_color_code"] = 2
            elif any(k in text for k in ("沒", "無煙")):
                out["smoke_color_code"] = 0
            else:
                out["smoke_color_code"] = 3
        if "爆炸的聲音" in question:
            out["has_explosion"] = 0 if any(k in text for k in ("沒", "無")) else 1
        if "燒到旁邊的房子" in question:
            out["spread_risk"] = 0 if any(k in text for k in ("沒", "不會", "不會")) else 1
        if "還有沒有人沒出來" in question:
            out["people_trapped_code"] = 0 if any(
                k in text for k in ("沒有人", "沒人", "無人", "都出來")
            ) else 1
        if "總共幾層樓" in question:
            n = re.search(r"(\d+)", text)
            if n:
                floors = int(n.group(1))
                if floors <= 3:
                    out["building_floors_code"] = 1
                elif floors <= 10:
                    out["building_floors_code"] = 2
                elif floors <= 15:
                    out["building_floors_code"] = 3
                else:
                    out["building_floors_code"] = 4
        if "幾樓開始燒" in question:
            if "地下" in text:
                out["fire_floor_code"] = 1
            else:
                n = re.search(r"(\d+)", text)
                if n:
                    floors = int(n.group(1))
                    if floors <= 3:
                        out["fire_floor_code"] = 2
                    elif floors <= 10:
                        out["fire_floor_code"] = 3
                    elif floors <= 15:
                        out["fire_floor_code"] = 4
                    else:
                        out["fire_floor_code"] = 5
        if "什麼蓋的" in question:
            if "木" in text:
                out["building_structure"] = 1
            elif "連造" in text:
                out["building_structure"] = 3
            elif "鐵皮" in text or "铁皮" in text:
                out["building_structure"] = 2
            elif "磚" in text or "砖" in text:
                out["building_structure"] = 4
            elif "SRC" in text.upper():
                out["building_structure"] = 6
            elif "RC" in text.upper():
                out["building_structure"] = 5
            else:
                out["building_structure"] = 0
        if "範圍大概多大" in question:
            ping = re.search(r"(\d+)\s*坪", text)
            if ping:
                n = int(ping.group(1))
                if n <= 50:
                    out["burn_area_code"] = 1
                elif n <= 100:
                    out["burn_area_code"] = 2
                elif n <= 300:
                    out["burn_area_code"] = 3
                elif n <= 500:
                    out["burn_area_code"] = 4
                else:
                    out["burn_area_code"] = 5
            else:
                out["burn_area_code"] = 0
        if "消防車進得去" in question:
            alley = any(k in text for k in ("小巷", "進不去"))
            water = any(k in text for k in ("缺水", "沒有水源", "沒水源"))
            if alley and water:
                out["access_water_info"] = 3
            elif alley:
                out["access_water_info"] = 1
            elif water:
                out["access_water_info"] = 2
            else:
                out["access_water_info"] = 0
        if "汽車還是機車" in question:
            if "機車" in text:
                out["vehicle_wildfire_code"] = 1
            elif "汽車" in text or "車子" in text:
                out["vehicle_wildfire_code"] = 0
            elif "船" in text:
                out["vehicle_wildfire_code"] = 5
            elif "飛機" in text:
                out["vehicle_wildfire_code"] = 6
        if "山上，還是路邊的平地" in question:
            out["vehicle_wildfire_code"] = 8 if "山" in text else 7
        if "聽到警報聲" in question:
            if "警報" in text:
                out["minor_fire_code"] = 3
            elif "瓦斯" in text:
                out["minor_fire_code"] = 2
            elif "電線" in text:
                out["minor_fire_code"] = 1
            elif "垃圾" in text:
                out["minor_fire_code"] = 0
            else:
                out["minor_fire_code"] = 4

        phone = re.search(r"09\d{8}", text)
        if phone:
            out["caller_contact"] = phone.group(0)
        if "先生" in text:
            out["caller_salutation"] = "先生"
        elif "小姐" in text:
            out["caller_salutation"] = "小姐"
        return out

    def classify_fire_route(
        self,
        caller_text: str,
        question: str | None = None,
        *,
        which: str = "q1",
    ) -> str | None:
        self.route_calls.append((which, caller_text))
        text = caller_text.strip()
        if which == "q1":
            if any(k in text for k in ("不是", "其他", "其它", "車子", "草木", "垃圾")):
                return "other"
            if any(k in text for k in ("房子", "房屋", "是", "透天", "公寓")):
                return "building"
            return None
        if any(k in text for k in ("車", "汽車", "機車")):
            return "vehicle"
        if any(k in text for k in ("山", "草", "林", "田")):
            return "vegetation"
        return "minor"

    def extract_address(
        self,
        caller_text: str,
        use_question: bool = False,
        include_floor: bool = True,
    ) -> dict:
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
    def _run_flow(
        self,
        answers: list[str],
        *,
        bert: FakeFireBert | None = None,
    ) -> tuple[SopEngine119, ScriptedIO, FireExtractor]:
        io = ScriptedIO(answers)
        llm = FireExtractor()
        engine = SopEngine119(
            io=io,
            llm_extractor=llm,  # type: ignore[arg-type]
            sub_classifiers=bert,
        )
        engine.case.main_category = "火警"
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

    def test_building_tab_a_flow(self) -> None:
        engine, io, _ = self._run_flow([
            "房子在燒",
            "透天厝",
            "有火苗竄出來",
            "黑煙",
            "沒有爆炸",
            "沒有燒到旁邊",
            "沒有人，都出來了",
            "總共5樓",
            "3樓開始燒",
            "磚造屋",
            "大約10坪",
            "進得去，附近有水源",
            "電話0912345678，我是先生",
        ])
        self.assertEqual(engine.case.fire_tab, "A")
        self.assertEqual(engine.case.fire_incident_type, 0)
        self.assertEqual(engine.case.building_type_code, "10")
        self.assertEqual(engine.case.has_flame, 1)
        self.assertEqual(engine.case.smoke_color_code, 1)
        self.assertEqual(engine.case.has_explosion, 0)
        self.assertEqual(engine.case.spread_risk, 0)
        self.assertEqual(engine.case.people_trapped_code, 0)
        self.assertIs(engine.case.people_trapped, False)
        self.assertEqual(engine.case.building_floors_code, 2)
        self.assertEqual(engine.case.fire_floor_code, 2)
        self.assertEqual(engine.case.building_structure, 4)
        self.assertEqual(engine.case.burn_area_code, 1)
        self.assertEqual(engine.case.access_water_info, 0)
        self.assertTrue(any(SAFETY_MESSAGE in message for message in io.messages))
        self.assertFalse(any("不要往上逃生" in message for message in io.messages))
        self.assertEqual(engine.case.result, "dispatched")

    def test_vehicle_tab_b1_flow(self) -> None:
        engine, io, _ = self._run_flow([
            "不是房子，是車子",
            "車子在燒",
            "汽車",
            "電話0933555777，我是先生",
        ])
        self.assertEqual(engine.case.fire_tab, "B1")
        self.assertEqual(engine.case.fire_incident_type, 1)
        self.assertEqual(engine.case.non_building_fire, 0)
        self.assertEqual(engine.case.vehicle_wildfire_code, 0)
        self.assertTrue(any(SAFETY_MESSAGE in message for message in io.messages))
        self.assertEqual(engine.case.result, "dispatched")

    def test_vegetation_tab_b2_flow(self) -> None:
        engine, io, _ = self._run_flow([
            "其它東西",
            "山上的草木在燒",
            "燒在山上",
            "電話0944666888，我是小姐",
        ])
        self.assertEqual(engine.case.fire_tab, "B2")
        self.assertEqual(engine.case.vehicle_wildfire_code, 8)
        self.assertTrue(any(SAFETY_MESSAGE in message for message in io.messages))

    def test_minor_tab_c_flow(self) -> None:
        engine, io, _ = self._run_flow([
            "不是房子",
            "都不是，是垃圾在燒",
            "電話0922333444，我是小姐",
        ])
        self.assertEqual(engine.case.fire_tab, "C")
        self.assertEqual(engine.case.non_building_fire, 1)
        self.assertEqual(engine.case.minor_fire_code, 0)
        self.assertTrue(any(SAFETY_MESSAGE in message for message in io.messages))

    def test_previously_supplied_fields_are_not_asked_again(self) -> None:
        io = ScriptedIO([])
        llm = FireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        engine._apply_extracted_fields({
            "fire_incident_type": 0,
            "building_type_code": "11",
            "has_flame": 1,
            "smoke_color_code": 1,
            "has_explosion": 0,
            "spread_risk": 0,
            "people_trapped_code": 0,
            "building_floors_code": 2,
            "fire_floor_code": 3,
            "building_structure": 5,
            "burn_area_code": 1,
            "access_water_info": 0,
        })
        HuoJingGenericHandler().run_generic_flow(engine)
        self.assertFalse(io.answers)
        self.assertEqual(engine.case.fire_tab, "A")
        self.assertTrue(any(SAFETY_MESSAGE in message for message in io.messages))
        self.assertFalse(any("請問" in message for message in io.messages))

    def test_explicit_fire_field_correction_overwrites_old_value(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.main_category = "火警"
        engine._apply_extracted_fields({
            "vehicle_wildfire_code": 0,
            "has_flame": 0,
        })
        engine._apply_extracted_fields({
            "vehicle_wildfire_code": 1,
            "has_flame": 1,
        })
        self.assertEqual(engine.case.vehicle_wildfire_code, 1)
        self.assertEqual(engine.case.has_flame, 1)

    def test_existing_callback_number_is_confirmed_at_end(self) -> None:
        io = ScriptedIO(["對，我是先生"])
        llm = FireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.caller_contact = "0911222333"

        HuoJingGenericHandler().collect_caller_info(engine)

        self.assertEqual(engine.case.caller_contact, "0911222333")
        self.assertEqual(engine.case.caller_salutation, "先生")
        self.assertTrue(any("0911222333" in message for message in io.messages))
        self.assertTrue(any("請問是先生還是小姐" in message for message in io.messages))
        self.assertEqual(len(llm.general_calls), 1)
        self.assertEqual(engine.case.result, "dispatched")

    def test_fire_trigger_is_recorded_without_repeating_dispatch_message(self) -> None:
        class TriggeringFireExtractor(FireExtractor):
            def check_fire_trigger_scenarios(
                self, caller_text: str, already_triggered: list[int]
            ) -> list[int]:
                return [] if 2 in already_triggered else [2]

        io = ScriptedIO([])
        llm = TriggeringFireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        handler = HuoJingGenericHandler()

        handler._check_and_respond_to_triggers("火勢很大", engine)

        self.assertEqual(engine.case.triggered_scenarios, [2])
        self.assertFalse(any("消防車已經派了" in message for message in io.messages))

    def test_bert_high_confidence_fills_codes_but_still_asks_remaining(self) -> None:
        bert = FakeFireBert(label="透天厝", conf=0.72)
        engine, io, _ = self._run_flow([
            "房子在燒",
            "有火苗",
            "黑煙",
            "沒有爆炸",
            "沒有燒到旁邊",
            "沒有人",
            "3樓",
            "2樓",
            "RC",
            "20坪",
            "進得去有水源",
            "電話0912345678，我是先生",
        ], bert=bert)
        self.assertEqual(engine.case.building_type_code, "10")
        self.assertEqual(engine.case.sub_category, "透天厝")
        self.assertGreater(engine.case.sub_conf or 0, 0.5)
        self.assertFalse(any("哪一種建築物" in message for message in io.messages))
        self.assertTrue(any("火苗竄出來" in message for message in io.messages))
        self.assertTrue(bert.calls)

    def test_bert_low_confidence_does_not_fill_subtype(self) -> None:
        bert = FakeFireBert(label="透天厝", conf=0.4)
        engine, _, _ = self._run_flow([
            "房子在燒",
            "公寓大樓",
            "有火苗",
            "白煙",
            "沒有爆炸",
            "沒有燒到旁邊",
            "沒有人",
            "4樓",
            "1樓",
            "磚造",
            "8坪",
            "進得去",
            "電話0912345678，我是先生",
        ], bert=bert)
        self.assertEqual(engine.case.building_type_code, "11")
        self.assertNotEqual(engine.case.sub_category, "透天厝")

    def test_q2_rule_fallback_when_classify_returns_none(self) -> None:
        class SilentRouteExtractor(FireExtractor):
            def classify_fire_route(self, caller_text, question=None, *, which="q1"):
                self.route_calls.append((which, caller_text))
                return None

        io = ScriptedIO([
            "不是房子",
            "路邊雜草",
            "路邊的平地",
            "電話0911222333，我是小姐",
        ])
        llm = SilentRouteExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        handler = HuoJingGenericHandler()
        handler.run_generic_flow(engine)
        handler.collect_caller_info(engine)
        self.assertEqual(engine.case.fire_tab, "B2")
        self.assertEqual(engine.case.vehicle_wildfire_code, 7)


class FireTabMapTests(unittest.TestCase):
    def test_bert_does_not_overwrite_conflicting_route(self) -> None:
        case = SimpleNamespace(
            fire_tab=None,
            fire_incident_type=0,
            building_type_code=None,
            non_building_fire=None,
            vehicle_wildfire_code=None,
            minor_fire_code=None,
            sub_category=None,
            sub_conf=None,
        )
        apply_bert_subtype_to_case(case, "汽車", 0.9)
        self.assertEqual(case.fire_incident_type, 0)
        self.assertIsNone(case.vehicle_wildfire_code)
        self.assertEqual(case.sub_category, "汽車")


if __name__ == "__main__":
    unittest.main()
