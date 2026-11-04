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
BURN_REMINDERS = ["可以的話，請協助沖冷水到救護人員到達為止。", "燙到的地方先不要擦任何藥。"]
STOP_BLEEDING_REMINDER = "先拿乾淨的毛巾或衣服，用力壓住傷口止血。"


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
BREATHING = ("有在呼吸", {"breathing": "有呼吸"})
NO_BREATHING = ("沒有呼吸了", {"breathing": "無呼吸"})


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
        報案人位置沒提到，性別年齡照樣問；意識不問（意識要報案人位置 = 在現場）。"""
        engine, io = _run("墜落傷", [self.NOT_YET, PASSER, MALE_40])
        self.assertEqual(_asked("墜落傷", io), ["墜落狀況", "報案身分", "性別"])
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertEqual(engine.case.caller_relation, "路過")  # 改判後的回答照樣記下來

    def test_stuck_escalates_and_asks_where(self) -> None:
        engine, io = _run("墜落傷", [
            self.JUMPED, self.FIVE_F, PASSER, MALE_40, self.STUCK, self.RAIN_SHELTER, self.NEAR, AWAKE,
        ])
        self.assertEqual(_asked("墜落傷", io), [
            "墜落狀況", "墜落高度", "報案身分", "性別", "患者位置", "卡住位置", "報案人位置", "意識",
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

    def test_unresponsive_not_breathing_transfers_to_human(self) -> None:
        with self.assertRaises(TransferToHumanError):
            _run("墜落傷", [
                self.JUMPED, self.FIVE_F, FAMILY, MALE_40, self.GROUND, self.NEAR, COMA,
                NO_BREATHING,
            ])

    def test_abnormal_breathing_transfers_to_human(self) -> None:
        """呼吸不正常也轉真人（使用者 11/02 決定），講原程式轉人工那句。"""
        with self.assertRaises(TransferToHumanError):
            _run("墜落傷", [
                self.JUMPED, self.FIVE_F, FAMILY, MALE_40, self.GROUND, self.NEAR, COMA,
                ("呼吸很微弱、斷斷續續", {"breathing": "呼吸不正常"}),
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
        engine, io = _run("上吊", [self.NOT_UNTIED, self.NO_BREAK, PASSER, MALE_40],
                          hanging_location="橋墩下面")
        self.assertEqual(_asked("上吊", io), ["上吊狀況", "破門需求", "報案身分", "性別"])
        self.assertEqual(engine.case.main_category, "緊急救援")

    def test_remote_place_said_later_still_escalates(self) -> None:
        """患者位置那題已經過了，報案人回答報案身分時才講橋墩：還是要改判。"""
        engine, _ = _run("上吊", [
            self.NOT_UNTIED, self.NO_BREAK,
            ("不認識，他吊在橋墩那邊", {"caller_relation": "不認識", "hanging_location": "橋墩"}),
            MALE_40,
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


class ChangedAnswerTests(unittest.TestCase):
    """報案人改口：救護答案跟火警一樣以最新講的為準。"""

    def _engine(self) -> SopEngine119:
        engine = SopEngine119(io=ScriptedIO([]), llm_extractor=FakeLLM({}))  # type: ignore[arg-type]
        engine.case.main_category = "救護"
        return engine

    def test_symptom_follows_latest(self) -> None:
        """病徵先說「不舒服」、被追問後說肚子不舒服：病徵要更新，不能停在第一句。"""
        engine = self._engine()
        engine._apply_extracted_fields({"symptoms": "不舒服"})
        engine._apply_extracted_fields({"symptoms": "腹痛及身體不適"})
        self.assertEqual(engine.case.symptoms, "腹痛及身體不適")

    def test_consciousness_changed_follows_latest(self) -> None:
        """意識先說醒著、後來說叫不醒：意識改成昏迷；不寫廠商的「是否有意識」。"""
        engine = self._engine()
        engine._apply_extracted_fields({"consciousness_level": "意識清醒"})
        engine._apply_extracted_fields({"consciousness_level": "昏迷"})
        self.assertEqual(engine.case.consciousness_level, "昏迷")
        self.assertIsNone(engine.case.consciousness)

    def test_free_text_field_takes_latest_answer(self) -> None:
        """燒燙傷原因這類照報案人說的記的欄位：「不是熱水，是熱油」→ 改成熱油。"""
        engine = self._engine()
        engine._apply_extracted_fields({"burn_cause": "熱水"})
        engine._apply_extracted_fields({"burn_cause": "熱油"})
        self.assertEqual(engine.case.burn_cause, "熱油")

    def test_not_mentioned_keeps_answer(self) -> None:
        """這一句沒講到（抽出 null）不會把已經記下的答案清掉。"""
        engine = self._engine()
        engine._apply_extracted_fields({"burn_cause": "熱水"})
        engine._apply_extracted_fields({"burn_cause": None})
        self.assertEqual(engine.case.burn_cause, "熱水")


class GeWanTests(unittest.TestCase):
    WRIST_KNIFE = ("手腕，用美工刀", {"injury_severity": "手腕割傷", "cutting_tool": "美工刀"})
    REMOVED = ("拿走了", {"tool_status": "已移除"})

    def test_family_awake_then_reminder(self) -> None:
        _, io = _run("割腕", [self.WRIST_KNIFE, self.REMOVED, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("割腕", io), [
            "傷勢", "工具移除", "報案身分", "性別", "意識", STOP_BLEEDING_REMINDER,
        ])

    def test_caller_is_patient_no_consciousness(self) -> None:
        _, io = _run("割腕", [self.WRIST_KNIFE, self.REMOVED, MALE_40], caller_relation="本人")
        self.assertEqual(_asked("割腕", io), ["傷勢", "工具移除", "性別", STOP_BLEEDING_REMINDER])


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
    HOT_WATER = ("被熱水燙到", {"burn_cause": "熱水"})
    BLISTER = ("大腿起水泡，一個手掌大", {"injury_severity": "大腿起水泡，約一個手掌大"})

    def test_family_awake_then_reminders(self) -> None:
        _, io = _run("燒燙傷", [self.HOT_WATER, self.BLISTER, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("燒燙傷", io), [
            "燒燙傷原因", "燙傷傷勢", "報案身分", "性別", "意識", *BURN_REMINDERS,
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


class JiBingTests(unittest.TestCase):
    """01-急病：照 1028 題目表問；沒有觸發情境、肚子起伏、服藥探問（使用者 11/02 決定）。"""
    CHEST_PAIN = ("他胸口很痛", {"symptoms": "胸或上腹(疼痛或壓迫)"})

    def test_family_awake(self) -> None:
        _, io = _run("急病", [self.CHEST_PAIN, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("急病", io), ["病徵", "報案身分", "性別", "意識"])

    def test_unresponsive_breathing_continues(self) -> None:
        _, io = _run("急病", [self.CHEST_PAIN, FAMILY, MALE_40, COMA, BREATHING])
        self.assertEqual(_asked("急病", io), ["病徵", "報案身分", "性別", "意識", "呼吸"])

    def test_not_breathing_transfers_without_vendor_lines(self) -> None:
        """無呼吸直接轉真人：不問肚子起伏，也不講「開擴音教你做急救」這類觸發語句。"""
        steps = [self.CHEST_PAIN, FAMILY, MALE_40, COMA, NO_BREATHING]
        io = ScriptedIO([answer for answer, _ in steps])
        engine = SopEngine119(io=io, llm_extractor=FakeLLM(dict(steps)))  # type: ignore[arg-type]
        engine.case.main_category = "救護"
        engine.case.sub_category = "急病"
        with self.assertRaises(TransferToHumanError):
            get_handler("急病").run_subtype_flow(engine)
        self.assertEqual(_asked("急病", io), [
            "病徵", "報案身分", "性別", "意識", "呼吸", TRANSFER_LINE,
        ])


class GeneralInjuryTests(unittest.TestCase):
    """10-一般受傷：還沒標 OK，先照題目表問給承辦實測。"""
    FELL = ("在家跌倒", {"injury_cause": "跌倒", "injury_place": "住家室內"})
    KNEE = ("膝蓋", {"injury_location": "膝蓋"})
    BLEEDING = ("有在流血", {"injury_severity": "流血"})
    FINGER_CUT = ("被機器切斷手指", {"injury_cause": "機器切斷手指"})
    SEVERED = ("手指斷掉了，一直流血", {"injury_severity": "手指斷掉、流血"})
    SEVERED_FINGER_REMINDER = (
        "請將斷掉的手指用乾淨的塑膠袋裝好，再放進另一個裝冰水的袋子，"
        "不要直接碰到冰塊，等一下交給救護人員。"
    )

    def test_family_awake_then_reminder(self) -> None:
        """發生場所是被動題，報案人講到就記、不問。"""
        engine, io = _run("一般受傷", [self.FELL, self.KNEE, self.BLEEDING, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("一般受傷", io), [
            "受傷原因", "受傷部位", "傷勢", "報案身分", "性別", "意識", STOP_BLEEDING_REMINDER,
        ])
        self.assertEqual(engine.case.injury_place, "住家室內")

    def test_severed_finger_reminder(self) -> None:
        _, io = _run("一般受傷", [self.FINGER_CUT, ("右手", {"injury_location": "右手"}),
                                  self.SEVERED, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("一般受傷", io)[-2:], [
            STOP_BLEEDING_REMINDER, self.SEVERED_FINGER_REMINDER,
        ])

    def test_passer_not_on_scene_skips_gender_and_consciousness(self) -> None:
        _, io = _run("一般受傷", [self.FELL, self.KNEE, self.BLEEDING, PASSER],
                     caller_location="不在現場")
        self.assertEqual(_asked("一般受傷", io), [
            "受傷原因", "受傷部位", "傷勢", "報案身分", STOP_BLEEDING_REMINDER,
        ])


class LuDaoTests(unittest.TestCase):
    """14-路倒：還沒標 OK，先照題目表問給承辦實測。"""
    DRUNK = ("看起來喝醉了", {"collapse_status": "喝醉"})
    UNWELL = ("好像身體不舒服", {"collapse_status": "身體不舒服"})
    ONE = ("一個", {"patient_count": "1人"})
    RED_COAT = ("穿紅色外套", {"patient_appearance": "穿紅色外套"})

    def test_family_awake(self) -> None:
        engine, io = _run("路倒", [self.UNWELL, self.ONE, self.RED_COAT, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("路倒", io), [
            "路倒狀況", "患者人數", "患者外觀特徵", "報案身分", "性別", "意識",
        ])
        self.assertIsNone(engine.case.drinking_status)

    def test_drunk_also_records_drinking(self) -> None:
        """xlsx 備註：路倒狀況回答喝醉，是否飲酒也記成有喝酒。"""
        engine, _ = _run("路倒", [self.DRUNK, self.ONE, self.RED_COAT, FAMILY, MALE_40, AWAKE])
        self.assertEqual(engine.case.drinking_status, "有喝酒")

    def test_passer_not_on_scene_skips_gender_and_consciousness(self) -> None:
        _, io = _run("路倒", [self.UNWELL, self.ONE, self.RED_COAT, PASSER],
                     caller_location="不在現場")
        self.assertEqual(_asked("路倒", io), ["路倒狀況", "患者人數", "患者外觀特徵", "報案身分"])


class CheHuoTests(unittest.TestCase):
    """02-車禍：還沒標 OK，先照題目表問給承辦實測。"""
    CAR_SCOOTER = ("汽車撞機車", {"crash_vehicles": "汽車撞機車"})
    ONE = ("一個", {"patient_count": "1人"})
    NOT_TRAPPED = ("沒有", {"crash_trapped": "無人受困"})
    TRAPPED = ("有一個卡在車子底下", {"crash_trapped": "有人受困"})

    def test_family_awake(self) -> None:
        engine, io = _run("車禍", [self.CAR_SCOOTER, self.ONE, self.NOT_TRAPPED, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("車禍", io), [
            "事故車種", "患者人數", "有無人員受困", "報案身分", "性別", "意識",
        ])
        self.assertEqual(engine.case.main_category, "救護")

    def test_passer_not_on_scene_skips_gender_and_consciousness(self) -> None:
        _, io = _run("車禍", [self.CAR_SCOOTER, self.ONE, self.NOT_TRAPPED, PASSER],
                     caller_location="不在現場")
        self.assertEqual(_asked("車禍", io), ["事故車種", "患者人數", "有無人員受困", "報案身分"])

    def test_trapped_escalates_without_speaking_and_keeps_asking(self) -> None:
        """xlsx 備註：有人受困 → 改判緊急救援；不講話，車禍題目照樣問完，次案類維持車禍。"""
        engine, io = _run("車禍", [self.CAR_SCOOTER, self.ONE, self.TRAPPED, FAMILY, MALE_40, AWAKE])
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertEqual(engine.case.sub_category, "車禍")
        self.assertEqual(_asked("車禍", io), [
            "事故車種", "患者人數", "有無人員受困", "報案身分", "性別", "意識",
        ])


class DaJiaShouShangTests(unittest.TestCase):
    """09-打架受傷：還沒標 OK，先照題目表問給承辦實測。"""
    STOPPED = ("已經沒在打了", {"conflict_status": "已停止"})
    ONGOING = ("還在打", {"conflict_status": "進行中"})
    ONE = ("一個", {"patient_count": "1人"})
    KNIFE = ("有拿刀", {"weapon_held": "刀"})

    def test_stopped_skips_weapon(self) -> None:
        _, io = _run("打架受傷", [self.STOPPED, self.ONE, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("打架受傷", io), [
            "衝突狀況", "患者人數", "報案身分", "性別", "意識",
        ])

    def test_ongoing_asks_weapon(self) -> None:
        engine, io = _run("打架受傷", [self.ONGOING, self.ONE, self.KNIFE, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("打架受傷", io), [
            "衝突狀況", "患者人數", "持械", "報案身分", "性別", "意識",
        ])
        self.assertEqual(engine.case.weapon_held, "刀")

    def test_passer_not_on_scene_skips_gender_and_consciousness(self) -> None:
        _, io = _run("打架受傷", [self.STOPPED, self.ONE, PASSER], caller_location="不在現場")
        self.assertEqual(_asked("打架受傷", io), ["衝突狀況", "患者人數", "報案身分"])


class YunFuDaiChanTests(unittest.TestCase):
    """12-孕婦待產：還沒標 OK，先照題目表問給承辦實測。"""
    REGULAR = ("有規則陣痛", {"contractions": "規則陣痛"})
    WATER_BROKEN = ("羊水已經破了", {"contractions": "已經破水"})
    DUE = ("預產期下禮拜，三十九週", {"due_date": "下禮拜", "pregnancy_week": "39週"})
    SECOND = ("第二胎，單胞胎", {"multiple_pregnancy": "第2胎、單胞胎"})
    NORMAL = ("都正常", {"prenatal_history": "產檢正常"})
    AGE_30 = ("三十歲", {"patient_age": "30歲"})
    LIE_ON_LEFT = "請孕婦本人往左邊側躺，先不要用力。"
    TOWEL = "如果羊水破了，請拿乾淨的毛巾墊在孕婦屁股下方。"

    def test_family_awake_then_lie_on_left(self) -> None:
        """報案身分先問；清醒才講左側躺；沒有破水不講墊毛巾。性別是被動題，不問。"""
        _, io = _run("孕婦待產", [FAMILY, self.REGULAR, self.DUE, self.SECOND, self.NORMAL,
                                  self.AGE_30, AWAKE])
        self.assertEqual(_asked("孕婦待產", io), [
            "報案身分", "陣痛狀況", "預產期", "胎次與胎數", "產檢狀況", "年齡", "意識",
            self.LIE_ON_LEFT,
        ])

    def test_neighbor_skips_pregnancy_details(self) -> None:
        """預產期、週數、胎次、產檢只問本人、家人、朋友；年齡的條件不同，鄰居照問。"""
        _, io = _run("孕婦待產", [NEIGHBOR, self.REGULAR, self.AGE_30, AWAKE])
        self.assertEqual(_asked("孕婦待產", io), [
            "報案身分", "陣痛狀況", "年齡", "意識", self.LIE_ON_LEFT,
        ])

    def test_water_broken_then_towel(self) -> None:
        _, io = _run("孕婦待產", [FAMILY, self.WATER_BROKEN, self.DUE, self.SECOND, self.NORMAL,
                                  self.AGE_30, AWAKE])
        self.assertEqual(_asked("孕婦待產", io)[-2:], [self.LIE_ON_LEFT, self.TOWEL])

    def test_due_date_only_then_ask_week(self) -> None:
        _, io = _run("孕婦待產", [FAMILY, self.REGULAR, ("下禮拜", {"due_date": "下禮拜"}),
                                  ("三十九週", {"pregnancy_week": "39週"}), self.SECOND,
                                  self.NORMAL, self.AGE_30, AWAKE])
        self.assertEqual(_asked("孕婦待產", io)[:4], [
            "報案身分", "陣痛狀況", "預產期", "現在懷孕幾週了？",
        ])

    def test_caller_is_patient_also_lie_on_left(self) -> None:
        """本人報案不問意識，但能講電話就是清醒，也講左側躺。"""
        _, io = _run("孕婦待產", [self.REGULAR, self.DUE, self.SECOND, self.NORMAL, self.AGE_30],
                     caller_relation="本人")
        self.assertEqual(_asked("孕婦待產", io), [
            "陣痛狀況", "預產期", "胎次與胎數", "產檢狀況", "年齡", self.LIE_ON_LEFT,
        ])

    def test_keyword_rule_uses_name_from_xlsx(self) -> None:
        """名稱統一用「孕婦待產」：關鍵字規則判出的名稱也要查得到孕婦的 handler。"""
        from subcategory_keywords_119 import match_rescue_subcategory

        name = match_rescue_subcategory("我老婆羊水破了要生了")[0]
        self.assertEqual(name, "孕婦待產")
        self.assertEqual(type(get_handler(name)).__name__, "YunFuJiChanHandler")


class CompoundFollowUpTests(unittest.TestCase):
    """一句問兩個關鍵要素的題目，報案人只答一個時，用單問句補問另一個。"""

    def test_gender_only_then_ask_age(self) -> None:
        _, io = _run("割腕", [
            GeWanTests.WRIST_KNIFE, GeWanTests.REMOVED, FAMILY,
            ("是女生", {"patient_gender": "女性"}), ("三十歲", {"patient_age": "30歲"}), AWAKE,
        ])
        self.assertEqual(_asked("割腕", io), [
            "傷勢", "工具移除", "報案身分", "性別", "請問患者大概幾歲？", "意識",
            STOP_BLEEDING_REMINDER,
        ])

    def test_wrist_injury_only_then_ask_tool(self) -> None:
        _, io = _run("割腕", [
            ("手腕", {"injury_severity": "手腕割傷"}), ("美工刀", {"cutting_tool": "美工刀"}),
            GeWanTests.REMOVED, FAMILY, MALE_40, AWAKE,
        ])
        self.assertEqual(_asked("割腕", io), [
            "傷勢", "是用什麼工具受傷的？", "工具移除", "報案身分", "性別", "意識",
            STOP_BLEEDING_REMINDER,
        ])

    def test_medicine_only_then_ask_amount(self) -> None:
        _, io = _run("吞食藥物", [
            ("安眠藥", {"ingested_substance": "安眠藥"}), ("二十顆", {"drug_amount": "約20顆"}),
            FAMILY, MALE_40, AWAKE,
        ])
        self.assertEqual(_asked("吞食藥物", io), [
            "服用藥物", "知道大概吃了幾顆嗎？", "報案身分", "性別", "意識", MEDICINE_BAG_REMINDER,
        ])


class DaoShangTests(unittest.TestCase):
    """03-刀傷(切割傷)：還沒標 OK，先照 1102 題目表問給承辦實測。"""
    ACCIDENT = ("切菜不小心割到", {"injury_cause": "不小心割到"})
    HAND = ("手指", {"injury_location": "手指"})
    BLEEDING = ("一直流血", {"injury_severity": "一直流血"})

    def test_family_awake(self) -> None:
        _, io = _run("刀傷(切割傷)", [self.ACCIDENT, self.HAND, self.BLEEDING, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("刀傷(切割傷)", io), [
            "受傷原因", "受傷部位", "傷勢", "報案身分", "性別", "意識",
        ])


class DianJiShangTests(unittest.TestCase):
    """07-電擊傷：還沒標 OK，先照 1102 題目表問給承辦實測。"""
    HIGH_VOLTAGE = ("被高壓電電到", {"electric_type": "高壓電"})
    POWER_OFF = ("已經斷電了", {"power_off": "已斷電"})
    ONE = ("一個", {"patient_count": "1人"})
    WORKER = ("是工地的工人", {"patient_identity": "工地工人"})

    def test_family_awake(self) -> None:
        _, io = _run("電擊傷", [self.HIGH_VOLTAGE, self.POWER_OFF, self.ONE, self.WORKER,
                                FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("電擊傷", io), [
            "電擊種類", "現場是否已斷電", "患者人數", "傷患身分", "報案身分", "性別", "意識",
        ])


class NiShuiTests(unittest.TestCase):
    """11-溺水：還沒標 OK，先照 1102 題目表問給承辦實測。"""
    ASHORE = ("已經拉上來了", {"drowning_status": "已拉上岸"})
    IN_WATER = ("還在水裡", {"drowning_status": "未拉上岸"})
    SLIPPED = ("失足掉下去的", {"drowning_cause": "失足落水"})
    ONE = ("一個", {"patient_count": "1人"})

    def test_ashore_stays_rescue(self) -> None:
        engine, io = _run("溺水", [self.ASHORE, self.SLIPPED, self.ONE, FAMILY, MALE_40, AWAKE])
        self.assertEqual(_asked("溺水", io), [
            "溺水狀況", "溺水原因", "患者人數", "報案身分", "性別", "意識",
        ])
        self.assertEqual(engine.case.main_category, "救護")

    def test_in_water_escalates_without_speaking_and_keeps_asking(self) -> None:
        """xlsx 備註：還在水裡 → 改判緊急救援；不講話，溺水題目照樣問完，次案類維持溺水。"""
        engine, io = _run("溺水", [self.IN_WATER, self.SLIPPED, self.ONE, FAMILY, MALE_40, AWAKE])
        self.assertEqual(engine.case.main_category, "緊急救援")
        self.assertEqual(engine.case.sub_category, "溺水")
        self.assertEqual(_asked("溺水", io), [
            "溺水狀況", "溺水原因", "患者人數", "報案身分", "性別", "意識",
        ])


class SubCategoryToExtractorTests(unittest.TestCase):
    """救護抽取時要告訴抽取器目前次案類（刀傷的受傷原因跟其他案類的參考範圍不同）。"""

    def test_engine_passes_sub_category(self) -> None:
        seen: list = []

        class RecordingLLM(FakeLLM):
            def extract_general_fields(self, caller_text, question=None, **kwargs) -> dict:
                seen.append(kwargs.get("sub_category"))
                return super().extract_general_fields(caller_text, question)

        io = ScriptedIO(["切菜不小心割到"])
        engine = SopEngine119(io=io, llm_extractor=RecordingLLM({}))  # type: ignore[arg-type]
        engine.case.main_category = "救護"
        engine.case.sub_category = "刀傷(切割傷)"
        engine._ask_and_extract("請問是自己不小心割到，還是被別人弄傷的？")
        self.assertIn("刀傷(切割傷)", seen)


class OkTablesTests(unittest.TestCase):

    # 7 張 OK 表，加上還沒標 OK、先照表問給承辦實測的案類
    TABLE_SUBTYPES = ("墜落傷", "燒燙傷", "精神異常", "吞食藥物", "上吊", "燒炭", "割腕",
                      "急病", "一般受傷", "路倒", "車禍", "打架受傷", "孕婦待產",
                      "刀傷(切割傷)", "槍傷", "壓傷", "電擊傷", "溺水", "喝農藥", "吸入廢氣", "其它")

    def test_tables_match_case_type_qa(self) -> None:
        """照題目表問的案類，跟程式讀的 CaseTypeQA.xlsx 逐題對得上（題號靠位置算）。"""
        path = Path(__file__).resolve().parents[1] / "scripts" / "CaseTypeQA.xlsx"
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        for name in self.TABLE_SUBTYPES:
            with self.subTest(name=name):
                rows = [r for r in ws.iter_rows(values_only=True) if r[1] == f"救護-{name}"]
                self.assertEqual([r[5] for r in rows], [i.element for i in EMS_QUESTIONS[name]])

    def test_no_trigger_scenarios(self) -> None:
        """照題目表問的案類不用觸發情境（使用者 10/28 決定）。"""
        for name in self.TABLE_SUBTYPES:
            with self.subTest(name=name):
                self.assertFalse(hasattr(get_handler(name), "_send_trigger_responses"))


if __name__ == "__main__":
    unittest.main()
