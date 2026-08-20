"""runner.py 与 adapters 单元测试。"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import TaskTestCase, append_event, make_artifact, make_event  # noqa: E402
from agent_dealer.runner import Runner, RunnerState, load_adapters  # noqa: E402
from agent_dealer.adapters.manual import ManualAdapter  # noqa: E402
from agent_dealer.adapters.command import CommandAdapter  # noqa: E402
from agent_dealer.errors import MMACError  # noqa: E402


class RunnerStateTests(TaskTestCase):
    def test_persist_and_reload(self):
        path = os.path.join(self.root, "state.json")
        s = RunnerState(path)
        s.mark("evt-1")
        s.mark("evt-2")
        s2 = RunnerState(path)
        self.assertEqual(s2.processed, ["evt-1", "evt-2"])

    def test_mark_idempotent(self):
        path = os.path.join(self.root, "state.json")
        s = RunnerState(path)
        s.mark("evt-1")
        s.mark("evt-1")
        self.assertEqual(s.processed, ["evt-1"])


class ManualAdapterTests(unittest.TestCase):
    def test_start_prints_prompt(self):
        buf = io.StringIO()
        adapter = ManualAdapter(stream=buf)
        result = adapter.start("/tmp/t", "B", "请执行", {"event_id": "e1"})
        self.assertEqual(result.state, "notified")
        self.assertIn("请执行", buf.getvalue())
        self.assertIn("B", buf.getvalue())


class CommandAdapterTests(unittest.TestCase):
    def test_build_command_substitution(self):
        a = CommandAdapter(["run", "{role}", "{task_dir}"])
        cmd = a.build_command("/tasks/t1", "B", "p")
        self.assertEqual(cmd, ["run", "B", "/tasks/t1"])

    def test_start_and_poll_success(self):
        with tempfile.TemporaryDirectory() as task_dir:
            a = CommandAdapter(["true"])
            r = a.start(task_dir, "B", "p", {"event_id": "e"})
            self.assertEqual(r.state, "started")
            self.assertIn("log=", r.detail)
            import time
            time.sleep(0.1)
            self.assertEqual(a.poll(r.run_id), "completed")

    def test_start_and_poll_failure(self):
        with tempfile.TemporaryDirectory() as task_dir:
            a = CommandAdapter(["false"])
            r = a.start(task_dir, "B", "p", {"event_id": "e"})
            import time
            time.sleep(0.1)
            self.assertEqual(a.poll(r.run_id), "failed")

    def test_start_nonexistent_command(self):
        with tempfile.TemporaryDirectory() as task_dir:
            a = CommandAdapter(["definitely-not-a-command-xyz"])
            r = a.start(task_dir, "B", "p", {"event_id": "e"})
            self.assertEqual(r.state, "failed")


class LoadAdaptersTests(TaskTestCase):
    def _config(self, data):
        path = os.path.join(self.root, "adapters.json")
        with open(path, "w") as fh:
            json.dump(data, fh)
        return path

    def test_load_manual(self):
        adapters = load_adapters(self._config({"B": {"type": "manual"}}))
        self.assertIsInstance(adapters["B"], ManualAdapter)

    def test_load_command(self):
        adapters = load_adapters(self._config({"A": {"type": "command", "argv": ["echo"]}}))
        self.assertIsInstance(adapters["A"], CommandAdapter)

    def test_unknown_type(self):
        with self.assertRaises(MMACError):
            load_adapters(self._config({"B": {"type": "magic"}}))

    def test_command_requires_argv(self):
        with self.assertRaises(MMACError):
            load_adapters(self._config({"B": {"type": "command"}}))


class RunnerLogicTests(TaskTestCase):
    def _runner(self):
        buf = io.StringIO()
        adapters = {"A": ManualAdapter(stream=buf), "B": ManualAdapter(stream=buf)}
        return Runner(self.task_dir, adapters, poll_interval=0.01), buf

    def test_no_action_on_created(self):
        runner, _ = self._runner()
        self.assertIsNone(runner.pending_action())

    def test_action_on_plan_ready(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art], recipient="B"))
        runner, buf = self._runner()
        event = runner.pending_action()
        self.assertIsNotNone(event)
        result = runner.run_once()
        self.assertEqual(result.state, "notified")
        self.assertIn("B", buf.getvalue())
        # 去重：再次 run_once 不重复调度
        self.assertIsNone(runner.run_once())

    def test_no_action_when_chain_broken(self):
        with open(os.path.join(self.task_dir, "coordination.md"), "a") as fh:
            fh.write("\n<!-- MMAC-EVENT-BEGIN -->\n```json\n{bad\n```\n<!-- MMAC-EVENT-END -->\n")
        runner, _ = self._runner()
        self.assertIsNone(runner.pending_action())

    def test_no_action_on_terminal(self):
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CANCELLED", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001"))
        runner, _ = self._runner()
        self.assertIsNone(runner.pending_action())

    def test_state_persisted_after_dispatch(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art], recipient="B"))
        runner, _ = self._runner()
        runner.run_once()
        # 模拟 Runner 重启：新实例不应重复处理 evt-0003
        runner2, _ = self._runner()
        self.assertIsNone(runner2.run_once())

    def test_build_prompt_mentions_role_and_event(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        ev = make_event(self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
                        caused_by="evt-0001", artifacts=[art], recipient="B")
        append_event(self.task_dir, ev)
        runner, _ = self._runner()
        prompt = runner.build_prompt(ev)
        self.assertIn("B", prompt)
        self.assertIn("evt-0003", prompt)


class TierConfigTests(TaskTestCase):
    """0.4.0 档位注入：control.md agents_detail/workflow → adapter config/环境/prompt。"""

    def _plan_ready_event(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        ev = make_event(self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
                        caused_by="evt-0001", artifacts=[art], recipient="B")
        append_event(self.task_dir, ev)
        return ev

    def _add_tiers(self):
        path = os.path.join(self.task_dir, "control.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace(
            "    model: kimi-k2.5\n",
            "    model: kimi-k2.5\n    effort: high\n    thinking: on\n", 1)
        text = text.replace(
            "  planning_agent: A\n",
            "  planning_agent: A\n  permission_mode: confirm\n", 1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_role_config_reads_control(self):
        self._add_tiers()
        runner, _ = self._runner_with_adapters()
        cfg = runner.role_config("B")
        self.assertEqual(cfg, {"model": "kimi-k2.5", "effort": "high",
                               "thinking": "on", "permission_mode": "confirm"})

    def test_role_config_defaults(self):
        runner, _ = self._runner_with_adapters()
        cfg = runner.role_config("A")
        self.assertEqual(cfg, {"model": "gpt-5.6-luna", "effort": "medium",
                               "thinking": "off", "permission_mode": "yolo"})

    def test_role_config_blanks_placeholder_model(self):
        # init 默认写 model: configurable——注入前必须置空，不传占位符给客户端
        path = os.path.join(self.task_dir, "control.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("model: gpt-5.6-luna", "model: configurable", 1))
        runner, _ = self._runner_with_adapters()
        self.assertEqual(runner.role_config("A")["model"], "")

    def test_build_prompt_includes_tier_line(self):
        self._add_tiers()
        ev = self._plan_ready_event()
        runner, _ = self._runner_with_adapters()
        prompt = runner.build_prompt(ev, runner.role_config("B"))
        self.assertIn("model=kimi-k2.5", prompt)
        self.assertIn("effort=high", prompt)
        self.assertIn("thinking=on", prompt)
        self.assertIn("permission_mode=confirm", prompt)

    def test_dispatch_passes_config_to_adapter(self):
        self._add_tiers()
        self._plan_ready_event()
        captured = {}

        class SpyAdapter:
            name = "spy"

            def start(self, task_dir, role, prompt, event, config=None):
                captured["config"] = config
                from agent_dealer.adapters.base import AdapterResult
                return AdapterResult("spy-1", "notified")

        runner = Runner(self.task_dir, {"B": SpyAdapter()}, poll_interval=0.01)
        result = runner.run_once()
        self.assertEqual(result.state, "notified")
        self.assertEqual(captured["config"]["effort"], "high")
        self.assertEqual(captured["config"]["model"], "kimi-k2.5")

    def _runner_with_adapters(self):
        buf = io.StringIO()
        adapters = {"A": ManualAdapter(stream=buf), "B": ManualAdapter(stream=buf)}
        return Runner(self.task_dir, adapters, poll_interval=0.01), buf


class CommandAdapterTierTests(unittest.TestCase):
    def test_build_command_tier_placeholders(self):
        a = CommandAdapter(["run", "--model", "{model}", "--effort", "{effort}",
                            "--thinking", "{thinking}", "--mode", "{permission_mode}"])
        cmd = a.build_command("/t", "B", "p", {"model": "kimi-k2.5", "effort": "high",
                                               "thinking": "on", "permission_mode": "yolo"})
        self.assertEqual(cmd, ["run", "--model", "kimi-k2.5", "--effort", "high",
                               "--thinking", "on", "--mode", "yolo"])

    def test_build_command_placeholder_blank_without_config(self):
        a = CommandAdapter(["run", "{model}"])
        self.assertEqual(a.build_command("/t", "B", "p", None), ["run", ""])

    def test_start_injects_mmac_env(self):
        with tempfile.TemporaryDirectory() as task_dir:
            a = CommandAdapter(
                [sys.executable, "-c",
                 "import os,sys;print(os.environ['MMAC_EFFORT'],"
                 "os.environ['MMAC_MODEL'],os.environ['MMAC_PERMISSION_MODE'])"])
            r = a.start(task_dir, "B", "p", {"event_id": "e"},
                        config={"model": "kimi-k2.5", "effort": "high",
                                "thinking": "on", "permission_mode": "yolo"})
            self.assertEqual(r.state, "started")
            import time
            for _ in range(50):
                if a.poll(r.run_id) != "running":
                    break
                time.sleep(0.05)
            log = os.path.join(task_dir, "tmp", "adapter-%s.log" % r.run_id)
            with open(log) as fh:
                self.assertIn("high kimi-k2.5 yolo", fh.read())

    def test_manual_adapter_accepts_config_kwarg(self):
        buf = io.StringIO()
        adapter = ManualAdapter(stream=buf)
        result = adapter.start("/t", "B", "p", {"event_id": "e1"},
                               config={"effort": "high"})
        self.assertEqual(result.state, "notified")


if __name__ == "__main__":
    unittest.main()
