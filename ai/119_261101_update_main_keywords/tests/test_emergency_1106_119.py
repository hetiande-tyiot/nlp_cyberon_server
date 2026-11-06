"""
緊急救援照 1106 xlsx 的題目表問（使用者 11/05、11/06 決定）。

- 有次案類就照那張表的順序問；主動題已有答案就跳過，條件不成立就不問
- 性別、年齡只答到一個就補問：溺水、跳水、跳樓用「患者」，山難、卡住夾住、破門用「當事人」
- 判不出次案類：問「請描述發生什麼事需要救援？」「是有人受傷，還是有人困住出不來嗎？」，
  兩句都問完還是判不出來就不再問
- 車禍救助、瓦斯漏氣的火煙狀況看得到火或煙 → 改判火警（車禍救助 B1、瓦斯漏氣 A）；只有火花不改判
- 呼吸 = 呼吸不正常、無呼吸 → 轉真人
- 名稱跟救護、火警、災害一樣的關鍵要素共用欄位

這裡的 LLM 是假的：每一句要抽出什麼，由測試事先指定。
"""

from __future__ import annotations

import types
import unittest

from emergency_tab_map_119 import (
    DISPATCH_LINE,
    INCIDENT_QUESTION,
    INCIDENT_REASK_QUESTION,
    emergency_fields_to_extract,
)
from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler
from llm_extractor_119 import LLMExtractor119
from sop_119_engine import DialogueIO, MainCategorySwitched, SopEngine119, TransferToHumanError


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError(f"測試回答已用盡，最後一句是：{self.messages[-1]}")
        return self.answers.pop(0)


class FakeLLM:
    def __init__(self, extracted: dict[str, dict]):
        self.extracted = extracted

    def extract_general_fields(self, caller_text, question=None, *, main_category=None,
                               call_type=None, fire_tab=None, sub_category=None) -> dict:
        return dict(self.extracted.get((caller_text or "").strip(), {}))

    def extract_caller_info(self, question, text, include_address=False):
        return {}

    def generate_summary(self, transcript_texts, filled_fields):
        return "緊急救援測試摘要"

    def remap_sop_fields_for_subcategory(self, **_kwargs):
        return {}


class SwitchBert:
    """全文出現「河」才判成溺水；把握程度可以調。"""

    def __init__(self, drown_conf: float = 0.92, crash_conf: float = 0.04):
        self.drown_conf = drown_conf
        self.crash_conf = crash_conf

    def predict(self, text, main_cat):
        if "河" in (text or ""):
            probs = {"溺水": self.drown_conf, "車禍救助": self.crash_conf}
            label, conf = "溺水", self.drown_conf
        else:
            probs = {"車禍救助": 0.9, "溺水": 0.05}
            label, conf = "車禍救助", 0.9
        return types.SimpleNamespace(final_label=label, classifier_conf=conf, all_probs=probs)


def _engine(sub: str | None, steps: list[tuple[str, dict]]) -> tuple[SopEngine119, ScriptedIO]:
    io = ScriptedIO([answer for answer, _ in steps])
    llm = FakeLLM({answer: fields for answer, fields in steps})
    engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
    engine.case.main_category = "緊急救援"
    engine.case.sub_category = sub
    engine.case.address_confirmed = True
    return engine, io


class EmergencyQuestionTests(unittest.TestCase):
    def test_crash_asks_xlsx_questions_in_order(self) -> None:
        steps = [
            ("汽車撞機車", {"crash_vehicles": "汽車撞機車"}),
            ("腳受傷", {"injury_location": "腳"}),
            ("一直流血", {"injury_severity": "一直流血"}),
            ("有人卡在車裡", {"trapped_status": "有人受困"}),
            ("一個受傷一個卡住", {"patient_count": "受傷1人、受困1人"}),
            ("沒有火也沒有煙", {"fire_or_smoke": "無火無煙"}),
            ("我是路過的", {"caller_relation": "路過"}),
            ("擋到一個車道", {"traffic_impact": "佔用部分車道"}),
        ]
        engine, io = _engine("車禍救助", steps)
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        # 意識的前置條件要看報案身分，報案身分排在後面：輪到意識時還不知道身分，照 xlsx 順序不問
        self.assertEqual(io.messages, [
            DISPATCH_LINE,
            "請問是什麼車跟什麼車的車禍？",
            "傷到哪裡？",
            "傷得嚴不嚴重？有沒有一直流血？",
            "有沒有人被困在車裡出不來？",
            "有幾個人受傷？幾個人受困？",
            "車子有沒有冒煙或起火？",
            "請問是當事人還是路人代報？",
            "有擋到路嗎？車子還過得去嗎？",
        ])
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertEqual(engine.case.trapped_status, "有人受困")
        self.assertEqual(engine.case.traffic_impact, "佔用部分車道")

    def test_crash_caller_off_scene_skips_scene_questions(self) -> None:
        steps = [
            ("機車自摔", {"crash_vehicles": "機車自摔"}),
            ("我是他家人", {"caller_relation": "家人"}),
            ("不知道", {}),
        ]
        engine, io = _engine("車禍救助", steps)
        engine.case.caller_location = "不在現場"
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [
            DISPATCH_LINE,
            "請問是什麼車跟什麼車的車禍？",
            "請問是當事人還是路人代報？",
            "有擋到路嗎？車子還過得去嗎？",
        ])

    def test_known_answers_are_skipped(self) -> None:
        engine, io = _engine("電梯受困", [
            ("裡面有兩個人", {"lift_count": "2人"}),
            ("還沒", {"lift_company": "還沒聯絡"}),
            ("我是管理員", {"caller_relation": "管理室"}),
        ])
        engine.case.lift_building = "幸福社區A棟"
        engine.case.lift_floor = "3樓"
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [
            DISPATCH_LINE,
            "裡面有幾個人？",
            "有聯絡電梯公司了嗎？",
            "請問是本人嗎？還是管理員或警衛？",
        ])


class EmergencySingleMissingTests(unittest.TestCase):
    def test_drown_follow_up_uses_patient(self) -> None:
        steps = [
            ("游泳抽筋", {"drowning_cause": "游泳抽筋"}),
            ("一個人", {"patient_count": "1人"}),
            ("還在水裡", {"drowning_status": "還在水裡"}),
            ("大概十公尺", {"drown_distance": "約10公尺"}),
            ("沒有", {"drown_flotation": "沒有"}),
            ("我是他朋友", {"caller_relation": "朋友"}),
            ("是男生", {"patient_gender": "男性"}),
            ("二十幾歲", {"patient_age": "20幾歲"}),
            ("還會動", {"consciousness_level": "清醒"}),
            ("紅色衣服", {"patient_appearance": "紅色衣服"}),
        ]
        engine, io = _engine("溺水", steps)
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        index = io.messages.index("請問患者是男生還是女生？大概幾歲？")
        self.assertEqual(io.messages[index + 1], "請問患者大概幾歲？")
        self.assertEqual(io.messages[-1], "他穿什麼顏色的衣服？")

    def test_mountain_follow_up_uses_party(self) -> None:
        steps = [
            ("迷路了", {"mountain_cause": "迷路"}),
            ("兩個人", {"patient_count": "2人"}),
            ("在步道上", {"mountain_location": "步道上"}),
            ("我是他家人", {"caller_relation": "家人"}),
            ("五十歲", {"patient_age": "50歲"}),
            ("是女生", {"patient_gender": "女性"}),
            ("早上八點", {"mountain_entry": "早上八點上山"}),
            ("走主線", {"mountain_route": "主線步道"}),
        ]
        engine, io = _engine("山難", steps)
        engine.case.caller_location = "不在現場"
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [
            DISPATCH_LINE,
            "請問發生什麼事？是迷路還是受傷？",
            "你們總共幾個人？",
            "您現在在哪裡？手機可以看到座標嗎？",
            "請問是本人還是家屬朋友代報？",
            "請問當事人是男生還是女生？大概幾歲？",
            "請問當事人是男生還是女生？",
            "幾點上山的？從哪裡上去的？",
            "你們走哪一條路線？最後經過什麼地標？",
        ])


class EmergencyNoSubcategoryTests(unittest.TestCase):
    def test_two_incident_questions_then_stop(self) -> None:
        steps = [
            ("我這邊需要幫忙", {"incident_description": "需要幫忙"}),
            ("我也不知道", {}),
        ]
        engine, io = _engine(None, steps)
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [INCIDENT_QUESTION, INCIDENT_REASK_QUESTION, DISPATCH_LINE])

    def test_incident_already_described_asks_second_only(self) -> None:
        engine, io = _engine(None, [("不知道", {})])
        engine.case.incident_description = "需要幫忙"
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(io.messages, [INCIDENT_REASK_QUESTION, DISPATCH_LINE])

    def test_known_subcategory_asks_neither(self) -> None:
        engine, io = _engine("破門", [
            ("獨居聯絡不上", {"door_reason": "獨居聯絡不上"}),
            ("我是他兒子", {"caller_relation": "家人"}),
            ("七十歲男生", {"patient_gender": "男性", "patient_age": "70歲"}),
            ("大門", {"door_kind": "大門"}),
            ("沒有鑰匙", {"door_locksmith": "沒有鑰匙"}),
            ("同意", {"door_consent": "同意"}),
        ])
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertNotIn(INCIDENT_QUESTION, io.messages)
        self.assertNotIn(INCIDENT_REASK_QUESTION, io.messages)
        # 有無回應排在報案身分前面：輪到時還不知道身分，照 xlsx 順序不問
        self.assertNotIn("敲門或打電話，會有回應嗎？", io.messages)


class EmergencySubSwitchTests(unittest.TestCase):
    """題目問到一半換次案類（原本 test_emergency_sub_switch_119 的情境，改成 1106 題目表）。"""

    def _run(self, steps: list[tuple[str, dict]], bert: SwitchBert) -> tuple[SopEngine119, ScriptedIO]:
        io = ScriptedIO([answer for answer, _ in steps])
        llm = FakeLLM({answer: fields for answer, fields in steps})
        engine = SopEngine119(io=io, llm_extractor=llm, sub_classifiers=bert)  # type: ignore[arg-type]
        engine.case.main_category = "緊急救援"
        engine.case.sub_category = "車禍救助"
        engine.case.sub_conf = 0.9
        engine.case.incident_description = "兩台車撞在一起"
        engine.case.address_confirmed = True
        engine.case.transcript = [{"role": "caller", "text": "兩台車撞在一起"}]
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        return engine, io

    def test_confident_classifier_switches_and_keeps_person_answers(self) -> None:
        engine, io = self._run([
            ("人掉進河裡了 我是他朋友 男生四十歲", {
                "crash_vehicles": "機車", "caller_relation": "朋友",
                "patient_gender": "男性", "patient_age": "40歲",
            }),
            ("游泳抽筋", {"drowning_cause": "游泳抽筋"}),
            ("一個", {"patient_count": "1人"}),
            ("還在水裡", {"drowning_status": "還在水裡"}),
            ("十公尺", {"drown_distance": "約10公尺"}),
            ("沒有", {"drown_flotation": "沒有"}),
            ("還會動", {"consciousness_level": "清醒"}),
            ("紅色衣服", {"patient_appearance": "紅色衣服"}),
        ], SwitchBert())
        self.assertEqual(engine.case.sub_category, "溺水")
        # 車禍救助的答案清掉；報案身分、性別、年齡是同一個人，留著不重問
        self.assertIsNone(engine.case.crash_vehicles)
        self.assertEqual(engine.case.caller_relation, "朋友")
        self.assertEqual(engine.case.patient_age, "40歲")
        self.assertEqual(io.messages, [
            DISPATCH_LINE,
            "請問是什麼車跟什麼車的車禍？",
            "請問是怎麼落水的？",
            "有幾個人落水？",
            "還有看到人嗎？",
            "離岸邊大概多遠？",
            "對方有穿救生衣或泳圈嗎？",
            "對方還會動嗎？",
            "他穿什麼顏色的衣服？",
        ])

    def test_unsure_classifier_keeps_crash_questions(self) -> None:
        engine, io = self._run([
            ("人掉進河裡了", {"crash_vehicles": "機車"}),
            ("腳", {"injury_location": "腳"}),
            ("擦傷", {"injury_severity": "擦傷"}),
            ("沒有人被困", {"trapped_status": "無人受困"}),
            ("一個人受傷", {"patient_count": "受傷1人"}),
            # 不用「沒有冒煙」：含氣爆的硬規則詞「有冒煙」，會被改判氣爆（已回報使用者）
            ("沒看到煙也沒看到火", {"fire_or_smoke": "無火無煙"}),
            ("我是路人", {"caller_relation": "路過"}),
            ("沒擋到路", {"traffic_impact": "未影響交通"}),
        ], SwitchBert(drown_conf=0.55, crash_conf=0.48))
        self.assertEqual(engine.case.sub_category, "車禍救助")
        self.assertEqual(engine.case.crash_vehicles, "機車")
        self.assertNotIn("請問是怎麼落水的？", io.messages)


class EmergencySwitchToFireTests(unittest.TestCase):
    def test_crash_with_fire_switches_to_fire_b1(self) -> None:
        for state in ("有火有煙", "有火無煙", "無火有煙"):
            with self.subTest(state=state):
                engine, io = _engine("車禍救助", [])
                engine.case.fire_or_smoke = state
                engine.case.caller_relation = "路過"
                with self.assertRaises(MainCategorySwitched):
                    JinJiJiuYuanGenericHandler().run_generic_flow(engine)
                self.assertEqual(engine.case.main_category, "火警")
                self.assertEqual(engine.case.fire_tab, "B1")
                # 火警也用到的欄位留著
                self.assertEqual(engine.case.fire_or_smoke, state)
                self.assertEqual(io.messages, [DISPATCH_LINE])

    def test_gas_with_fire_switches_to_fire_a(self) -> None:
        engine, _io = _engine("瓦斯漏氣(建築物)", [
            ("是住家", {"place_usage": "住宅"}),
            ("我住附近", {"caller_relation": "鄰居"}),
            # 不用「有冒煙」：那是 119keywords.xlsx 氣爆的硬規則詞，會先把次案類改成氣爆
            ("外面在冒黑煙", {"fire_or_smoke": "無火有煙"}),
        ])
        with self.assertRaises(MainCategorySwitched):
            JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.main_category, "火警")
        self.assertEqual(engine.case.fire_tab, "A")
        self.assertEqual(engine.case.place_usage, "住宅")
        # 緊急救援自己的欄位清掉、共用給救護的報案身分在火警用不到也清掉
        self.assertIsNone(engine.case.caller_relation)

    def test_spark_only_does_not_switch(self) -> None:
        engine, _io = _engine("瓦斯漏氣(建築物)", [
            ("是住家", {"place_usage": "住宅"}),
            ("我住附近", {"caller_relation": "鄰居"}),
            ("只有一點火花", {"fire_or_smoke": "只有火花"}),
            ("廚房", {"gas_smell_place": "廚房"}),
            ("很濃", {"gas_smell_strength": "很濃"}),
            ("天然氣", {"gas_type": "天然氣"}),
        ])
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_other_subcategory_with_fire_does_not_switch(self) -> None:
        engine, _io = _engine("跳樓", [
            ("還在上面", {"fall_status": "尚未跳下"}),
            ("他說要跳", {"fall_intent": "說要跳"}),
            ("十樓", {"fall_floor": "10樓"}),
            ("我是鄰居", {"caller_relation": "鄰居"}),
            ("男生三十歲", {"patient_gender": "男性", "patient_age": "30歲"}),
        ])
        engine.case.fire_or_smoke = "有火有煙"
        JinJiJiuYuanGenericHandler().run_generic_flow(engine)
        self.assertEqual(engine.case.main_category, "緊急救援")


class EmergencyBreathingTransferTests(unittest.TestCase):
    def test_no_breathing_transfers(self) -> None:
        for state in ("呼吸不正常", "無呼吸"):
            with self.subTest(state=state):
                engine, io = _engine("其他", [])
                engine.case.breathing = state
                with self.assertRaises(TransferToHumanError):
                    JinJiJiuYuanGenericHandler().run_generic_flow(engine)
                self.assertEqual(io.messages[-1], "請不要掛斷電話，我立即為您轉接專人。")


class EmergencySharedFieldTests(unittest.TestCase):
    def test_shared_fields_saved_in_emergency(self) -> None:
        engine, _io = _engine(None, [])
        engine._apply_extracted_fields({
            "caller_relation": "家人",
            "consciousness_level": "沒有反應",
            "trapped_status": "有人受困",
            "fire_or_smoke": "只有火花",
            "traffic_impact": "完全無法通行",
            "lift_count": "2人",
        })
        self.assertEqual(engine.case.caller_relation, "家人")
        self.assertEqual(engine.case.consciousness_level, "沒有反應")
        self.assertEqual(engine.case.trapped_status, "有人受困")
        self.assertEqual(engine.case.fire_or_smoke, "只有火花")
        self.assertEqual(engine.case.traffic_impact, "完全無法通行")
        self.assertEqual(engine.case.lift_count, "2人")

    def test_emergency_fields_blocked_in_other_categories(self) -> None:
        engine, _io = _engine(None, [])
        engine.case.main_category = "救護"
        engine._apply_extracted_fields({"lift_count": "2人", "traffic_impact": "完全無法通行"})
        self.assertIsNone(engine.case.lift_count)
        self.assertIsNone(engine.case.traffic_impact)

    def test_rescue_to_emergency_keeps_shared_fields(self) -> None:
        engine, _io = _engine(None, [])
        engine.case.main_category = "救護"
        engine.case.caller_relation = "朋友"
        engine.case.patient_gender = "男性"
        engine.case.consciousness_level = "清醒"
        engine.case.symptoms = "頭暈"
        engine._migrate_case_for_main_switch("救護", "緊急救援")
        self.assertEqual(engine.case.caller_relation, "朋友")
        self.assertEqual(engine.case.patient_gender, "男性")
        self.assertEqual(engine.case.consciousness_level, "清醒")
        self.assertIsNone(engine.case.symptoms)


class EmergencyExtractionTests(unittest.TestCase):
    def test_known_subcategory_extracts_its_table_only(self) -> None:
        calls = []

        def extract_slots(text, schema, rules, **_kwargs):
            calls.append((schema, rules))
            return {}

        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = extract_slots
        ext.extract_general_fields("測試", "測試", main_category="緊急救援", sub_category="車禍救助")
        schema, rules = next(call for call in calls if "crash_vehicles" in call[0])
        self.assertEqual(set(schema), set(emergency_fields_to_extract("車禍救助")))
        self.assertNotIn("lift_count", schema)
        # 火煙狀況、人員受困用火警的抽取規則
        self.assertIn("fire_or_smoke 火煙狀況", rules)
        self.assertIn("trapped_status 人員受困", rules)
        self.assertIn("受傷幾人、受困幾人", rules)

    def _post_process(self, answer: str, ai_output: dict) -> dict:
        """假的 LLM 回 ai_output，看抽取後處理最後留下什麼。"""
        ext = object.__new__(LLMExtractor119)
        ext.backend = "gguf"
        ext.extract_slots = lambda text, schema, rules, **_k: {
            key: val for key, val in ai_output.items() if key in schema
        }
        return ext.extract_general_fields(
            answer, "他還有沒有呼吸？", main_category="緊急救援", sub_category=None,
        )

    def test_breathing_keeps_xlsx_text(self) -> None:
        # 舊的是／否判斷曾把「無呼吸」改成 False、把「呼吸不正常」丟掉，轉真人就觸發不了
        for answer, state in (
            ("他沒有呼吸", "無呼吸"), ("有在呼吸", "有呼吸"),
            ("呼吸怪怪的很喘", "呼吸不正常"), ("我看不到", "未知"),
        ):
            with self.subTest(state=state):
                self.assertEqual(self._post_process(answer, {"breathing": state})["breathing"], state)
        self.assertNotIn("breathing", self._post_process("他沒有呼吸", {"breathing": False}))

    def test_answers_outside_xlsx_options_are_dropped(self) -> None:
        result = self._post_process("他跳下去了", {
            "dive_status": "已經跳下", "door_kind": "房間門", "consciousness_level": "昏迷",
        })
        self.assertEqual(result, {})
        result = self._post_process("他跳下去了", {"dive_status": "已跳下", "consciousness_level": "沒有反應"})
        self.assertEqual(result["dive_status"], "已跳下")
        self.assertEqual(result["consciousness_level"], "沒有反應")

    def test_old_yes_no_keywords_do_not_write_breathing(self) -> None:
        engine, _io = _engine("其他", [("他沒有呼吸", {})])
        engine._extract_all_fields_from_reply("他沒有呼吸", question="他還有沒有呼吸？")
        self.assertIsNone(engine.case.breathing)

    def test_honorific_gender_uses_xlsx_wording(self) -> None:
        engine, _io = _engine("其他", [])
        engine.case.transcript.append({"role": "caller", "text": "有一位先生手卡在機器裡"})
        engine._ensure_known_fields_from_history()
        # 從「一位先生」推出男；緊急救援跟救護一樣記成 xlsx 的「男性」，不是「男」
        self.assertEqual(engine.case.patient_gender, "男性")
        self.assertIsNone(engine.case.caller_is_patient)

    def test_unknown_subcategory_extracts_all_tables(self) -> None:
        fields = emergency_fields_to_extract(None)
        for field in ("crash_vehicles", "lift_count", "door_consent", "place_usage", "incident_description"):
            self.assertIn(field, fields)


if __name__ == "__main__":
    unittest.main()
