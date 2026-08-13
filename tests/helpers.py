"""测试基建：快速构造合成任务目录与合法事件。"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from agent_collaboration import validator  # noqa: E402

CONTROL = """```yaml
protocol:
  name: cross-model-file-collaboration
  version: "1.0"

task:
  id: {task_id}
  title: 合成测试任务
  created_at: 2026-08-11T10:00:00+08:00
  owner: human

workflow:
  planning_agent: A
  default_executor: B
  multimodal_executor: C
  reviewer: A
  allow_parallel_execution: false
  poll_interval_seconds: 5
  claim_lease_seconds: 900
  stale_agent_timeout_seconds: 1200

agents:
  A:
    provider: openai
    client: codex
    model: gpt-5.6-luna
  B:
    provider: moonshot
    client: kimi-cli
    model: kimi-k2.5
  C:
    provider: zhipu
    client: claude
    model: glm-5.2

quality_gate:
  enabled: true
  strict: true
  target_score: 90
  max_score: 100
  max_revision_cycles: 3
  blocking_issues_must_be_zero: true
  require_tests_when_applicable: true
  require_evidence: true

rubric:
  requirement_fulfillment: 30
  correctness: 25
  tests_and_verification: 20
  maintainability: 10
  security_and_risk: 10
  documentation: 5

permissions:
  allowed_paths: ["./"]
  forbidden_paths: [".git/"]
  allow_network: false

budget:
  max_cost_weight: 30
```
"""

ACTORS = {
    "coordinator": {"role": "coordinator", "instance_id": "coord-1", "provider": "local",
                    "client": "test", "model": "test-model"},
    "A": {"role": "A", "instance_id": "a-1", "provider": "openai",
          "client": "codex", "model": "gpt-5.6-luna"},
    "B": {"role": "B", "instance_id": "b-1", "provider": "moonshot",
          "client": "kimi-cli", "model": "kimi-k2.5"},
    "C": {"role": "C", "instance_id": "c-1", "provider": "zhipu",
          "client": "claude", "model": "glm-5.2"},
}

_TS = [0]


def next_ts() -> str:
    _TS[0] += 1
    return "2026-08-11T10:%02d:%02d+08:00" % (_TS[0] // 60 % 60, _TS[0] % 60)


def make_event(task_id: str, etype: str, role: str, prev, eid: str,
               caused_by=None, recipient: str = "A", revision_cycle: int = 0,
               payload=None, artifacts=None, status=None, summary=""):
    if status is None:
        expected = validator.EVENT_EXPECTED_STATUS[etype]
        status = expected if expected is not None else None
    if status is None:
        raise ValueError("status-keeping 事件需显式给 status")
    return {
        "protocol_version": "1.0",
        "event_id": eid,
        "previous_event_id": prev,
        "task_id": task_id,
        "parent_task_id": None,
        "type": etype,
        "status": status,
        "actor": dict(ACTORS[role]),
        "recipient": {"role": recipient},
        "caused_by": caused_by,
        "revision_cycle": revision_cycle,
        "timestamp": next_ts(),
        "artifacts": artifacts or [],
        "summary": summary or etype,
        "payload": payload or {},
    }


def make_task(root: str, task_id: str = "task-test-001") -> str:
    """在 root/tasks/<task_id> 创建合法任务骨架（含 TASK_CREATED）。"""
    task_dir = os.path.join(root, "tasks", task_id)
    for sub in ("artifacts/plans", "artifacts/executions", "artifacts/reviews",
                "artifacts/media", "locks", "tmp"):
        os.makedirs(os.path.join(task_dir, sub), exist_ok=True)
    with open(os.path.join(task_dir, "control.md"), "w", encoding="utf-8") as fh:
        fh.write(CONTROL.format(task_id=task_id))
    created = make_event(task_id, "TASK_CREATED", "coordinator", None,
                         "evt-0001", recipient="A",
                         payload={"goal": "测试"})
    with open(os.path.join(task_dir, "coordination.md"), "w", encoding="utf-8") as fh:
        fh.write("# test\n")
        fh.write(validator.serialize_event(created))
        fh.write("\n")
    return task_dir


def append_event(task_dir: str, event: dict) -> None:
    with open(os.path.join(task_dir, "coordination.md"), "a", encoding="utf-8") as fh:
        fh.write("\n" + validator.serialize_event(event) + "\n")


def make_artifact(task_dir: str, rel: str, content: str = "artifact body\n") -> dict:
    import hashlib
    full = os.path.join(task_dir, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(content)
    return {
        "path": rel,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "media_type": "text/markdown",
        "version": 1,
    }


def review_payload(score: int = 95, blocking: int = 0, cycle: int = 0) -> dict:
    return {
        "score": score,
        "target_score": 90,
        "blocking_issues": blocking,
        "required_tests_passed": True,
        "required_evidence_present": True,
        "issues": [],
        "next_revision_cycle": cycle + 1,
    }


class TaskTestCase(unittest.TestCase):
    """带临时任务目录的基类。"""

    task_id = "task-test-001"

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.task_dir = make_task(self.root, self.task_id)

    def validate(self, candidate=None, **kw):
        return validator.validate_task(self.task_dir, candidate=candidate, **kw)

    def rules(self, report) -> set:
        return {i.rule for i in report.errors}
