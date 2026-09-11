"""
盡可能完整覆蓋火警垂片：27 案類映射、四張垂片問句、Streamlit 階段、
BERT 填碼、Q1 轉人工、Q2 預設輕微、代碼正規化。

執行：
  cd /root/work/119 && python -m unittest tests.test_fire_tabs_complete_119 -v
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from app_119 import (
    _FIRE_BRANCH_STAGES,
    _FIRE_PREFIX,
    _FIRE_SUFFIX,
    _STAGE_LABELS_DICT,
    _get_visible_stages,
)
from case_info_119 import CaseInfo119
from fire_tab_map_119 import (
    BERT_FIRE_LABELS,
    FIRE_BERT_CONF_THRESHOLD,
    FIRE_SUBTYPES,
    ROUTE_Q1,
    ROUTE_Q2,
    SAFETY_MESSAGE,
    TAB_A,
    TAB_B1,
    TAB_B2,
    TAB_C,
    FIELD_LABELS_ZH,
    TAB_QUESTIONS,
    apply_bert_subtype_to_case,
    apply_route_q1,
    apply_route_q2,
    codes_for_label,
    infer_route_q1,
    infer_route_q2,
    normalize_fire_field,
    resolve_fire_tab,
    tab_for_codes,
    tab_for_subtype,
)
from handlers.火警通用 import HuoJingGenericHandler
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError


class ScriptedIO(DialogueIO):
    def __init__(self, answers: list[str]):
        self.answers = list(answers)
        self.messages: list[str] = []

    def say(self, text: str) -> None:
        self.messages.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError(f"測試回答已用盡；已說出：{self.messages}")
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
        return SimpleNamespace(final_label=self.label, classifier_conf=self.conf)


class CompleteFireExtractor:
    """依受理員問句填垂片代碼，覆蓋 A/B1/B2/C 及較多樣細類。"""

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

        if "房子在燒嗎" in question:
            if any(k in text for k in ("不是", "其他", "其它", "車子", "草木", "垃圾")):
                out["fire_incident_type"] = 1
            elif any(k in text for k in ("房子", "房屋", "透天", "公寓", "大樓", "倉庫")):
                out["fire_incident_type"] = 0
            elif text in ("是", "對", "对", "有", "嗯"):
                out["fire_incident_type"] = 0

        if "車子在燒，還是山上" in question:
            if any(k in text for k in ("車", "汽車", "機車", "隧道", "船", "飛機", "火車", "軌道")):
                out["non_building_fire"] = 0
            elif any(k in text for k in ("山", "草", "林", "田")):
                out["non_building_fire"] = 0
            elif any(k in text for k in ("垃圾", "電線", "瓦斯", "警報", "都不是", "查看")):
                out["non_building_fire"] = 1
                if "垃圾" in text:
                    out["minor_fire_code"] = 0
                elif "電線" in text:
                    out["minor_fire_code"] = 1
                elif "瓦斯" in text:
                    out["minor_fire_code"] = 2
                elif "警報" in text:
                    out["minor_fire_code"] = 3
                elif "查看" in text:
                    out["minor_fire_code"] = 4

        if "哪一種建築物" in question:
            mapping = (
                ("透天", "10"), ("公寓", "11"), ("集合", "11"), ("倉庫", "12"),
                ("旅館", "20"), ("百貨", "20"), ("車站", "21"), ("電影院", "22"),
                ("學校", "23"), ("醫院", "23"), ("毒災", "24"), ("市場", "25"),
                ("工廠", "25"), ("石化", "26"), ("古蹟", "27"), ("地下", "28"),
                ("高層", "29"),
            )
            for key, code in mapping:
                if key in text:
                    out["building_type_code"] = code
                    break
            else:
                out["building_type_code"] = "00"

        if "火苗竄出來" in question:
            out["has_flame"] = 0 if any(k in text for k in ("沒", "只有煙")) else 1
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
            out["spread_risk"] = 0 if any(k in text for k in ("沒", "不會")) else 1
        if "還有沒有人沒出來" in question:
            out["people_trapped_code"] = 0 if any(
                k in text for k in ("沒有人", "沒人", "無人", "都出來")
            ) else 1
        if "總共幾層樓" in question:
            n = re.search(r"(\d+)", text)
            if n:
                floors = int(n.group(1))
                out["building_floors_code"] = (
                    1 if floors <= 3 else 2 if floors <= 10 else 3 if floors <= 15 else 4
                )
        if "幾樓開始燒" in question:
            if "地下" in text:
                out["fire_floor_code"] = 1
            else:
                n = re.search(r"(\d+)", text)
                if n:
                    floors = int(n.group(1))
                    out["fire_floor_code"] = (
                        2 if floors <= 3 else 3 if floors <= 10 else 4 if floors <= 15 else 5
                    )
        if "什麼蓋的" in question:
            if "木" in text:
                out["building_structure"] = 1
            elif "連造" in text:
                out["building_structure"] = 3
            elif "鐵皮" in text:
                out["building_structure"] = 2
            elif "磚" in text:
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
                out["burn_area_code"] = (
                    1 if n <= 50 else 2 if n <= 100 else 3 if n <= 300 else 4 if n <= 500 else 5
                )
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
            pairs = (
                ("機車", 1), ("汽車", 0), ("隧道", 2), ("火車", 3), ("軌道", 3),
                ("捷運", 3), ("化學", 4), ("毒劑", 4), ("船", 5), ("飛機", 6),
            )
            for key, code in pairs:
                if key in text:
                    out["vehicle_wildfire_code"] = code
                    break
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
        self, caller_text: str, question: str | None = None, *, which: str = "q1",
    ) -> str | None:
        text = caller_text.strip()
        if which == "q1":
            if any(k in text for k in ("不是", "其他", "其它", "車子", "草木", "垃圾")):
                return "other"
            if any(k in text for k in ("房子", "房屋", "透天", "公寓", "倉庫")):
                return "building"
            if text in ("是", "對", "对", "有", "嗯"):
                return "building"
            return None
        if any(k in text for k in ("車", "汽車", "機車", "隧道", "船", "飛機", "軌道")):
            return "vehicle"
        if any(k in text for k in ("山", "草", "林", "田")):
            return "vegetation"
        if any(k in text for k in ("垃圾", "電線", "瓦斯", "警報", "都不是", "查看")):
            return "minor"
        return None

    def extract_address(self, caller_text: str, use_question: bool = False, include_floor: bool = True) -> dict:
        return {}

    def extract_caller_info(self, question: str, caller_text: str, include_address: bool = False) -> dict:
        phone = re.search(r"09\d{8}", caller_text)
        salutation = "先生" if "先生" in caller_text else ("小姐" if "小姐" in caller_text else None)
        return {
            "caller_name": None,
            "caller_contact": phone.group(0) if phone else None,
            "caller_salutation": salutation,
        }

    def check_fire_trigger_scenarios(self, caller_text: str, already_triggered: list[int]) -> list[int]:
        return []

    def generate_summary(self, transcript_texts: list[str], filled_fields: dict) -> str:
        return "火災完整測試摘要"


TAB_A_DETAIL = [
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
]
PHONE = "電話0912345678，我是先生"


def _run(answers: list[str], bert: FakeFireBert | None = None):
    io = ScriptedIO(answers)
    llm = CompleteFireExtractor()
    engine = SopEngine119(io=io, llm_extractor=llm, sub_classifiers=bert)  # type: ignore[arg-type]
    engine.case.main_category = "火警"
    handler = HuoJingGenericHandler()
    handler.run_generic_flow(engine)
    handler.collect_caller_info(engine)
    if io.answers:
        raise AssertionError(f"仍有未消耗回答：{io.answers}")
    return engine, io, llm


class FireMapCompleteTests(unittest.TestCase):
    def test_27_subtypes_have_tab_and_codes(self) -> None:
        self.assertEqual(len(FIRE_SUBTYPES), 27)
        names = [item.name for item in FIRE_SUBTYPES]
        self.assertEqual(len(names), len(set(names)))
        by_tab = {TAB_A: 13, TAB_B1: 7, TAB_B2: 2, TAB_C: 5}
        for tab, n in by_tab.items():
            self.assertEqual(sum(1 for item in FIRE_SUBTYPES if item.tab == tab), n)

        for item in FIRE_SUBTYPES:
            codes = codes_for_label(item.name)
            self.assertIsNotNone(codes)
            self.assertEqual(tab_for_subtype(item.name), item.tab)
            self.assertEqual(codes_for_label("火警-" + item.name)["sub_category"], item.name)
            derived = tab_for_codes(
                item.fire_incident_type,
                item.non_building_fire,
                item.vehicle_wildfire_code,
                item.minor_fire_code,
            )
            self.assertEqual(derived, item.tab, item.name)

    def test_bert_v2_13_labels_all_mapped(self) -> None:
        self.assertEqual(len(BERT_FIRE_LABELS), 13)
        for label in BERT_FIRE_LABELS:
            self.assertIsNotNone(codes_for_label(label), label)
            self.assertIn(tab_for_subtype(label), {TAB_A, TAB_B1, TAB_B2, TAB_C})

    def test_route_keywords(self) -> None:
        self.assertEqual(infer_route_q1("房子在燒"), "building")
        self.assertEqual(infer_route_q1("是"), "building")
        self.assertEqual(infer_route_q1("不是房子，是車子"), "other")
        self.assertEqual(infer_route_q1("其它東西"), "other")
        self.assertIsNone(infer_route_q1("嗯不知道"))

        self.assertEqual(infer_route_q2("汽車起火"), "vehicle")
        self.assertEqual(infer_route_q2("山上雜草"), "vegetation")
        self.assertEqual(infer_route_q2("都不是，垃圾"), "minor")
        self.assertIsNone(infer_route_q2("嗯"))

    def test_normalize_codes(self) -> None:
        self.assertEqual(normalize_fire_field("building_type_code", "透天厝"), "10")
        self.assertEqual(normalize_fire_field("building_type_code", 11), "11")
        self.assertEqual(normalize_fire_field("has_flame", "有火苗"), 1)
        self.assertEqual(normalize_fire_field("smoke_color_code", "黑煙"), 1)
        self.assertEqual(normalize_fire_field("vehicle_wildfire_code", "機車"), 1)
        self.assertEqual(normalize_fire_field("vehicle_wildfire_code", "船舶"), 5)
        self.assertEqual(normalize_fire_field("minor_fire_code", "瓦斯漏氣"), 2)
        self.assertEqual(normalize_fire_field("building_floors_code", "12樓"), 3)
        self.assertEqual(normalize_fire_field("fire_floor_code", "地下室"), 1)
        self.assertEqual(normalize_fire_field("burn_area_code", "80坪"), 2)
        self.assertEqual(normalize_fire_field("access_water_info", "小巷而且缺水"), 3)

    def test_apply_bert_fills_all_27_subtypes(self) -> None:
        for item in FIRE_SUBTYPES:
            with self.subTest(name=item.name):
                case = CaseInfo119()
                apply_bert_subtype_to_case(case, item.name, 0.91)
                self.assertEqual(case.sub_category, item.name)
                self.assertEqual(case.fire_incident_type, item.fire_incident_type)
                self.assertEqual(resolve_fire_tab(case), item.tab)
                self.assertEqual(case.fire_tab, item.tab)
                if item.building_type_code is not None:
                    self.assertEqual(case.building_type_code, item.building_type_code)
                if item.vehicle_wildfire_code is not None:
                    self.assertEqual(case.vehicle_wildfire_code, item.vehicle_wildfire_code)
                if item.minor_fire_code is not None:
                    self.assertEqual(case.minor_fire_code, item.minor_fire_code)

    def test_case_info_has_all_coded_fields(self) -> None:
        case = CaseInfo119()
        for key in FIELD_LABELS_ZH:
            self.assertTrue(hasattr(case, key), key)
            self.assertIsNone(getattr(case, key))


class StreamlitFireStageTests(unittest.TestCase):
    def test_all_tab_questions_have_stage_labels(self) -> None:
        for tab, items in TAB_QUESTIONS.items():
            for field, stage, question in items:
                self.assertIn(stage, _STAGE_LABELS_DICT, f"{tab} {stage}")
                self.assertTrue(question.strip())

    def test_visible_stages_switch_by_fire_tab(self) -> None:
        for tab, branch in _FIRE_BRANCH_STAGES.items():
            keys = [k for k, _ in _get_visible_stages("火警", None, fire_tab=tab)]
            for stage in branch:
                self.assertIn(stage, keys, f"{tab} missing {stage}")
            for other, other_branch in _FIRE_BRANCH_STAGES.items():
                if other == tab:
                    continue
                for stage in other_branch:
                    self.assertNotIn(stage, keys, f"{tab} should not show {stage}")
            self.assertTrue(keys.index("火警_route_1") < keys.index(branch[0]))
            self.assertTrue(keys.index(branch[-1]) < keys.index("火警_safety"))
            self.assertIn("火警_caller_info", keys)

    def test_prefix_suffix_include_new_fire_flow(self) -> None:
        self.assertIn("火警_route_1", _FIRE_PREFIX)
        self.assertIn("火警_route_2", _FIRE_PREFIX)
        self.assertNotIn("火警_initial_1", _FIRE_PREFIX)
        self.assertIn("火警_safety", _FIRE_SUFFIX)

    def test_branch_stages_match_tab_questions(self) -> None:
        for tab, items in TAB_QUESTIONS.items():
            stages = [stage for _field, stage, _q in items]
            self.assertEqual(_FIRE_BRANCH_STAGES[tab], stages)

    def test_tab_a_hides_q2_in_progress(self) -> None:
        keys_a = [k for k, _ in _get_visible_stages("火警", None, fire_tab=TAB_A)]
        keys_unknown = [k for k, _ in _get_visible_stages("火警", None, fire_tab=None)]
        keys_b1 = [k for k, _ in _get_visible_stages("火警", None, fire_tab=TAB_B1)]
        self.assertNotIn("火警_route_2", keys_a)
        self.assertIn("火警_route_2", keys_unknown)
        self.assertIn("火警_route_2", keys_b1)

    def test_streamlit_scenarios_cover_four_tabs(self) -> None:
        path = Path(__file__).with_name("streamlit_scenarios_119.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        fire = [s for s in data["scenarios"] if s.get("category") == "火警"]
        tabs = {s["expected"]["fire_tab"] for s in fire}
        self.assertEqual(tabs, {TAB_A, TAB_B1, TAB_B2, TAB_C})

    def test_classifier_loads_fire_v2(self) -> None:
        source = Path(__file__).resolve().parents[1].joinpath(
            "classifier_with_llm.py"
        ).read_text(encoding="utf-8")
        self.assertIn("TW-119-BERT-sub_火警_v2", source)
        self.assertRegex(source, r'"火警"\s*:\s*"TW-119-BERT-sub_火警_v2"')


class FireTabDialogueTests(unittest.TestCase):
    def test_tab_a_asks_every_question_then_safety(self) -> None:
        engine, io, _ = _run(["房子在燒", "透天厝", *TAB_A_DETAIL, PHONE])
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.building_type_code, "10")
        asked = "\n".join(io.messages)
        self.assertIn(ROUTE_Q1, asked)
        self.assertNotIn(ROUTE_Q2, asked)
        for _field, _stage, question in TAB_QUESTIONS[TAB_A]:
            self.assertIn(question, asked)
        self.assertIn(SAFETY_MESSAGE, asked)
        self.assertIn("先生還是小姐", asked)
        self.assertEqual(engine.case.result, "dispatched")

    def test_tab_a_other_building_types(self) -> None:
        cases = (
            ("集合住宅公寓", "11"),
            ("倉庫", "12"),
            ("旅館百貨", "20"),
            ("車站運輸中樞", "21"),
            ("電影院", "22"),
            ("學校醫院", "23"),
            ("毒災場所", "24"),
            ("傳統市場工廠", "25"),
            ("石化廠", "26"),
            ("古蹟", "27"),
            ("地下街", "28"),
            ("高層大樓", "29"),
        )
        for answer, code in cases:
            with self.subTest(answer=answer):
                engine, _, _ = _run(["房子在燒", answer, *TAB_A_DETAIL, PHONE])
                self.assertEqual(engine.case.fire_tab, TAB_A)
                self.assertEqual(engine.case.building_type_code, code)

    def test_q1_skipped_when_building_already_known(self) -> None:
        io = ScriptedIO(["透天厝", *TAB_A_DETAIL, PHONE])
        llm = CompleteFireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        engine.case.fire_incident_type = 0
        handler = HuoJingGenericHandler()
        handler.run_generic_flow(engine)
        handler.collect_caller_info(engine)
        asked = "\n".join(io.messages)
        self.assertNotIn(ROUTE_Q1, asked)
        self.assertNotIn(ROUTE_Q2, asked)
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertIn(SAFETY_MESSAGE, asked)

    def test_engine_run_fire_after_address(self) -> None:
        io = ScriptedIO(["房子在燒", "透天厝", *TAB_A_DETAIL, PHONE])
        llm = CompleteFireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        engine.case.address = "新北市板橋區文化路100號"
        engine.case.address_confirmed = True

        def _fake_address(*_a, **_k):
            engine._say("已確認地址，消防車已派出了喔。")

        engine._run_address_flow = _fake_address  # type: ignore[method-assign]
        engine._run_火警()
        asked = "\n".join(io.messages)
        self.assertIn("已確認地址，消防車已派出了喔。", asked)
        self.assertIn(ROUTE_Q1, asked)
        self.assertIn(SAFETY_MESSAGE, asked)
        self.assertEqual(engine.case.fire_tab, TAB_A)
        self.assertEqual(engine.case.flow_stage, "completed")
        self.assertEqual(engine.case.result, "dispatched")
        self.assertEqual(engine.case.building_type_code, "10")

    def test_tab_b1_all_vehicle_codes(self) -> None:
        cases = (
            ("汽車", 0),
            ("機車", 1),
            ("隧道", 2),
            ("軌道火車", 3),
            ("化學槽車", 4),
            ("船舶", 5),
            ("飛機", 6),
        )
        for answer, code in cases:
            with self.subTest(answer=answer):
                engine, io, _ = _run([
                    "不是房子，是車子",
                    "車子在燒",
                    answer,
                    PHONE,
                ])
                self.assertEqual(engine.case.fire_tab, TAB_B1)
                self.assertEqual(engine.case.vehicle_wildfire_code, code)
                asked = "\n".join(io.messages)
                self.assertIn(ROUTE_Q2, asked)
                self.assertIn("那是汽車還是機車呢", asked)
                self.assertIn(SAFETY_MESSAGE, asked)

    def test_tab_b2_flat_and_mountain(self) -> None:
        engine, _, _ = _run(["其它東西", "草木在燒", "路邊的平地", PHONE])
        self.assertEqual(engine.case.fire_tab, TAB_B2)
        self.assertEqual(engine.case.vehicle_wildfire_code, 7)

        engine, _, _ = _run(["其它東西", "山上的草木在燒", "燒在山上", PHONE])
        self.assertEqual(engine.case.fire_tab, TAB_B2)
        self.assertEqual(engine.case.vehicle_wildfire_code, 8)

    def test_tab_c_all_minor_codes(self) -> None:
        cases = (
            ("都不是，是垃圾在燒", 0, True),
            ("都不是，電線桿冒煙", 1, True),
            ("都不是，瓦斯漏氣", 2, True),
            ("都不是，警報器作響", 3, True),
            ("都不是，請查看案件", 4, True),
        )
        for q2, code, skip_c in cases:
            with self.subTest(q2=q2):
                engine, io, _ = _run(["不是房子", q2, PHONE])
                self.assertEqual(engine.case.fire_tab, TAB_C)
                self.assertEqual(engine.case.minor_fire_code, code)
                asked = "\n".join(io.messages)
                self.assertIn(SAFETY_MESSAGE, asked)
                if skip_c:
                    self.assertNotIn("聽到警報聲呢", asked)

    def test_q1_unresolved_transfers(self) -> None:
        io = ScriptedIO(["不清楚啊", "還是不清楚"])
        llm = CompleteFireExtractor()
        engine = SopEngine119(io=io, llm_extractor=llm)  # type: ignore[arg-type]
        engine.case.main_category = "火警"
        with self.assertRaises(TransferToHumanError) as ctx:
            HuoJingGenericHandler().run_generic_flow(engine)
        self.assertEqual(ctx.exception.reason, "fire_tab_unresolved")
        self.assertEqual(ctx.exception.result, "human_transfer")
        self.assertTrue(any("轉接專人" in m for m in io.messages))

    def test_q2_unresolved_defaults_to_tab_c(self) -> None:
        engine, io, _ = _run([
            "不是房子",
            "嗯不清楚",
            "還是不知道",
            "看到有煙像查看",
            PHONE,
        ])
        self.assertEqual(engine.case.fire_tab, TAB_C)
        self.assertEqual(engine.case.minor_fire_code, 4)
        self.assertIn(SAFETY_MESSAGE, "\n".join(io.messages))


class FireBertHookTests(unittest.TestCase):
    def test_high_conf_fills_each_bert_tab(self) -> None:
        samples = (
            ("透天厝", TAB_A, {"building_type_code": "10"}, ["房子在燒", *TAB_A_DETAIL, PHONE]),
            ("汽車", TAB_B1, {"vehicle_wildfire_code": 0}, ["不是房子", PHONE]),
            ("山林田野(山地)", TAB_B2, {"vehicle_wildfire_code": 8}, ["其它東西", PHONE]),
            ("垃圾", TAB_C, {"minor_fire_code": 0}, ["不是房子", PHONE]),
        )
        for label, tab, expect, answers in samples:
            with self.subTest(label=label):
                bert = FakeFireBert(label=label, conf=0.81)
                engine, io, _ = _run(answers, bert=bert)
                self.assertEqual(engine.case.fire_tab, tab)
                self.assertEqual(engine.case.sub_category, label)
                for key, val in expect.items():
                    self.assertEqual(getattr(engine.case, key), val)
                self.assertTrue(bert.calls)
                self.assertIn(SAFETY_MESSAGE, "\n".join(io.messages))

    def test_conf_equal_threshold_does_not_fill(self) -> None:
        bert = FakeFireBert(label="透天厝", conf=FIRE_BERT_CONF_THRESHOLD)
        engine, _, _ = _run(["房子在燒", "公寓大樓", *TAB_A_DETAIL, PHONE], bert=bert)
        self.assertEqual(engine.case.building_type_code, "11")
        self.assertNotEqual(engine.case.sub_category, "透天厝")

    def test_refresh_does_not_override_locked_route(self) -> None:
        case = SimpleNamespace(
            fire_tab=TAB_A,
            fire_incident_type=0,
            building_type_code="11",
            non_building_fire=None,
            vehicle_wildfire_code=None,
            minor_fire_code=None,
            sub_category=None,
            sub_conf=None,
        )
        apply_bert_subtype_to_case(case, "汽車", 0.99)
        self.assertEqual(case.fire_tab, TAB_A)
        self.assertEqual(case.fire_incident_type, 0)
        self.assertIsNone(case.vehicle_wildfire_code)

    def test_engine_refresh_uses_concatenated_caller_text(self) -> None:
        bert = FakeFireBert(label="集合住宅", conf=0.9)
        engine = SopEngine119(
            io=ScriptedIO([]),
            llm_extractor=CompleteFireExtractor(),  # type: ignore[arg-type]
            sub_classifiers=bert,
        )
        engine.case.main_category = "火警"
        engine.case.transcript = [
            {"role": "caller", "text": "板橋大樓失火"},
            {"role": "caller", "text": "集合住宅在燒"},
        ]
        engine._refresh_fire_subtype_from_bert()
        self.assertEqual(engine.case.sub_category, "集合住宅")
        self.assertEqual(engine.case.building_type_code, "11")
        self.assertIn("集合住宅在燒", bert.calls[0][0])
        self.assertEqual(bert.calls[0][1], "火警")


class FireApplyFieldTests(unittest.TestCase):
    def test_zero_codes_are_filled_and_synced(self) -> None:
        engine = SopEngine119(io=ScriptedIO([]))
        engine.case.main_category = "火警"
        engine._apply_extracted_fields({
            "has_flame": 0,
            "people_trapped_code": 0,
            "spread_risk": 1,
        })
        self.assertEqual(engine.case.has_flame, 0)
        self.assertTrue(engine._is_field_filled("has_flame"))
        self.assertIs(engine.case.people_trapped, False)
        self.assertIs(engine.case.fire_spread, True)

    def test_route_helpers_lock_tabs(self) -> None:
        case = SimpleNamespace(fire_incident_type=None, fire_tab=None, non_building_fire=None)
        apply_route_q1(case, "building")
        self.assertEqual(case.fire_tab, TAB_A)
        case = SimpleNamespace(fire_incident_type=None, fire_tab=None, non_building_fire=None)
        apply_route_q2(case, "vehicle")
        self.assertEqual(case.fire_tab, TAB_B1)


if __name__ == "__main__":
    unittest.main()
