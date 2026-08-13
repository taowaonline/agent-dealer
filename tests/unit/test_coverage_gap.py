"""覆盖率收尾：watch、doctor JSON、claim subtask、锁状态分支、--version、adapter stop。"""
import json
import os
import sys
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import TaskTestCase, append_event, make_event  # noqa: E402
from agent_dealer.cli import main as cli_main  # noqa: E402
from agent_dealer.store import TaskStore  # noqa: E402
from agent_dealer.adapters.command import CommandAdapter  # noqa: E402


class CliCoverageTests(TaskTestCase):
    def run_cli(self, *argv):
        buf = StringIO()
        with redirect_stdout(buf):
            code = cli_main(list(argv))
        return code, buf.getvalue()

    def test_version_flag(self):
        code, out = self.run_cli("--version")
        self.assertEqual(code, 0)
        self.assertRegex(out.strip(), r"^\d+\.\d+\.\d+$")

    def test_doctor_json(self):
        code, out = self.run_cli("doctor", self.task_dir, "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(data["ok"])
        self.assertIn("clients", data)

    def test_doctor_with_active_lock_note(self):
        store = TaskStore(self.task_dir)
        store.acquire_lock("someone")
        code, out = self.run_cli("doctor", self.task_dir, "--json")
        data = json.loads(out)
        self.assertTrue(any("持有" in n for n in data["notes"]))
        store.release_lock(None, force=True)

    def test_doctor_with_expired_lock(self):
        store = TaskStore(self.task_dir)
        store.acquire_lock("dead")
        info_path = os.path.join(store.lock_path, "owner.json")
        with open(info_path) as fh:
            info = json.load(fh)
        info["lease_until"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        with open(info_path, "w") as fh:
            json.dump(info, fh)
        code, out = self.run_cli("doctor", self.task_dir, "--json")
        data = json.loads(out)
        self.assertTrue(any("过期" in p for p in data["problems"]))
        store.release_lock(None, force=True)

    def test_doctor_orphan_cleanup_note(self):
        store = TaskStore(self.task_dir)
        with open(os.path.join(store.tmp_dir, "x.stage"), "w") as fh:
            fh.write("x")
        code, out = self.run_cli("doctor", self.task_dir, "--json")
        data = json.loads(out)
        self.assertTrue(any("孤儿" in n for n in data["notes"]))

    def test_claim_with_subtask_id(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        from helpers import make_artifact
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art],
            payload={"subtasks": [{"subtask_id": "ST-1", "owner": "B"}]}))
        code, out = self.run_cli("claim", self.task_dir, "--role", "B",
                                 "--instance-id", "b-1", "--model", "kimi-k2.5",
                                 "--subtask-id", "ST-1", "--summary", "认领 ST-1")
        self.assertEqual(code, 0, out)

    def test_validate_json_subcommand(self):
        code, out = self.run_cli("validate", self.task_dir, "--json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])

    def test_watch_terminal_exits(self):
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CANCELLED", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001"))
        cfg = os.path.join(self.root, "adapters.json")
        with open(cfg, "w") as fh:
            json.dump({"B": {"type": "manual"}}, fh)
        code, out = self.run_cli("watch", self.task_dir, "--adapters", cfg,
                                 "--interval", "0.05")
        self.assertEqual(code, 0)
        self.assertIn("终态", out)

    def test_publish_missing_event_file(self):
        code, out = self.run_cli("publish", self.task_dir, "no-such.json",
                                 "--instance-id", "x")
        self.assertEqual(code, 1)
        self.assertIn("E302", out)

    def test_publish_mmac_error_printed(self):
        bad = os.path.join(self.root, "bad.json")
        with open(bad, "w") as fh:
            json.dump({"type": "WORK_READY", "status": "WORK_READY"}, fh)
        code, out = self.run_cli("publish", self.task_dir, bad, "--instance-id", "x")
        self.assertEqual(code, 1)
        self.assertIn("MMAC-", out)


class StoreCoverageTests(TaskTestCase):
    def test_status_and_last_event_empty(self):
        import shutil
        empty = os.path.join(self.root, "tasks", "task-empty2")
        os.makedirs(empty)
        with open(os.path.join(empty, "coordination.md"), "w") as fh:
            fh.write("# empty\n")
        store = TaskStore(empty)
        self.assertIsNone(store.last_event())
        self.assertIsNone(store.status())

    def test_heartbeat_without_lease(self):
        store = TaskStore(self.task_dir)
        self.assertIsNone(store.heartbeat("B"))

    def test_release_nonexistent_lock(self):
        store = TaskStore(self.task_dir)
        store.release_lock(None)  # 无锁时安全返回


class CommandAdapterStopTests(unittest.TestCase):
    def test_stop_running_process(self):
        a = CommandAdapter(["sleep", "30"])
        r = a.start("/", "B", "p", {"event_id": "e"})
        result = a.stop(r.run_id)
        self.assertEqual(result.state, "stopped")


if __name__ == "__main__":
    unittest.main()
