# 状态机速查

```text
CREATED
  → PLANNING
  → PLAN_READY
  → CLAIMED
  → EXECUTING
  → WORK_READY
  → REVIEWING
  ├→ APPROVED              （终态）
  ├→ REVISION_REQUIRED → CLAIMED → EXECUTING → WORK_READY
  ├→ BLOCKED               （终态）
  ├→ FAILED                （终态）
  └→ CANCELLED             （终态）
```

## 合法流转表（校验器强制）

| 当前状态 | 允许的下一状态 |
| --- | --- |
| CREATED | PLANNING, CANCELLED |
| PLANNING | PLAN_READY, BLOCKED, FAILED, CANCELLED |
| PLAN_READY | CLAIMED, CANCELLED, FAILED |
| CLAIMED | EXECUTING, CLAIMED, FAILED, CANCELLED, BLOCKED |
| EXECUTING | WORK_READY, BLOCKED, FAILED, CANCELLED |
| WORK_READY | REVIEWING, CLAIMED, EXECUTING, WORK_READY, CANCELLED, FAILED |
| REVIEWING | APPROVED, REVISION_REQUIRED, BLOCKED, FAILED, CANCELLED |
| REVISION_REQUIRED | CLAIMED, EXECUTING, BLOCKED, FAILED, CANCELLED |
| 任一终态 | 仅 TASK_REOPENED（→ CLAIMED，由 human/coordinator 发布） |

说明：

- `WORK_READY → CLAIMED/EXECUTING/WORK_READY` 用于并行子任务交错；
  只有 `REVIEW_STARTED` 才进入 REVIEWING（语义：全部子任务收齐）。
- 状态保持事件（HEARTBEAT 等）不改变状态。
- 达到最大返工次数仍未通过必须进入 BLOCKED，不得降低分数线。
- solo 模式（`workflow.mode: solo`）下 APPROVED 为**临时批准**：发布者与
  执行者同源，`REVIEW_APPROVED` 必须带 `self_review: true` +
  `reproduced_commands`（校验器强制）。后续任何独立审查（multi 模式任务或
  第二模型复核）可发布新的 `REVIEW_APPROVED` / `REVISION_REQUIRED` 覆盖它
  （需先 TASK_REOPENED）。

## 返工轮次

```text
首次实施 → 审查
返工 1 → 审查
返工 2 → 审查
返工 3 → 审查
仍未达标 → BLOCKED
```
