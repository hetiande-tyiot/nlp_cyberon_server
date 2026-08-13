"""
119 地址測試集
━━━━━━━━━━━━━
報警人常常「說不清楚」地址：少講縣市、少講區、只講路名、分好幾次補、
中途更正。本檔以資料表列出各種說法與期望結果，四個層級各自獨立：

  MERGE_CASES  分次補述 / 更正時的地址合併（merge_address）
  HINT_CASES   單句規則抽取（extract_address_hint，LLM 失敗時的備援）
  CITY_CASES   未報縣市時預設套用新北市（ensure_city_prefix）
  FLOW_CASES   多輪對話走完整地址流程（含補問、覆誦、轉人工）

FLOW_CASES 一律 mock 掉辖區 API（固定回有效），所以驗的是「送去查的地址對不對」，
不是 API 本身。實機驗證請另外用真實地址打 JURISDICTION_API_URL。
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from location_validation_119 import JurisdictionResult
from sop_119_engine import DialogueIO, SopEngine119, TransferToHumanError
from sop_utils_119 import (
    classify_location_type,
    ensure_city_prefix,
    extract_address_hint,
    has_outdoor_location_hint,
    merge_address,
    strip_floor_question,
)


# ── 分次補述 / 更正時的合併 ────────────────────────────────────────────────────
# (編號, 說明, 已有地址, 新補片段, 期望結果)
MERGE_CASES = [
    # 少說路段 / 門牌 / 樓層，之後才補
    ("M01", "補路段", "新北市土城區中央路", "2段1號3樓", "新北市土城區中央路2段1號3樓"),
    ("M02", "補門牌", "新北市土城區中央路2段", "1號3樓", "新北市土城區中央路2段1號3樓"),
    ("M03", "補樓層", "新北市土城區中央路2段1號", "3樓", "新北市土城區中央路2段1號3樓"),
    ("M04", "補國字路段", "新北市板橋區文化路", "一段188號", "新北市板橋區文化路一段188號"),
    ("M05", "補巷", "新北市三重區重新路", "五段609巷", "新北市三重區重新路五段609巷"),
    ("M06", "補弄與號", "新北市三重區重新路五段609巷", "12弄5號",
     "新北市三重區重新路五段609巷12弄5號"),
    ("M07", "補之N門牌", "新北市新莊區中正路", "100之1號", "新北市新莊區中正路100之1號"),
    ("M08", "補樓之N", "新北市永和區永平路", "148號2樓之3", "新北市永和區永平路148號2樓之3"),
    ("M09", "補弄號", "新北市中和區連城路347巷", "1弄2號", "新北市中和區連城路347巷1弄2號"),
    ("M10", "補號與高樓層", "新北市汐止區大同路二段", "336號10樓",
     "新北市汐止區大同路二段336號10樓"),
    ("M11", "補巷號", "新北市淡水區中正路", "1巷2號", "新北市淡水區中正路1巷2號"),
    ("M12", "補地下樓層", "新北市樹林區中山路一段", "50號B1", "新北市樹林區中山路一段50號B1"),
    ("M13", "補國字門牌", "新北市板橋區文化路一段", "一八八號", "新北市板橋區文化路一段一八八號"),
    ("M14", "補門牌帶附近", "新北市土城區中央路2段", "1號附近", "新北市土城區中央路2段1號附近"),

    # 報警人重報已講過的成分 → 不可累加
    ("M20", "重報路段", "新北市土城區中央路2段", "2段1號3樓", "新北市土城區中央路2段1號3樓"),
    ("M21", "重報門牌", "新北市板橋區文化路一段188號", "188號", "新北市板橋區文化路一段188號"),
    ("M22", "重報整串巷弄", "新北市中和區連城路347巷1弄2號", "347巷1弄2號",
     "新北市中和區連城路347巷1弄2號"),

    # 更正同一層級 → 取代，不是累加
    ("M30", "改樓層", "新北市土城區中央路2段1號3樓", "5樓", "新北市土城區中央路2段1號5樓"),
    ("M31", "改門牌保留樓層", "新北市土城區中央路2段1號3樓", "3號",
     "新北市土城區中央路2段3號3樓"),
    ("M32", "改號保留巷弄", "新北市中和區連城路347巷1弄2號", "5號",
     "新北市中和區連城路347巷1弄5號"),
    ("M33", "改弄與號", "新北市三重區重新路五段609巷12弄5號", "20弄5號",
     "新北市三重區重新路五段609巷20弄5號"),

    # 重報時帶路名但省略區 → 保留區，不可掉
    ("M40", "重報路名省略區", "新北市土城區中央路", "中央路2段1號3樓",
     "新北市土城區中央路2段1號3樓"),
    ("M41", "重報路名省略區2", "新北市板橋區文化路", "文化路一段188號",
     "新北市板橋區文化路一段188號"),
    ("M42", "重報巷省略區", "新北市中和區連城路347巷", "連城路347巷1弄2號",
     "新北市中和區連城路347巷1弄2號"),

    # 整個換掉
    ("M50", "換一條路", "新北市土城區裕民路142號", "永和區永平路148號", "永和區永平路148號"),
    ("M51", "換區", "新北市板橋區文化路一段188號", "板橋區中山路一段10號", "板橋區中山路一段10號"),
    ("M52", "地標改門牌", "板橋分局後埔所", "民權街二段87號一樓", "民權街二段87號一樓"),

    # 邊界
    ("M60", "舊址為空", None, "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓"),
    ("M61", "新片段為空", "新北市土城區中央路2段1號3樓", None, "新北市土城區中央路2段1號3樓"),
    ("M62", "新片段是不知道", "新北市土城區中央路", "不知道", "新北市土城區中央路"),
    ("M63", "門牌不被地標覆蓋", "新北市土城區中央路2段1號3樓", "土城國小旁邊",
     "新北市土城區中央路2段1號3樓"),
]


# ── 單句規則抽取（LLM 失敗時的備援）─────────────────────────────────────────────
# (編號, 報警人原話, 期望抽取, 期望地址類別)
HINT_CASES = [
    ("H01", "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", "address"),
    ("H02", "新北市土城區中央路二段一號三樓", "新北市土城區中央路二段一號三樓", "address"),
    ("H03", "我在新北市板橋區文化路一段188號", "新北市板橋區文化路一段188號", "address"),
    ("H04", "地址在三重區重新路五段609巷12弄5號", "三重區重新路五段609巷12弄5號", "address"),
    ("H05", "這裡是新莊區中正路100之1號", "新莊區中正路100之1號", "address"),
    ("H06", "永和區永平路148號2樓之3", "永和區永平路148號2樓之3", "address"),
    ("H07", "汐止區大同路二段336號10樓", "汐止區大同路二段336號10樓", "address"),
    ("H08", "樹林區中山路一段50號B1", "樹林區中山路一段50號B1", "address"),
    ("H09", "中和區景興街 210 巷 2 弄 33 號 4 樓", "中和區景興街 210 巷 2 弄 33 號 4 樓",
     "address"),
    ("H10", "淡水區中正路1巷2號有人昏倒", "淡水區中正路1巷2號", "address"),
    ("H11", "救護車！蘆洲區長榮路68號", "蘆洲區長榮路68號", "address"),
    ("H12", "不是，是林口區文化二路一段100號", "林口區文化二路一段100號", "address"),
    ("H13", "土城區中央路2段1號3樓，快一點", "土城區中央路2段1號3樓", "address"),
    ("H14", "中央路2段1號3樓", "中央路2段1號3樓", "address"),
    # 說不清楚：規則抽不到，交給補問/轉人工（有 LLM 時另由 LLM 處理）
    ("H20", "2段1號3樓", None, "address"),
    ("H21", "3樓", None, None),
    ("H22", "就在這裡", None, None),
    ("H23", "土城國小對面", None, None),
    # 非門牌類地點：由各自分支處理
    ("H30", "捷運永寧站2號出口", None, "mrt"),
    ("H31", "國道三號南向52公里處", None, "highway"),
]


# ── 未報縣市 → 預設新北市 ──────────────────────────────────────────────────────
CITY_CASES = [
    ("C01", "土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓"),
    ("C02", "板橋區文化路一段188號", "新北市板橋區文化路一段188號"),
    ("C03", "台北市中正區忠孝東路一段1號", "台北市中正區忠孝東路一段1號"),
    ("C04", "臺北市信義區市府路45號", "臺北市信義區市府路45號"),
    ("C05", "桃園市中壢區中大路300號", "桃園市中壢區中大路300號"),
    ("C06", "基隆市仁愛區愛一路1號", "基隆市仁愛區愛一路1號"),
    ("C07", "新竹縣竹北市光明六路10號", "新竹縣竹北市光明六路10號"),
    ("C08", "嘉義市西區垂楊路100號", "嘉義市西區垂楊路100號"),
    ("C09", "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓"),
    ("C10", "", ""),
]


# ── 多輪對話 ──────────────────────────────────────────────────────────────────
# (編號, 說明, 報警人逐輪回答, 期望最終地址, 期望送查地址 or None, 是否轉人工)
FLOW_CASES = [
    # 一次講完整
    ("F01", "完整地址", ["新北市土城區中央路2段1號3樓", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F02", "國字數字", ["新北市土城區中央路二段一號三樓", "是"],
     "新北市土城區中央路二段一號三樓", "新北市土城區中央路二段一號三樓", False),
    ("F03", "口語前綴", ["我在新北市板橋區文化路一段188號", "是"],
     "新北市板橋區文化路一段188號", "新北市板橋區文化路一段188號", False),
    ("F04", "之N門牌", ["新莊區中正路100之1號", "是"],
     "新北市新莊區中正路100之1號", "新北市新莊區中正路100之1號", False),
    ("F05", "地下樓層", ["樹林區中山路一段50號B1", "是"],
     "新北市樹林區中山路一段50號B1", "新北市樹林區中山路一段50號B1", False),
    ("F06", "地址夾事件描述", ["淡水區中正路1巷2號有人昏倒", "是"],
     "新北市淡水區中正路1巷2號", "新北市淡水區中正路1巷2號", False),
    ("F07", "先喊救護車", ["救護車！蘆洲區長榮路68號", "是"],
     "新北市蘆洲區長榮路68號", "新北市蘆洲區長榮路68號", False),

    # 少講縣市
    ("F10", "少說縣市", ["土城區中央路2段1號3樓", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F11", "少說縣市_巷弄", ["中和區連城路347巷1弄2號", "是"],
     "新北市中和區連城路347巷1弄2號", "新北市中和區連城路347巷1弄2號", False),

    # 少講區 → 補問
    ("F20", "少說區_補問", ["中央路2段1號3樓", "土城區", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F21", "少說區_補問含縣市", ["中央路2段1號3樓", "新北市土城區", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F22", "少說區_問不出來", ["中央路2段1號3樓", "不知道", "不清楚"],
     "中央路2段1號3樓", None, True),

    # 分次補述
    ("F30", "先路名後路段", ["新北市土城區中央路", "2段1號3樓", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F31", "先路段後門牌", ["新北市土城區中央路2段", "1號3樓", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F32", "最後才補樓層", ["新北市土城區中央路2段1號", "3樓", "是"],
     "新北市土城區中央路2段1號3樓", None, False),
    ("F33", "重報路段", ["新北市土城區中央路2段", "2段1號3樓", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F34", "重報含路名省略區", ["新北市土城區中央路", "中央路2段1號3樓", "是"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", False),
    ("F35", "巷弄分兩輪", ["新北市三重區重新路五段609巷", "12弄5號", "是"],
     "新北市三重區重新路五段609巷12弄5號", "新北市三重區重新路五段609巷12弄5號", False),

    # 覆誦時更正
    ("F40", "更正換一條路", ["新北市土城區中央路2段1號3樓", "不是，是永和區永平路148號", "是"],
     "新北市永和區永平路148號", "新北市永和區永平路148號", False),
    ("F41", "更正換樓層", ["新北市土城區中央路2段1號3樓", "不是，是5樓", "是"],
     "新北市土城區中央路2段1號5樓", None, False),
    ("F42", "更正換門牌", ["新北市土城區中央路2段1號3樓", "不是，是3號", "是"],
     "新北市土城區中央路2段3號3樓", None, False),

    # 其他縣市不可被覆蓋
    ("F50", "台北市", ["台北市中正區忠孝東路一段1號", "是"],
     "台北市中正區忠孝東路一段1號", "台北市中正區忠孝東路一段1號", False),
    ("F51", "桃園市", ["桃園市中壢區中大路300號", "是"],
     "桃園市中壢區中大路300號", "桃園市中壢區中大路300號", False),

    # 非門牌類（不打辖區 API）
    ("F60", "路口", ["新北市板橋區仁化街與文化路路口", "是"],
     "板橋區仁化街與文化路路口", None, False),
    ("F61", "路口缺第二條路", ["新北市板橋區仁化街路口", "文化路", "是"],
     "板橋區仁化街與文化路路口", None, False),
    ("F62", "高速公路", ["國道三號南向52公里處", "是"],
     "國道三號 南向 52公里處", None, False),
    ("F63", "高速公路缺方向", ["國道三號", "南向52公里", "是"],
     "國道三號 南向 52公里處", None, False),

    # 說不清楚 → 轉人工
    ("F70", "完全說不出來", ["不知道", "不清楚"], None, None, True),
    ("F71", "就在這裡", ["就在這裡", "不知道", "不清楚"], "就在這裡", None, True),
    ("F72", "只講樓層", ["3樓", "不知道", "不清楚"], "3樓", None, True),
    ("F73", "只講門牌", ["1號3樓", "不知道", "不清楚"], "1號3樓", None, True),
    ("F74", "覆誦時說不知道", ["新北市土城區中央路2段1號3樓", "不知道", "還是不知道"],
     "新北市土城區中央路2段1號3樓", "新北市土城區中央路2段1號3樓", True),
]


# ── 戶外地點 → 問地址時不再追問幾樓 ────────────────────────────────────────────
# (編號, 問地址之前報警人已講的話, 是否算戶外)
OUTDOOR_CASES = [
    ("O01", "有人在巷口被車撞了", True),
    ("O02", "路邊有人昏倒", True),
    ("O03", "有人躺在天橋上", True),
    ("O04", "人行道上有人倒地", True),
    ("O05", "公園裡有人不舒服", True),
    ("O06", "機車騎士在路口摔車", True),
    ("O07", "國道三號南向有車禍", True),
    ("O08", "陸橋下面有人流血", True),
    ("O09", "公車站牌旁邊有人昏過去", True),
    ("O10", "河堤那邊有人溺水", True),
    ("O11", "騎樓下有人倒著", True),
    ("O12", "地下道裡面有人受傷", True),
    # 對照組：室內或未提及地點 → 仍要問樓層
    ("O20", "我媽媽在家昏倒了", False),
    ("O21", "救護車", False),
    ("O22", "辦公室有人不舒服", False),
    ("O23", "廚房起火了", False),
]

# (編號, 原問句, 期望去掉樓層後的問句)
FLOOR_QUESTION_CASES = [
    ("Q01", "請先告訴我地址？幾樓？", "請先告訴我地址？"),
    ("Q02", "請問事發地址在哪裡？幾樓？", "請問事發地址在哪裡？"),
    ("Q03", "請先告訴我地址？幾層？", "請先告訴我地址？"),
    ("Q04", "請先告訴我地址？樓層？", "請先告訴我地址？"),
    # 不含樓層追問的問句不可被動到
    ("Q05", "地址在哪裡呢？附近有明顯建物或標示嗎？",
     "地址在哪裡呢？附近有明顯建物或標示嗎？"),
]


class ScriptedIO(DialogueIO):
    def __init__(self, answers):
        self.answers = list(answers)
        self.questions: list[str] = []

    def say(self, text: str) -> None:
        self.questions.append(text)

    def hear_text(self) -> str:
        if not self.answers:
            raise AssertionError("測試回答已用盡")
        return self.answers.pop(0)


class StubLLM:
    """最小 LLM 樁：地址原樣回傳，「是」才視為確認。"""

    def extract_address(self, caller_text: str, use_question: bool = False) -> dict:
        return {"address": caller_text}

    def extract_confirmation(
        self, question: str, caller_text: str, current_address: str
    ) -> dict:
        if caller_text.strip() in {"是", "對", "沒錯"}:
            return {"confirmed": True, "new_address": None}
        return {"confirmed": None, "new_address": None}

    def extract_general_fields(self, *args, **kwargs) -> dict:
        return {}


class MergeCaseTests(unittest.TestCase):
    def test_merge_cases(self) -> None:
        for cid, label, current, new, expected in MERGE_CASES:
            with self.subTest(case=f"{cid} {label}"):
                self.assertEqual(merge_address(current, new), expected)


class HintCaseTests(unittest.TestCase):
    def test_hint_cases(self) -> None:
        for cid, text, expected_hint, expected_type in HINT_CASES:
            with self.subTest(case=f"{cid} {text}"):
                self.assertEqual(extract_address_hint(text), expected_hint)
                self.assertEqual(classify_location_type(text), expected_type)


class CityCaseTests(unittest.TestCase):
    def test_city_cases(self) -> None:
        for cid, text, expected in CITY_CASES:
            with self.subTest(case=f"{cid} {text}"):
                self.assertEqual(ensure_city_prefix(text), expected)


class OutdoorCaseTests(unittest.TestCase):
    def test_outdoor_hint_cases(self) -> None:
        for cid, text, expected in OUTDOOR_CASES:
            with self.subTest(case=f"{cid} {text}"):
                self.assertIs(has_outdoor_location_hint(text), expected)

    def test_floor_question_stripping(self) -> None:
        for cid, question, expected in FLOOR_QUESTION_CASES:
            with self.subTest(case=f"{cid} {question}"):
                self.assertEqual(strip_floor_question(question), expected)

    @patch(
        "sop_119_engine.query_jurisdiction",
        return_value=JurisdictionResult(True, "測試分局"),
    )
    def test_outdoor_case_is_not_asked_for_floor(self, _query) -> None:
        for cid, pre_text, outdoor in OUTDOOR_CASES:
            with self.subTest(case=f"{cid} {pre_text}"):
                io = ScriptedIO(["新北市土城區中央路2段1號", "是"])
                engine = SopEngine119(io=io)
                engine.case.transcript.append(
                    {"role": "assistant", "text": "119，這裡是勤務中心"}
                )
                engine.case.transcript.append({"role": "caller", "text": pre_text})

                FlowCaseTests._run(engine)

                addr_question = io.questions[0]
                if outdoor:
                    self.assertEqual(addr_question, "請先告訴我地址？")
                else:
                    self.assertEqual(addr_question, "請先告訴我地址？幾樓？")


class FlowCaseTests(unittest.TestCase):
    def test_flow_cases(self) -> None:
        for cid, label, answers, expected_addr, expected_query, transfers in FLOW_CASES:
            with self.subTest(case=f"{cid} {label}"):
                io = ScriptedIO(answers)
                engine = SopEngine119(io=io, llm_extractor=StubLLM())
                sent: list[str] = []

                def fake_query(addr, **kwargs):
                    sent.append(addr)
                    return JurisdictionResult(True, "測試分局")

                with patch("sop_119_engine.query_jurisdiction", side_effect=fake_query):
                    if transfers:
                        with self.assertRaises(TransferToHumanError):
                            self._run(engine)
                    else:
                        self._run(engine)

                self.assertEqual(engine.case.address, expected_addr)
                self.assertFalse(io.answers, "回答未用完，流程比預期短")
                if expected_query is not None:
                    self.assertEqual(sent[-1], expected_query)
                if not transfers:
                    self.assertTrue(engine.case.address_confirmed)

    @staticmethod
    def _run(engine: SopEngine119) -> None:
        engine._run_address_flow(
            stage_ask="救護_location",
            stage_confirm="救護_location_confirm",
            dispatch_line="已確認地址，救護車已派出了喔。",
            ask_questions=(
                "請先告訴我地址？幾樓？",
                "請問事發地址在哪裡？幾樓？",
            ),
        )


if __name__ == "__main__":
    unittest.main()