"""
救護 OK 表（1028 xlsx）墜落傷、上吊、割腕、吞食藥物、精神異常、燒燙傷照題目表重寫後的測試。
燒炭另見 test_ems_shaotan_119。

每類測：問的順序照 xlsx、條件題該問才問、xlsx 備註的改判／轉真人／提醒、
OK 表的案類不講觸發情境的話，以及題目表跟程式讀的 CaseTypeQA.xlsx 逐題對得上。

這裡的 LLM 是假的：每一句回答要抽出什麼，都由測試事先指定。
所以這些測試檢查的是「流程有沒有照規則問、跳過、改判」，
不檢查真正的 LLM 能不能從報案人的話判斷出正確的說法。
"""

from __future__ import annotations

import unittest
from pathlib import Path

import openpyxl

from ems_tab_map_119 import EMS_QUESTIONS, is_child_age
from handlers import get_handler
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError

BREAK_IN_LINE = "這需要破門，我已為您加派消防車前往。"
TRANSFER_LINE = "請不要掛斷電話，我立即為您轉接專人。"
MEDICINE_BAG_REMINDER = "如果有發現藥袋，請一併提供給救護人員帶到醫院。"


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
    """extracted：報案人的每一句回答 → LLM 應該抽出的欄位（模擬 LLM 已正確理解語意）。"""

    def __init__(self, extracted: dict[str, dict]):
        self.extracted = extracted

    def extract_general_fields(self, caller_text, question=None, **_kwargs) -> dict:
        return dict(self.extracted.get(caller_text.strip(), {}))

    def extract_slots(self, *_args, **_kwargs) -> dict:
        return {}

    def generate_summary(self, transcript_texts, filled_fields):
        return "救護測試摘要"


def _run(sub_category: str, steps: list[tuple[str, dict]], **prefilled):
    """已經知道次案類，直接從題目表第一題開始。steps：依實際被問的順序排列的 (回答, 抽出的欄位)。"""
    io = ScriptedIO([answer for answer, _ in steps])
    engine = SopEngine119(io=io, llm_extractor=FakeLLM(dict(steps)))  # type: ignore[arg-type]
    engine.case.main_category = "救護"
    engine.case.sub_category = sub_category
    for key, value in prefilled.items():
        setattr(engine.case, key, value)
    get_handler(sub_category).run_subtype_flow(engine)
    return engine, io


def _asked(sub_category: str, io: ScriptedIO) -> list[str]:
    """AI 說過的話換成「問了哪些關鍵要素」；不是問句的話照原文列出。"""
    by_question = {item.question: item.element
                   for item in EMS_QUESTIONS[sub_category] if item.question}
    return [by_question.get(m, m) for m in io.messages]


FAMILY = ("我是他家人", {"caller_relation": "家人"})
FRIEND = ("我是他朋友", {"caller_relation": "朋友"})
PASSER = ("我是路過的", {"caller_relation": "路過"})
NEIGHBOR = ("我是鄰居", {"caller_relation": "鄰居"})
MALE_40 = ("男生，四十歲", {"patient_gender": "男性", "patient_age": "40歲"})
AWAKE = ("他醒著", {"consciousness_level": "意識清醒"})
COMA = ("叫不醒", {"consciousness_level": "昏迷"})
BREATHING = ("有在呼吸", {"breathing": True})
NO_BREATHING = ("沒有呼吸了", {"breathing": False})


class ZhuiLuoShangTests(unittest.TestCase):
    JUMPED = ("已經掉下來了", {"fall_status": "已跳下"})
    NOT_YET = ("還在頂樓邊邊", {"fall_status": "尚未跳下"})
    FIVE_F = ("五樓", {"fall_height": "5樓"})
    GROUND = ("在一樓地上", {"fall_position": "地面(一樓)"})
    STUCK = ("卡在雨遮上", {"fall_position": "卡住"})
    UNKNOWN_POS = ("我不清楚", {"fall_position": "不清楚"})
    RAIN_SHELTER = ("遮雨棚", {"stuck_location": "遮雨棚"})
    NEAR = ("我在他旁邊", {"caller_location": "在現場"})

    def test_jumped_ground_family(self) -> None:
        engine, io = _run("墜落傷", [
            self.JUMPED, self.FIVE_F, FAMILY, MALE_40, self.GROUND, self.NEAR, AWAKE,
        ])
        self.assertEqual(_asked("墜落傷", io), [
            "墜落狀況", "墜落高度", "報案身分", "性別", "患者位置", "報案人位置", "意識",
        ])
        self.assertEqual(engine.case.main_category, "救護")

    def test_not_yet_jumped_escalates_silently(self) -> None:
        """尚未跳下：改判緊急救援，不講話；墜落高度、患者位置等「已跳下」才問的題不問。
        報案人位置沒問到，意識也不問（意識要報案人位置 = 在現場）。"""
        engine, io = _run("墜落傷", [self.NOT_YET, PASSER])
        self.assertEqual(_asked("墜落傷", io), ["墜落狀況", "報案身分"])
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertEqual(engine.case.caller_relation, "路過")  # 改判後的回答照樣記下來

    def test_stuck_escalates_and_asks_where(self) -> None:
        engine, io = _run("墜落傷", [
            self.JUMPED, self.FIVE_F, PASSER, self.STUCK, self.RAIN_SHELTER, self.NEAR, AWAKE,
        ])
        self.assertEqual(_asked("墜落傷", io), [
            "墜落狀況", "墜落高度", "報案身分", "患者位置", "卡住位置", "報案人位置", "意識",
        ])
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_stuck_said_before_position_question_escalates(self) -> None:
        """問墜落高度時就講卡住：還沒輪到患者位置那題，也要改判。"""
        engine, _ = _run("墜落傷", [
            self.JUMPED, ("五樓，卡在雨遮上", {"fall_height": "5樓", "fall_position": "卡住"}),
            PASSER, self.RAIN_SHELTER, self.NEAR, AWAKE,
        ])
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_unknown_position_skips_caller_location(self) -> None:
        """患者位置不清楚：報案人位置不問，所以意識、呼吸也不問（意識要報案人位置 = 在現場）。"""
        _, io = _run("墜落傷", [self.JUMPED, self.FIVE_F, FAMILY, MALE_40, self.UNKNOWN_POS])
        self.assertEqual(_asked("墜落傷", io), [
            "墜落狀況", "墜落高度", "報案身分", "性別", "患者位置",
        ])

    def test_unresponsive_not_breathing_is_ohca(self) -> None:
        with self.assertRaises(TransferToHumanError):
            _run("墜落傷", [
                self.JUMPED, self.FIVE_F, FAMILY, MALE_40, self.GROUND, self.NEAR, COMA,
                NO_BREATHING,
            ])


class ShangDiaoTests(unittest.TestCase):
    UNTIED = ("已經解下來了", {"hanging_status": "已解開繩子"})
    NOT_UNTIED = ("還吊著", {"hanging_status": "還沒解開"})
    NEED_BREAK = ("門鎖著要破門", {"break_in_need": "需要破門"})
    NO_BREAK = ("門開著", {"break_in_need": "不需要破門"})

    def test_untied_family_awake(self) -> None:
        _, io = _run("上吊", [self.UNTIED, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("上吊", io), ["上吊狀況", "報案身分", "性別", "意識"])

    def test_not_untied_break_in(self) -> None:
        """還沒解開：問破門；需要破門講廠商原句改判；繩子沒解開不問意識。"""
        engine, io = _run("上吊", [self.NOT_UNTIED, self.NEED_BREAK, FAMILY, MALE_40])
        self.assertEqual(_asked("上吊", io), [
            "上吊狀況", "破門需求", BREAK_IN_LINE, "報案身分", "性別",
        ])
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_remote_place_escalates_silently(self) -> None:
        engine, io = _run("上吊", [self.NOT_UNTIED, self.NO_BREAK, PASSER],
                          hanging_location="橋墩下面")
        self.assertEqual(_asked("上吊", io), ["上吊狀況", "破門需求", "報案身分"])
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_remote_place_said_later_still_escalates(self) -> None:
        """患者位置那題已經過了，報案人回答報案身分時才講橋墩：還是要改判。"""
        engine, _ = _run("上吊", [
            self.NOT_UNTIED, self.NO_BREAK,
            ("不認識，他吊在橋墩那邊", {"caller_relation": "不認識", "hanging_location": "橋墩"}),
        ])
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_break_in_said_later_still_escalates(self) -> None:
        """破門需求那題沒答清楚，回答報案身分時才講要破門：還是要改判、只講一次破門那句。"""
        engine, io = _run("上吊", [
            self.NOT_UNTIED, ("我也不知道", {}),
            ("我是家人，門反鎖了要破門", {"caller_relation": "家人", "break_in_need": "需要破門"}),
            MALE_40,
        ])
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertEqual(io.messages.count(BREAK_IN_LINE), 1)

    def test_break_in_changed_answer_escalates(self) -> None:
        """破門需求那題答不用，回答報案身分時改口要破門：答案跟著改，改判、講破門那句。"""
        engine, io = _run("上吊", [
            self.NOT_UNTIED, self.NO_BREAK,
            ("我是家人，門其實反鎖了要破門", {"caller_relation": "家人", "break_in_need": "需要破門"}),
            MALE_40,
        ])
        self.assertEqual(engine.case.break_in_need, "需要破門")
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertEqual(io.messages.count(BREAK_IN_LINE), 1)

    def test_untied_unresponsive_breathing(self) -> None:
        engine, io = _run("上吊", [self.UNTIED, FAMILY, MALE_40, COMA, BREATHING])
        self.assertEqual(_asked("上吊", io)[-2:], ["意識", "呼吸"])
        self.assertFalse(engine.case.is_ohca)


class ChangedAnswerTests(unittest.TestCase):
    """報案人改口：救護答案跟火警一樣以最新講的為準。"""

    def _engine(self) -> SopEngine119:
        engine = SopEngine119(io=ScriptedIO([]), llm_extractor=FakeLLM({}))  # type: ignore[arg-type]
        engine.case.main_category = "救護"
        return engine

    def test_consciousness_changed_recomputes_is_conscious(self) -> None:
        """意識先說醒著、後來說叫不醒：意識程度改成昏迷，「是否有意識」也跟著變成否。"""
        engine = self._engine()
        engine._apply_extracted_fields({"consciousness_level": "意識清醒"})
        self.assertTrue(engine.case.consciousness)
        engine._apply_extracted_fields({"consciousness_level": "昏迷"})
        self.assertEqual(engine.case.consciousness_level, "昏迷")
        self.assertFalse(engine.case.consciousness)

    def test_free_text_field_takes_latest_answer(self) -> None:
        """燒燙傷原因這類照報案人說的記的欄位：「不是熱水，是熱油」→ 改成熱油。"""
        engine = self._engine()
        engine._apply_extracted_fields({"injury_cause": "熱水"})
        engine._apply_extracted_fields({"injury_cause": "熱油"})
        self.assertEqual(engine.case.injury_cause, "熱油")

    def test_not_mentioned_keeps_answer(self) -> None:
        """這一句沒講到（抽出 null）不會把已經記下的答案清掉。"""
        engine = self._engine()
        engine._apply_extracted_fields({"injury_cause": "熱水"})
        engine._apply_extracted_fields({"injury_cause": None})
        self.assertEqual(engine.case.injury_cause, "熱水")


class GeWanTests(unittest.TestCase):
    WRIST_KNIFE = ("手腕，用美工刀", {"injury_severity": "手腕割傷", "cutting_tool": "美工刀"})
    REMOVED = ("拿走了", {"tool_status": "已移除"})

    def test_family_awake(self) -> None:
        _, io = _run("割腕", [self.WRIST_KNIFE, self.REMOVED, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("割腕", io), ["初步傷勢", "工具狀況", "報案身分", "性別", "意識"])

    def test_caller_is_patient_no_consciousness(self) -> None:
        _, io = _run("割腕", [self.WRIST_KNIFE, self.REMOVED, MALE_40], caller_relation="本人")
        self.assertEqual(_asked("割腕", io), ["初步傷勢", "工具狀況", "性別"])


class TunShiYaoWuTests(unittest.TestCase):
    PILLS = ("安眠藥，大概二十顆", {"ingested_substance": "安眠藥", "drug_amount": "約20顆"})

    def test_family_awake_then_medicine_bag_reminder(self) -> None:
        _, io = _run("吞食藥物", [self.PILLS, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("吞食藥物", io), [
            "服用藥物", "報案身分", "性別", "意識", MEDICINE_BAG_REMINDER,
        ])

    def test_passer_not_on_scene_skips_gender_and_consciousness(self) -> None:
        _, io = _run("吞食藥物", [self.PILLS, PASSER], caller_location="不在現場")
        self.assertEqual(_asked("吞食藥物", io), ["服用藥物", "報案身分", MEDICINE_BAG_REMINDER])


class JingShenYiChangTests(unittest.TestCase):
    ATTACKS = ("他拿東西打人", {"aggression": "攻擊他人"})
    NONE = ("沒有", {"aggression": "無"})
    TWO_HURT = ("兩個人受傷", {"injured_count": "2人"})
    FORCED = ("要強送", {"forced_admission": "需要"})
    NOT_FORCED = ("不用", {"forced_admission": "不需要"})
    REASON = ("一直摔東西", {"forced_admission_reason": "摔丟東西"})
    HISTORY = ("有思覺失調", {"medical_history": "思覺失調"})
    ACCOMPANY = ("他媽媽在旁邊", {"family_accompany": "有"})

    def test_attacks_forced_family(self) -> None:
        """家人報案：問病史、不問家屬陪同；不問意識呼吸。"""
        _, io = _run("精神異常", [
            self.ATTACKS, self.TWO_HURT, self.FORCED, self.REASON, FAMILY, MALE_40, self.HISTORY,
        ])
        self.assertEqual(_asked("精神異常", io), [
            "攻擊傾向", "受傷人數", "強制送醫", "強制送醫原因", "報案身分", "性別", "病史",
        ])

    def test_neighbor_asks_family_accompany_not_history(self) -> None:
        _, io = _run("精神異常", [self.NONE, self.NOT_FORCED, NEIGHBOR, MALE_40, self.ACCOMPANY])
        self.assertEqual(_asked("精神異常", io), [
            "攻擊傾向", "強制送醫", "報案身分", "性別", "家屬陪同",
        ])

    def test_friend_asks_history_and_family_accompany(self) -> None:
        _, io = _run("精神異常", [
            self.NONE, self.NOT_FORCED, FRIEND, MALE_40, self.HISTORY, self.ACCOMPANY,
        ])
        self.assertEqual(_asked("精神異常", io)[-2:], ["病史", "家屬陪同"])


class ShaoTangShangTests(unittest.TestCase):
    HOT_WATER = ("被熱水燙到", {"injury_cause": "熱水"})
    BLISTER = ("大腿起水泡，一個手掌大", {"injury_severity": "大腿起水泡，約一個手掌大"})

    def test_family_awake(self) -> None:
        _, io = _run("燒燙傷", [self.HOT_WATER, self.BLISTER, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("燒燙傷", io), [
            "燒燙傷原因", "燙傷傷勢", "報案身分", "性別", "意識",
        ])

    def test_child_transfers_to_human(self) -> None:
        """14 歲（含）以下：轉真人。"""
        with self.assertRaises(TransferToHumanError):
            _, io = _run("燒燙傷", [
                self.HOT_WATER, self.BLISTER, FAMILY, ("男生，五歲", {"patient_gender": "男性",
                                                                    "patient_age": "5歲"}),
            ])

    def test_child_age_rule(self) -> None:
        for age in ("5歲", "十四歲", "14歲", "3個月", "八歲"):
            self.assertTrue(is_child_age(age), age)
        for age in ("15歲", "二十五歲", "40歲", None, "不知道"):
            self.assertFalse(is_child_age(age), age)


class OkTablesTests(unittest.TestCase):

    def test_tables_match_case_type_qa(self) -> None:
        """7 張 OK 表的題目表，跟程式讀的 CaseTypeQA.xlsx 逐題對得上（題號靠位置算）。"""
        path = Path(__file__).resolve().parents[1] / "scripts" / "CaseTypeQA.xlsx"
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        for name in ("墜落傷", "燒燙傷", "精神異常", "吞食藥物", "上吊", "燒炭", "割腕"):
            with self.subTest(name=name):
                rows = [r for r in ws.iter_rows(values_only=True) if r[1] == f"救護-{name}"]
                self.assertEqual([r[5] for r in rows], [i.element for i in EMS_QUESTIONS[name]])

    def test_no_trigger_scenarios(self) -> None:
        """OK 表的案類不用觸發情境（使用者 10/28 決定）。"""
        for name in ("墜落傷", "燒燙傷", "精神異常", "吞食藥物", "上吊", "燒炭", "割腕"):
            with self.subTest(name=name):
                self.assertFalse(hasattr(get_handler(name), "_send_trigger_responses"))


if __name__ == "__main__":
    unittest.main()
