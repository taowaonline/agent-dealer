"""集成测试：崩溃恢复——孤儿暂存、过期锁接管、部分写入检测、E2E 重复稳定性。"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import TaskTestCase, append_event, make_artifact, make_event, review_payload  # noqa: E402
from agent_dealer.store import TaskStore  # noqa: E402


class CrashRecoveryTests(TaskTestCase):
    def test_orphan_stage_cleanup(self):
        store = TaskStore(self.task_dir)
        # 模拟"写产物后、追加事件前"崩溃：tmp 残留 .stage
        with open(os.path.join(store.tmp_dir, "plan-v001.md.stage"), "w") as fh:
            fh.write("partial")
        removed = store.cleanup_orphans()
        self.assertEqual(removed, ["plan-v001.md.stage"])
        self.assertEqual(os.listdir(store.tmp_dir), [])

    def test_stale_lock_takeover_and_log(self):
        store = TaskStore(self.task_dir)
        store.acquire_lock("crashed-agent")
        info_path = os.path.join(store.lock_path, "owner.json")
        with open(info_path) as fh:
            info = json.load(fh)
        info["lease_until"] = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        with open(info_path, "w") as fh:
            json.dump(info, fh)
        lock = store.acquire_lock("recovery-agent")
        self.assertEqual(store.lock_info()["owner"], "recovery-agent")
        lock.release()
        with open(os.path.join(self.task_dir, "locks", "recovery.log")) as fh:
            self.assertIn("接管", fh.read())

    def test_partial_append_detected(self):
        # 模拟追加到一半崩溃：事件块不完整
        with open(os.path.join(self.task_dir, "coordination.md"), "a") as fh:
            fh.write('\n<!-- MMAC-EVENT-BEGIN -->\n```json\n{"event_id": "x",')
        report = TaskStore(self.task_dir).validate()
        self.assertFalse(report.ok)
        self.assertIn("marker-mismatch", {i.rule for i in report.errors})


class E2EFlowTests(TaskTestCase):
    """完整 A→B→A 流程连续执行 10 次：结果一致且无残留锁。"""

    ROUNDS = 10

    def _run_flow(self, task_dir, task_id):
        store = TaskStore(task_dir)
        seq = [
            ("PLANNING_STARTED", "A", "A"),
            ("TASK_CLAIMED", "B", "B"),  # 占位，顺序在下面按协议驱动
        ]
        # PLANNING
        store.publish(make_event(task_id, "PLANNING_STARTED", "A", None,
                                 "e-%s-02" % task_id[-2:], caused_by="evt-0001"), owner="a")
        art_src = os.path.join(self.root, "plan-%s.md" % task_id)
        with open(art_src, "w") as fh:
            fh.write("# plan\n")
        plan_art = {"path": "artifacts/plans/plan-v001.md", "sha256": "",
                    "media_type": "text/markdown", "version": 1}
        store.publish(make_event(task_id, "PLAN_READY", "A", None,
                                 "e-%s-03" % task_id[-2:], caused_by="e-%s-02" % task_id[-2:],
                                 artifacts=[plan_art], recipient="B"),
                      owner="a", artifact_sources={"artifacts/plans/plan-v001.md": art_src})
        store.publish(make_event(task_id, "TASK_CLAIMED", "B", None,
                                 "e-%s-04" % task_id[-2:], caused_by="e-%s-03" % task_id[-2:],
                                 recipient="B"), owner="b")
        store.publish(make_event(task_id, "EXECUTION_STARTED", "B", None,
                                 "e-%s-05" % task_id[-2:], caused_by="e-%s-04" % task_id[-2:]),
                      owner="b")
        ex_src = os.path.join(self.root, "ex-%s.md" % task_id)
        with open(ex_src, "w") as fh:
            fh.write("# execution\n")
        ex_art = {"path": "artifacts/executions/execution-b-v001.md", "sha256": "",
                  "media_type": "text/markdown", "version": 1}
        store.publish(make_event(task_id, "WORK_READY", "B", None,
                                 "e-%s-06" % task_id[-2:], caused_by="e-%s-03" % task_id[-2:],
                                 artifacts=[ex_art], recipient="A"),
                      owner="b", artifact_sources={"artifacts/executions/execution-b-v001.md": ex_src})
        store.publish(make_event(task_id, "REVIEW_STARTED", "A", None,
                                 "e-%s-07" % task_id[-2:], caused_by="e-%s-06" % task_id[-2:]),
                      owner="a")
        rv_src = os.path.join(self.root, "rv-%s.md" % task_id)
        with open(rv_src, "w") as fh:
            fh.write("# review\n")
        rv_art = {"path": "artifacts/reviews/review-v001.md", "sha256": "",
                  "media_type": "text/markdown", "version": 1}
        store.publish(make_event(task_id, "REVIEW_APPROVED", "A", None,
                                 "e-%s-08" % task_id[-2:], caused_by="e-%s-07" % task_id[-2:],
                                 artifacts=[rv_art], payload=review_payload(score=96)),
                      owner="a", artifact_sources={"artifacts/reviews/review-v001.md": rv_src})
        return store

    def test_e2e_10_rounds_consistent(self):
        statuses = []
        for i in range(self.ROUNDS):
            task_id = "task-e2e-%03d" % i
            from helpers import make_task
            task_dir = make_task(self.root, task_id)
            store = self._run_flow(task_dir, task_id)
            report = store.validate()
            self.assertTrue(report.ok, "round %d: %s" % (i, [str(x) for x in report.errors][:3]))
            statuses.append(report.final_status)
            # 无残留锁
            self.assertFalse(os.path.isdir(store.lock_path), "round %d 残留锁" % i)
            # 无孤儿暂存
            stages = [f for f in os.listdir(store.tmp_dir) if f.endswith(".stage")]
            self.assertEqual(stages, [], "round %d 孤儿暂存" % i)
        self.assertEqual(statuses, ["APPROVED"] * self.ROUNDS)


if __name__ == "__main__":
    unittest.main()
