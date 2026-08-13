"""errors.py 单元测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_collaboration import errors  # noqa: E402


class ErrorTests(unittest.TestCase):
    def test_codes_are_stable_and_unique(self):
        codes = [s.code for s in errors.SPECS.values()]
        self.assertEqual(len(codes), len(set(codes)))
        for code in codes:
            self.assertTrue(code.startswith("MMAC-E"), code)

    def test_format_includes_hint(self):
        msg = errors.E401_LOCK_CONFLICT.format("被 x 持有")
        self.assertIn("MMAC-E401_LOCK_CONFLICT", msg)
        self.assertIn("建议", msg)
        self.assertIn("被 x 持有", msg)

    def test_mmac_error_to_dict(self):
        err = errors.MMACError(errors.E301_HASH_MISMATCH, "abc")
        d = err.to_dict()
        self.assertEqual(d["code"], "MMAC-E301_HASH_MISMATCH")
        self.assertEqual(d["detail"], "abc")
        self.assertIn("hint", d)

    def test_required_specs_exist(self):
        for name in ("E101_INVALID_STATE", "E201_UNAUTHORIZED_ROLE",
                     "E301_HASH_MISMATCH", "E401_LOCK_CONFLICT",
                     "E501_APPROVAL_REQUIRED"):
            self.assertTrue(hasattr(errors, name), name)


if __name__ == "__main__":
    unittest.main()
