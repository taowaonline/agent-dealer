"""cli.py 单元测试：通过 main() 端到端驱动各子命令。"""
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_dealer.cli import main  # noqa: E402


class CliTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self._cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self._cwd)

    def run_cli(self, *argv):
        buf = StringIO()
        with redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def init_task(self, task_id="task-cli-001"):
        code, out = self.run_cli(
            "init", task_id, "--title", "CLI 测试任务",
            "--model", "test-model")
        self.assertEqual(code, 0, out)
        return os.path.join("tasks", task_id)


class InitTests(CliTestBase):
    def test_init_creates_structure(self):
        task_dir = self.init_task()
        for sub in ("control.md", "coordination.md", "artifacts", "locks", "tmp"):
            self.assertTrue(os.path.exists(os.path.join(task_dir, sub)), sub)
        code, out = self.run_cli("validate", task_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("全部通过", out)

    def test_init_twice_fails(self):
        self.init_task()
        code, out = self.run_cli("init", "task-cli-001", "--title", "x", "--model", "m")
        self.assertEqual(code, 1)

    def test_init_requires_real_model(self):
        env = {k: v for k, v in os.environ.items() if k != "MMAC_MODEL"}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            code, out = self.run_cli("init", "task-model-001", "--title", "x")
        self.assertEqual(code, 1)
        self.assertIn("MMAC-E202_PLACEHOLDER_MODEL", out)
        code, out = self.run_cli("init", "task-model-002", "--title", "x",
                                 "--model", "unknown-model")
        self.assertEqual(code, 1)
        self.assertIn("MMAC-E202_PLACEHOLDER_MODEL", out)

    def test_quickstart_path_within_five_commands(self):
        # 文档 §8.1：从 init 到 PLAN_READY 不超过 5 条命令
        task_dir = self.init_task()                                        # 1
        code, out = self.run_cli("event", "prepare", task_dir,
                                 "--type", "PLANNING_STARTED", "--role", "A",
                                 "--model", "gpt-5.6-luna")                # 2
        self.assertEqual(code, 0, out)
        ev_path = out.split("已写入 ")[1].split("\n")[0].strip()
        code, out = self.run_cli("publish", task_dir, ev_path,
                                 "--instance-id", "a-1")                   # 3
        self.assertEqual(code, 0, out)
        with open("plan.md", "w") as fh:
            fh.write("# plan\n")
        code, out = self.run_cli("artifact", "add", task_dir, "plan.md",
                                 "--dest", "artifacts/plans/plan-v001.md",
                                 "--media-type", "text/markdown")          # 4
        self.assertEqual(code, 0, out)
        art = json.loads(out)
        code, out = self.run_cli("event", "prepare", task_dir,
                                 "--type", "PLAN_READY", "--role", "A",
                                 "--model", "gpt-5.6-luna")                # 5 内完成
        ev_path = out.split("已写入 ")[1].split("\n")[0].strip()
        with open(ev_path) as fh:
            ev = json.load(fh)
        ev["artifacts"] = [art]
        ev["recipient"] = {"role": "B"}
        with open(ev_path, "w") as fh:
            json.dump(ev, fh)
        code, out = self.run_cli("publish", task_dir, ev_path, "--instance-id", "a-1")
        self.assertEqual(code, 0, out)
        code, out = self.run_cli("status", task_dir)
        self.assertIn("PLAN_READY", out)


class StatusNextTests(CliTestBase):
    def test_status_json(self):
        task_dir = self.init_task()
        code, out = self.run_cli("status", task_dir, "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["final_status"], "CREATED")
        self.assertEqual(data["event_count"], 1)

    def test_next_routing(self):
        task_dir = self.init_task()
        code, out = self.run_cli("next", task_dir, "--json")
        data = json.loads(out)
        self.assertEqual(data["next_role"], "A")
        self.assertFalse(data["done"])


class ClaimTests(CliTestBase):
    def test_claim_publishes_event_and_lease(self):
        task_dir = self.init_task()
        # 先到 PLAN_READY 才能合法 CLAIM
        self.run_cli("event", "prepare", task_dir, "--type", "PLANNING_STARTED",
                     "--role", "A", "--model", "gpt-5.6-luna", "--out", "e1.json")
        self.run_cli("publish", task_dir, "e1.json", "--instance-id", "a-1")
        with open("p.md", "w") as fh:
            fh.write("x\n")
        _, out = self.run_cli("artifact", "add", task_dir, "p.md",
                              "--dest", "artifacts/plans/plan-v001.md",
                              "--media-type", "text/markdown")
        art = json.loads(out)
        self.run_cli("event", "prepare", task_dir, "--type", "PLAN_READY",
                     "--role", "A", "--model", "gpt-5.6-luna", "--out", "e2.json")
        with open("e2.json") as fh:
            ev = json.load(fh)
        ev["artifacts"] = [art]
        with open("e2.json", "w") as fh:
            json.dump(ev, fh)
        self.run_cli("publish", task_dir, "e2.json", "--instance-id", "a-1")
        code, out = self.run_cli("claim", task_dir, "--role", "B",
                                 "--instance-id", "b-1", "--model", "kimi-k2.5")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(task_dir, "locks", "claim-B.json")))
        code, out = self.run_cli("validate", task_dir)
        self.assertEqual(code, 0, out)


class DoctorTests(CliTestBase):
    def test_doctor_healthy(self):
        task_dir = self.init_task()
        code, out = self.run_cli("doctor", task_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("健康", out)

    def test_doctor_detects_secret(self):
        task_dir = self.init_task()
        with open(os.path.join(task_dir, "tmp", "leak.txt"), "w") as fh:
            fh.write("AKIAIOSFODNN7EXAMPLE\n")
        code, out = self.run_cli("doctor", task_dir)
        self.assertEqual(code, 1)
        self.assertIn("密钥", out)


class PublishTests(CliTestBase):
    def test_dry_run_does_not_append(self):
        task_dir = self.init_task()
        self.run_cli("event", "prepare", task_dir, "--type", "PLANNING_STARTED",
                     "--role", "A", "--model", "gpt-5.6-luna", "--out", "e.json")
        before = open(os.path.join(task_dir, "coordination.md")).read()
        code, out = self.run_cli("publish", "--dry-run", task_dir, "e.json")
        self.assertEqual(code, 0, out)
        after = open(os.path.join(task_dir, "coordination.md")).read()
        self.assertEqual(before, after)

    def test_publish_invalid_event_fails(self):
        task_dir = self.init_task()
        with open("bad.json", "w") as fh:
            json.dump({"type": "WORK_READY"}, fh)
        code, out = self.run_cli("publish", task_dir, "bad.json", "--instance-id", "x")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
