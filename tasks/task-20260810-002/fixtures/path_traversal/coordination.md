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
      "path": "../../etc/passwd",
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
      "path": "../../etc/passwd",
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
