"""
緊急救援題目進行中換成另一個次案類。

硬規則或分類器換類之後，舊專屬題停止，新次案類只問還沒填的題，
已經記入的關係、性別、意識不再問。
"""

from __future__ import annotations

import types
import unittest

from emergency_accident_119 import (
    BREATHING_QUESTION,
    CONSCIOUSNESS_QUESTION,
    DISPATCH_LINE,
    PATIENT_QUESTION,
    RELATION_QUESTION,
)
from emergency_rescue_subs_119 import (
    DROWN_QUESTIONS,
    MODE_PASSIVE,
    asked_questions,
)
from handlers.緊急救援通用 import JinJiJiuYuanGenericHandler
from sop_119_engine import DialogueIO, SopEngine119

VEHICLE_QUESTION = "是什麼車跟什麼車車禍？"
INJURY_QUESTION = "有人受傷嗎？傷在哪裡？"


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
    def __init__(self, by_answer: dict[str, dict], remapped: dict | None = None):
        self.by_answer = by_answer
        self.remapped = remapped or {}

    def extract_general_fields(self, caller_text, question=None, *,
                               main_category=None, call_type=None, fire_tab=None) -> dict:
        return dict(self.by_answer.get((caller_text or "").strip(), {}))

    def extract_caller_info(self, question, text, include_address=False):
        return dict(self.by_answer.get((text or "").strip(), {}))

    def generate_summary(self, transcript_texts, filled_fields):
        return "換類測試摘要"

    def remap_sop_fields_for_subcategory(self, **_kwargs):
        return dict(self.remapped)


class SwitchBert:
    """全文出現「河」才判成溺水，而且要比車禍救助更有把握。"""

    def __init__(self, drown_conf: float = 0.92, accident_conf: float = 0.04):
        self.drown_conf = drown_conf
        self.accident_conf = accident_conf

    def predict(self, text, main_cat):
        if "河" in (text or ""):
            probs = {"溺水": self.drown_conf, "車禍救助": self.accident_conf}
            label = "溺水"
            conf = self.drown_conf
        else:
            probs = {"車禍救助": 0.9, "溺水": 0.05}
            label = "車禍救助"
            conf = 0.9
        return types.SimpleNamespace(
            final_label=label,
            classifier_conf=conf,
            all_probs=probs,
        )


def _run(steps, *, bert=None, remapped=None):
    io = ScriptedIO([answer for answer, _fields in steps])
    llm = AnswerLLM(
        {answer: fields for answer, fields in steps},
        remapped=remapped,
    )
    engine = SopEngine119(io=io, llm_extractor=llm, sub_classifiers=bert)  # type: ignore[arg-type]
    engine.case.main_category = "緊急救援"
    engine.case.sub_category = "車禍救助"
    engine.case.sub_conf = 0.9
    engine.case.incident_description = "兩台車撞在一起"
    engine.case.address_confirmed = True
    engine.case.address = "板橋區文化路一段10號"
    engine.case.transcript = [{"role": "caller", "text": "兩台車撞在一起"}]
    handler = JinJiJiuYuanGenericHandler()
    handler.run_generic_flow(engine)
    handler.collect_caller_info(engine)
    return engine, io


class EmergencySubSwitchTests(unittest.TestCase):
    def test_hard_rule_stops_accident_questions_and_keeps_shared_answers(self) -> None:
        engine, io = _run([
            (
                "聽到氣爆聲 我是他朋友 男生四十歲 人還清醒",
                {
                    "accident_vehicle_type": "機車車禍",
                    "caller_relation": "朋友",
                    "patient_gender": "男",
                    "patient_age": "四十歲",
                    "consciousness": True,
                },
            ),
            ("還有呼吸", {"breathing": True}),
            ("王小明 0912345678", {"caller_name": "王小明", "caller_contact": "0912345678"}),
        ])
        self.assertEqual(engine.case.sub_category, "氣爆")
        self.assertEqual(engine.case.suspected_sub_category, "氣爆")
        self.assertIsNone(engine.case.accident_vehicle_type)
        self.assertEqual(engine.case.caller_relation, "朋友")
        self.assertEqual(engine.case.patient_gender, "男")
        self.assertEqual(engine.case.patient_age, "四十歲")
        self.assertIs(engine.case.consciousness, True)
        self.assertIs(engine.case.breathing, True)
        self.assertEqual(io.messages[0], DISPATCH_LINE)
        self.assertIn(VEHICLE_QUESTION, io.messages)
        self.assertNotIn(INJURY_QUESTION, io.messages)
        self.assertNotIn(RELATION_QUESTION, io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertIn(BREATHING_QUESTION, io.messages)
        self.assertLess(
            io.messages.index(VEHICLE_QUESTION),
            io.messages.index(BREATHING_QUESTION),
        )
        self.assertEqual(engine.case.result, "dispatched")

    def test_classifier_switches_to_drowning_and_skips_filled_questions(self) -> None:
        drown_questions = [
            item.question
            for item in asked_questions(DROWN_QUESTIONS)
            if item.field not in ("drown_gender", "drown_age")
        ]
        steps = [(
            "人掉進河裡了 我是他朋友 男生四十歲",
            {
                "accident_vehicle_type": "機車車禍",
                "caller_relation": "朋友",
                "patient_gender": "男",
                "patient_age": "四十歲",
            },
        )]
        for question in drown_questions:
            steps.append((f"答：{question}", {}))
        steps.append(("還有呼吸", {"breathing": True}))
        steps.append(("林小姐 0922333444", {
            "caller_name": "林小姐", "caller_contact": "0922333444",
        }))
        engine, io = _run(
            steps,
            bert=SwitchBert(),
            remapped={
                "drown_gender": "男性",
                "drown_age": "四十歲",
                "caller_relation": "別人",
            },
        )
        self.assertEqual(engine.case.sub_category, "溺水")
        self.assertIsNone(engine.case.suspected_sub_category)
        self.assertIsNone(engine.case.accident_vehicle_type)
        self.assertEqual(engine.case.caller_relation, "朋友")
        self.assertEqual(engine.case.drown_gender, "男性")
        self.assertEqual(engine.case.drown_age, "四十歲")
        self.assertIn(VEHICLE_QUESTION, io.messages)
        self.assertNotIn(INJURY_QUESTION, io.messages)
        for question in drown_questions:
            self.assertIn(question, io.messages)
            self.assertLess(
                io.messages.index(VEHICLE_QUESTION),
                io.messages.index(question),
            )
        gender_q = next(item.question for item in DROWN_QUESTIONS if item.field == "drown_gender")
        age_q = next(item.question for item in DROWN_QUESTIONS if item.field == "drown_age")
        passive_q = next(item.question for item in DROWN_QUESTIONS if item.mode == MODE_PASSIVE)
        self.assertNotIn(gender_q, io.messages)
        self.assertNotIn(age_q, io.messages)
        self.assertNotIn(passive_q, io.messages)
        self.assertNotIn(RELATION_QUESTION, io.messages)
        self.assertNotIn(PATIENT_QUESTION, io.messages)
        self.assertNotIn(CONSCIOUSNESS_QUESTION, io.messages)
        self.assertIn(BREATHING_QUESTION, io.messages)
        self.assertEqual(engine.case.result, "dispatched")

    def test_narrow_margin_does_not_leave_the_accident_questions(self) -> None:
        engine, io = _run([
            ("人掉進河裡了", {"accident_vehicle_type": "機車車禍"}),
            ("沒有人受傷", {"accident_injury": "無"}),
            ("沒有人被困", {"accident_trapped": "無人受困"}),
            ("人還清醒", {"accident_consciousness": "意識清醒"}),
            ("車子沒有燃燒", {"accident_burning": "車子沒有燃燒"}),
            ("我是路人", {"accident_caller_role": "路人"}),
            ("沒擋到路", {"accident_traffic_impact": "沒擋到路"}),
            ("他朋友", {"caller_relation": "朋友"}),
            ("男生四十歲", {"patient_gender": "男", "patient_age": "四十歲"}),
            ("還有呼吸", {"breathing": True}),
            ("王小明 0912345678", {"caller_name": "王小明", "caller_contact": "0912345678"}),
        ], bert=SwitchBert(drown_conf=0.55, accident_conf=0.48))
        self.assertEqual(engine.case.sub_category, "車禍救助")
        self.assertEqual(engine.case.accident_vehicle_type, "機車車禍")
        self.assertIn(INJURY_QUESTION, io.messages)
        role_q = next(item.question for item in DROWN_QUESTIONS if item.field == "drown_caller_role")
        self.assertNotIn(role_q, io.messages)


if __name__ == "__main__":
    unittest.main()
