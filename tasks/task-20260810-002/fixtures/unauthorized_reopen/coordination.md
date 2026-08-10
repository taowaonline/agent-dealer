# Coordination Log (fixture)

本文件由 gen.py 生成，仅用于测试。

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e1",
  "previous_event_id": null,
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "TASK_CREATED",
  "status": "CREATED",
  "actor": {
    "role": "coordinator",
    "instance_id": "fixture-coord-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "A"
  },
  "caused_by": null,
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:00:00+08:00",
  "artifacts": [],
  "summary": "fixture event TASK_CREATED",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e2",
  "previous_event_id": "e1",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "PLANNING_STARTED",
  "status": "PLANNING",
  "actor": {
    "role": "A",
    "instance_id": "fixture-a-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "B"
  },
  "caused_by": "e1",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:00:30+08:00",
  "artifacts": [],
  "summary": "fixture event PLANNING_STARTED",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e3",
  "previous_event_id": "e2",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "PLAN_READY",
  "status": "PLAN_READY",
  "actor": {
    "role": "A",
    "instance_id": "fixture-a-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "B"
  },
  "caused_by": "e1",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:01:00+08:00",
  "artifacts": [
    {
      "path": "sample.txt",
      "sha256": "a3c6acb4dd171f305d805c0d1344a0f794b228b2c78e9ee166950e075256409c",
      "media_type": "text/plain",
      "version": 1
    }
  ],
  "summary": "fixture event PLAN_READY",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e4",
  "previous_event_id": "e3",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "TASK_CLAIMED",
  "status": "CLAIMED",
  "actor": {
    "role": "B",
    "instance_id": "fixture-b-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "A"
  },
  "caused_by": "e3",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:01:30+08:00",
  "artifacts": [
    {
      "path": "sample.txt",
      "sha256": "a3c6acb4dd171f305d805c0d1344a0f794b228b2c78e9ee166950e075256409c",
      "media_type": "text/plain",
      "version": 1
    }
  ],
  "summary": "fixture event TASK_CLAIMED",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e5",
  "previous_event_id": "e4",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "EXECUTION_STARTED",
  "status": "EXECUTING",
  "actor": {
    "role": "B",
    "instance_id": "fixture-b-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "B"
  },
  "caused_by": "e4",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:02:00+08:00",
  "artifacts": [],
  "summary": "fixture event EXECUTION_STARTED",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e6",
  "previous_event_id": "e5",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "WORK_READY",
  "status": "WORK_READY",
  "actor": {
    "role": "B",
    "instance_id": "fixture-b-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "B"
  },
  "caused_by": "e5",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:02:30+08:00",
  "artifacts": [],
  "summary": "fixture event WORK_READY",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e7",
  "previous_event_id": "e6",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "REVIEW_STARTED",
  "status": "REVIEWING",
  "actor": {
    "role": "A",
    "instance_id": "fixture-a-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "B"
  },
  "caused_by": "e6",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:03:00+08:00",
  "artifacts": [],
  "summary": "fixture event REVIEW_STARTED",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e8",
  "previous_event_id": "e7",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "REVIEW_APPROVED",
  "status": "APPROVED",
  "actor": {
    "role": "A",
    "instance_id": "fixture-a-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "B"
  },
  "caused_by": "e7",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:03:30+08:00",
  "artifacts": [
    {
      "path": "sample.txt",
      "sha256": "a3c6acb4dd171f305d805c0d1344a0f794b228b2c78e9ee166950e075256409c",
      "media_type": "text/plain",
      "version": 1
    }
  ],
  "summary": "fixture event REVIEW_APPROVED",
  "payload": {
    "score": 95,
    "target_score": 90,
    "blocking_issues": 0,
    "required_tests_passed": true,
    "required_evidence_present": true
  }
}
```
<!-- MMAC-EVENT-END -->

<!-- MMAC-EVENT-BEGIN -->
```json
{
  "protocol_version": "1.0",
  "event_id": "e9",
  "previous_event_id": "e8",
  "task_id": "task-fixture-001",
  "parent_task_id": null,
  "type": "TASK_REOPENED",
  "status": "CLAIMED",
  "actor": {
    "role": "B",
    "instance_id": "fixture-b-001",
    "provider": "zhipu",
    "client": "claude",
    "model": "glm-5.2"
  },
  "recipient": {
    "role": "B"
  },
  "caused_by": "e8",
  "revision_cycle": 0,
  "timestamp": "2026-08-10T13:04:00+08:00",
  "artifacts": [],
  "summary": "fixture event TASK_REOPENED",
  "payload": {}
}
```
<!-- MMAC-EVENT-END -->
