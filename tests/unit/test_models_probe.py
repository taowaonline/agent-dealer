"""models 探测（probe_clients/cmd_models/模型目录）单元测试：mock 探测，不依赖真实安装。"""
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_dealer import cli  # noqa: E402


def _proc(returncode=0, stdout=b"", stderr=b""):
    m = unittest.mock.Mock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _no_clients():
    return unittest.mock.patch.object(cli.shutil, "which", return_value=None)


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

    def test_registry_covers_mainstream_clients(self):
        clients = {spec["client"] for spec in cli.CLIENT_REGISTRY}
        self.assertLessEqual(
            {"claude", "codex", "kimi", "deepseek", "zai", "cursor"}, clients)

    def test_zai_probes_candidate_commands_in_order(self):
        seen = []

        def fake_which(cmd):
            seen.append(cmd)
            return "/usr/bin/%s" % cmd if cmd == "glm" else None

        with unittest.mock.patch.object(cli.shutil, "which", fake_which), \
             unittest.mock.patch.object(
                cli.subprocess, "run",
                return_value=_proc(stdout=b"glm-cli 1.0\n")):
            result = cli.probe_clients()
        zai = [item for item in result if item["client"] == "zai"][0]
        self.assertTrue(zai["installed"])
        self.assertEqual(zai["version"], "glm-cli 1.0")
        self.assertIn("zai", seen)
        self.assertIn("glm", seen)

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


class ModelsCatalogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.catalog = os.path.join(self._tmp.name, "models.json")

    def _env(self):
        return unittest.mock.patch.dict(os.environ, {cli.MODELS_FILE_ENV: self.catalog})

    def test_load_catalog(self):
        with open(self.catalog, "w") as fh:
            json.dump({"models": [
                {"client": "claude", "model": "gpt-5.6-sol",
                 "efforts": ["low", "medium", "high"], "thinking": True},
                {"client": "claude", "model": "glm-5.3",
                 "efforts": ["low", "medium", "high", "max"], "thinking": True},
            ]}, fh)
        with self._env():
            models = cli.load_models_catalog()
        self.assertEqual(models[0]["model"], "gpt-5.6-sol")
        self.assertEqual(models[1]["efforts"], ["low", "medium", "high", "max"])
        self.assertTrue(models[0]["thinking"])

    def test_missing_catalog_is_empty(self):
        with self._env():
            self.assertEqual(cli.load_models_catalog(), [])

    def test_malformed_catalog_degrades_to_empty(self):
        with open(self.catalog, "w") as fh:
            fh.write("{not json")
        with self._env(), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.load_models_catalog(), [])

    def test_entries_without_model_skipped(self):
        with open(self.catalog, "w") as fh:
            json.dump({"models": [{"client": "claude"}, {"model": "ok"}]}, fh)
        with self._env():
            models = cli.load_models_catalog()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["model"], "ok")

    def test_models_command_merges_catalog_with_probe(self):
        with open(self.catalog, "w") as fh:
            json.dump({"models": [
                {"client": "claude", "model": "gpt-5.6-sol",
                 "efforts": ["low", "medium", "high"], "thinking": True},
                {"client": "claude", "model": "glm-5.3",
                 "efforts": ["low", "medium", "high", "max"], "thinking": True},
            ]}, fh)
        fake = [{"client": "claude", "label": "Claude Code", "path": "/usr/bin/claude",
                 "installed": True, "version": "2.1.142"}]
        with self._env(), \
                unittest.mock.patch.object(cli, "probe_clients", return_value=fake):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["models"])
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("gpt-5.6-sol", text)
        self.assertIn("low/medium/high/max", text)
        self.assertIn("glm-5.3", text)
        self.assertIn("thinking: 支持", text)

    def test_models_json_shape(self):
        fake = [{"client": "claude", "label": "Claude Code", "path": None,
                 "installed": False, "version": None}]
        with self._env(), \
                unittest.mock.patch.object(cli, "probe_clients", return_value=fake):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["models", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["clients"], fake)
        self.assertEqual(data["models"], [])
        self.assertEqual(data["catalog_path"], self.catalog)

    def test_models_add_creates_and_upserts(self):
        with self._env():
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main([
                    "models", "--add", "claude:gpt-5.6-sol:low,medium,high:on",
                    "--add", "claude:glm-5.3:low,medium,high,max:on"])
        self.assertEqual(code, 0)
        with open(self.catalog) as fh:
            models = json.load(fh)["models"]
        self.assertEqual(len(models), 2)
        self.assertEqual(models[1]["model"], "glm-5.3")
        self.assertEqual(models[1]["efforts"], ["low", "medium", "high", "max"])
        self.assertTrue(models[1]["thinking"])
        # upsert：同 client+model 覆盖，不重复
        with self._env():
            with redirect_stdout(io.StringIO()):
                cli.main(["models", "--add", "claude:glm-5.3:high:off"])
        with open(self.catalog) as fh:
            models = json.load(fh)["models"]
        self.assertEqual(len(models), 2)
        glm = [m for m in models if m["model"] == "glm-5.3"][0]
        self.assertEqual(glm["efforts"], ["high"])
        self.assertFalse(glm["thinking"])

    def test_models_add_defaults(self):
        with self._env(), redirect_stdout(io.StringIO()):
            code = cli.main(["models", "--add", "kimi:kimi-k2.5"])
        self.assertEqual(code, 0)
        with open(self.catalog) as fh:
            m = json.load(fh)["models"][0]
        self.assertEqual(m["efforts"], ["low", "medium", "high"])
        self.assertFalse(m["thinking"])

    def test_models_add_rejects_bad_specs(self):
        cases = ["glm-5.3",                       # 缺 client
                 "claude:",                        # 缺 model
                 "claude:m:ultra",                 # 非法 effort
                 "claude:m:high:maybe",            # 非法 thinking
                 "claude:m:high:on:extra"]         # 段数超限
        for i, spec in enumerate(cases):
            with self._env(), redirect_stdout(io.StringIO()) as buf:
                code = cli.main(["models", "--add", spec])
            self.assertEqual(code, 1, spec)
            self.assertIn("MMAC-E105_INVALID_CONTROL", buf.getvalue(), spec)
            self.assertFalse(os.path.exists(self.catalog))

    def test_models_init_wizard_saves_selection(self):
        answers = iter(["", "gpt-5.6-sol", "low,medium,high", "y", "n"])
        with self._env(), \
                unittest.mock.patch("builtins.input", side_effect=lambda _: next(answers)), \
                unittest.mock.patch.object(cli, "probe_clients", return_value=[]), \
                unittest.mock.patch.object(sys.stdin, "isatty", return_value=True), \
                redirect_stdout(io.StringIO()):
            code = cli.main(["models", "--init"])
        self.assertEqual(code, 0)
        with open(self.catalog) as fh:
            models = json.load(fh)["models"]
        self.assertEqual(models, [{"client": "claude", "model": "gpt-5.6-sol",
                                   "efforts": ["low", "medium", "high"], "thinking": True}])

    def test_models_init_non_tty_suggests_add(self):
        with self._env(), \
                unittest.mock.patch.object(sys.stdin, "isatty", return_value=False), \
                redirect_stdout(io.StringIO()) as buf:
            code = cli.main(["models", "--init"])
        self.assertEqual(code, 1)
        self.assertIn("--add", buf.getvalue())
        self.assertFalse(os.path.exists(self.catalog))

    def test_models_init_refuses_existing(self):
        with open(self.catalog, "w") as fh:
            json.dump({"models": []}, fh)
        with self._env(), redirect_stdout(io.StringIO()):
            code = cli.main(["models", "--init"])
        self.assertEqual(code, 1)

    def test_models_hint_without_catalog(self):
        fake = [{"client": "claude", "label": "Claude Code", "path": None,
                 "installed": False, "version": None}]
        with self._env(), \
                unittest.mock.patch.object(cli, "probe_clients", return_value=fake):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["models"])
        self.assertEqual(code, 0)
        self.assertIn("--init", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
