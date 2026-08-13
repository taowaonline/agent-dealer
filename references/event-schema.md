# 事件 Schema 速查（schema v1.0）

## 事件块格式

````markdown
<!-- MMAC-EVENT-BEGIN -->
```json
{ ... }
```
<!-- MMAC-EVENT-END -->
````

只有同时具备开始标记、合法 JSON 对象和结束标记的事件才有效。

## 必需字段

| 字段 | 约束 |
| --- | --- |
| `protocol_version` | 字符串，当前支持 `"1.0"` |
| `event_id` | 全局唯一非空字符串（优先 UUID） |
| `previous_event_id` | 写入前链尾事件 ID；首事件为 `null` |
| `task_id` | 所属任务；同一日志内必须一致 |
| `parent_task_id` | 字符串或 `null` |
| `type` | 标准事件类型之一（见下表） |
| `status` | 事件发布后的任务状态，与 type 对应 |
| `actor` | `{role, instance_id, provider, client, model}` 全非空；`model` 必须为真实标识，禁用占位符 |
| `recipient` | `{"role": ...}`；指明下一应行动角色，未被指名者不得据此认领 |
| `caused_by` | 触发事件 ID，必须引用本任务已存在事件；首事件可为 `null` |
| `revision_cycle` | 非负整数；首次实施为 0，每次返工递增 1，不得跳变 |
| `timestamp` | ISO 8601 带时区 |
| `artifacts` | 数组；元素 `{path, sha256, media_type, version}` |
| `summary` | 一句话摘要 |
| `payload` | 对象；类型相关负载（见下） |

## artifact 字段

- `path`：任务目录内相对路径；任务目录外用绝对路径；禁止 `..` 穿越与 symlink 逃逸。
- `sha256`：64 位小写 hex。
- `version`：≥1 整数；同一逻辑路径演进时必须递增。
- legacy 相对项目根路径只读 fallback + 告警；supersede 与 grandfather 规则见 docs/protocol.md。

## 标准事件类型

```text
TASK_CREATED  PLANNING_STARTED  PLAN_READY  TASK_DECOMPOSED
TASK_CLAIMED  TASK_RECLAIMED    EXECUTION_STARTED  HEARTBEAT
WORK_READY    REVIEW_STARTED    REVIEW_APPROVED    REVISION_REQUIRED
REVISION_STARTED  TASK_BLOCKED  TASK_FAILED  TASK_CANCELLED
TASK_REOPENED  ROLE_OVERRIDE    EVENT_REJECTED
```

## 状态保持事件

`HEARTBEAT`、`ROLE_OVERRIDE`、`EVENT_REJECTED`、`TASK_DECOMPOSED` 的 `status`
必须与进入前状态完全一致。

## 类型相关 payload 约束（校验器强制）

- `REVIEW_APPROVED` / `REVISION_REQUIRED`：`score`(0..max)、`blocking_issues`、
  `required_tests_passed`、`required_evidence_present`(bool) 必填；
  `target_score` 如填必须与 control.md 一致。
- `REVISION_REQUIRED`：`next_revision_cycle = revision_cycle + 1`；
  `revision_cycle >= max_revision_cycles` 时必须 `TASK_BLOCKED`。
- `REVIEW_APPROVED` 必须引用 `artifacts/reviews/` 下的版本化审查产物。
- 并行子任务事件使用 `payload.subtask_id`；旧字段 `payload.subtask` 仅告警兼容。
