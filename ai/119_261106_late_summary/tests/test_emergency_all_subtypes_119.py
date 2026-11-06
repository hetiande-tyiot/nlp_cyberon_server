"""
緊急救援每一個已接上的次案類，走一遍真實對話。

次案類先定好，再用假的抽取器把每一句回答記進對應欄位。
流程本身是線上那一支：派車、專用題、收尾、姓名電話。
"""

from __future__ import annotations

import unittest

from emergency_accident_119 import (
    ACCIDENT_QUESTIONS,
    BREATHING_QUESTION,
    CONSCIOUSNESS_QUESTION,
    DISPATCH_LINE,
    PATIENT_QUESTION,
    RELATION_QUESTION,
)
from emergency_rescue_subs_119 import (
    DOOR_QUESTIONS,
    DIVE_QUESTIONS,
    DROWN_QUESTIONS,
    FALL_QUESTIONS,
    GAS_QUESTIONS,
    LIFT_QUESTIONS,
    MOUNTAIN_QUESTIONS,
    TRAP_QUESTIONS,
    asked_questions,
)
from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler
from sop_119_engine import DialogueIO, SopEngine119


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError(
                "回答用完了，下一句是：" + (self.messages[-1] if self.messages else "")
            )
        return self.answers.pop(0)


class AnswerLLM:
    """這一輪回答對應哪些欄位，由測試事先寫好。"""

    def __init__(self, by_answer: dict[str, dict]):
        self.by_answer = by_answer

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        return dict(self.by_answer.get((caller_text or "").strip(), {}))

    def extract_caller_info(self, question, text, include_address=False):
        return dict(self.by_answer.get((text or "").strip(), {}))

    def generate_summary(self, transcript_texts, filled_fields):
        return "緊急救援測試摘要"


def _steps(*pairs: tuple[str, dict]) -> list[tuple[str, dict]]:
    return list(pairs)


def _run(sub: str, steps: list[tuple[str, dict]]) -> tuple[SopEngine119, ScriptedIO]:
    io = ScriptedIO([answer for answer, _ in steps])
    llm = AnswerLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    engine.case.main_category = "緊急救援"
    engine.case.sub_category = sub
    engine.case.sub_conf = 1.0
    engine.case.incident_description = "現場需要救援"
    engine.case.address_confirmed = True
    engine.case.address = "板橋區文化路一段10號"
    handler = JinJiJiuYuanGenericHandler()
    handler.run_generic_flow(engine)
    handler.collect_caller_info(engine)
    return engine, io


def _closing(name: str, phone: str) -> list[str]:
    return [
        f"姓名：{name}，聯繫方式：{phone}，已為您記錄。",
        "請在現場耐心等待，確認入口通暢，並引導救援人員，謝謝。",
    ]


def _expect_questions(questions, *extra: str, name: str, phone: str) -> list[str]:
    asked = [item.question for item in asked_questions(questions)]
    return [
        DISPATCH_LINE, *asked, *extra,
        "請問你的姓名與聯繫方式？",
        *_closing(name, phone),
    ]


class AllEmergencySubtypeTests(unittest.TestCase):
    def test_traffic_accident_full_call(self) -> None:
        engine, io = _run("車禍救助", _steps(
            ("機車撞到汽車", {"accident_vehicle_type": "機車車禍"}),
            ("頭有流血", {"accident_injury": "頭部外傷流血(含頸部)"}),
            ("有一個人卡在車裡", {"accident_trapped": "有人受困"}),
            ("兩個受傷一個受困", {"accident_casualty_count": "兩個受傷一個受困"}),
            ("叫不醒", {"accident_consciousness": "昏迷"}),
            ("車子沒有燃燒", {"accident_burning": "車子沒有燃燒"}),
            ("我是路人", {"accident_caller_role": "我是路人"}),
            ("擋到一個車道還過得去", {"accident_traffic_impact": "擋到一個車道還過得去"}),
            ("他兒子", {"caller_relation": "兒子"}),
            ("男生四十歲", {"patient_gender": "男", "patient_age": "四十歲"}),
            ("還有呼吸", {"breathing": True}),
            ("王小明 0912000111", {"caller_name": "王小明", "caller_contact": "0912000111"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            ACCIDENT_QUESTIONS, RELATION_QUESTION, PATIENT_QUESTION, BREATHING_QUESTION,
            name="王小明", phone="0912000111",
        ))
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.accident_vehicle_type, "機車車禍")
        self.assertEqual(engine.case.accident_caller_role, "路過")
        self.assertEqual(engine.case.result, "dispatched")
        self.assertEqual(engine.case.sub_category, "車禍救助")

    def test_drowning_full_call(self) -> None:
        engine, io = _run("溺水", _steps(
            ("在海邊玩水", {"drown_caller_role": "路人", "drown_cause": "戲水"}),
            ("一個人落水", {"drown_count": "一個人"}),
            ("還看得到人", {"drown_sight": "還在水裡"}),
            ("離岸大約二十公尺", {"drown_distance": "大約二十公尺"}),
            ("沒穿救生衣", {"drown_flotation": "沒有"}),
            ("人還會動", {"drown_consciousness": "意識清醒"}),
            ("是男生", {"drown_gender": "男性"}),
            ("大概八歲", {"drown_age": "八歲"}),
            ("穿紅色上衣", {"drown_clothing": "紅色上衣"}),
            ("我不認識他", {"caller_relation": "不認識"}),
            ("有呼吸", {"breathing": True}),
            ("林小姐 0922000222", {"caller_name": "林小姐", "caller_contact": "0922000222"}),
        ))
        # 第一句同時講了身分和原因，原因題若已記入就跳過。這裡分開答，原因是第二個欄位
        # 但第一句的抽取只在「在海邊玩水」那一輪。改成每題一句。
        self.assertNotIn("是跟團體一起來的嗎？有帶隊的人嗎？", io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.sub_category, "溺水")
        self.assertEqual(engine.case.result, "dispatched")

    def test_dive_already_in_water_full_call(self) -> None:
        engine, io = _run("跳水", _steps(
            ("已經跳下去了", {"dive_status": "已經跳下"}),
            ("還在水面", {"dive_sight": "還在水裡"}),
            ("我是家屬", {"dive_caller_role": "家屬"}),
            ("女生", {"dive_gender": "女性"}),
            ("大概二十歲", {"dive_age": "二十歲"}),
            ("白色上衣", {"dive_clothing": "白色上衣"}),
            ("只有一個人", {"dive_count": "一個人"}),
            ("還會動", {"dive_consciousness": "意識清醒"}),
            ("我是她媽媽", {"caller_relation": "媽媽"}),
            ("有呼吸", {"breathing": True}),
            ("陳媽媽 0933000333", {"caller_name": "陳媽媽", "caller_contact": "0933000333"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            DIVE_QUESTIONS, RELATION_QUESTION, BREATHING_QUESTION,
            name="陳媽媽", phone="0933000333",
        ))
        self.assertEqual(engine.case.dive_status, "已經跳下")
        self.assertEqual(engine.case.dive_count, "一個人")
        self.assertEqual(engine.case.result, "dispatched")

    def test_fall_still_high_full_call(self) -> None:
        engine, io = _run("跳樓", _steps(
            ("我是家人", {"fall_caller_role": "家人"}),
            ("人還在頂樓", {"high_fall_status": "還在高處（頂樓、窗外、陽台等）"}),
            ("他說要跳", {"fall_intent": "說要跳"}),
            ("現在在十二樓", {"fall_floor": "十二樓"}),
            ("男生", {"fall_gender": "男性"}),
            ("大概五十歲", {"fall_age": "五十歲"}),
            ("我是他弟弟", {"caller_relation": "弟弟"}),
            ("人還清醒", {}),
            ("有呼吸", {"breathing": True}),
            ("張先生 0944000444", {"caller_name": "張先生", "caller_contact": "0944000444"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            FALL_QUESTIONS, RELATION_QUESTION, CONSCIOUSNESS_QUESTION, BREATHING_QUESTION,
            name="張先生", phone="0944000444",
        ))
        self.assertIn("他是要自殺嗎？", io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertIs(engine.case.consciousness, True)
        self.assertEqual(engine.case.result, "dispatched")

    def test_mountain_injured_full_call(self) -> None:
        engine, io = _run("山難", _steps(
            ("腳扭到", {"mountain_cause": "腳扭到"}),
            ("小腿有傷口", {"mountain_injury": "四肢明顯外傷"}),
            ("我們兩個人", {"mountain_count": "兩個人"}),
            ("在步道涼亭附近", {"mountain_location": "步道涼亭附近"}),
            ("我同行", {"mountain_caller_role": "同行者"}),
            ("男生", {"mountain_gender": "男性"}),
            ("大概三十歲", {"mountain_age": "三十歲"}),
            ("人是清醒的", {"mountain_consciousness": "意識清醒"}),
            ("早上八點從登山口上去", {"mountain_entry": "早上八點從登山口上去"}),
            ("走主線經過涼亭", {"mountain_route": "主線經過涼亭"}),
            ("水還有食物不多", {"mountain_supplies": "水還有，食物不多"}),
            ("我是他朋友", {"caller_relation": "朋友"}),
            ("有呼吸", {"breathing": True}),
            ("吳先生 0955000555", {"caller_name": "吳先生", "caller_contact": "0955000555"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            MOUNTAIN_QUESTIONS, RELATION_QUESTION, BREATHING_QUESTION,
            name="吳先生", phone="0955000555",
        ))
        self.assertNotIn("是自己來，還是跟團體一起？", io.messages)
        self.assertEqual(engine.case.mountain_cause, "受傷")
        self.assertEqual(engine.case.mountain_caller_role, "代為報案")
        self.assertEqual(engine.case.result, "dispatched")

    def test_trap_family_full_call(self) -> None:
        engine, io = _run("其他(卡住夾住)", _steps(
            ("手指", {"trap_body_part": "手指"}),
            ("卡在戒指裡", {"trap_object": "戒指"}),
            ("現在還卡著", {"trap_freed": "還卡著"}),
            ("沒有流血", {"trap_injury": "沒有"}),
            ("在家裡", {"trap_place": "住家"}),
            ("女生", {"trap_gender": "女性"}),
            ("大概三十歲", {"trap_age": "三十歲"}),
            ("我是家人", {"trap_caller_role": "家人"}),
            ("人是清醒的", {"trap_consciousness": "意識清醒"}),
            ("我是她媽媽", {"caller_relation": "媽媽"}),
            ("有呼吸", {"breathing": True}),
            ("黃媽媽 0966000666", {"caller_name": "黃媽媽", "caller_contact": "0966000666"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            TRAP_QUESTIONS, RELATION_QUESTION, BREATHING_QUESTION,
            name="黃媽媽", phone="0966000666",
        ))
        self.assertEqual(engine.case.trap_caller_role, "家人")
        self.assertEqual(engine.case.result, "dispatched")

    def test_gas_leak_full_call(self) -> None:
        engine, io = _run("瓦斯漏氣(建築物)", _steps(
            ("透天厝", {"gas_building_use": "透天厝"}),
            ("我是住戶", {"gas_caller_role": "住戶"}),
            ("沒有看到火", {"gas_flame": "沒有"}),
            ("在廚房聞到", {"gas_smell_place": "廚房"}),
            ("味道很濃", {"gas_smell_strength": "很濃"}),
            ("用的是天然氣", {"gas_type": "天然氣"}),
            ("我是屋主太太", {"caller_relation": "太太"}),
            ("女生六十歲", {"patient_gender": "女", "patient_age": "六十歲"}),
            ("人還清醒", {}),
            ("有呼吸", {"breathing": True}),
            ("周太太 0977000777", {"caller_name": "周太太", "caller_contact": "0977000777"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            GAS_QUESTIONS,
            RELATION_QUESTION, PATIENT_QUESTION, CONSCIOUSNESS_QUESTION, BREATHING_QUESTION,
            name="周太太", phone="0977000777",
        ))
        self.assertNotIn("旁邊有房子或車子嗎？", io.messages)
        self.assertNotIn("有人身體不舒服嗎？", io.messages)
        self.assertEqual(engine.case.gas_type, "天然氣")
        self.assertEqual(engine.case.result, "dispatched")

    def test_lift_full_call(self) -> None:
        engine, io = _run("電梯受困", _steps(
            ("社區管理員王先生", {"lift_caller_role": "管理員"}),
            ("府中社區 B 棟二號梯", {"lift_building": "府中社區 B 棟二號梯"}),
            ("停在五樓", {"lift_floor": "五樓"}),
            ("裡面三個人", {"lift_count": "三個人"}),
            ("已經打給電梯公司", {"lift_company": "已經聯絡"}),
            ("人都清醒", {"lift_consciousness": "意識清醒"}),
            ("我是這棟的管理員", {"caller_relation": "管理員"}),
            ("裡面有一位男士", {"patient_gender": "男", "patient_age": "不詳"}),
            ("有呼吸", {"breathing": True}),
            ("王先生 0912345678", {"caller_name": "王先生", "caller_contact": "0912345678"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            LIFT_QUESTIONS, RELATION_QUESTION, PATIENT_QUESTION, BREATHING_QUESTION,
            name="王先生", phone="0912345678",
        ))
        self.assertNotIn("裡面的人有沒有受傷或不舒服？", io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertEqual(engine.case.lift_caller_role, "管理員或警衛")
        self.assertEqual(engine.case.result, "dispatched")

    def test_door_family_full_call(self) -> None:
        engine, io = _run("破門", _steps(
            ("我是家人", {"door_caller_role": "家人"}),
            ("屋裡沒人應門", {"door_reason": "屋裡沒人應門"}),
            ("敲門沒有回應", {"knock_response": "沒有回應"}),
            ("是大門", {"door_kind": "大門"}),
            ("沒有鑰匙", {"door_locksmith": "沒有鑰匙"}),
            ("家屬同意", {"door_consent": "同意"}),
            ("是男生", {"door_gender": "男性"}),
            ("大概七十歲", {"door_age": "七十歲"}),
            ("我是他兒子", {"caller_relation": "兒子"}),
            ("人還清醒", {}),
            ("有呼吸", {"breathing": True}),
            ("蔡先生 0999000999", {"caller_name": "蔡先生", "caller_contact": "0999000999"}),
        ))
        self.assertEqual(io.messages, _expect_questions(
            DOOR_QUESTIONS, RELATION_QUESTION, CONSCIOUSNESS_QUESTION, BREATHING_QUESTION,
            name="蔡先生", phone="0999000999",
        ))
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertEqual(engine.case.door_caller_role, "家人")
        self.assertEqual(engine.case.knock_response, "沒有回應")
        self.assertEqual(engine.case.result, "dispatched")

    def test_unfinished_subtype_only_gets_the_tail(self) -> None:
        """還沒做專用題的次案類，只走大類收尾。"""
        engine, io = _run("氣爆", _steps(
            ("我是鄰居", {"caller_relation": "鄰居"}),
            ("男生五十歲", {"patient_gender": "男", "patient_age": "五十歲"}),
            ("人還清醒", {}),
            ("有呼吸", {"breathing": True}),
            ("何先生 0911222333", {"caller_name": "何先生", "caller_contact": "0911222333"}),
        ))
        self.assertEqual(io.messages, [
            DISPATCH_LINE,
            RELATION_QUESTION,
            PATIENT_QUESTION,
            CONSCIOUSNESS_QUESTION,
            BREATHING_QUESTION,
            "請問你的姓名與聯繫方式？",
            *_closing("何先生", "0911222333"),
        ])
        self.assertEqual(engine.case.sub_category, "氣爆")
        self.assertEqual(engine.case.result, "dispatched")


if __name__ == "__main__":
    unittest.main()
