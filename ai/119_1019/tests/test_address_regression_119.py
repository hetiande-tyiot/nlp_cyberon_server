"""地址抽取／覆寫的事故迴歸測試。

事故一（2026-09-02 13:37）：「欸我住在那個辦土城區中央路3段61巷2號4樓」，
行政區被抽成「個辦土城區」，拼出的地址送 addrCheck 必然查無，
有效地址被要求重報，最終降級為轉真人。

事故二（2026-09-04 09:45）：孕婦急產案，救護車已派出後，
報案人回答「在哪裡產檢？」說「國泰醫院」，
`_apply_location_rules` 無條件把 address 覆寫成醫院名，派遣地址錯誤。
"""

from __future__ import annotations

import unittest

from address_hint_119 import phonetic_correction_note
from location_validation_119 import (
    DEFAULT_ADDRCHECK_FAILURE_TEXT,
    addrcheck_failure_reason,
)
from address_mapper_119 import get_location_mapper
from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import (
    build_street_address,
    dropped_address_details,
    extract_address_district,
    extract_address_number,
    extract_alley_only,
    extract_address_road,
    extract_street_address_components,
    is_bare_district_or_city,
    landmark_layer_from_hint,
    looks_like_pregnancy_count,
    merge_address,
    strip_district_prefix_from_road,
)


class SilentIO(DialogueIO):
    def say(self, text: str) -> None:
        pass

    def hear_text(self) -> str:
        raise AssertionError("本測試不應觸發提問")


class DistrictExtractionTests(unittest.TestCase):
    def test_spoken_filler_before_district_is_dropped(self) -> None:
        self.assertEqual(
            extract_address_district("欸我住在那個辦土城區中央路3段61巷2號4樓"),
            "土城區",
        )

    def test_district_ignores_leading_noise(self) -> None:
        cases = {
            "呃我在中和區景平路100號": "中和區",
            "嗯那個板橋區文化路一段10號": "板橋區",
            "新北市板橋區大華街2號4樓": "板橋區",
            "就是三峽區大學路1號": "三峽區",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_address_district(text), expected)

    def test_district_outside_whitelist_falls_back_to_regex(self) -> None:
        self.assertEqual(
            extract_address_district("台中市西屯區台灣大道300號"), "西屯區"
        )

    def test_rebuilt_address_has_no_filler(self) -> None:
        text = "欸我住在那個辦土城區中央路3段61巷2號4樓"
        parts = extract_street_address_components(text)
        self.assertEqual(
            build_street_address(
                parts.get("address_district"),
                parts.get("address_road"),
                parts.get("address_number"),
                existing=text,
            ),
            "土城區中央路3段61巷2號4樓",
        )


class RoadExtractionTests(unittest.TestCase):
    def test_filler_before_road_is_dropped(self) -> None:
        cases = {
            "嗯，那個亞洲路3號2樓": "亞洲路",
            "土城區那個亞洲路3號2樓": "亞洲路",
            "就是中山北路二段5號": "中山北路二段",
            "我家在文化路一段10號": "文化路一段",
            "位於中正路100號": "中正路",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_address_road(text), expected)

    def test_stripping_never_produces_invalid_road(self) -> None:
        """剝除不得產生「路」「大道」這種只剩通稱的路名。

        2026-09-06 起這兩句改回 None：路名主體全是贅詞字（「那個」）就不算
        路名，寧可去問也不要拿「那個路」去查 addrCheck。原本的不變量
        ——不得剝出單一通稱——仍然成立，這裡改成直接斷言它。
        """
        for text in ("那個路口", "那個大道3號"):
            with self.subTest(text=text):
                road = extract_address_road(text)
                self.assertNotIn(road, ("路", "街", "大道"))
                if road is not None:
                    self.assertGreater(len(road), 1)


class AddressLockTests(unittest.TestCase):
    def _engine_with_settled_address(self) -> SopEngine119:
        engine = SopEngine119(SilentIO())
        engine.case.address = "土城區亞洲路3號2樓"
        engine.case.location_type = "address"
        engine.case.address_district = "土城區"
        engine.case.address_road = "亞洲路"
        engine.case.address_number = "3號"
        return engine

    def test_landmark_cannot_overwrite_after_address_flow(self) -> None:
        engine = self._engine_with_settled_address()
        engine._address_locked = True
        engine._apply_location_rules("國泰醫院")
        self.assertEqual(engine.case.address, "土城區亞洲路3號2樓")
        self.assertEqual(engine.case.location_type, "address")

    def test_landmark_still_applies_during_address_flow(self) -> None:
        """流程進行中行為不變，報案人仍可把地點改成地標。"""
        engine = self._engine_with_settled_address()
        engine._address_locked = False
        engine._apply_location_rules("國泰醫院")
        self.assertEqual(engine.case.address, "國泰醫院")
        self.assertEqual(engine.case.location_type, "landmark")

    def test_lock_still_allows_backfill_when_no_address(self) -> None:
        """地址抽取失敗的案件，上鎖後仍要能從後續對話補到地點。"""
        engine = SopEngine119(SilentIO())
        engine._address_locked = True
        engine._apply_location_rules("國泰醫院")
        self.assertEqual(engine.case.address, "國泰醫院")
        self.assertEqual(engine.case.location_type, "landmark")

    def test_address_flow_sets_lock(self) -> None:
        """內層任何 return 路徑離開後都必須上鎖。"""
        engine = SopEngine119(SilentIO())
        self.assertFalse(engine._address_locked)

        def boom(**_kwargs):
            raise RuntimeError("內層中斷")

        engine._run_address_flow_inner = boom
        with self.assertRaises(RuntimeError):
            engine._run_address_flow(
                stage_ask="x",
                stage_confirm="y",
                dispatch_line="z",
                ask_questions=("問地址？",),
            )
        self.assertTrue(engine._address_locked)


class AddrcheckReasonTests(unittest.TestCase):
    def test_known_reasons_map_to_readable_text(self) -> None:
        self.assertEqual(addrcheck_failure_reason("road_only"), "查無此門牌")
        self.assertEqual(addrcheck_failure_reason("not_found"), "查無此路段")

    def test_unknown_reason_uses_default(self) -> None:
        for value in (None, "", "brand_new_reason"):
            with self.subTest(value=value):
                self.assertEqual(
                    addrcheck_failure_reason(value),
                    DEFAULT_ADDRCHECK_FAILURE_TEXT,
                )

    def test_no_reason_text_mentions_jurisdiction(self) -> None:
        """119 走 addrCheck，不查管轄分局，訊息不該再提管轄單位。"""
        for text in (
            DEFAULT_ADDRCHECK_FAILURE_TEXT,
            addrcheck_failure_reason("road_only"),
            addrcheck_failure_reason("not_found"),
        ):
            with self.subTest(text=text):
                self.assertNotIn("管轄", text)


if __name__ == "__main__":
    unittest.main()


class NonDistrictWordTests(unittest.TestCase):
    """STT 誤聽產生的「不分區」等詞不可當成行政區。

    事故（2026-09-04 09:45）：報案人被問「請告訴我是那一區？」，
    STT 聽成「不分區」，regex 退路把它當區名 → 組出「不分區亞洲路3號」
    → addrCheck 必然查無 → 報案人被要求整段重報。
    """

    def test_non_district_words_are_rejected(self) -> None:
        for text in ("不分區", "不分區。", "學區", "社區", "工業區", "轄區"):
            with self.subTest(text=text):
                self.assertIsNone(extract_address_district(text))

    def test_non_district_word_in_sentence(self) -> None:
        self.assertIsNone(extract_address_district("不分區亞洲路3號2樓"))

    def test_real_districts_still_extracted(self) -> None:
        self.assertEqual(extract_address_district("土城區亞洲路3號"), "土城區")


class DistrictFuzzyGuessTests(unittest.TestCase):
    """行政區音近比對不得靜默改寫地址。

    原本 _fuzzy_match_district_by_tl 無門檻（best_score 由 -1.0 起跳），
    任何輸入都必定回傳某一區：「不分區」曾被比成「瑞芳區」。
    """

    def setUp(self) -> None:
        self.mapper = get_location_mapper()
        if self.mapper is None:
            self.skipTest("地址 mapper 未載入")

    def test_low_similarity_is_not_guessed(self) -> None:
        for text in ("不分區亞洲路3號2樓", "沒有區中山路1號"):
            with self.subTest(text=text):
                mapped, guess = self.mapper.map_location_detail(text)
                self.assertEqual(mapped, text)
                self.assertIsNone(guess)

    def test_guess_is_reported_not_silent(self) -> None:
        mapped, guess = self.mapper.map_location_detail("土成區中央路3段61巷2號")
        self.assertEqual(mapped, "土城區中央路3段61巷2號")
        # (原片段, 猜出的區, 相似度)；第三項供 fuzzy_match_log_119 取樣用。
        self.assertEqual(guess[:2], ("土成區", "土城區"))
        self.assertIsInstance(guess[2], float)

    def test_exact_district_is_not_a_guess(self) -> None:
        _mapped, guess = self.mapper.map_location_detail("土城區亞洲路3號")
        self.assertIsNone(guess)


class DistrictGuessRevertTests(unittest.TestCase):
    def _engine(self) -> SopEngine119:
        engine = SopEngine119(SilentIO())
        engine.case.address = "土成區中央路3段61巷2號"
        engine.case.address_district = "土成區"
        engine._normalize_location_fields()
        return engine

    def test_guess_recorded_on_normalize(self) -> None:
        engine = self._engine()
        if engine._district_guess is None:
            self.skipTest("地址 mapper 未載入")
        self.assertEqual(engine.case.address_district, "土城區")
        self.assertEqual(engine._district_guess, ("土成區", "土城區"))

    def test_unconfirmed_guess_reverted_on_failure(self) -> None:
        """沒走完覆誦就失敗 → 猜測不得留在 case 裡誤導真人。"""
        engine = self._engine()
        if engine._district_guess is None:
            self.skipTest("地址 mapper 未載入")
        engine._mark_address_failure("地址查無")
        self.assertEqual(engine.case.address, "土成區中央路3段61巷2號")
        self.assertEqual(engine.case.address_district, "土成區")
        self.assertIsNone(engine._district_guess)


class PatientCountTests(unittest.TestCase):
    """胎數不是傷病患人數。

    事故（2026-09-04 09:45）：問「單胞胎還是雙胞胎？」答「三胞胎」，
    patient_count 被填成「三胞胎」（該通根本沒問過傷患人數）。
    """

    def test_pregnancy_counts_detected(self) -> None:
        for value in ("三胞胎", "雙胞胎", "單胞胎", "龍鳳胎", "雙胎"):
            with self.subTest(value=value):
                self.assertTrue(looks_like_pregnancy_count(value))

    def test_real_counts_pass(self) -> None:
        for value in ("1", "一個人", "兩位", "3人", None, ""):
            with self.subTest(value=value):
                self.assertFalse(looks_like_pregnancy_count(value))

    def test_engine_rejects_pregnancy_count(self) -> None:
        engine = SopEngine119(SilentIO())
        engine.case.main_category = "救護"
        engine._apply_extracted_fields({"patient_count": "三胞胎"})
        self.assertIsNone(engine.case.patient_count)

    def test_engine_accepts_real_count(self) -> None:
        engine = SopEngine119(SilentIO())
        engine.case.main_category = "救護"
        engine._apply_extracted_fields({"patient_count": "1"})
        self.assertEqual(engine.case.patient_count, "1")


class KnownDistrictProtectionTests(unittest.TestCase):
    """合法行政區名不得被歸一化改寫。

    離線重放 56 通真實通話時發現：報案人講「台北市信義區松高路1號」，
    地址被改成「台北市萬裡區松高路1號」。兩個來源：
      1. 音近比對：信義區→萬裡區 0.700、中正區→新莊區 0.733、
         文山區→金山區 0.769，都高於真實 STT 錯誤（汐只區→汐止區 0.636），
         光調門檻擋不掉
      2. map_city.json 有 7 條把真實行政區映射掉：士林區→樹林區、
         中正區→中和區、萬華區→中和區、北投區→板橋區、新屋區→新莊區、
         桃園區→泰山區、蘆竹區→蘆洲區
    兩者皆為既有行為（0903 線上版相同），非五步流程引入。
    """

    def setUp(self) -> None:
        self.mapper = get_location_mapper()
        if self.mapper is None:
            self.skipTest("地址 mapper 未載入")

    def test_valid_districts_are_untouched(self) -> None:
        for text in (
            "台北市信義區松高路1號",   # 音近會配成萬裡區
            "士林區中正路1號",         # 映射表有 士林區→樹林區
            "中正區忠孝東路1號",       # 映射表有 中正區→中和區
            "文山區景隆街2號",         # 音近會配成金山區
            "桃園區中山路1號",         # 映射表有 桃園區→泰山區
            "土城區中央路3段61巷2號",   # 受理範圍內，本來就該原樣
        ):
            with self.subTest(text=text):
                self.assertEqual(self.mapper.map_location(text), text)

    def test_real_stt_errors_still_corrected(self) -> None:
        """保護不能擋掉真正該修的 STT 音近錯誤。"""
        self.assertEqual(
            self.mapper.map_location("土成區中央路3段61巷2號"),
            "土城區中央路3段61巷2號",
        )
        self.assertEqual(
            self.mapper.map_location("汐只區中山路1號"), "汐止區中山路1號"
        )

    def test_is_known_district(self) -> None:
        from sop_utils_119 import is_known_district

        for name in ("土城區", "信義區", "文山區", "桃園區", "仁愛區"):
            with self.subTest(name=name):
                self.assertTrue(is_known_district(name))
        for name in ("不分區", "學區", "個辦土城區", "", None):
            with self.subTest(name=name):
                self.assertFalse(is_known_district(name))


class RealCallRegressionTests(unittest.TestCase):
    """2026-09-04 19:54–20:02 四通上線實測抓到的問題。"""

    def test_city_prefix_not_polluted_by_filler(self) -> None:
        """「那個新北市」→「個新北市」，送 addrCheck 必然查無。

        實測 19:54：報案人講「嗯，在那個新北市五股區明德路12巷」，
        組出「個新北市五股區明德路12巷28號」，API 只認得出路名，
        回「明德路有好幾個區都有」，流程繞了三輪才問到。
        """
        from sop_utils_119 import extract_address_city

        self.assertEqual(
            extract_address_city("嗯，在那個新北市五股區明德路12巷"), "新北市"
        )
        text = "嗯，在那個新北市五股區明德路12巷28號"
        parts = extract_street_address_components(text)
        self.assertEqual(
            build_street_address(
                parts.get("address_district"),
                parts.get("address_road"),
                parts.get("address_number"),
                existing=text,
            ),
            "新北市五股區明德路12巷28號",
        )

    def test_city_not_duplicated(self) -> None:
        from sop_utils_119 import compose_street_address

        self.assertEqual(
            compose_street_address(
                None, "新北市三重正義南路", "12號",
                existing="那個新北市三重正義南路12號",
            ).count("新北市"),
            1,
        )

    def test_full_district_prefix_stripped_from_road(self) -> None:
        self.assertEqual(extract_address_road("三重區的正義南路"), "正義南路")

    def test_district_abbreviation_does_not_break_road(self) -> None:
        """只剝完整區名：剝簡稱會把「中山北路二段」削成「北路二段」。"""
        self.assertEqual(
            extract_address_road("就是中山北路二段5號"), "中山北路二段"
        )
        self.assertEqual(extract_address_road("中和區中和路100號"), "中和路")

    def test_whole_utterance_is_not_an_address(self) -> None:
        """實測 19:59：59 字的整段話因句中有「醫院」被判 landmark 存進 case。"""
        from sop_utils_119 import is_usable_address

        long_text = (
            "欸，我跟你講喔，那個就是他的身體也很不舒服。趕快來好不好，"
            "我，我要送醫院。在那個。那個新北市永和區。合約那個422號"
        )
        self.assertFalse(is_usable_address(long_text))
        self.assertTrue(is_usable_address("新北市板橋區民生路三段2號B1"))
        self.assertTrue(is_usable_address("重慶插角插角國小這邊的四維公園"))


class DispatchedAddressLockTests(unittest.TestCase):
    """派遣後的地址不得被後續對話改寫（address 型態）。

    實測兩通中招：「我是路人，所以我沒有開車」→ 路名變「我是路人路」；
    「不知道他躺在路邊」→ 路名變「不知道他躺在路」，並被唸出來覆誦。
    先前的 _address_locked 只擋 landmark/mrt/路口/國道，漏了 address 型態。
    """

    def _engine(self, locked: bool) -> SopEngine119:
        engine = SopEngine119(SilentIO())
        engine.case.address = "五股區明德路12巷28號"
        engine.case.location_type = "address"
        engine.case.address_district = "五股區"
        engine.case.address_road = "明德路12巷"
        engine.case.address_number = "28號"
        engine._address_locked = locked
        return engine

    def test_locked_address_survives_later_talk(self) -> None:
        for text in (
            "呃，我是路人，所以我沒有開車，就看到有有人那個機車自摔。",
            "不知道他躺在路邊，感覺。感覺沒有清醒。",
        ):
            with self.subTest(text=text):
                engine = self._engine(locked=True)
                engine._apply_location_rules(text)
                self.assertEqual(engine.case.address, "五股區明德路12巷28號")
                self.assertEqual(engine.case.address_road, "明德路12巷")

    def test_unlocked_still_updates_during_flow(self) -> None:
        """流程進行中仍須能增量更新，否則補問就失效了。"""
        engine = self._engine(locked=False)
        engine._apply_location_rules("其實是板橋區文化路一段10號")
        self.assertNotEqual(engine.case.address, "五股區明德路12巷28號")


class StreetMappingExclusionTests(unittest.TestCase):
    """map_street.json 中「來源本身就是真實路名」的條目要被排除。

    2026-09-04 20:57 真實通話：報案人講「重陽路跟新北大道的岔路交叉路口」，
    存檔成 `板橋區三和路與新新新新新新思源路口` 且已派遣。
    vendor 用臺語音近自動生成該表（1707 個真實路名 × 平均 15 個變體），
    生成時沒排除「變體本身已是另一條真實路名」。
    以 scripts/audit_street_mapping.py 逐條打 addrCheck 驗證出 25 條。
    """

    def setUp(self) -> None:
        self.mapper = get_location_mapper()
        if self.mapper is None:
            self.skipTest("地址 mapper 未載入")

    def test_exclusion_list_loaded(self) -> None:
        self.assertGreater(len(self.mapper.excluded_street_keys), 0)
        for key in ("重陽路", "中山北路", "凌雲路", "高速公路", "新北大道路"):
            with self.subTest(key=key):
                self.assertIn(key, self.mapper.excluded_street_keys)
                self.assertNotIn(key, self.mapper.street_mapping)

    def test_real_roads_are_not_rewritten(self) -> None:
        for text in (
            "三重區重陽路一段1號",      # 三重區真的有重陽路（一/二/四段）
            "淡水區中山北路二段1號",     # 淡水區真的有中山北路
            "五股區凌雲路三段1號",       # 五股區真的有凌雲路
            "淡水區濱海路一段49號",      # 淡水區真的有濱海路
        ):
            with self.subTest(text=text):
                self.assertEqual(self.mapper.map_location(text), text)

    def test_highway_keyword_not_turned_into_a_road(self) -> None:
        """「高速公路」原本被映射成「復興路」，害國道案件走錯分支。"""
        self.assertEqual(self.mapper.map_location("高速公路"), "高速公路")

    def test_genuine_stt_errors_still_corrected(self) -> None:
        """排除清單不能把表的正常功能一起關掉。"""
        self.assertEqual(
            self.mapper.map_location("三重區三河路二段1號"), "三重區三和路二段1號"
        )

    def test_missing_exclusion_file_is_tolerated(self) -> None:
        from pathlib import Path

        from address_mapper_119 import _load_street_exclusions

        self.assertEqual(_load_street_exclusions(Path("/nonexistent")), set())


class LaneAlleyMergeTests(unittest.TestCase):
    """報案人單獨補「31巷」時要併進路名。

    路名 regex 需要「X路」開頭，報案人補一句「還有31巷」「648巷6號」時
    抽不到，巷弄就此消失。實測兩通因此覆誦時唸成「國光路11號」、
    「仁愛街28號」，報案人連續否認、通話被拉長：
      2026-09-04 20:55 三重仁愛街283巷 — 報案人講了三次 283巷
      2026-09-05 10:54 板橋國光路31巷  — 覆誦兩次都少了 31巷
    """

    def test_lane_extracted_when_spoken_alone(self) -> None:
        from sop_utils_119 import extract_lane_alley

        cases = {
            "還有31巷": "31巷",
            "31巷11號": "31巷",
            "648巷6號": "648巷",
            "283巷28號5樓": "283巷",
            "中央路3段61巷2號": "61巷",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(extract_lane_alley(text), expected)

    def test_non_lane_text_yields_none(self) -> None:
        from sop_utils_119 import extract_lane_alley

        for text in ("國光路", "11號", "3樓", "板橋區", ""):
            with self.subTest(text=text):
                self.assertIsNone(extract_lane_alley(text))

    def test_merge_lane_into_road(self) -> None:
        engine = SopEngine119(SilentIO())
        engine.case.address_road = "國光路"
        self.assertTrue(engine._merge_lane_into_road("還有31巷"))
        self.assertEqual(engine.case.address_road, "國光路31巷")

    def test_merge_is_idempotent(self) -> None:
        """路名已含巷弄就不再附加，避免「國光路31巷31巷」。"""
        engine = SopEngine119(SilentIO())
        engine.case.address_road = "國光路31巷"
        self.assertFalse(engine._merge_lane_into_road("還有31巷"))
        self.assertEqual(engine.case.address_road, "國光路31巷")

    def test_no_road_means_no_merge(self) -> None:
        engine = SopEngine119(SilentIO())
        engine.case.address_road = None
        self.assertFalse(engine._merge_lane_into_road("31巷11號"))
        self.assertIsNone(engine.case.address_road)

    def test_number_is_not_mistaken_for_lane(self) -> None:
        engine = SopEngine119(SilentIO())
        engine.case.address_road = "國光路"
        self.assertFalse(engine._merge_lane_into_road("11號"))
        self.assertEqual(engine.case.address_road, "國光路")

    def test_lane_only_reply_is_not_a_new_address(self) -> None:
        """純巷弄補述不是「新地址」。

        報案人在覆誦時說「還有136巷8弄」，_resolve_address_correction 曾把它
        合併成「新北市板橋區還有136巷8弄」——路名整個消失，覆誦又唸回
        「光武街16號」，報案人連講三次都沒被接住（2026-09-06 00:33 實測）。
        巷弄補述應由 _merge_lane_into_road 併回路名。
        """
        from sop_utils_119 import extract_address_road, extract_lane_alley

        for text in ("還有136巷8弄", "還有31巷", "跟你說，不是，就是把中間還有。136巷8弄"):
            with self.subTest(text=text):
                # 沒有路名但有巷弄 → 會被 _resolve_address_correction 濾掉
                self.assertIsNone(extract_address_road(text))
                self.assertIsNotNone(extract_lane_alley(text))

        # 有路名的更正仍要當成新地址處理
        self.assertIsNotNone(extract_address_road("不是，是中和區景平路431巷"))


class DistrictPrefixInRoadTests(unittest.TestCase):
    """路名開頭重複行政區時要剝掉。

    報案人常把區和路連著講，2026-09-05／09-06 三通中招：
      「中和景平路」＋中和區 → 組成「中和區中和景平路27號」→ addrCheck 查無
      「板橋國光路」＋板橋區、「新莊的中港路」＋新莊區 同理
    API 實測「中和景平路431巷27號」本身就是 valid，是我們組壞了才查無。

    ⚠️ 與 `_ROAD_PREFIX_DISTRICTS` 的差異：那個單看路名，無法判斷
    「中山北路」的「中山」該不該剝（剝了變「北路二段」仍是合法路名，
    守衛擋不住）。這裡多了「與已知行政區重複」的條件，才安全。
    """

    def test_duplicated_district_is_stripped(self) -> None:
        from sop_utils_119 import strip_district_prefix_from_road

        cases = [
            ("中和景平路", "中和區", "景平路"),
            ("板橋國光路", "板橋區", "國光路"),
            ("新莊的中港路", "新莊區", "中港路"),
            ("板橋區文化路", "板橋區", "文化路"),
        ]
        for road, district, expected in cases:
            with self.subTest(road=road):
                self.assertEqual(
                    strip_district_prefix_from_road(road, district), expected
                )

    def test_unrelated_prefix_is_kept(self) -> None:
        """行政區不同就不該動——這是與無條件剝簡稱的關鍵差異。"""
        from sop_utils_119 import strip_district_prefix_from_road

        cases = [
            ("中山北路二段", "淡水區"),
            ("中和路", "板橋區"),
            ("中央路3段61巷", "土城區"),
            ("景平路", "中和區"),
        ]
        for road, district in cases:
            with self.subTest(road=road, district=district):
                self.assertEqual(
                    strip_district_prefix_from_road(road, district), road
                )

    def test_missing_district_is_noop(self) -> None:
        from sop_utils_119 import strip_district_prefix_from_road

        self.assertEqual(
            strip_district_prefix_from_road("中和景平路", None), "中和景平路"
        )

    def test_rebuild_syncs_the_road_field(self) -> None:
        """欄位要一起更新，否則 address 與 address_road 對不起來。"""
        engine = SopEngine119(SilentIO())
        engine.case.address_district = "中和區"
        engine.case.address_road = "中和景平路"
        engine.case.address_number = "27號"

        self.assertEqual(engine._rebuild_street_address(), "中和區景平路27號")
        self.assertEqual(engine.case.address_road, "景平路")


class RoadSectionMergeTests(unittest.TestCase):
    """段跟巷弄一樣，單獨補述時要併回路名。

    2026-09-06 01:25 實測：報案人講「一段22號」，`extract_address_road`
    需要路名開頭所以抽不到「一段」，最終存「明德路22號」，
    API 回「最接近的是 明德路一段22號（報案人未提及段別）」——
    段其實講了，只是沒被接住。修正後該通由 invalid 變 valid。
    """

    def _merge(self, road: str, text: str) -> str:
        engine = SopEngine119(SilentIO())
        engine.case.address_road = road
        engine._merge_lane_into_road(text)
        return engine.case.address_road

    def test_section_merged(self) -> None:
        self.assertEqual(self._merge("明德路", "一段22號"), "明德路一段")

    def test_section_before_lane(self) -> None:
        """段必須接在巷之前：「中央路三段61巷」而非「中央路61巷三段」。"""
        self.assertEqual(self._merge("中央路", "三段61巷2號"), "中央路三段61巷")

    def test_lane_appended_to_road_with_section(self) -> None:
        self.assertEqual(self._merge("明德路一段", "105巷"), "明德路一段105巷")

    def test_section_not_inserted_after_lane(self) -> None:
        """路名已有巷弄時不能再插段進去，會變成「中央路61巷三段」。"""
        self.assertEqual(self._merge("中央路61巷", "三段"), "中央路61巷")

    def test_idempotent(self) -> None:
        self.assertEqual(self._merge("明德路一段", "一段22號"), "明德路一段")
        self.assertEqual(self._merge("國光路31巷", "還有31巷"), "國光路31巷")

    def test_extract_helpers(self) -> None:
        from sop_utils_119 import extract_road_section, road_has_section

        self.assertEqual(extract_road_section("一段22號"), "一段")
        self.assertEqual(extract_road_section("三段61巷2號"), "三段")
        self.assertIsNone(extract_road_section("22號"))
        self.assertTrue(road_has_section("中央路三段"))
        self.assertFalse(road_has_section("中央路"))


class BareDistrictNameTests(unittest.TestCase):
    """省略「區」的口語區名（2026-09-06 04:42 實測）。

    報案人說「救護車在那個鶯歌」，抽不到區 → 落到地標分支 →
    AI 問「確定是鶯歌這個地址嗎？」。連兩通都是這樣開場。

    只認新北市 29 區：臺北市的「中山」「信義」「大安」同時是路名前綴，
    「中山北路」會被拆成「中山區」＋「北路」。
    """

    def test_bare_district_is_recognised(self) -> None:
        cases = {
            "欸我我我我我要一個那個救護車在那個。鶯歌那邊。": "鶯歌區",
            "呃，我要那個救護車在那個鶯歌。": "鶯歌區",
            "鶯歌國慶街慶。那個164號2樓。": "鶯歌區",
            "我在板橋文化路一段10號": "板橋區",
            "不是是新莊。區中港路648巷6號。": "新莊區",
        }
        for text, want in cases.items():
            with self.subTest(text=text[:20]):
                self.assertEqual(extract_address_district(text), want)

    def test_bare_district_needs_context_on_both_sides(self) -> None:
        """前後都要有線索，否則兩個字常常是別的詞。"""
        for text in (
            "我要送台大金山。開刀。",   # 醫院名，「金山」前面是「大」
            "中和路100號",             # 路名，後面只有「路」不算路名
            "永和路50號",
            "中山北路二段100號",        # 臺北市區名不在裸名單內
            "這是三重點",              # 後面是「點」
            "先中和一下再說",
        ):
            with self.subTest(text=text[:20]):
                self.assertIsNone(extract_address_district(text))

    def test_bare_district_prefix_is_stripped_from_road(self) -> None:
        """區路連著講：抽到區之後，路名前綴才剝得掉。"""
        parts = extract_street_address_components("鶯歌國慶街慶。那個164號2樓。")
        self.assertEqual(
            strip_district_prefix_from_road(
                parts["address_road"], parts["address_district"]
            ),
            "國慶街",
        )


class DateIsNotHouseNumberTests(unittest.TestCase):
    """「N月N號」是日期不是門牌。

    國語的「號」同時是門牌與日期的量詞。報案人交代病史或事發時間時
    （「他3月23號開過刀」「上禮拜5號就這樣了」）會出現裸的「N號」，
    取第一個匹配就會把日期填進門牌。
    """

    def test_date_is_rejected(self) -> None:
        for text in (
            "他3月23號開過刀",
            "3月23號那天",
            "民國115年3月23號",
            "今天9月6日",
        ):
            with self.subTest(text=text[:20]):
                self.assertIsNone(extract_address_number(text))

    def test_house_number_after_a_date_is_still_found(self) -> None:
        """句子裡先有日期、後有門牌，門牌仍要抽得到。"""
        self.assertEqual(
            extract_address_number("3月23號那次是在中央路3段61巷2號"), "2號"
        )

    def test_ordinary_house_numbers_unaffected(self) -> None:
        for text, want in (
            ("中央路3段61巷2號4樓", "2號"),
            ("國慶街164號2樓", "164號"),
            ("大觀路1段28巷6弄4號", "4號"),
            ("復興路12之3號", "12之3號"),
        ):
            with self.subTest(text=text):
                self.assertEqual(extract_address_number(text), want)


class NarrowedReaskTests(unittest.TestCase):
    """第二輪重問只問缺的元件（2026-09-06 04:44 實測）。"""

    def _engine(self, district=None, road=None, number=None):
        engine = SopEngine119(io=SilentIO())
        engine.case.address_district = district
        engine.case.address_road = road
        engine.case.address_number = number
        return engine

    def test_known_district_asks_only_for_road(self) -> None:
        engine = self._engine(district="鶯歌區")
        self.assertEqual(engine._narrowed_reask("請問事發地址在哪裡？幾樓？"),
                         "鶯歌區的哪一條路呢？")

    def test_known_road_asks_only_for_number(self) -> None:
        engine = self._engine(district="鶯歌區", road="國慶街")
        self.assertEqual(engine._narrowed_reask("請問事發地址在哪裡？"),
                         "鶯歌區國慶街幾號呢？")

    def test_nothing_known_keeps_the_general_question(self) -> None:
        engine = self._engine()
        self.assertEqual(engine._narrowed_reask("請問事發地址在哪裡？"),
                         "請問事發地址在哪裡？")

    def test_road_without_district_keeps_the_general_question(self) -> None:
        """只有路名時不能只問號——路名可能落在好幾個區。"""
        engine = self._engine(road="中港路")
        self.assertEqual(engine._narrowed_reask("請問事發地址在哪裡？"),
                         "請問事發地址在哪裡？")


class DispatchAnnouncementTests(unittest.TestCase):
    """沒派車就不能說「已派出」。

    OHCA 轉真人的話術原本寫死「救護車已派出，請不要掛斷電話…」。
    但生命征象是在地址流程**之後**才問的，任何在派遣前就轉出去的通話
    （地址查不到、報案人講不清楚、打錯電話）都會聽到這句不實陳述。
    """

    def test_flag_starts_false(self) -> None:
        self.assertFalse(SopEngine119(io=SilentIO())._dispatch_announced)

    def test_transfer_line_omits_dispatch_when_nothing_dispatched(self) -> None:
        from sop_119_engine import TransferToHumanError

        said: list[str] = []

        class RecordingIO(SilentIO):
            def say(self, text: str) -> None:
                said.append(text)

        engine = SopEngine119(io=RecordingIO())
        with self.assertRaises(TransferToHumanError):
            engine._check_ohca_and_transfer(None, "consciousness")
        self.assertEqual(said, ["請不要掛斷電話，我立即為您轉接專人。"])

    def test_transfer_line_keeps_dispatch_after_a_real_dispatch(self) -> None:
        from sop_119_engine import TransferToHumanError

        said: list[str] = []

        class RecordingIO(SilentIO):
            def say(self, text: str) -> None:
                said.append(text)

        engine = SopEngine119(io=RecordingIO())
        engine._dispatch_announced = True
        with self.assertRaises(TransferToHumanError):
            engine._check_ohca_and_transfer(None, "consciousness")
        self.assertEqual(
            said, ["救護車已派出，請不要掛斷電話，我立即為您轉接專人。"]
        )


class RoadFillerPeelingTests(unittest.TestCase):
    """句中沒有「區」也沒有縣市時，路名 regex 會連贅詞一起吃。

    2026-09-06 10:35 實測「我這邊是民生路2段」——`extract_address_road` 的
    切點只有「區」和縣市，兩個都沒有就從句首開始比對，抽出
    「我這邊是民生路2段」，含人稱被 `looks_like_real_road` 整個否決，
    路名變成 None，覆誦後倒退問「請問是什麼路？」。
    """

    def test_leading_fillers_are_peeled(self) -> None:
        cases = {
            "我這邊是民生路2段。兩百。號之18樓。": "民生路2段",
            "我這邊是民生路2段": "民生路2段",
            "是中山北路二段": "中山北路二段",
            "我這邊是那個板橋實踐路。132號這個。": "板橋實踐路",
            "我跟你說，我這裡是那個分科路。351巷31號。": "分科路351巷",
        }
        for text, want in cases.items():
            with self.subTest(text=text[:20]):
                self.assertEqual(extract_address_road(text), want)

    def test_peeling_never_eats_into_the_road_name(self) -> None:
        """剝到剩「北路」就是 ⑩-6 那個坑——贅詞字表刻意不收路名開頭字。"""
        for text in ("中山北路二段", "中正路一段", "民生路二段", "大觀路1段"):
            with self.subTest(text=text):
                self.assertEqual(extract_address_road(text), text)

    def test_narrative_words_still_block_extraction(self) -> None:
        """剝除只處理贅詞；敘述動詞仍要讓整個候選作廢。"""
        for text in ("他躺在中山北路二段", "我看到有人倒在那邊"):
            with self.subTest(text=text[:20]):
                self.assertIsNone(extract_address_road(text))

    def test_question_fragments_are_not_roads(self) -> None:
        for text in ("我不知道什麼路欸", "馬偕，我也不知道什麼路欸。", "是哪一條路？"):
            with self.subTest(text=text[:20]):
                self.assertIsNone(extract_address_road(text))

    def test_generic_words_for_road_are_not_roads(self) -> None:
        """「馬路」「路口」是路的通稱，不是路名。"""
        for text in ("是。進得去。他就在馬路旁邊。", "我是路人路過現場。",
                     "就在那個路口"):
            with self.subTest(text=text[:20]):
                self.assertIsNone(extract_address_road(text))


class RejectedCandidateNeverRevivedTests(unittest.TestCase):
    """addrCheck 否決過的候選不得在最後被撿回來。

    最終挑選只比「哪個字多」，而 LLM 整合出來的地址往往最長。
    被 API 判 not_found／road_only 之後仍會在 `_restore_best_candidate`
    被選為「最完整的候選」寫進 case.address。
    """

    def _engine_with_candidates(self, *candidates):
        engine = SopEngine119(io=SilentIO())
        for text, status in candidates:
            engine._record_address_candidate(text, source="test",
                                             api_status=status)
        return engine

    def test_api_rejected_candidate_is_excluded(self) -> None:
        engine = self._engine_with_candidates(
            ("板橋區大華街2號", None),
            ("板橋區不存在路999號", "road_only"),   # 較長但已被否決
        )
        self.assertEqual(engine._best_candidate_address(), "板橋區大華街2號")

    def test_unchecked_candidate_can_still_win(self) -> None:
        """沒驗過（api_status=None）不等於被否決——09-02 那通靠這個還原。"""
        engine = self._engine_with_candidates(
            ("土城區", None),
            ("土城區中央路3段61巷2號", None),
        )
        self.assertEqual(
            engine._best_candidate_address(), "土城區中央路3段61巷2號"
        )

    def test_valid_candidate_beats_a_longer_rejected_one(self) -> None:
        engine = self._engine_with_candidates(
            ("土城區中央路3段61巷2號", "valid"),
            ("土城區中央路3段二十六11巷2號", "not_found"),
        )
        self.assertEqual(
            engine._best_candidate_address(), "土城區中央路3段61巷2號"
        )


class DroppedAddressDetailTests(unittest.TestCase):
    """原話有「之N」或樓層、地址裡沒有 → 要回頭問（2026-09-06 10:35 實測）。

    STT 把「200之1號8樓」拆成「兩百。號之18樓」，規則只撿得到門牌號，
    覆誦唸成「200號」，得等報案人自己發現並更正——那是把校對工作丟給
    正在急著求救的人。
    """

    def test_detects_dropped_sub_number_and_floor(self) -> None:
        self.assertEqual(
            dropped_address_details(
                "我這邊是民生路2段。兩百。號之18樓。", "新北市板橋區民生路二段200號"
            ),
            (True, True),
        )

    def test_nothing_missing_when_address_already_has_them(self) -> None:
        for spoken, address in (
            ("民生路二段200之1號8樓", "新北市板橋區民生路二段200之1號8樓"),
            ("五股區六合街92號5樓", "新北市五股區六合街92號5樓"),
            ("新店區中興路3段290號1樓", "新北市新店區中興路3段290號1樓"),
        ):
            with self.subTest(spoken=spoken):
                self.assertEqual(dropped_address_details(spoken, address),
                                 (False, False))

    def test_no_false_alarm_when_caller_never_said_them(self) -> None:
        self.assertEqual(
            dropped_address_details("板橋區國光路31巷11號",
                                    "新北市板橋區國光路31巷11號"),
            (False, False),
        )

    def test_asked_at_most_once(self) -> None:
        engine = SopEngine119(io=SilentIO())
        engine._dropped_details_asked = True
        engine.case.address = "新北市板橋區民生路二段200號"
        engine.case.transcript = [
            {"role": "caller", "text": "我這邊是民生路2段。兩百。號之18樓。"}
        ]
        engine._ask_dropped_address_details()   # SilentIO 一問就 AssertionError


class NeverReaskWhatTheAddressAlreadyHasTests(unittest.TestCase):
    """不得追問 case.address 裡看得到的元件（2026-09-06 10:35 實測）。

    AI 才剛覆誦「確定是新北市板橋區民生路二段200號這個地址嗎？」，
    下一句就問「請問是什麼路？」。根因是路名 regex 沒抽到（見
    RoadFillerPeelingTests），components 空著；補問前會先跑
    `_fill_components_from_address()`，所以只要抽得到就不會問。
    這條測試把那個不變量鎖住。
    """

    def test_components_are_recovered_from_the_address_string(self) -> None:
        for address, want in (
            ("新北市板橋區民生路二段200號",
             ("板橋區", "民生路二段", "200號")),
            ("新北市五股區六合街92號5樓", ("五股區", "六合街", "92號")),
            ("新北市新店區中興路3段290號1樓",
             ("新店區", "中興路3段", "290號")),
            ("土城區中央路3段61巷2號", ("土城區", "中央路3段61巷", "2號")),
        ):
            with self.subTest(address=address):
                engine = SopEngine119(io=SilentIO())
                engine.case.address = address
                engine._fill_components_from_address()
                self.assertEqual(
                    (engine.case.address_district, engine.case.address_road,
                     engine.case.address_number),
                    want,
                    "地址字串裡看得到的元件必須填得回來，否則就會倒退重問",
                )


class MergeKeepsRoadTests(unittest.TestCase):
    """補述只給門牌／樓層時，合併不得吃掉路名（2026-09-06 10:35 實測）。

    覆誦「新北市板橋區民生路二段200號」後報案人更正「200之1號8樓」，
    逐輪 LLM 抽出的片段沒有路名，`merge_address` 只保留區名前綴，
    組成「新北市板橋區200之1號8樓」——路名整段消失，
    下一句就問「請問是什麼路？」，明明才剛唸過。
    """

    CURRENT = "新北市板橋區民生路二段200號"

    def test_detail_only_fragment_keeps_the_road(self) -> None:
        for fragment, want in (
            ("200之1號8樓", "新北市板橋區民生路二段200之1號8樓"),
            ("200之1號", "新北市板橋區民生路二段200之1號"),
        ):
            with self.subTest(fragment=fragment):
                self.assertEqual(merge_address(self.CURRENT, fragment), want)

    def test_section_survives_the_merge(self) -> None:
        """前綴要留到完整路名——只留「民生路」就把「二段」弄丟了。"""
        merged = merge_address(self.CURRENT, "200之1號8樓")
        self.assertIn("民生路二段", merged)

    def test_district_is_not_duplicated(self) -> None:
        """補述自己帶了區名時不得再加一次（曾組出「板橋區板橋區民生路…」）。"""
        merged = merge_address(self.CURRENT, "板橋區民生路二段200之1號8樓")
        self.assertEqual(merged.count("板橋區"), 1)

    def test_switching_to_another_road_still_replaces(self) -> None:
        """報案人改口換一條路時，舊路名不能被黏著不放。"""
        self.assertEqual(
            merge_address("中和區連城路347巷附近", "中和區景平路27號"),
            "中和區景平路27號",
        )

    def test_lane_supplement_unaffected(self) -> None:
        self.assertEqual(
            merge_address("中和區連城路347巷附近", "連城路347巷1弄2號附近"),
            "中和區連城路347巷1弄2號附近",
        )


class LandmarkSupplementDoesNotHijackAddressTests(unittest.TestCase):
    """報案人補一句社區名時，地址與型別要一起保持一致（2026-09-06 10:40 實測）。

    覆誦「五股區六合街92號5樓」後報案人答「對對對，就是那個陸光新城」。
    這是補充說明，不是改地址。門牌完整時本來就不受影響；但地址若已被
    hint 導向清成殘缺片段，LLM 的地標名會整個換掉它——換掉本身可接受
    （地標查得到、殘缺片段查不到），問題是 `location_type` 走「空欄位才
    填入」的規則改不動，於是內容是地標、type 還是 address，
    拿去做門牌驗證必然查無。
    """

    def _apply(self, address, location_type, *, locked=False):
        engine = SopEngine119(io=SilentIO())
        engine.case.address = address
        engine.case.location_type = location_type
        engine._address_locked = locked
        engine._apply_extracted_fields(
            {"location_type": "landmark", "address": "陸光新城"}
        )
        return engine.case.address, engine.case.location_type

    def test_complete_address_is_untouched(self) -> None:
        for address in ("新北市五股區六合街92號5樓", "五股區六合街999號"):
            with self.subTest(address=address):
                self.assertEqual(self._apply(address, "address"),
                                 (address, "address"))

    def test_type_follows_when_the_address_is_replaced(self) -> None:
        self.assertEqual(self._apply("五股區", "address"),
                         ("陸光新城", "landmark"))

    def test_type_is_set_when_there_was_no_address(self) -> None:
        self.assertEqual(self._apply(None, None), ("陸光新城", "landmark"))

    def test_locked_address_is_not_rewritten_by_the_llm(self) -> None:
        """派遣後的閒聊一樣會進 extract_slots——規則路徑有這道鎖，LLM 路徑漏了。"""
        self.assertEqual(self._apply("五股區", "address", locked=True),
                         ("五股區", "address"))
        self.assertEqual(
            self._apply("新北市五股區六合街92號5樓", "address", locked=True),
            ("新北市五股區六合街92號5樓", "address"),
        )


class BareDistrictNotSentToAddrCheckTests(unittest.TestCase):
    """純區名／縣市名不得送 addrCheck 的自動判斷層。

    自動層會盡力配一個地標給你，而且回 valid：
        五股區 → 五股區公所
        新北市 → 樹林區「新北市肉品市場」
    報案人只講到區，正確反應是繼續問路，不是拿去查。
    """

    def test_bare_names_are_recognised(self) -> None:
        for text in ("五股區", "新北市", "新北市板橋區", "鶯歌區。"):
            with self.subTest(text=text):
                self.assertTrue(is_bare_district_or_city(text))

    def test_anything_with_a_road_is_not_bare(self) -> None:
        for text in ("板橋區文化路", "五股區六合街92號", "新北市板橋區民生路二段"):
            with self.subTest(text=text):
                self.assertFalse(is_bare_district_or_city(text))

    def test_probe_refuses_bare_names(self) -> None:
        for text in ("五股區", "新北市"):
            with self.subTest(text=text):
                engine = SopEngine119(io=SilentIO())
                engine.case.address = text
                self.assertIsNone(engine._probe_location_type())


class HintLayerTests(unittest.TestCase):
    """從 addrCheck 自動判斷的 hint 反推它命中哪一層。"""

    def test_layer_is_read_from_the_hint(self) -> None:
        cases = {
            "地標比對成功：地標：板橋國小 → 新北市板橋區文化路一段23號": "landmark",
            "地址有效：新北市板橋區民生路二段200號": "address",
            "國道定位成功：國道3南下35.138公里處": "highway",
            "「文化路」與「民生路」在板橋區有 5 處交會，請追問": "intersection",
        }
        for hint, want in cases.items():
            with self.subTest(hint=hint[:20]):
                self.assertEqual(landmark_layer_from_hint(hint), want)

    def test_not_found_gives_no_layer(self) -> None:
        self.assertIsNone(
            landmark_layer_from_hint("查無「陸光新城」，是否為 新北市瑞芳區連福新城？")
        )


class GenericMappingKeysRemovedTests(unittest.TestCase):
    """通用名詞當映射鍵，會污染所有含該詞的名稱（2026-09-07）。

    `map_other_road.json` 有「國小→插角國小」「大道→縣民大道」「社區→尖山湖」。
    子字串替換讓每一所學校、每一條大道都中招——而且是在送 addrCheck **之前**，
    所以本來查得到的「板橋國小→文化路一段23號」永遠查不到。
    """

    def setUp(self) -> None:
        self.mapper = get_location_mapper()

    def test_generic_keys_are_excluded(self) -> None:
        for key in ("國小", "大道", "社區"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.mapper.other_mapping)

    def test_school_names_survive(self) -> None:
        for name in ("板橋國小", "土城清水國小", "蘆洲成功國小", "重慶國小"):
            with self.subTest(name=name):
                self.assertEqual(self.mapper.map_location(name), name)

    def test_boulevard_names_survive(self) -> None:
        for name in ("新北大道一段100號", "觀海大道", "台灣大道三段99號"):
            with self.subTest(name=name):
                self.assertEqual(self.mapper.map_location(name), name)

    def test_value_already_present_blocks_the_substitution(self) -> None:
        """目標名稱已在原文裡 → 這次命中只是它的一小段。

        「北大道→新北大道」碰上「新北大道」會替出「新新北大道」，
        跟 vendor 報告裡「新新新新新新思源路」是同一個病。
        """
        self.assertEqual(self.mapper.map_location("冷飯坑"), "冷飯坑")

    def test_legitimate_completions_still_work(self) -> None:
        """排除的是通用詞，不是整張表——真正的 STT 修正要留著。"""
        self.assertEqual(self.mapper.map_location("冷飯"), "冷飯坑")
        self.assertEqual(self.mapper.map_location("汐只區橫科路"), "汐止區橫科路")


class NormalizedAddressNotOverwrittenTests(unittest.TestCase):
    """addrCheck 正規化過的地址，不得被報案人的原話講法蓋回去。

    2026-09-07 17:04 實測：報案人說「永和區永鎮路128號」，addrCheck 回
        「永鎮路128號」查無此路名，已依讀音修正為「永貞路128號」
    流程採用永貞路、覆誦也唸永貞路、報案人答「對。是的。」——然後逐輪 LLM
    從原話又抽一次「永鎮路」把它蓋回去，**存檔存了一條不存在的路**。
    """

    def _apply(self, current, new_addr):
        engine = SopEngine119(io=SilentIO())
        engine.case.address = current
        engine._apply_extracted_fields({"address": new_addr})
        return engine.case.address

    def test_spoken_variant_does_not_replace_the_normalized_form(self) -> None:
        self.assertEqual(
            self._apply("新北市永和區永貞路128號", "新北市永和區永鎮路128號"),
            "新北市永和區永貞路128號",
        )

    def test_a_real_correction_still_goes_through(self) -> None:
        """報案人真的改地址時兩者不會相等，不能被這道防護擋掉。"""
        self.assertEqual(
            self._apply("新北市永和區永貞路128號", "新北市永和區永和路128號"),
            "新北市永和區永和路128號",
        )

    def test_supplements_still_merge(self) -> None:
        for current, fragment, want in (
            ("新北市永和區永貞路128號", "新北市永和區永貞路128號5樓",
             "新北市永和區永貞路128號5樓"),
            ("新北市板橋區民生路二段200號", "200之1號8樓",
             "新北市板橋區民生路二段200之1號8樓"),
        ):
            with self.subTest(fragment=fragment):
                self.assertEqual(self._apply(current, fragment), want)

    def test_components_follow_the_normalized_address(self) -> None:
        """正規化之後元件要重抽——留著舊路名會讓受理員看到不存在的路。"""
        engine = SopEngine119(io=SilentIO())
        engine.case.address = "新北市永和區永鎮路128號"
        engine._fill_components_from_address()
        self.assertEqual(engine.case.address_road, "永鎮路")

        engine.case.address = "新北市永和區永貞路128號"
        engine._fill_components_from_address(overwrite=True)
        self.assertEqual(engine.case.address_road, "永貞路")
        self.assertEqual(engine.case.address_district, "永和區")
        self.assertEqual(engine.case.address_number, "128號")

    def test_default_fill_still_keeps_existing_components(self) -> None:
        """預設模式不能改動已累積的元件（逐輪累積比事後回推可靠）。"""
        engine = SopEngine119(io=SilentIO())
        engine.case.address = "新北市永和區永貞路128號"
        engine.case.address_road = "永貞路128巷"
        engine._fill_components_from_address()
        self.assertEqual(engine.case.address_road, "永貞路128巷")


class PhoneticCorrectionNoteTests(unittest.TestCase):
    """讀音修正要標記給受理員（2026-09-07 17:04 實測）。

    addrCheck 的 hint 自己就寫著這個修正無法用複誦確認：
        注意：兩者讀音相同，向報案人複述路名無法分辨，
        如需確認請改問門牌號、樓層或附近路口。
    AI 唸「永貞路」、報案人答「對」——那個「對」不具鑑別力。
    只在「本轄同音路名僅此一條」時 API 才修，所以不攔流程，標記即可。
    """

    HINT = (
        "「永鎮路128號」查無此路名，已依讀音修正為「新北市永和區永貞路128號」"
        "（本轄同音路名僅此一條）。注意：兩者讀音相同，向報案人複述路名"
        "無法分辨，如需確認請改問門牌號、樓層或附近路口。"
    )

    def test_note_names_both_forms(self) -> None:
        note = phonetic_correction_note(self.HINT)
        self.assertIsNotNone(note)
        self.assertIn("永鎮路128號", note)
        self.assertIn("永貞路128號", note)
        self.assertIn("覆誦無法分辨", note)

    def test_plain_valid_hint_has_no_note(self) -> None:
        for hint in (
            "地址有效：新北市板橋區民生路二段200號",
            "地標比對成功：地標：板橋國小 → 新北市板橋區文化路一段23號",
            None,
            "",
        ):
            with self.subTest(hint=(hint or "")[:20]):
                self.assertIsNone(phonetic_correction_note(hint))

    def test_engine_records_the_note(self) -> None:
        engine = SopEngine119(io=SilentIO())
        engine.case.address = "新北市永和區永鎮路128號"
        engine._adopt_normalized_address(self.HINT)
        self.assertEqual(engine.case.address, "新北市永和區永貞路128號")
        self.assertIn("永鎮路", engine.case.address_corrected_note or "")

    def test_note_reaches_the_frontend_payload(self) -> None:
        engine = SopEngine119(io=SilentIO())
        engine.case.address = "新北市永和區永鎮路128號"
        engine._adopt_normalized_address(self.HINT)
        self.assertIn("address_corrected_note", engine.case.to_dict())

    def test_note_is_kept_out_of_the_summary_prompt(self) -> None:
        """技術欄位不進摘要 prompt，跟 address_error_reason 一樣。"""
        engine = SopEngine119(io=SilentIO())
        engine.case.address = "新北市永和區永鎮路128號"
        engine._adopt_normalized_address(self.HINT)
        self.assertNotIn("address_corrected_note", engine.case.filled_fields_for_summary())


class StandaloneAlleyTests(unittest.TestCase):
    """報案人在覆誦時單獨補「弄」（2026-09-08 00:49 實測）。

    AI 覆誦「中和街155巷30號」，報案人答「是還有24弄」——`parse_yes_no`
    看到開頭的「是」就判定確認，弄整個丟掉，派往 155巷30號。

    危險在於**兩個都是有效門牌**：中和街155巷30號 與 155巷24弄30號
    都存在、都是不同的地方，addrCheck 不會有任何警訊。
    """

    def test_standalone_alley_is_extracted(self) -> None:
        for text in ("是還有24弄", "還有24弄", "24弄", "155巷24弄30號"):
            with self.subTest(text=text):
                self.assertEqual(extract_alley_only(text), "24弄")

    def test_no_alley_no_match(self) -> None:
        for text in ("30號", "155巷", "是的", ""):
            with self.subTest(text=text):
                self.assertIsNone(extract_alley_only(text))

    def test_alley_is_appended_to_a_road_that_already_has_a_lane(self) -> None:
        engine = SopEngine119(io=SilentIO())
        engine.case.address = "新北市新莊區中和街155巷30號"
        engine.case.address_district = "新莊區"
        engine.case.address_road = "中和街155巷"
        engine.case.address_number = "30號"
        self.assertTrue(engine._merge_lane_into_road("是還有24弄"))
        self.assertEqual(engine.case.address_road, "中和街155巷24弄")

    def test_existing_alley_is_not_duplicated(self) -> None:
        engine = SopEngine119(io=SilentIO())
        engine.case.address_road = "中和街155巷24弄"
        self.assertFalse(engine._merge_lane_into_road("是還有24弄"))
        self.assertEqual(engine.case.address_road, "中和街155巷24弄")

    def test_road_without_a_lane_still_takes_the_lane_path(self) -> None:
        """沒有巷的路名走原本的 extract_lane_alley，不受這條新分支影響。"""
        engine = SopEngine119(io=SilentIO())
        engine.case.address_road = "中和街"
        self.assertTrue(engine._merge_lane_into_road("還有155巷"))
        self.assertEqual(engine.case.address_road, "中和街155巷")


class InternalFillerRunTests(unittest.TestCase):
    """贅詞夾在路名中間（2026-09-08 00:43 實測）。

    「永豐公園在那個中山路2段」——地標名不是贅詞字，剝不掉開頭，
    整串被當成路名送驗，存成 address_road =「永豐公園在那個中山路2段」。
    """

    def test_cuts_after_an_internal_filler_run(self) -> None:
        cases = {
            "永豐公園在那個中山路2段。三百九。309巷。41號。前面。": "中山路2段",
            "永豐公園在那個中山路2段": "中山路2段",
            "板橋國小這邊的長安街": "長安街",
        }
        for text, want in cases.items():
            with self.subTest(text=text[:20]):
                self.assertEqual(extract_address_road(text), want)

    def test_a_single_filler_char_does_not_cut(self) -> None:
        """門檻是連續兩個以上——「旁邊」的「旁」不在表內，只剩一個「邊」。"""
        self.assertEqual(
            extract_address_road("那個。蘆洲成功國小旁邊。長安街。三十一三十一。好。"),
            "長安街",
        )

    def test_real_roads_are_never_cut(self) -> None:
        for name in ("中山北路二段", "中正路一段", "大觀路1段", "民生路二段"):
            with self.subTest(name=name):
                self.assertEqual(extract_address_road(name), name)


class DispatchedAddressComponentLockTests(unittest.TestCase):
    """派遣後的地址不得被「元件重組」路徑改寫。

    2026-09-16 實測 f91714ac：地址已確認並派遣（板橋區南雅南路二段32號5樓），
    報案人下一句句尾夾了 STT 雜訊「內壢區走路」，case 存下來變成
    「新北市萬裡區走路32號5樓」——區、路被換掉，號與樓留著。

    _address_locked 原本只擋 _apply_extracted_fields 的整串 address 與
    _apply_location_rules，漏了 _update_street_address_from_input：它拿
    區/路/號元件覆寫後再用 compose_street_address 重組，等於繞過鎖。
    """

    CONFIRMED = "新北市板橋區南雅南路二段32號5樓"
    # 該通真實逐字稿（派遣後那一句）
    NOISE = "欸，就我昨天。那個吃藥。然後今天早上可能血壓過高，身體不舒服。內壢區走路。"

    def _engine(self, locked: bool) -> SopEngine119:
        engine = SopEngine119(SilentIO())
        engine.case.address = self.CONFIRMED
        engine.case.location_type = "address"
        engine.case.address_district = "板橋區"
        engine.case.address_road = "南雅南路二段"
        engine.case.address_number = "32號"
        engine.case.address_confirmed = True
        engine._address_locked = locked
        return engine

    def test_locked_address_survives_component_path(self) -> None:
        engine = self._engine(locked=True)
        engine._update_street_address_from_input(self.NOISE)
        self.assertEqual(engine.case.address, self.CONFIRMED)
        self.assertEqual(engine.case.address_district, "板橋區")
        self.assertEqual(engine.case.address_road, "南雅南路二段")

    def test_locked_blocks_any_component_overwrite(self) -> None:
        """不只這一句——任何句子在上鎖後都不該動到已成立的門牌。"""
        for text in (
            "內壢區走路。",
            "我在中山路啦。",
            "不知道他躺在路邊。",
        ):
            with self.subTest(text=text):
                engine = self._engine(locked=True)
                engine._update_street_address_from_input(text)
                self.assertEqual(engine.case.address, self.CONFIRMED)

    def test_unlocked_still_updates_during_flow(self) -> None:
        """流程進行中（未上鎖）仍須能增量補元件，否則五步流程就失效了。"""
        engine = SopEngine119(SilentIO())
        engine.case.location_type = "address"
        engine.case.address = "板橋區"
        engine._address_locked = False
        engine._update_street_address_from_input("文化路一段100號")
        self.assertIn("文化路一段", engine.case.address or "")
        self.assertIn("100號", engine.case.address or "")
