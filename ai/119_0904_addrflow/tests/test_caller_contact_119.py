from __future__ import annotations

import threading
import unittest

from sop_119_engine import DialogueIO, SopEngine119
from sop_utils_119 import normalize_phone_digits, validate_phone_number


class SilentIO(DialogueIO):
    def say(self, text: str) -> None: ...
    def hear_text(self) -> str: return ""


class PhoneValidationTests(unittest.TestCase):
    """號碼碼數驗證。手機 09+8=10 碼；市話 區號+用戶號碼（新北 02+8=10 碼）。"""

    def test_valid_mobile(self) -> None:
        for n in ("0922338444", "0912345678", "0900000000"):
            with self.subTest(n=n):
                digits, valid, reason = validate_phone_number(n)
                self.assertTrue(valid, f"{n} 應為合法手機（reason={reason}）")
                self.assertEqual(digits, n)

    def test_short_mobile_is_rejected(self) -> None:
        """實測 f91714ac：「0922338444」尾三碼被 STT 聽成「是是是」，只剩 7 碼。"""
        digits, valid, reason = validate_phone_number("0922338")
        self.assertFalse(valid)
        self.assertEqual(digits, "0922338")
        self.assertIn("7 碼", reason or "")
        self.assertIn("不足", reason or "")

    def test_long_mobile_is_rejected(self) -> None:
        _, valid, reason = validate_phone_number("09223384445")
        self.assertFalse(valid)
        self.assertIn("超過", reason or "")

    def test_valid_landline_02(self) -> None:
        """新北／台北：02 + 8 碼 = 10 碼。"""
        for n in ("0229683110", "02-2968-3110", "(02)29683110"):
            with self.subTest(n=n):
                _, valid, reason = validate_phone_number(n)
                self.assertTrue(valid, f"{n} 應為合法市話（reason={reason}）")

    def test_short_landline_02_is_rejected(self) -> None:
        _, valid, reason = validate_phone_number("022968311")   # 9 碼
        self.assertFalse(valid)
        self.assertIn("10 碼", reason or "")

    def test_other_area_codes(self) -> None:
        self.assertTrue(validate_phone_number("0912345678")[1])      # 手機
        self.assertTrue(validate_phone_number("039123456")[1])       # 03 + 7 = 9
        self.assertTrue(validate_phone_number("089123456")[1])       # 089 + 6 = 9
        self.assertFalse(validate_phone_number("0891234567")[1])     # 089 多一碼
        self.assertFalse(validate_phone_number("03912345")[1])       # 03 短一碼

    def test_toll_free_and_service_numbers(self) -> None:
        self.assertTrue(validate_phone_number("0800092000")[1])      # 0800 + 6 = 10
        self.assertTrue(validate_phone_number("119")[1])
        self.assertTrue(validate_phone_number("110")[1])

    def test_missing_leading_zero(self) -> None:
        _, valid, reason = validate_phone_number("922338444")
        self.assertFalse(valid)
        self.assertIn("缺少開頭的 0", reason or "")

    def test_country_code_is_normalized(self) -> None:
        for n in ("+886922338444", "886922338444", "+886-922-338-444"):
            with self.subTest(n=n):
                digits, valid, _ = validate_phone_number(n)
                self.assertEqual(digits, "0922338444")
                self.assertTrue(valid)

    def test_missing_is_not_an_error(self) -> None:
        """沒提供號碼 ≠ 號碼錯誤，不能誤報。"""
        for n in (None, "", "   ", "不知道"):
            with self.subTest(n=n):
                digits, valid, reason = validate_phone_number(n)
                self.assertEqual(digits, "")
                self.assertIsNone(valid)
                self.assertIsNone(reason)


class SetCallerContactTests(unittest.TestCase):
    """engine.set_caller_contact：照實存原值、另外標記格式問題。"""

    def _engine(self) -> SopEngine119:
        return SopEngine119(SilentIO())

    def test_valid_number_marks_true(self) -> None:
        e = self._engine()
        e.set_caller_contact("0922338444")
        self.assertEqual(e.case.caller_contact, "0922338444")
        self.assertIs(e.case.caller_contact_valid, True)
        self.assertIsNone(e.case.caller_contact_reason)

    def test_bad_number_is_kept_verbatim_and_flagged(self) -> None:
        """不竄改、不追問（2026-09-16 決定），只標記。"""
        e = self._engine()
        e.set_caller_contact("0922338")
        self.assertEqual(e.case.caller_contact, "0922338")   # 原值保留
        self.assertIs(e.case.caller_contact_valid, False)
        self.assertIn("不足", e.case.caller_contact_reason or "")

    def test_missing_number_stays_unknown(self) -> None:
        e = self._engine()
        e.set_caller_contact(None)
        self.assertIsNone(e.case.caller_contact)
        self.assertIsNone(e.case.caller_contact_valid)

    def test_no_deadlock_when_called_normally(self) -> None:
        """set_caller_contact 自己拿 _case_lock（普通 Lock、不可重入）。

        呼叫點若殘留在 `with engine._case_lock:` 區塊內就會永久卡死，
        所以這裡用 timeout 守住——卡住就是回歸。
        """
        e = self._engine()
        done = threading.Event()

        def run() -> None:
            e.set_caller_contact("0922338444")
            done.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.assertTrue(done.wait(timeout=5.0), "set_caller_contact 卡住了 → 死鎖")

    def test_case_lock_released_afterwards(self) -> None:
        e = self._engine()
        e.set_caller_contact("0922338444")
        self.assertTrue(e._case_lock.acquire(timeout=1.0), "_case_lock 沒被釋放")
        e._case_lock.release()


class NormalizeDigitsTests(unittest.TestCase):
    def test_strips_separators(self) -> None:
        self.assertEqual(normalize_phone_digits("0922-338-444"), "0922338444")
        self.assertEqual(normalize_phone_digits("(02) 2968 3110"), "0229683110")
        self.assertEqual(normalize_phone_digits("0922338444。是是是"), "0922338444")


if __name__ == "__main__":
    unittest.main()
