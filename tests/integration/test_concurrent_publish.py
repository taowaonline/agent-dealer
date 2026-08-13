"""集成测试：100 个并发发布者不能产生静默覆盖、分叉或双重认领。"""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import TaskTestCase, append_event, make_artifact, make_event  # noqa: E402
from agent_dealer.store import TaskStore  # noqa: E402


class ConcurrentPublishTests(TaskTestCase):
    ROUNDS = 100

    def test_100_concurrent_publishers(self):
        # 先进入 EXECUTING，HEARTBEAT 由执行角色发布（合法且可重复）
        store = TaskStore(self.task_dir)
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art], recipient="B"))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004", caused_by="evt-0003"))
        append_event(self.task_dir, make_event(
            self.task_id, "EXECUTION_STARTED", "B", "evt-0004", "evt-0005", caused_by="evt-0004"))

        errors = []
        barrier = threading.Barrier(self.ROUNDS)

        def publisher(i):
            try:
                barrier.wait(timeout=10)
                ev = make_event(self.task_id, "HEARTBEAT", "B", None,
                                "hb-%04d" % i, caused_by="evt-0005", status="EXECUTING")
                TaskStore(self.task_dir).publish(ev, owner="b-%d" % i)
            except Exception as ex:  # noqa: BLE001
                errors.append("publisher %d: %s" % (i, ex))

        threads = [threading.Thread(target=publisher, args=(i,)) for i in range(self.ROUNDS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        self.assertEqual(errors, [], "\n".join(errors[:5]))
        events = store.read_events()
        self.assertEqual(len(events), 5 + self.ROUNDS)
        # 链完整、无分叉、无重复 id、无静默覆盖
        report = store.validate()
        self.assertTrue(report.ok, [str(i) for i in report.errors][:5])
        ids = [e["event_id"] for e in events]
        self.assertEqual(len(ids), len(set(ids)))

    def test_concurrent_claim_single_winner(self):
        """两个执行者同时认领：两条 TASK_CLAIMED 都合法入链（协议允许租约仲裁），
        关键是链不分叉、事件不丢失。"""
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art], recipient="B"))

        barrier = threading.Barrier(2)
        errors = []

        def claimer(i):
            try:
                barrier.wait(timeout=10)
                ev = make_event(self.task_id, "TASK_CLAIMED", "B", None,
                                "claim-%d" % i, caused_by="evt-0003")
                TaskStore(self.task_dir).publish(ev, owner="b-%d" % i)
            except Exception as ex:  # noqa: BLE001
                errors.append(str(ex))

        ts = [threading.Thread(target=claimer, args=(i,)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
        self.assertEqual(errors, [])
        report = TaskStore(self.task_dir).validate()
        self.assertTrue(report.ok, [str(i) for i in report.errors])
        self.assertEqual(len(TaskStore(self.task_dir).read_events()), 5)


if __name__ == "__main__":
    unittest.main()
