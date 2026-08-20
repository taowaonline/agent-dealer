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


class InitTierTests(CliTestBase):
    def _control(self, task_id):
        with open(os.path.join("tasks", task_id, "control.md")) as fh:
            return fh.read()

    def test_init_tiers_written_to_control(self):
        code, out = self.run_cli(
            "init", "task-tier-001", "--title", "x", "--model", "m1",
            "--effort", "max", "--thinking", "on", "--permission-mode", "confirm",
            "--role-config", "A:effort=high", "--role-config", "A:model=gpt-5.6-luna")
        self.assertEqual(code, 0, out)
        control = self._control("task-tier-001")
        self.assertIn("permission_mode: confirm", control)
        self.assertIn("model: gpt-5.6-luna", control)
        self.assertIn("effort: high", control)   # A 角色 role-config 覆盖
        self.assertIn("effort: max", control)    # B/C 继承全局默认
        self.assertIn("thinking: on", control)
        # 新字段落盘后链校验零错误
        code, out = self.run_cli("validate", "tasks/task-tier-001")
        self.assertEqual(code, 0, out)

    def test_init_defaults_are_medium_off_yolo(self):
        task_dir = self.init_task()  # 不带任何新参数
        control = self._control("task-cli-001")
        self.assertIn("effort: medium", control)
        self.assertIn("thinking: off", control)
        self.assertIn("permission_mode: yolo", control)
        code, out = self.run_cli("validate", task_dir)
        self.assertEqual(code, 0, out)

    def test_solo_init_accepts_only_solo_role_config(self):
        code, out = self.run_cli(
            "init", "task-solo-tier", "--title", "x", "--model", "m1",
            "--solo", "--effort", "high", "--role-config", "B:thinking=on")
        self.assertEqual(code, 0, out)
        control = self._control("task-solo-tier")
        self.assertIn("mode: solo", control)
        self.assertIn("effort: high", control)
        self.assertIn("thinking: on", control)
        # solo 只有一个角色：A 不在有效角色集合
        code, out = self.run_cli(
            "init", "task-solo-bad", "--title", "x", "--model", "m1",
            "--solo", "--role-config", "A:effort=high")
        self.assertEqual(code, 1)
        self.assertIn("MMAC-E105_INVALID_CONTROL", out)

    def test_role_config_rejects_bad_inputs(self):
        cases = [
            ("bad-format", 1, "MMAC-E105_INVALID_CONTROL"),
            ("Z:effort=high", 1, "MMAC-E105_INVALID_CONTROL"),
            ("A:foo=1", 1, "MMAC-E105_INVALID_CONTROL"),
            ("A:effort=ultra", 1, "MMAC-E105_INVALID_CONTROL"),
            ("A:thinking=maybe", 1, "MMAC-E105_INVALID_CONTROL"),
            ("A:model=todo", 1, "MMAC-E202_PLACEHOLDER_MODEL"),
        ]
        for i, (cfg, want_code, want_err) in enumerate(cases):
            code, out = self.run_cli(
                "init", "task-role-bad-%d" % i, "--title", "x",
                "--model", "m1", "--role-config", cfg)
            self.assertEqual(code, want_code, (cfg, out))
            self.assertIn(want_err, out, cfg)


class ReportTests(CliTestBase):
    def _drive_to_review(self, task_id):
        """A 规划、B 执行的完整合法链至 REVIEW_STARTED，返回 (task_dir, review 产物)。"""
        from helpers import make_task, append_event, make_artifact, make_event
        task_dir = make_task(self.root, task_id)
        append_event(task_dir, make_event(task_id, "PLANNING_STARTED", "A",
                                          "evt-0001", "evt-0002", caused_by="evt-0001"))
        plan = make_artifact(task_dir, "artifacts/plans/plan-v001.md")
        append_event(task_dir, make_event(
            task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[plan], recipient="B"))
        append_event(task_dir, make_event(task_id, "TASK_CLAIMED", "B",
                                          "evt-0003", "evt-0004", caused_by="evt-0003"))
        append_event(task_dir, make_event(task_id, "EXECUTION_STARTED", "B",
                                          "evt-0004", "evt-0005", caused_by="evt-0004"))
        ex = make_artifact(task_dir, "artifacts/executions/execution-b-v001.md")
        append_event(task_dir, make_event(
            task_id, "WORK_READY", "B", "evt-0005", "evt-0006",
            caused_by="evt-0003", artifacts=[ex]))
        append_event(task_dir, make_event(task_id, "REVIEW_STARTED", "A",
                                          "evt-0006", "evt-0007", caused_by="evt-0006"))
        return task_dir, make_artifact(task_dir, "artifacts/reviews/review-v001.md")

    def _full_chain(self, task_id="task-report-001"):
        from helpers import append_event, make_event, review_payload
        task_dir, review = self._drive_to_review(task_id)
        append_event(task_dir, make_event(
            task_id, "REVIEW_APPROVED", "A", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[review],
            payload=review_payload(score=95)))
        return task_dir

    def test_report_json_aggregates_agents_and_evaluation(self):
        task_dir = self._full_chain()
        code, out = self.run_cli("report", task_dir, "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["final_status"], "APPROVED")
        self.assertEqual(data["event_count"], 8)
        by_role = {a["role"]: a for a in data["agents"]}
        self.assertEqual(by_role["A"]["event_counts"]["PLANNING_STARTED"], 1)
        self.assertEqual(by_role["A"]["event_counts"]["REVIEW_APPROVED"], 1)
        self.assertEqual(by_role["B"]["event_counts"]["TASK_CLAIMED"], 1)
        self.assertEqual(
            [a["path"] for a in by_role["A"]["artifacts"]],
            ["artifacts/plans/plan-v001.md", "artifacts/reviews/review-v001.md"])
        self.assertEqual(by_role["A"]["latest_review"]["score"], 95)
        self.assertEqual(data["evaluation"]["type"], "REVIEW_APPROVED")
        self.assertEqual(data["evaluation"]["score"], 95)
        self.assertFalse(data["evaluation"]["self_review"])
        self.assertEqual(data["todos"], [])

    def test_report_text_output(self):
        task_dir = self._full_chain()
        code, out = self.run_cli("report", task_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("各 Agent 贡献", out)
        self.assertIn("任务评价", out)
        self.assertIn("REVIEW_APPROVED by A: score=95", out)
        self.assertIn("TODO", out)

    def test_report_lists_unresolved_revision_issues(self):
        from helpers import append_event, make_event, review_payload
        task_dir, review = self._drive_to_review("task-report-rev")
        payload = {**review_payload(score=60, blocking=2),
                   "issues": ["测试缺失", {"description": "文档未更新"}]}
        append_event(task_dir, make_event(
            "task-report-rev", "REVISION_REQUIRED", "A", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[review], payload=payload))
        code, out = self.run_cli("report", task_dir, "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["evaluation"]["type"], "REVISION_REQUIRED")
        todos = [t["todo"] for t in data["todos"]]
        self.assertIn("测试缺失", todos)
        self.assertIn("文档未更新", todos)

    def test_report_flags_solo_temporary_approval(self):
        from helpers import (append_event, make_event, make_artifact,
                             review_payload)
        task_dir, _ = self._drive_to_review("task-report-solo")
        # 切 solo：B 全链自审需自证证据
        path = os.path.join(task_dir, "control.md")
        with open(path) as fh:
            text = fh.read()
        with open(path, "w") as fh:
            fh.write(text.replace("workflow:\n", "workflow:\n  mode: solo\n", 1))
        review = make_artifact(task_dir, "artifacts/reviews/review-v002.md")
        payload = {**review_payload(score=95), "self_review": True,
                   "reproduced_commands": ["agent_dealer validate tasks/x"]}
        append_event(task_dir, make_event(
            "task-report-solo", "REVIEW_APPROVED", "B", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[review], payload=payload))
        code, out = self.run_cli("report", task_dir, "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertTrue(data["evaluation"]["self_review"])
        self.assertTrue(any("独立" in t["todo"] for t in data["todos"]))

    def test_report_on_fresh_task(self):
        task_dir = self.init_task()
        code, out = self.run_cli("report", task_dir, "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertEqual(data["final_status"], "CREATED")
        self.assertEqual(data["agents"][0]["role"], "coordinator")
        self.assertIsNone(data["evaluation"])


if __name__ == "__main__":
    unittest.main()
