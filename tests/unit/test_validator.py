"""validator.py 单元测试：链、状态机、权限、质量门、supersede、grandfather。"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import (TaskTestCase, append_event, make_artifact, make_event,  # noqa: E402
                     review_payload)


class ChainTests(TaskTestCase):
    def test_minimal_task_ok(self):
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        self.assertEqual(r.final_status, "CREATED")

    def test_broken_chain(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-9999", "evt-0002",
                        caused_by="evt-0001")
        append_event(self.task_dir, ev)
        self.assertIn("broken-chain", self.rules(self.validate()))

    def test_fork_detected(self):
        ev1 = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                         caused_by="evt-0001")
        append_event(self.task_dir, ev1)
        ev2 = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0003",
                         caused_by="evt-0001")
        append_event(self.task_dir, ev2)
        rules = self.rules(self.validate())
        self.assertIn("broken-chain", rules)
        self.assertIn("fork", rules)

    def test_duplicate_event_id(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0001",
                        caused_by="evt-0001")
        append_event(self.task_dir, ev)
        self.assertIn("duplicate-event-id", self.rules(self.validate()))

    def test_caused_by_future(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-9999")
        append_event(self.task_dir, ev)
        self.assertIn("bad-caused-by", self.rules(self.validate()))

    def test_first_event_must_be_created(self):
        coord = os.path.join(self.task_dir, "coordination.md")
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", None, "evt-x")
        with open(coord, "w") as fh:
            from agent_collaboration import validator
            fh.write(validator.serialize_event(ev))
        self.assertIn("first-event", self.rules(self.validate()))


class StateMachineTests(TaskTestCase):
    def test_illegal_transition(self):
        ev = make_event(self.task_id, "WORK_READY", "B", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        append_event(self.task_dir, ev)
        self.assertIn("illegal-transition", self.rules(self.validate()))

    def test_type_status_mismatch(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001", status="PLAN_READY")
        append_event(self.task_dir, ev)
        self.assertIn("type-status-mismatch", self.rules(self.validate()))

    def test_terminal_guard(self):
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CANCELLED", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001"))
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0002", "evt-0003",
            caused_by="evt-0002"))
        self.assertIn("terminal-guard", self.rules(self.validate()))

    def test_reopen_allowed_after_terminal(self):
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CANCELLED", "coordinator", "evt-0001", "evt-0002",
            caused_by="evt-0001"))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_REOPENED", "coordinator", "evt-0002", "evt-0003",
            caused_by="evt-0002"))
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])

    def test_unknown_event_type(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        ev["type"] = "NOT_A_TYPE"
        append_event(self.task_dir, ev)
        self.assertIn("unknown-event-type", self.rules(self.validate()))

    def _drive_to_executing(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art]))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004", caused_by="evt-0003"))
        append_event(self.task_dir, make_event(
            self.task_id, "EXECUTION_STARTED", "B", "evt-0004", "evt-0005", caused_by="evt-0004"))

    def test_heartbeat_keeps_status(self):
        self._drive_to_executing()
        append_event(self.task_dir, make_event(
            self.task_id, "HEARTBEAT", "B", "evt-0005", "evt-0006",
            caused_by="evt-0005", status="EXECUTING"))
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        self.assertEqual(r.final_status, "EXECUTING")

    def test_heartbeat_wrong_status(self):
        self._drive_to_executing()
        append_event(self.task_dir, make_event(
            self.task_id, "HEARTBEAT", "B", "evt-0005", "evt-0006",
            caused_by="evt-0005", status="REVIEWING"))
        self.assertIn("status-keeping-violation", self.rules(self.validate()))


class FieldTests(TaskTestCase):
    def _append_broken(self, mutate):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        mutate(ev)
        append_event(self.task_dir, ev)
        return self.validate()

    def test_missing_required_field(self):
        r = self._append_broken(lambda e: e.pop("caused_by"))
        self.assertIn("missing-field", self.rules(r))

    def test_bad_timestamp(self):
        r = self._append_broken(lambda e: e.update(timestamp="昨天"))
        self.assertIn("bad-timestamp", self.rules(r))

    def test_placeholder_model(self):
        r = self._append_broken(lambda e: e["actor"].update(model="configured-model"))
        self.assertIn("placeholder-model", self.rules(r))

    def test_bool_revision_cycle(self):
        r = self._append_broken(lambda e: e.update(revision_cycle=True))
        self.assertIn("bad-revision-cycle", self.rules(r))

    def test_bad_sha256_format(self):
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        art["sha256"] = "zzz"

        def m(e):
            e["artifacts"] = [art]
        r = self._append_broken(m)
        self.assertIn("bad-sha256", self.rules(r))

    def test_path_traversal_rejected(self):
        art = {"path": "../../etc/passwd", "sha256": "0" * 64,
               "media_type": "text/plain", "version": 1}
        r = self._append_broken(lambda e: e.update(artifacts=[art]))
        self.assertIn("path-traversal", self.rules(r))


class RolePolicyTests(TaskTestCase):
    def test_executor_cannot_approve(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art]))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004", caused_by="evt-0003",
            revision_cycle=0))
        append_event(self.task_dir, make_event(
            self.task_id, "EXECUTION_STARTED", "B", "evt-0004", "evt-0005", caused_by="evt-0004"))
        ex = make_artifact(self.task_dir, "artifacts/executions/execution-b-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "WORK_READY", "B", "evt-0005", "evt-0006",
            caused_by="evt-0003", artifacts=[ex]))
        # B 试图自审
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_STARTED", "B", "evt-0006", "evt-0007", caused_by="evt-0006"))
        self.assertIn("unauthorized-role", self.rules(self.validate()))

    def test_planner_cannot_execute(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art]))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "A", "evt-0003", "evt-0004", caused_by="evt-0003"))
        self.assertIn("unauthorized-role", self.rules(self.validate()))

    def test_unregistered_role(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        ev["actor"]["role"] = "Z"
        append_event(self.task_dir, ev)
        self.assertIn("unregistered-role", self.rules(self.validate()))


class QualityGateTests(TaskTestCase):
    def _drive_to_review(self):
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002", caused_by="evt-0001"))
        art = make_artifact(self.task_dir, "artifacts/plans/plan-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art]))
        append_event(self.task_dir, make_event(
            self.task_id, "TASK_CLAIMED", "B", "evt-0003", "evt-0004", caused_by="evt-0003"))
        append_event(self.task_dir, make_event(
            self.task_id, "EXECUTION_STARTED", "B", "evt-0004", "evt-0005", caused_by="evt-0004"))
        ex = make_artifact(self.task_dir, "artifacts/executions/execution-b-v001.md")
        append_event(self.task_dir, make_event(
            self.task_id, "WORK_READY", "B", "evt-0005", "evt-0006",
            caused_by="evt-0003", artifacts=[ex]))
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_STARTED", "A", "evt-0006", "evt-0007", caused_by="evt-0006"))
        return make_artifact(self.task_dir, "artifacts/reviews/review-v001.md")

    def test_approve_happy_path(self):
        review_art = self._drive_to_review()
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_APPROVED", "A", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[review_art],
            payload=review_payload(score=95)))
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        self.assertEqual(r.final_status, "APPROVED")

    def test_low_score_cannot_approve(self):
        review_art = self._drive_to_review()
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_APPROVED", "A", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[review_art],
            payload=review_payload(score=60)))
        self.assertIn("quality-gate", self.rules(self.validate()))

    def test_approve_requires_review_artifact(self):
        self._drive_to_review()
        append_event(self.task_dir, make_event(
            self.task_id, "REVIEW_APPROVED", "A", "evt-0007", "evt-0008",
            caused_by="evt-0007", payload=review_payload(score=95)))
        self.assertIn("missing-review-artifact", self.rules(self.validate()))

    def test_revision_cycle_limit(self):
        review_art = self._drive_to_review()
        p = review_payload(score=60, cycle=3)
        p["next_revision_cycle"] = 4
        append_event(self.task_dir, make_event(
            self.task_id, "REVISION_REQUIRED", "A", "evt-0007", "evt-0008",
            caused_by="evt-0007", artifacts=[review_art], payload=p, revision_cycle=3))
        self.assertIn("revision-limit", self.rules(self.validate()))


class ArtifactTests(TaskTestCase):
    def test_hash_mismatch(self):
        art = make_artifact(self.task_dir, "artifacts/plans/p.md")
        art["sha256"] = "1" * 64
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
            caused_by="evt-0001", artifacts=[art]))
        self.assertIn("hash-mismatch", self.rules(self.validate()))

    def test_missing_artifact(self):
        art = {"path": "artifacts/plans/ghost.md", "sha256": "0" * 64,
               "media_type": "text/markdown", "version": 1}
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
            caused_by="evt-0001", artifacts=[art]))
        self.assertIn("artifact-missing", self.rules(self.validate()))

    def test_supersede_downgrades_to_warning(self):
        art1 = make_artifact(self.task_dir, "artifacts/plans/p.md", "v1\n")
        append_event(self.task_dir, make_event(
            self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
            caused_by="evt-0001", artifacts=[art1]))
        # 文件演进到 v2，后续事件以更高版本 + 新哈希引用
        art2 = make_artifact(self.task_dir, "artifacts/plans/p.md", "v2\n")
        art2["version"] = 2
        append_event(self.task_dir, make_event(
            self.task_id, "PLAN_READY", "A", "evt-0002", "evt-0003",
            caused_by="evt-0001", artifacts=[art2]))
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        self.assertIn("superseded", {i.rule for i in r.warnings})

    def test_expected_warnings_grandfather(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        ev["actor"]["model"] = "configured-model"
        append_event(self.task_dir, ev)
        with open(os.path.join(self.task_dir, "expected-warnings.json"), "w") as fh:
            json.dump({"downgrade": [{"event_id": "evt-0002", "rule": "placeholder-model"}]}, fh)
        r = self.validate()
        self.assertTrue(r.ok, [str(i) for i in r.errors])
        self.assertIn("placeholder-model", {i.rule for i in r.warnings})

    def test_expected_warnings_do_not_hide_unlisted(self):
        ev = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                        caused_by="evt-0001")
        ev["actor"]["model"] = "configured-model"
        append_event(self.task_dir, ev)
        with open(os.path.join(self.task_dir, "expected-warnings.json"), "w") as fh:
            json.dump({"downgrade": [{"event_id": "evt-OTHER", "rule": "placeholder-model"}]}, fh)
        self.assertIn("placeholder-model", self.rules(self.validate()))


class CandidateTests(TaskTestCase):
    def test_candidate_validated_without_writing(self):
        before = open(os.path.join(self.task_dir, "coordination.md")).read()
        bad = make_event(self.task_id, "WORK_READY", "B", "evt-0001", "evt-0002",
                         caused_by="evt-0001")
        r = self.validate(candidate=bad)
        self.assertFalse(r.ok)
        after = open(os.path.join(self.task_dir, "coordination.md")).read()
        self.assertEqual(before, after)

    def test_good_candidate_passes(self):
        good = make_event(self.task_id, "PLANNING_STARTED", "A", "evt-0001", "evt-0002",
                          caused_by="evt-0001")
        r = self.validate(candidate=good)
        self.assertTrue(r.ok, [str(i) for i in r.errors])


class MarkerTests(TaskTestCase):
    def test_unpaired_markers(self):
        with open(os.path.join(self.task_dir, "coordination.md"), "a") as fh:
            fh.write("\n<!-- MMAC-EVENT-BEGIN -->\n```json\n{}\n```\n")
        self.assertIn("marker-mismatch", self.rules(self.validate()))

    def test_invalid_json_event(self):
        with open(os.path.join(self.task_dir, "coordination.md"), "a") as fh:
            fh.write("\n<!-- MMAC-EVENT-BEGIN -->\n```json\n{\"a\": }\n```\n<!-- MMAC-EVENT-END -->\n")
        self.assertIn("json-invalid", self.rules(self.validate()))


class FixtureSuiteTests(unittest.TestCase):
    """迁移夹具回归：合法通过，负例全部失败。"""

    FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")

    def _run(self, name):
        from agent_collaboration.validator import validate_task
        return validate_task(os.path.join(self.FIXTURES, name))

    def test_valid_fixture(self):
        self.assertTrue(self._run("valid").ok)

    def test_negative_fixtures(self):
        for name in ("bad_caused_by", "bad_hash", "bad_iso_timestamp",
                     "duplicate_event_id", "fork_previous", "illegal_status_type",
                     "missing_required_field", "path_traversal", "placeholder_model"):
            with self.subTest(fixture=name):
                self.assertFalse(self._run(name).ok, name)


if __name__ == "__main__":
    unittest.main()
