"""
報案人關鍵字標籤的測試（important_tags_119.py 的 CALLER_KEYWORD_TAGS）：
報案人原話講到 docs/案類標籤表.xlsx「系統顯示關鍵詞」頁裡的詞，就把那個詞本身
加進 ImportantTag，提醒受理員。

- 講到關鍵字 → 標那個詞
- 太籠統的詞（例如「有人」「大樓」）不標，否則幾乎每通電話都會被標
- 短的詞包在比較長的詞裡面時只標長的，避免同一句話標出兩個意思一樣的詞
- 合併既有標籤時，報案人關鍵字不會被濾掉
"""

from __future__ import annotations

import unittest

from important_tags_119 import (
    CALLER_KEYWORD_TAGS,
    CASE_CONTENT_TAGS,
    match_important_tags,
    merge_important_tags,
)


class CallerKeywordTagTests(unittest.TestCase):

    def test_keyword_in_caller_words_becomes_tag(self) -> None:
        self.assertEqual(match_important_tags("我爸爸口吐白沫，叫不醒"), ["口吐白沫", "叫不醒"])

    def test_vague_words_are_not_tagged(self) -> None:
        self.assertEqual(match_important_tags("有人在大樓裡面，頭暈，需要救護車"), [])

    def test_short_word_inside_longer_word_keeps_only_longer(self) -> None:
        self.assertEqual(match_important_tags("房間裡有人燒炭"), ["有人燒炭"])
        self.assertEqual(match_important_tags("他吃藥自殺"), ["吃藥自殺"])

    def test_merge_keeps_caller_keywords(self) -> None:
        merged = merge_important_tags(["持刀"], ["被捅", "持刀"])
        self.assertEqual(merged, ["持刀", "被捅"])

    def test_keywords_not_duplicated_in_case_content_tags(self) -> None:
        self.assertFalse(set(CALLER_KEYWORD_TAGS) & set(CASE_CONTENT_TAGS))


if __name__ == "__main__":
    unittest.main()
