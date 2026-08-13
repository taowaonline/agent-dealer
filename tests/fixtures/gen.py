#!/usr/bin/env python3
"""生成 validate.py 的协议夹具（合法 + 各种失败场景）。

每个 fixture 子目录会得到自己的 coordination.md，
其中事件以 fixtures/<name>/ 内的相对产物路径引用，保证自包含。

运行：python3 tasks/task-20260810-002/fixtures/gen.py
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ARTIFACT_TEXT = "fixture artifact content\n"
ARTIFACT_HASH = hashlib.sha256(ARTIFACT_TEXT.encode("utf-8")).hexdigest()

CONTROL_TEMPLATE = """protocol:
  name: cross-model-file-collaboration
  version: 1.0
task:
  id: task-fixture-001
  owner: human
workflow:
  planning_agent: A
  default_executor: B
  multimodal_executor: C
  reviewer: A
  allow_parallel_execution: true
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
agents:
  A:
    provider: openai
  B:
    provider: moonshot
  C:
    provider: zhipu
"""


def write_artifact(name: str) -> dict:
    """在 fixtures/<name>/ 下写一个 sample.txt 产物，返回 artifact 描述符。"""
    d = ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "sample.txt"
    p.write_text(ARTIFACT_TEXT, encoding="utf-8")
    return {
        "path": "sample.txt",
        "sha256": ARTIFACT_HASH,
        "media_type": "text/plain",
        "version": 1,
    }


def ev(
    eid: str,
    prev: str | None,
    etype: str,
    status: str,
    *,
    actor_role: str = "A",
    actor_instance: str = "fixture-a-001",
    actor_model: str = "glm-5.2",
    recipient_role: str = "B",
    caused_by: str | None = None,
    revision_cycle: int = 0,
    timestamp: str = "2026-08-10T13:00:00+08:00",
    artifacts: list | None = None,
    task_id: str = "task-fixture-001",
    protocol_version: str = "1.0",
    extra_fields: dict | None = None,
) -> dict:
    e = {
        "protocol_version": protocol_version,
        "event_id": eid,
        "previous_event_id": prev,
        "task_id": task_id,
        "parent_task_id": None,
        "type": etype,
        "status": status,
        "actor": {
            "role": actor_role,
            "instance_id": actor_instance,
            "provider": "zhipu",
            "client": "claude",
            "model": actor_model,
        },
        "recipient": {"role": recipient_role},
        "caused_by": caused_by,
        "revision_cycle": revision_cycle,
        "timestamp": timestamp,
        "artifacts": artifacts or [],
        "summary": f"fixture event {etype}",
        "payload": {},
    }
    if extra_fields:
        e.update(extra_fields)
    return e


def render(events: list) -> str:
    parts = ["# Coordination Log (fixture)\n", "本文件由 gen.py 生成，仅用于测试。\n"]
    for e in events:
        parts.append("<!-- MMAC-EVENT-BEGIN -->")
        parts.append("```json")
        parts.append(json.dumps(e, ensure_ascii=False, indent=2))
        parts.append("```")
        parts.append("<!-- MMAC-EVENT-END -->")
        parts.append("")
    return "\n".join(parts)


def write_coord(name: str, events: list) -> None:
    d = ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "control.md").write_text(CONTROL_TEMPLATE, encoding="utf-8")
    (d / "coordination.md").write_text(render(events), encoding="utf-8")


def valid_chain(artifact: dict | None = None, *, task_id: str = "task-fixture-001") -> list:
    arts = [artifact] if artifact else []
    e1 = ev("e1", None, "TASK_CREATED", "CREATED", actor_role="coordinator",
            actor_instance="fixture-coord-001", recipient_role="A",
            caused_by=None, timestamp="2026-08-10T13:00:00+08:00", task_id=task_id)
    e2 = ev("e2", "e1", "PLANNING_STARTED", "PLANNING", caused_by="e1",
            timestamp="2026-08-10T13:00:30+08:00", task_id=task_id)
    e3 = ev("e3", "e2", "PLAN_READY", "PLAN_READY", caused_by="e1",
            recipient_role="B", artifacts=arts, timestamp="2026-08-10T13:01:00+08:00",
            task_id=task_id)
    e4 = ev("e4", "e3", "TASK_CLAIMED", "CLAIMED", actor_role="B",
            actor_instance="fixture-b-001", recipient_role="A", caused_by="e3",
            artifacts=arts, timestamp="2026-08-10T13:01:30+08:00", task_id=task_id)
    return [e1, e2, e3, e4]


def main() -> None:
    # --- valid ---
    artifact = write_artifact("valid")
    write_coord("valid", valid_chain(artifact))

    # --- duplicate_event_id ---
    artifact = write_artifact("duplicate_event_id")
    chain = valid_chain(artifact)
    chain[-1] = dict(chain[-1])
    chain[-1]["event_id"] = "e1"  # 与首个事件重复
    chain[-1]["previous_event_id"] = "e3"
    write_coord("duplicate_event_id", chain)

    # --- bad_caused_by ---
    artifact = write_artifact("bad_caused_by")
    chain = valid_chain(artifact)
    chain[-1] = dict(chain[-1])
    chain[-1]["caused_by"] = "nonexistent-event-id"
    write_coord("bad_caused_by", chain)

    # --- illegal_status_type: type=WORK_READY 但 status=CLAIMED ---
    artifact = write_artifact("illegal_status_type")
    chain = valid_chain(artifact)
    chain[-1] = dict(chain[-1])
    chain[-1]["type"] = "WORK_READY"
    chain[-1]["status"] = "CLAIMED"  # 与 type 不一致
    write_coord("illegal_status_type", chain)

    # --- bad_hash ---
    d = ROOT / "bad_hash"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sample.txt").write_text("different content - hash mismatch\n", encoding="utf-8")
    chain = valid_chain({
        "path": "sample.txt",
        "sha256": ARTIFACT_HASH,  # 与上一步写入的内容不匹配
        "media_type": "text/plain",
        "version": 1,
    })
    write_coord("bad_hash", chain)

    # --- path_traversal ---
    artifact = write_artifact("path_traversal")
    chain = valid_chain({
        "path": "../../etc/passwd",
        "sha256": ARTIFACT_HASH,
        "media_type": "text/plain",
        "version": 1,
    })
    write_coord("path_traversal", chain)

    # --- placeholder_model ---
    artifact = write_artifact("placeholder_model")
    chain = valid_chain(artifact)
    chain[0] = dict(chain[0])
    chain[0]["actor"] = dict(chain[0]["actor"])
    chain[0]["actor"]["model"] = "configured-model"
    write_coord("placeholder_model", chain)

    # --- fork_previous: 两个事件指向同一个 previous_event_id ---
    artifact = write_artifact("fork_previous")
    e1, e2, e3, e4 = valid_chain(artifact)
    # e4 与 e3 都以 e2 为 previous（构造分叉）
    e3["previous_event_id"] = "e2"
    e4["previous_event_id"] = "e2"  # 与 e3 同 previous
    write_coord("fork_previous", [e1, e2, e3, e4])

    # --- bad_iso_timestamp ---
    artifact = write_artifact("bad_iso_timestamp")
    chain = valid_chain(artifact)
    chain[1] = dict(chain[1])
    chain[1]["timestamp"] = "2026-08-10 13:00:30"  # 缺 T 与时区
    write_coord("bad_iso_timestamp", chain)

    # --- missing_required_field ---
    artifact = write_artifact("missing_required_field")
    chain = valid_chain(artifact)
    chain[2] = dict(chain[2])
    del chain[2]["task_id"]  # 删除必需字段
    write_coord("missing_required_field", chain)

    # --- heartbeat_status_change：状态保持事件伪造 APPROVED ---
    artifact = write_artifact("heartbeat_status_change")
    chain = valid_chain(artifact)[:3]
    heartbeat = ev("e4", "e3", "HEARTBEAT", "APPROVED", actor_role="B",
                   actor_instance="fixture-b-001", caused_by="e3",
                   timestamp="2026-08-10T13:01:30+08:00")
    write_coord("heartbeat_status_change", chain + [heartbeat])

    # --- future_caused_by：caused_by 引用尚未出现的事件 ---
    artifact = write_artifact("future_caused_by")
    chain = valid_chain(artifact)
    chain[1] = dict(chain[1])
    chain[1]["caused_by"] = "e3"
    write_coord("future_caused_by", chain)

    # --- self_approval：B 冒充 reviewer 批准自己的交付 ---
    artifact = write_artifact("self_approval")
    chain = valid_chain(artifact)
    e5 = ev("e5", "e4", "EXECUTION_STARTED", "EXECUTING", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e4", timestamp="2026-08-10T13:02:00+08:00")
    e6 = ev("e6", "e5", "WORK_READY", "WORK_READY", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e5", artifacts=[artifact],
            timestamp="2026-08-10T13:02:30+08:00")
    e7 = ev("e7", "e6", "REVIEW_STARTED", "REVIEWING", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e6", timestamp="2026-08-10T13:03:00+08:00")
    e8 = ev("e8", "e7", "REVIEW_APPROVED", "APPROVED", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e7", artifacts=[artifact],
            timestamp="2026-08-10T13:03:30+08:00")
    e8["payload"] = {"score": 95, "target_score": 90, "blocking_issues": 0,
                     "required_tests_passed": True, "required_evidence_present": True}
    write_coord("self_approval", chain + [e5, e6, e7, e8])

    # --- low_score_approval：A 以低于门槛的分数批准 ---
    artifact = write_artifact("low_score_approval")
    chain = valid_chain(artifact)
    e5 = ev("e5", "e4", "EXECUTION_STARTED", "EXECUTING", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e4", timestamp="2026-08-10T13:02:00+08:00")
    e6 = ev("e6", "e5", "WORK_READY", "WORK_READY", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e5", artifacts=[artifact],
            timestamp="2026-08-10T13:02:30+08:00")
    e7 = ev("e7", "e6", "REVIEW_STARTED", "REVIEWING", actor_role="A",
            caused_by="e6", timestamp="2026-08-10T13:03:00+08:00")
    e8 = ev("e8", "e7", "REVIEW_APPROVED", "APPROVED", actor_role="A",
            caused_by="e7", artifacts=[artifact], timestamp="2026-08-10T13:03:30+08:00")
    e8["payload"] = {"score": 89, "target_score": 90, "blocking_issues": 0,
                     "required_tests_passed": True, "required_evidence_present": True}
    write_coord("low_score_approval", chain + [e5, e6, e7, e8])

    # --- revision_limit_exceeded：第 3 轮后仍错误地要求第 4 轮 ---
    artifact = write_artifact("revision_limit_exceeded")
    chain = valid_chain(artifact)
    e5 = ev("e5", "e4", "EXECUTION_STARTED", "EXECUTING", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e4", revision_cycle=3,
            timestamp="2026-08-10T13:02:00+08:00")
    e6 = ev("e6", "e5", "WORK_READY", "WORK_READY", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e5", revision_cycle=3,
            timestamp="2026-08-10T13:02:30+08:00")
    e7 = ev("e7", "e6", "REVIEW_STARTED", "REVIEWING", actor_role="A",
            caused_by="e6", revision_cycle=3, timestamp="2026-08-10T13:03:00+08:00")
    e8 = ev("e8", "e7", "REVISION_REQUIRED", "REVISION_REQUIRED", actor_role="A",
            caused_by="e7", revision_cycle=3, artifacts=[artifact],
            timestamp="2026-08-10T13:03:30+08:00")
    e8["payload"] = {"score": 88, "target_score": 90, "blocking_issues": 1,
                     "required_tests_passed": False, "required_evidence_present": True,
                     "next_revision_cycle": 4}
    write_coord("revision_limit_exceeded", chain + [e5, e6, e7, e8])

    # --- unauthorized_reopen：B 试图重开终态任务 ---
    artifact = write_artifact("unauthorized_reopen")
    chain = valid_chain(artifact)
    e5 = ev("e5", "e4", "EXECUTION_STARTED", "EXECUTING", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e4", timestamp="2026-08-10T13:02:00+08:00")
    e6 = ev("e6", "e5", "WORK_READY", "WORK_READY", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e5", timestamp="2026-08-10T13:02:30+08:00")
    e7 = ev("e7", "e6", "REVIEW_STARTED", "REVIEWING", actor_role="A",
            caused_by="e6", timestamp="2026-08-10T13:03:00+08:00")
    e8 = ev("e8", "e7", "REVIEW_APPROVED", "APPROVED", actor_role="A",
            caused_by="e7", artifacts=[artifact], timestamp="2026-08-10T13:03:30+08:00")
    e8["payload"] = {"score": 95, "target_score": 90, "blocking_issues": 0,
                     "required_tests_passed": True, "required_evidence_present": True}
    e9 = ev("e9", "e8", "TASK_REOPENED", "CLAIMED", actor_role="B",
            actor_instance="fixture-b-001", caused_by="e8", timestamp="2026-08-10T13:04:00+08:00")
    write_coord("unauthorized_reopen", chain + [e5, e6, e7, e8, e9])

    # --- symlink_escape：任务目录内链接指向任务目录外 ---
    artifact = write_artifact("symlink_escape")
    link = ROOT / "symlink_escape" / "escape-link"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to("/etc/hosts")
    artifact = {
        "path": "escape-link",
        "sha256": hashlib.sha256(Path("/etc/hosts").read_bytes()).hexdigest(),
        "media_type": "text/plain",
        "version": 1,
    }
    write_coord("symlink_escape", valid_chain(artifact))

    print("fixtures generated at", ROOT)
    for sub in sorted(ROOT.iterdir()):
        if sub.is_dir():
            print(" -", sub.name)


if __name__ == "__main__":
    main()
