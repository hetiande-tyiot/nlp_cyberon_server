"""
重要標籤分成兩種的測試（important_tags_119.py）：
- 案情標籤：LLM 可以選、也可以從報案人原話比對
- 系統狀態標籤：只由程式寫入，LLM 選了也不採用

為什麼：原本整份白名單都給 LLM 選，LLM 聽到「我要報火災」就自己標上
「火災類別無法確認」，後來火災類型分出來了，這個錯誤標籤也一直留著。
"""

from __future__ import annotations

import unittest

from important_tags_119 import (
    CASE_CONTENT_TAGS,
    IMPORTANT_TAGS,
    SYSTEM_STATUS_TAGS,
    match_important_tags,
    merge_important_tags,
)
from llm_extractor_119 import LLMExtractor119


class TagListTests(unittest.TestCase):

    def test_two_lists_cover_whole_whitelist(self) -> None:
        self.assertEqual(set(CASE_CONTENT_TAGS) | set(SYSTEM_STATUS_TAGS), set(IMPORTANT_TAGS))
        self.assertFalse(set(CASE_CONTENT_TAGS) & set(SYSTEM_STATUS_TAGS))

    def test_caller_words_never_produce_system_status_tags(self) -> None:
        self.assertEqual(match_important_tags("他持刀說要自殺，地址未確認"), ["持刀", "自殺"])

    def test_program_can_still_write_system_status_tags(self) -> None:
        merged = merge_important_tags(["持刀"], ["火災類型無法判斷，預設輕微火警"])
        self.assertEqual(merged, ["持刀", "火災類型無法判斷，預設輕微火警"])


class LLMTagChoiceTests(unittest.TestCase):
    """不載入模型：直接模擬 LLM 的輸出。"""

    def _extract(self, llm_output: dict) -> dict:
        ext = object.__new__(LLMExtractor119)
        ext.extract_slots = lambda *args, **kwargs: dict(llm_output)  # type: ignore[method-assign]
        return ext.extract_general_fields("我要報火災", "119 您好", main_category="火警")

    def test_llm_choosing_system_status_tag_is_dropped(self) -> None:
        out = self._extract({"ImportantTag": ["火災類別無法確認"]})
        self.assertNotIn("ImportantTag", out)

    def test_llm_case_tags_are_kept(self) -> None:
        out = self._extract({"ImportantTag": ["持刀", "地址搜尋失敗"]})
        self.assertEqual(out["ImportantTag"], ["持刀"])

    def test_prompt_only_lists_case_tags(self) -> None:
        captured = []
        ext = object.__new__(LLMExtractor119)
        ext.extract_slots = lambda text, schema, rules, **kw: captured.append(rules) or {}  # type: ignore[method-assign]
        ext.extract_general_fields("我要報火災", "119 您好", main_category="火警")
        all_rules = "\n".join(captured)
        self.assertIn("持刀", all_rules)
        for tag in SYSTEM_STATUS_TAGS:
            self.assertNotIn(tag, all_rules)


if __name__ == "__main__":
    unittest.main()
