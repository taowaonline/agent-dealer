"""security.py 单元测试。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_dealer import security  # noqa: E402
from agent_dealer.errors import MMACError  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def write(self, rel, content):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(content)
        return full


class SnapshotTests(Base):
    def test_snapshot_and_diff_added(self):
        self.write("a.txt", "1")
        old = security.snapshot_baseline(self.root)
        self.write("b.txt", "2")
        new = security.snapshot_baseline(self.root)
        diff = security.diff_baseline(old, new)
        self.assertEqual(diff["added"], ["b.txt"])
        self.assertEqual(diff["modified"], [])
        self.assertEqual(diff["deleted"], [])

    def test_diff_modified_and_deleted(self):
        self.write("a.txt", "1")
        self.write("b.txt", "2")
        old = security.snapshot_baseline(self.root)
        self.write("a.txt", "changed")
        os.unlink(os.path.join(self.root, "b.txt"))
        new = security.snapshot_baseline(self.root)
        diff = security.diff_baseline(old, new)
        self.assertEqual(diff["modified"], ["a.txt"])
        self.assertEqual(diff["deleted"], ["b.txt"])

    def test_snapshot_ignores_git(self):
        self.write(".git/config", "secret-ish")
        self.write("real.txt", "x")
        snap = security.snapshot_baseline(self.root)
        self.assertNotIn(".git/config", snap)
        self.assertIn("real.txt", snap)

    def test_save_and_load_baseline(self):
        self.write("a.txt", "1")
        snap = security.snapshot_baseline(self.root)
        security.save_baseline(self.root, snap)
        loaded = security.load_baseline(self.root)
        self.assertEqual(loaded["a.txt"], snap["a.txt"])

    def test_load_missing_baseline(self):
        self.assertIsNone(security.load_baseline(self.root))


class AllowedPathTests(Base):
    def test_within_allowed(self):
        violations = security.check_changes_allowed(
            ["src/x.py"], ["./"], [".git/"], self.root)
        self.assertEqual(violations, [])

    def test_forbidden_hit(self):
        violations = security.check_changes_allowed(
            [".git/hooks/x"], ["./"], [".git/"], self.root)
        self.assertEqual(violations, [".git/hooks/x"])

    def test_outside_allowed(self):
        violations = security.check_changes_allowed(
            ["elsewhere/x.py"], ["src/"], [], self.root)
        self.assertEqual(violations, ["elsewhere/x.py"])


class SecretScanTests(Base):
    def test_detects_aws_key(self):
        p = self.write("c.txt", "key = AKIAIOSFODNN7EXAMPLE\n")
        findings = security.scan_secrets(p)
        self.assertTrue(any(f["kind"] == "AWS Access Key" for f in findings))

    def test_detects_private_key(self):
        p = self.write("k.pem", "-----BEGIN PRIVATE KEY-----\nMII\n")
        self.assertTrue(security.scan_secrets(p))

    def test_clean_file_passes(self):
        p = self.write("clean.md", "hello world\n")
        self.assertEqual(security.scan_secrets(p), [])

    def test_redact(self):
        out = security.redact("token: AKIAIOSFODNN7EXAMPLE done")
        self.assertIn("REDACTED", out)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", out)

    def test_tree_scan_skips_git(self):
        self.write(".git/x", "AKIAIOSFODNN7EXAMPLE")
        self.write("ok.txt", "nothing")
        self.assertEqual(security.scan_tree_secrets(self.root), [])


class ProfileTests(Base):
    def test_trusted_local_ok(self):
        security.enforce_profile(security.PROFILE_TRUSTED_LOCAL, False, False)

    def test_untrusted_requires_sandbox_and_signing(self):
        with self.assertRaises(MMACError):
            security.enforce_profile(security.PROFILE_SANDBOXED_UNTRUSTED, True, False)
        with self.assertRaises(MMACError):
            security.enforce_profile(security.PROFILE_SANDBOXED_UNTRUSTED, False, True)

    def test_untrusted_ok_when_both(self):
        security.enforce_profile(security.PROFILE_SANDBOXED_UNTRUSTED, True, True)

    def test_unknown_profile(self):
        with self.assertRaises(MMACError):
            security.enforce_profile("yolo", True, True)


if __name__ == "__main__":
    unittest.main()
