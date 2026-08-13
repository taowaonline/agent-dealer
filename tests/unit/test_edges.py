"""覆盖率补充：边界与错误路径。"""
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import TaskTestCase, append_event, make_artifact, make_event, review_payload  # noqa: E402
from agent_collaboration import validator  # noqa: E402
from agent_collaboration.cli import main as cli_main  # noqa: E402
from agent_collaboration.errors import MMACError  # noqa: E402
from agent_collaboration.runner import Runner  # noqa: E402
from agent_collaboration.adapters.base import Adapter  # noqa: E402
from agent_collaboration.adapters.command import CommandAdapter  # noqa: E402
from agent_collaboration.adapters.manual import ManualAdapter  # noqa: E402


class ControlParseEdgeTests(TaskTestCase):
    def _write_control(self, text):
        with open(os.path.join(self.task_dir, "control.md"), "w") as fh:
            fh.write(text)

    def test_missing_control(self):
        os.unlink(os.path.join(self.task_dir, "control.md"))
        self.assertIn("control-missing", self.rules(self.validate()))

    def test_control_missing_agents(self):
        self._write_control("workflow:\n  planning_agent: A\n  default_executor: B\n"
                            "  multimodal_executor: C\n  reviewer: A\n"
                            "quality_gate:\n  target_score: 90\n  max_score: 100\n"
                            "  max_revision_cycles: 3\n"
                            "permissions:\n  allowed_paths: [\"./\"]\n  forbidden_paths: []\n")
        self.assertIn("control-agents-missing", self.rules(self.validate()))

    def test_control_rubric_sum(self):
        self._write_control("agents:\n  A:\n  B:\n  C:\n"
                            "workflow:\n  planning_agent: A\n  default_executor: B\n"
                            "  multimodal_executor: C\n  reviewer: A\n"
                            "quality_gate:\n  target_score: 90\n  max_score: 100\n"
                            "  max_revision_cycles: 3\n"
                            "rubric:\n  a: 50\n  b: 40\n"
                            "permissions:\n  allowed_paths: [\"./\"]\n  forbidden_paths: []\n")
        self.assertIn("control-rubric", self.rules(self.validate()))

    def test_control_target_above_max(self):
        self._write_control("agents:\n  A:\n  B:\n  C:\n"
                            "workflow:\n  planning_agent: A\n  default_executor: B\n"
                            "  multimodal_executor: C\n  reviewer: A\n"
                            "quality_gate:\n  target_score: 110\n  max_score: 100\n"
                            "  max_revision_cycles: 3\n"
                            "permissions:\n  allowed_paths: [\"./\"]\n  forbidden_paths: []\n")
        self.assertIn("control-field-range", self.rules(self.validate()))

    def test_control_scalar_list_fallback(self):
        # 非 JSON 列表语法的兼容解析
        self.assertEqual(validator._parse_scalar("[a, b, c]"), ["a", "b", "c"])
        self.assertEqual(validator._parse_scalar("true"), True)
        self.assertEqual(validator._parse_scalar("~"), None)
        self.assertEqual(validator._parse_scalar("42"), 42)
        self.assertEqual(validator._parse_scalar("'quoted'"), "quoted")
        self.assertEqual(validator._parse_scalar(""), "")


class EventFieldEdgeTests(TaskTestCase):
    def _broken(self, mutate):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        mutate(ev)
        append_event(self.task_dir, ev)
        return self.validate()

    def test_empty_event_id(self):
        self.assertIn("bad-event-id", self.rules(self._broken(lambda e: e.update(event_id=""))))

    def test_empty_task_id(self):
        self.assertIn("bad-task-id", self.rules(self._broken(lambda e: e.update(task_id=""))))

    def test_empty_protocol_version(self):
        self.assertIn("bad-protocol-version",
                      self.rules(self._broken(lambda e: e.update(protocol_version=""))))

    def test_timestamp_non_string(self):
        self.assertIn("bad-timestamp", self.rules(self._broken(lambda e: e.update(timestamp=123))))

    def test_actor_non_dict(self):
        self.assertIn("bad-actor", self.rules(self._broken(lambda e: e.update(actor="A"))))

    def test_recipient_non_dict(self):
        self.assertIn("bad-recipient", self.rules(self._broken(lambda e: e.update(recipient="A"))))

    def test_recipient_missing_role(self):
        self.assertIn("bad-recipient",
                      self.rules(self._broken(lambda e: e.update(recipient={"x": 1}))))

    def test_previous_bad_type(self):
        self.assertIn("bad-previous",
                      self.rules(self._broken(lambda e: e.update(previous_event_id=42))))

    def test_caused_by_bad_type(self):
        self.assertIn("bad-caused-by",
                      self.rules(self._broken(lambda e: e.update(caused_by=42))))

    def test_artifacts_non_list(self):
        self.assertIn("bad-artifacts",
                      self.rules(self._broken(lambda e: e.update(artifacts="x"))))

    def test_artifact_non_dict_entry(self):
        self.assertIn("bad-artifact",
                      self.rules(self._broken(lambda e: e.update(artifacts=["x"]))))

    def test_artifact_bad_version(self):
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        art["version"] = 0
        self.assertIn("bad-artifact-version",
                      self.rules(self._broken(lambda e: e.update(artifacts=[art]))))

    def test_artifact_missing_field(self):
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        del art["media_type"]
        self.assertIn("bad-artifact", self.rules(self._broken(lambda e: e.update(artifacts=[art]))))

    def test_unknown_status_string(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        # 未知 type + 未知 status 都被捕获
        ev["type"] = "WAT"
        self.assertIn("unknown-event-type", self.rules(self._broken(lambda e: e.update(type="WAT"))))


class SubtaskPolicyTests(TaskTestCase):
    def _setup_parallel(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        payload = {"subtasks": [{"subtask_id": "ST-1", "owner": "B"},
                                {"subtask_id": "ST-2", "owner": "C"}]}
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art], payload=payload))

    def test_unknown_subtask(self):
        self._setup_parallel()
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004",
            caused_by="evt-0003", payload={"subtask_id": "ST-99"}))
        self.assertIn("unknown-subtask", self.rules(self.validate()))

    def test_owner_mismatch(self):
        self._setup_parallel()
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "C", "evt-0003", "evt-0004",
            caused_by="evt-0003", payload={"subtask_id": "ST-1"}))
        self.assertIn("subtask-owner-mismatch", self.rules(self.validate()))

    def test_premature_review(self):
        self._setup_parallel()
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004",
            caused_by="evt-0003", payload={"subtask_id": "ST-1"}))
        append_event(self.task_dir, make_event(
            self.task_id, "EXECUTION_STARTED", "B", "evt-0004", "evt-0005",
            caused_by="evt-0004", payload={"subtask_id": "ST-1"}))
        ex = make_artifact(self.task_dir, "artifacts/executions/e.md")
        append_event(self.task_dir, make_event(
            self.task_id, "WORK_READY", "B", "evt-0005", "evt-0006",
            caused_by="evt-0003", artifacts=[ex], payload={"subtask_id": "ST-1"}))
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_STARTED", "A", "evt-0006", "evt-0007", caused_by="evt-0006"))
        self.assertIn("premature-review", self.rules(self.validate()))

    def test_parallel_missing_subtask_id_warns(self):
        self._setup_parallel()
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004", caused_by="evt-0003"))
        r = self.validate()
        self.assertIn("missing-subtask-id", {i.rule for i in r.warnings})

    def test_legacy_subtask_field_warns(self):
        self._setup_parallel()
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004",
            caused_by="evt-0003", payload={"subtask": "ST-1"}))
        r = self.validate()
        self.assertIn("legacy-subtask-field", {i.rule for i in r.warnings})


class PolicyEdgeTests(TaskTestCase):
    def test_reopen_by_non_coordinator(self):
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CANCELLED", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001"))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_REOPENED", "B", "evt-0002", "evt-0003", caused_by="evt-0002"))
        self.assertIn("unauthorized-role", self.rules(self.validate()))

    def test_role_override_grants_executor(self):
        append_event(self.task_dir, make_event(
            self.task_id, "ROLE_OVERRIDE", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001", status="CREATED", payload={"role": "A"}))
        # A 现在被授权执行
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0002", "evt-0003", caused_by="evt-0002"))
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0003", "evt-0004",
            caused_by="evt-0003", artifacts=[art]))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "A", "evt-0004", "evt-0005", caused_by="evt-0004"))
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])

    def test_role_override_by_executor_rejected(self):
        append_event(self.task_dir, make_event(
            self.task_id, "ROLE_OVERRIDE", "B", "evt-0001", "evt-0002",
            caused_by="evt-0001", status="CREATED", payload={"role": "B"}))
        self.assertIn("unauthorized-role", self.rules(self.validate()))

    def test_revision_cycle_jump(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
            caused_by="evt-0001", revision_cycle=2))
        self.assertIn("revision-jump", self.rules(self.validate()))

    def test_review_score_bool(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art]))
        p = review_payload(score=95)
        p["score"] = True
        rv = make_artifact(self.task_dir, "artifacts/reviews/r.md")
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004", caused_by="evt-0003"))
        append_event(self.task_dir, make_event(
            self.task_id, "EXECUTION_STARTED", "B", "evt-0004", "evt-0005", caused_by="evt-0004"))
        ex = make_artifact(self.task_dir, "artifacts/executions/e.md")
        append_event(self.task_dir, make_event(
            self.task_id, "WORK_READY", "B", "evt-0005", "evt-0006",
            caused_by="evt-0003", artifacts=[ex]))
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_STARTED", "A", "evt-0006", "evt-0007", caused_by="evt-0007"))
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_APPROVED", "A", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[rv], payload=p))
        self.assertIn("bad-score", self.rules(self.validate()))


class ArtifactPathEdgeTests(TaskTestCase):
    def test_forbidden_path_hit(self):
        # .git/ 在 forbidden_paths
        gitdir = os.path.join(self.root, ".git")
        os.makedirs(gitdir, exist_ok=True)
        with open(os.path.join(gitdir, "x"), "w") as fh:
            fh.write("x")
        import hashlib
        art = {"path": os.path.join(gitdir, "x"),
               "sha256": hashlib.sha256(b"x").hexdigest(),
               "media_type": "text/plain", "version": 1}
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
            caused_by="evt-0001", artifacts=[art]))
        self.assertIn("path-forbidden", self.rules(self.validate()))

    def test_abs_path_outside_allowed(self):
        import hashlib
        outside = os.path.join(self.root, "outside.md")
        with open(outside, "w") as fh:
            fh.write("x")
        # allowed_paths 是 ./，outside.md 在 root 下所以其实允许；
        # 改成 /etc/hosts 这种确定越界
        art = {"path": "/etc/hosts", "sha256": "0" * 64,
               "media_type": "text/plain", "version": 1}
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
            caused_by="evt-0001", artifacts=[art]))
        rules = self.rules(self.validate())
        self.assertTrue(rules & {"path-not-allowed", "hash-mismatch"}, rules)

    def test_symlink_escape(self):
        import hashlib
        outside = os.path.join(self.root, "outside-secret.txt")
        with open(outside, "w") as fh:
            fh.write("secret\n")
        link = os.path.join(self.task_dir, "artifacts", "link.txt")
        os.symlink(outside, link)
        art = {"path": "artifacts/link.txt",
               "sha256": hashlib.sha256(b"secret\n").hexdigest(),
               "media_type": "text/plain", "version": 1}
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
            caused_by="evt-0001", artifacts=[art]))
        self.assertIn("symlink-escape", self.rules(self.validate()))


class ApiSurfaceTests(TaskTestCase):
    def test_serialize_event_roundtrip(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "e2",
                        caused_by="evt-0001")
        block = validator.serialize_event(ev)
        self.assertIn("MMAC-EVENT-BEGIN", block)
        parsed = validator.parse_events(block, validator.ValidationReport("x"))
        self.assertEqual(parsed[0]["event_id"], "e2")

    def test_validate_missing_coordination(self):
        r = validator.validate_task(os.path.join(self.root, "nowhere"))
        self.assertIn("coordination-missing", {i.rule for i in r.errors})

    def test_format_report_and_json_main(self):
        r = self.validate()
        text = validator.format_report(r)
        self.assertIn("全部通过", text)
        buf = StringIO()
        with redirect_stdout(buf):
            code = validator.main([self.task_dir, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(buf.getvalue())
        self.assertTrue(data["ok"])

    def test_validator_main_usage_error(self):
        buf = StringIO()
        with redirect_stdout(buf):
            code = validator.main([])
        self.assertEqual(code, 2)

    def test_expected_warnings_malformed(self):
        with open(os.path.join(self.task_dir, "expected-warnings.json"), "w") as fh:
            fh.write("{broken")
        r = self.validate()  # 不应崩溃
        self.assertTrue(r.ok)

    def test_report_to_dict(self):
        d = self.validate().to_dict()
        self.assertEqual(d["final_status"], "CREATED")
        self.assertEqual(d["last_event_type"], "TASK_CREATED")


class CliEdgeTests(TaskTestCase):
    def run_cli(self, *argv):
        buf = StringIO()
        with redirect_stdout(buf):
            code = cli_main(list(argv))
        return code, buf.getvalue()

    def test_no_command_prints_help(self):
        code, _ = self.run_cli()
        self.assertEqual(code, 2)

    def test_status_on_missing_task(self):
        code, out = self.run_cli("status", os.path.join(self.root, "ghost"))
        self.assertEqual(code, 1)

    def test_next_on_terminal(self):
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CANCELLED", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001"))
        code, out = self.run_cli("next", self.task_dir, "--json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["done"])

    def test_next_role_filter_message(self):
        code, out = self.run_cli("next", self.task_dir, "--role", "B", "--json")
        data = json.loads(out)
        self.assertIn("无待办", data.get("message", ""))

    def test_next_on_broken_chain(self):
        with open(os.path.join(self.task_dir, "coordination.md"), "a") as fh:
            fh.write("\n<!-- MMAC-EVENT-BEGIN -->\n```json\n{bad\n```\n<!-- MMAC-EVENT-END -->\n")
        code, out = self.run_cli("next", self.task_dir)
        self.assertEqual(code, 1)

    def test_event_prepare_status_keeping(self):
        code, out = self.run_cli("event", "prepare", self.task_dir,
                                 "--type", "HEARTBEAT", "--role", "B",
                                 "--model", "kimi-k2.5", "--out",
                                 os.path.join(self.root, "hb.json"))
        self.assertEqual(code, 0, out)
        with open(os.path.join(self.root, "hb.json")) as fh:
            ev = json.load(fh)
        self.assertEqual(ev["status"], "CREATED")  # 继承当前状态

    def test_claim_empty_task(self):
        import shutil
        empty = os.path.join(self.root, "tasks", "task-empty")
        os.makedirs(empty)
        with open(os.path.join(empty, "coordination.md"), "w") as fh:
            fh.write("# empty\n")
        code, out = self.run_cli("claim", empty, "--role", "B", "--model", "kimi-k2.5")
        self.assertEqual(code, 1)


class RunnerEdgeTests(TaskTestCase):
    def test_run_loop_idle_exit(self):
        runner = Runner(self.task_dir, {"B": ManualAdapter(stream=StringIO())},
                        poll_interval=0.01, max_idle_cycles=3)
        runner.run()  # 应自行退出

    def test_run_loop_terminal_callback(self):
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CANCELLED", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001"))
        runner = Runner(self.task_dir, {}, poll_interval=0.01)
        seen = []
        runner.run(on_event=lambda k, d: seen.append(k))
        self.assertIn("terminal", seen)

    def test_dispatch_without_adapter(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art], recipient="B"))
        runner = Runner(self.task_dir, {}, poll_interval=0.01)
        event = runner.store.last_event()
        with self.assertRaises(MMACError):
            runner.dispatch(event)


class AdapterEdgeTests(unittest.TestCase):
    def test_base_adapter_defaults(self):
        a = Adapter()
        self.assertTrue(a.detect())
        self.assertIsNone(a.build_command("t", "B", "p"))
        self.assertEqual(a.poll("x"), "unknown")
        self.assertEqual(a.stop("x").state, "stopped")

    def test_command_stop_unknown(self):
        a = CommandAdapter(["true"])
        self.assertEqual(a.stop("nope").state, "unknown")

    def test_command_poll_unknown(self):
        a = CommandAdapter(["true"])
        self.assertEqual(a.poll("nope"), "unknown")


if __name__ == "__main__":
    unittest.main()
