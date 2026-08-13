"""store.py 单元测试：锁、原子发布、回滚、租约。"""
import json
import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import TaskTestCase, make_event, next_ts  # noqa: E402
from agent_dealer.errors import MMACError  # noqa: E402
from agent_dealer.store import TaskStore  # noqa: E402


class LockTests(TaskTestCase):
    def setUp(self):
        super().setUp()
        self.store = TaskStore(self.task_dir)

    def test_acquire_and_release(self):
        lock = self.store.acquire_lock("tester")
        self.assertTrue(os.path.isdir(self.store.lock_path))
        lock.release()
        self.assertFalse(os.path.isdir(self.store.lock_path))

    def test_lock_conflict(self):
        self.store.acquire_lock("first")
        with self.assertRaises(MMACError) as ctx:
            self.store.acquire_lock("second")
        self.assertIn("E401", str(ctx.exception))
        self.store.release_lock(None, force=True)

    def test_lock_context_manager(self):
        with self.store.acquire_lock("ctx"):
            self.assertTrue(os.path.isdir(self.store.lock_path))
        self.assertFalse(os.path.isdir(self.store.lock_path))

    def test_expired_lock_takeover(self):
        self.store.acquire_lock("dead-agent", lease_seconds=0)
        # 手工把 lease_until 改到过去
        info_path = os.path.join(self.store.lock_path, "owner.json")
        with open(info_path) as fh:
            info = json.load(fh)
        info["lease_until"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        with open(info_path, "w") as fh:
            json.dump(info, fh)
        lock = self.store.acquire_lock("rescuer")
        self.assertEqual(self.store.lock_info()["owner"], "rescuer")
        lock.release()
        self.assertTrue(os.path.isfile(os.path.join(self.task_dir, "locks", "recovery.log")))

    def test_lock_wait_timeout(self):
        self.store.acquire_lock("holder")
        start = time.time()
        with self.assertRaises(MMACError):
            self.store.acquire_lock("waiter", wait_seconds=0.2)
        self.assertLess(time.time() - start, 2)
        self.store.release_lock(None, force=True)

    def test_cannot_release_others_lock(self):
        lock = self.store.acquire_lock("owner-a")
        other = self.store.acquire_lock.__self__  # noqa
        from agent_dealer.store import LockHandle
        fake = LockHandle(self.store, "intruder")
        with self.assertRaises(MMACError):
            self.store.release_lock(fake)
        lock.release()


class LeaseTests(TaskTestCase):
    def setUp(self):
        super().setUp()
        self.store = TaskStore(self.task_dir)

    def test_write_and_read_lease(self):
        self.store.write_lease("B", "b-1", lease_seconds=900)
        lease = self.store.read_lease("B")
        self.assertEqual(lease["role"], "B")
        self.assertFalse(self.store.lease_expired("B"))

    def test_missing_lease_is_expired(self):
        self.assertTrue(self.store.lease_expired("C"))

    def test_heartbeat_refreshes(self):
        self.store.write_lease("B", "b-1")
        first = self.store.read_lease("B")["last_heartbeat"]
        time.sleep(0.01)
        self.store.heartbeat("B")
        second = self.store.read_lease("B")["last_heartbeat"]
        self.assertGreaterEqual(second, first)

    def test_expired_lease(self):
        self.store.write_lease("B", "b-1", lease_seconds=0)
        time.sleep(0.01)
        self.assertTrue(self.store.lease_expired("B"))


class PublishTests(TaskTestCase):
    def setUp(self):
        super().setUp()
        self.store = TaskStore(self.task_dir)

    def test_publish_happy_path(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", None, "evt-0002",
                        caused_by="evt-0001")
        published = self.store.publish(ev, owner="a-1")
        self.assertEqual(published["previous_event_id"], "evt-0001")
        r = self.store.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        self.assertEqual(r.final_status, "PLANNING")

    def test_publish_rejects_invalid_candidate(self):
        ev = make_event(self.task_id, "WORK_READY", "B", None, "evt-0002",
                        caused_by="evt-0001")
        before = open(self.store.coord_path).read()
        with self.assertRaises(MMACError):
            self.store.publish(ev, owner="b-1")
        after = open(self.store.coord_path).read()
        self.assertEqual(before, after)
        self.assertFalse(os.path.isdir(self.store.lock_path))

    def test_publish_sequential_chain(self):
        ev1 = make_event(self.task_id, "PLANNING_STARTED", "A", None, "evt-0002",
                         caused_by="evt-0001")
        self.store.publish(ev1, owner="a-1")
        art = {"path": "artifacts/plans/p.md", "sha256": "", "media_type": "text/markdown", "version": 1}
        src = os.path.join(self.root, "p.md")
        with open(src, "w") as fh:
            fh.write("plan body\n")
        ev2 = make_event(self.task_id, "PLAN_READY", "A", None, "evt-0003",
                         caused_by="evt-0002", artifacts=[art])
        self.store.publish(ev2, owner="a-1",
                           artifact_sources={"artifacts/plans/p.md": src})
        r = self.store.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        events = self.store.read_events()
        self.assertEqual(len(events), 3)
        self.assertEqual(events[-1]["artifacts"][0]["sha256"],
                         __import__("hashlib").sha256(b"plan body\n").hexdigest())

    def test_strict_previous_mismatch_rejected(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-WRONG", "evt-0002",
                        caused_by="evt-0001")
        with self.assertRaises(MMACError):
            self.store.publish(ev, owner="a-1", auto_previous=False)

    def test_publish_returns_event_with_previous(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", None, "evt-0002",
                        caused_by="evt-0001")
        published = self.store.publish(ev, owner="a-1")
        self.assertIsNotNone(published["previous_event_id"])


class ArtifactStagingTests(TaskTestCase):
    def setUp(self):
        super().setUp()
        self.store = TaskStore(self.task_dir)

    def test_stage_artifact(self):
        src = os.path.join(self.root, "x.md")
        with open(src, "w") as fh:
            fh.write("hello\n")
        staged = self.store.stage_artifact(src, "artifacts/plans/x.md")
        self.assertTrue(os.path.isfile(os.path.join(self.task_dir, "artifacts/plans/x.md")))
        self.assertEqual(len(staged["sha256"]), 64)

    def test_cleanup_orphans(self):
        orphan = os.path.join(self.store.tmp_dir, "ghost.md.stage")
        with open(orphan, "w") as fh:
            fh.write("x")
        keep = os.path.join(self.store.tmp_dir, "keep.md")
        with open(keep, "w") as fh:
            fh.write("x")
        removed = self.store.cleanup_orphans()
        self.assertIn("ghost.md.stage", removed)
        self.assertTrue(os.path.isfile(keep))


if __name__ == "__main__":
    unittest.main()
