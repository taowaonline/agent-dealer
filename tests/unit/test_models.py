"""models.py 单元测试：严格字段、round-trip、schema 版本。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from agent_collaboration import models  # noqa: E402
from agent_collaboration.errors import MMACError  # noqa: E402

ZERO_HASH = "0" * 64


def artifact_dict():
    return {"path": "artifacts/plans/plan-v001.md", "sha256": ZERO_HASH,
            "media_type": "text/markdown", "version": 1}


def actor_dict():
    return {"role": "A", "instance_id": "a-1", "provider": "openai",
            "client": "codex", "model": "gpt-5.6-luna"}


def event_dict():
    return {
        "protocol_version": "1.0",
        "event_id": "evt-1",
        "previous_event_id": None,
        "task_id": "task-x",
        "parent_task_id": None,
        "type": "TASK_CREATED",
        "status": "CREATED",
        "actor": actor_dict(),
        "recipient": {"role": "A"},
        "caused_by": None,
        "revision_cycle": 0,
        "timestamp": "2026-08-11T10:00:00+08:00",
        "artifacts": [artifact_dict()],
        "summary": "s",
        "payload": {"k": 1},
    }


class ArtifactRefTests(unittest.TestCase):
    def test_round_trip(self):
        a = models.ArtifactRef.from_dict(artifact_dict())
        self.assertEqual(a.to_dict(), artifact_dict())
        self.assertEqual(models.ArtifactRef.from_dict(a.to_dict()), a)

    def test_unknown_field_rejected(self):
        d = artifact_dict()
        d["extra"] = 1
        with self.assertRaises(MMACError):
            models.ArtifactRef.from_dict(d)

    def test_bad_sha256(self):
        d = artifact_dict()
        d["sha256"] = "xyz"
        with self.assertRaises(MMACError):
            models.ArtifactRef.from_dict(d)

    def test_version_must_be_positive_int(self):
        for bad in (0, -1, "1", True, 1.5):
            d = artifact_dict()
            d["version"] = bad
            with self.assertRaises(MMACError):
                models.ArtifactRef.from_dict(d)

    def test_empty_path_rejected(self):
        d = artifact_dict()
        d["path"] = " "
        with self.assertRaises(MMACError):
            models.ArtifactRef.from_dict(d)


class AgentIdentityTests(unittest.TestCase):
    def test_round_trip(self):
        a = models.AgentIdentity.from_dict(actor_dict())
        self.assertEqual(a.to_dict(), actor_dict())

    def test_missing_model_rejected(self):
        d = actor_dict()
        del d["model"]
        with self.assertRaises(MMACError):
            models.AgentIdentity.from_dict(d)

    def test_unknown_field_rejected(self):
        d = actor_dict()
        d["nickname"] = "x"
        with self.assertRaises(MMACError):
            models.AgentIdentity.from_dict(d)


class EventTests(unittest.TestCase):
    def test_round_trip(self):
        e = models.Event.from_dict(event_dict())
        self.assertEqual(e.to_dict(), event_dict())
        self.assertEqual(models.Event.from_dict(e.to_dict()), e)

    def test_unknown_top_field_rejected(self):
        d = event_dict()
        d["surprise"] = True
        with self.assertRaises(MMACError):
            models.Event.from_dict(d)

    def test_unsupported_protocol_version(self):
        d = event_dict()
        d["protocol_version"] = "9.9"
        with self.assertRaises(MMACError) as ctx:
            models.Event.from_dict(d)
        self.assertIn("E103", str(ctx.exception))

    def test_unknown_event_type(self):
        d = event_dict()
        d["type"] = "MAGIC_DONE"
        with self.assertRaises(MMACError):
            models.Event.from_dict(d)

    def test_unknown_status(self):
        d = event_dict()
        d["status"] = "KINDA_DONE"
        with self.assertRaises(MMACError):
            models.Event.from_dict(d)

    def test_bad_timestamp(self):
        d = event_dict()
        d["timestamp"] = "2026-08-11 10:00"
        with self.assertRaises(MMACError):
            models.Event.from_dict(d)

    def test_negative_revision_cycle(self):
        d = event_dict()
        d["revision_cycle"] = -1
        with self.assertRaises(MMACError):
            models.Event.from_dict(d)

    def test_recipient_must_be_object(self):
        d = event_dict()
        d["recipient"] = "A"
        with self.assertRaises(MMACError):
            models.Event.from_dict(d)

    def test_artifacts_must_be_list(self):
        d = event_dict()
        d["artifacts"] = {}
        with self.assertRaises(MMACError):
            models.Event.from_dict(d)

    def test_payload_non_dict_becomes_empty(self):
        d = event_dict()
        d["payload"] = [1, 2]
        e = models.Event.from_dict(d)
        self.assertEqual(e.payload, {})

    def test_all_event_types_accepted(self):
        for t in models.EVENT_TYPES:
            d = event_dict()
            d["type"] = t
            d["status"] = "CREATED"
            models.Event.from_dict(d)


class QualityGateTests(unittest.TestCase):
    def test_defaults(self):
        q = models.QualityGate()
        self.assertEqual(q.target_score, 90)
        self.assertEqual(q.max_revision_cycles, 3)

    def test_round_trip(self):
        q = models.QualityGate(target_score=80, strict=False)
        self.assertEqual(models.QualityGate.from_dict(q.to_dict()), q)

    def test_target_above_max_rejected(self):
        with self.assertRaises(MMACError):
            models.QualityGate(target_score=100, max_score=90)

    def test_bool_score_rejected(self):
        with self.assertRaises(MMACError):
            models.QualityGate(target_score=True)


class SubtaskTests(unittest.TestCase):
    def test_round_trip(self):
        s = models.Subtask("ST-1", "B", "编码", ["tools/"])
        self.assertEqual(models.Subtask.from_dict(s.to_dict()), s)

    def test_unknown_field_rejected(self):
        with self.assertRaises(MMACError):
            models.Subtask.from_dict({"subtask_id": "x", "owner": "B", "foo": 1})


class ControlConfigTests(unittest.TestCase):
    def _raw(self):
        return {
            "task": {"id": "t1"},
            "workflow": {"planning_agent": "A", "default_executor": "B",
                         "multimodal_executor": "C", "reviewer": "A"},
            "agents": {"A": {}, "B": {}, "C": {}},
            "quality_gate": {"target_score": 90, "max_score": 100, "max_revision_cycles": 3},
            "rubric": {"a": 60, "b": 40},
            "permissions": {"allowed_paths": ["./"], "forbidden_paths": []},
        }

    def test_valid(self):
        c = models.ControlConfig(self._raw())
        self.assertEqual(c.task_id, "t1")
        self.assertEqual(c.agent_roles, ["A", "B", "C"])

    def test_missing_workflow_field(self):
        raw = self._raw()
        del raw["workflow"]["reviewer"]
        with self.assertRaises(MMACError):
            models.ControlConfig(raw)

    def test_rubric_sum_must_be_100(self):
        raw = self._raw()
        raw["rubric"] = {"a": 50, "b": 40}
        with self.assertRaises(MMACError):
            models.ControlConfig(raw)

    def test_permissions_must_be_str_list(self):
        raw = self._raw()
        raw["permissions"]["allowed_paths"] = "./"
        with self.assertRaises(MMACError):
            models.ControlConfig(raw)

    def test_unknown_section_rejected(self):
        raw = self._raw()
        raw["evil"] = {}
        with self.assertRaises(MMACError):
            models.ControlConfig(raw)


if __name__ == "__main__":
    unittest.main()
