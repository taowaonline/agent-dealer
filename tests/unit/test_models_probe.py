"""models 探测（probe_clients/cmd_models）单元测试：全部 mock，不依赖真实安装。"""
import json
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_dealer import cli  # noqa: E402


def _proc(returncode=0, stdout=b"", stderr=b""):
    m = unittest.mock.Mock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


class ProbeClientsTests(unittest.TestCase):
    def test_installed_and_missing(self):
        with unittest.mock.patch.object(
                cli.shutil, "which",
                side_effect=lambda c: "/usr/bin/%s" % c if c == "codex" else None), \
             unittest.mock.patch.object(
                cli.subprocess, "run",
                return_value=_proc(stdout=b"codex-cli 1.2.3\n")):
            result = cli.probe_clients()
        by_name = {item["client"]: item for item in result}
        self.assertTrue(by_name["codex"]["installed"])
        self.assertEqual(by_name["codex"]["version"], "codex-cli 1.2.3")
        self.assertEqual(by_name["codex"]["path"], "/usr/bin/codex")
        self.assertFalse(by_name["claude"]["installed"])
        self.assertIsNone(by_name["claude"]["path"])
        self.assertIsNone(by_name["claude"]["version"])

    def test_timeout_degrades_to_unknown(self):
        import subprocess as real_subprocess
        with unittest.mock.patch.object(
                cli.shutil, "which", return_value="/usr/bin/codex"), \
             unittest.mock.patch.object(
                cli.subprocess, "run",
                side_effect=real_subprocess.TimeoutExpired(cmd="codex", timeout=10)):
            result = cli.probe_clients()
        self.assertEqual(result[0]["installed"], True)
        self.assertEqual(result[0]["version"], "unknown")

    def test_nonzero_exit_degrades_to_unknown(self):
        with unittest.mock.patch.object(
                cli.shutil, "which", return_value="/usr/bin/codex"), \
             unittest.mock.patch.object(
                cli.subprocess, "run", return_value=_proc(returncode=1)):
            result = cli.probe_clients()
        self.assertEqual(result[0]["version"], "unknown")

    def test_os_error_swallowed(self):
        with unittest.mock.patch.object(
                cli.shutil, "which", return_value="/usr/bin/codex"), \
             unittest.mock.patch.object(cli.subprocess, "run", side_effect=OSError("boom")):
            result = cli.probe_clients()
        self.assertEqual(result[0]["version"], "unknown")

    def test_stderr_fallback_for_version(self):
        with unittest.mock.patch.object(
                cli.shutil, "which", return_value="/usr/bin/kimi"), \
             unittest.mock.patch.object(
                cli.subprocess, "run",
                return_value=_proc(stdout=b"", stderr=b"kimi 0.37.1\n")):
            result = cli.probe_clients()
        self.assertEqual(result[0]["version"], "kimi 0.37.1")


class ModelsCommandTests(unittest.TestCase):
    def test_models_json(self):
        fake = [{"client": "codex", "path": "/usr/bin/codex", "installed": True,
                 "version": "codex-cli 1.2.3"},
                {"client": "claude", "path": None, "installed": False, "version": None}]
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with unittest.mock.patch.object(cli, "probe_clients", return_value=fake), \
                redirect_stdout(buf):
            code = cli.main(["models", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue()), fake)

    def test_models_text(self):
        fake = [{"client": "codex", "path": "/usr/bin/codex", "installed": True,
                 "version": "codex-cli 1.2.3"},
                {"client": "claude", "path": None, "installed": False, "version": None}]
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with unittest.mock.patch.object(cli, "probe_clients", return_value=fake), \
                redirect_stdout(buf):
            code = cli.main(["models"])
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("codex ✓ codex-cli 1.2.3", text)
        self.assertIn("claude ✗ 未安装", text)


if __name__ == "__main__":
    unittest.main()
