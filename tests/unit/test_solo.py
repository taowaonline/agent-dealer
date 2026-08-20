"""solo 模式（workflow.mode=solo）单元测试：单会话扮演全部角色 + 证据门槛补偿。"""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # tests/ → helpers
sys.path.insert(0, _HERE)                   # tests/unit → test_cli

from helpers import TaskTestCase, append_event, make_artifact, make_event, review_payload  # noqa: E402
from test_cli import CliTestBase  # noqa: E402


def make_solo(task_dir: str) -> None:
    """把标准 control.md 切到 solo 模式（保留 A/B/C 注册，B 扮演全部角色）。"""
    path = os.path.join(task_dir, "control.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert "mode:" not in text
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("workflow:\n", "workflow:\n  mode: solo\n", 1))


class SoloPolicyTests(TaskTestCase):
    def _drive_to_review(self, solo: bool = True):
        if solo:
            make_solo(self.task_dir)
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "B", "evt-0001", "evt-0002", caused_by="evt-0001"))
        plan = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "B", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[plan]))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004", caused_by="evt-0003"))
        append_event(self.task_dir, make_event(
            self.task_id, "EXECUTION_STARTED", "B", "evt-0004", "evt-0005", caused_by="evt-0004"))
        ex = make_artifact(self.task_dir, "artifacts/executions/execution-b-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "WORK_READY", "B", "evt-0005", "evt-0006",
            caused_by="evt-0003", artifacts=[ex]))
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_STARTED", "B", "evt-0006", "evt-0007", caused_by="evt-0006"))
        return make_artifact(self.task_dir, "artifacts/reviews/review-v001.md")

    def _approve(self, review_art, payload):
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_APPROVED", "B", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[review_art], payload=payload))

    def test_solo_chain_approves_with_self_evidence(self):
        review_art = self._drive_to_review(solo=True)
        self._approve(review_art, {
            **review_payload(score=95),
            "self_review": True,
            "reproduced_commands": ["flutter test test/services/speech_redline_test.dart"],
        })
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        self.assertEqual(r.final_status, "APPROVED")

    def test_solo_approve_requires_self_review_flag(self):
        review_art = self._drive_to_review(solo=True)
        self._approve(review_art, {
            **review_payload(score=95),
            "reproduced_commands": ["agent_dealer validate tasks/x"],
        })
        rules = self.rules(self.validate())
        self.assertIn("solo-review", rules)
        # 角色放宽生效：只剩证据缺失，不应再报权限错误
        self.assertNotIn("unauthorized-role", rules)

    def test_solo_approve_requires_nonempty_reproduced_commands(self):
        review_art = self._drive_to_review(solo=True)
        self._approve(review_art, {
            **review_payload(score=95),
            "self_review": True,
            "reproduced_commands": [],
        })
        self.assertIn("solo-review", self.rules(self.validate()))

    def test_multi_mode_still_rejects_executor_review(self):
        # 回归护栏：不加 mode: solo，B 全链自审依旧被权限规则拒绝
        review_art = self._drive_to_review(solo=False)
        self._approve(review_art, {
            **review_payload(score=95),
            "self_review": True,
            "reproduced_commands": ["agent_dealer validate tasks/x"],
        })
        rules = self.rules(self.validate())
        self.assertIn("unauthorized-role", rules)
        self.assertNotIn("solo-review", rules)

    def test_solo_relaxes_planning_role(self):
        make_solo(self.task_dir)
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "B", "evt-0001", "evt-0002", caused_by="evt-0001"))
        self.assertNotIn("unauthorized-role", self.rules(self.validate()))


class SoloInitTests(CliTestBase):
    def init_solo(self, task_id="task-solo-001"):
        code, out = self.run_cli(
            "init", task_id, "--title", "solo 任务",
            "--model", "test-model", "--solo")
        self.assertEqual(code, 0, out)
        return os.path.join("tasks", task_id)

    def test_init_solo_control_shape(self):
        task_dir = self.init_solo()
        with open(os.path.join(task_dir, "control.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("mode: solo", text)
        for key in ("planning_agent", "default_executor",
                    "multimodal_executor", "reviewer"):
            self.assertIn("%s: B" % key, text)
        self.assertNotIn("\n  A:", text)  # agents 只注册 solo 角色
        code, out = self.run_cli("validate", task_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("全部通过", out)

    def test_init_solo_task_created_recipient_is_solo_role(self):
        task_dir = self.init_solo()
        with open(os.path.join(task_dir, "coordination.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('"role": "B"', text)
        self.assertNotIn('"role": "A"', text)

    def test_init_multi_default_unchanged(self):
        code, out = self.run_cli(
            "init", "task-multi-001", "--title", "multi 任务", "--model", "test-model")
        self.assertEqual(code, 0, out)
        with open(os.path.join("tasks", "task-multi-001", "control.md"),
                  encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("mode: multi", text)
        self.assertIn("planning_agent: A", text)
        self.assertIn("reviewer: A", text)

    def test_status_marks_provisional_approval(self):
        # 端到端：CLI 建任务（control 已含 mode: solo）→ 补完整链 → status 标注临时批准
        task_dir = self.init_solo("task-solo-status")
        with open(os.path.join(task_dir, "coordination.md"), encoding="utf-8") as fh:
            created_id = json.loads(
                fh.read().split("```json\n")[1].split("\n```")[0])["event_id"]
        # init --solo 的 control 只注册 B，故 recipient 全部显式 B
        append_event(task_dir, make_event(
            "task-solo-status", "PLANNING_STARTED", "B",
            created_id, "evt-0002", caused_by=created_id, recipient="B"))
        plan = make_artifact(task_dir, "artifacts/plans/plan-v001.md")
        append_event(task_dir, make_event(
            "task-solo-status", "PLAN_READY", "B", "evt-0002", "evt-0003",
            caused_by=created_id, recipient="B", artifacts=[plan]))
        append_event(task_dir, make_event(
            "task-solo-status", "TASK_CLAIMED", "B", "evt-0003", "evt-0004",
            caused_by="evt-0003", recipient="B"))
        append_event(task_dir, make_event(
            "task-solo-status", "EXECUTION_STARTED", "B", "evt-0004", "evt-0005",
            caused_by="evt-0004", recipient="B"))
        ex = make_artifact(task_dir, "artifacts/executions/execution-b-v001.md")
        append_event(task_dir, make_event(
            "task-solo-status", "WORK_READY", "B", "evt-0005", "evt-0006",
            caused_by="evt-0003", recipient="B", artifacts=[ex]))
        append_event(task_dir, make_event(
            "task-solo-status", "REVIEW_STARTED", "B", "evt-0006", "evt-0007",
            caused_by="evt-0006", recipient="B"))
        review_art = make_artifact(task_dir, "artifacts/reviews/review-v001.md")
        append_event(task_dir, make_event(
            "task-solo-status", "REVIEW_APPROVED", "B", "evt-0007", "evt-0008",
            caused_by="evt-0007", recipient="B", artifacts=[review_art],
            payload={**review_payload(score=95), "self_review": True,
                     "reproduced_commands": ["agent_dealer validate tasks/task-solo-status"]}))
        code, out = self.run_cli("status", task_dir)
        self.assertEqual(code, 0, out)
        self.assertIn("solo 自审临时批准", out)


if __name__ == "__main__":
    unittest.main()
