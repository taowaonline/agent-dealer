# 协议参考（人类版）

> Agent 必读的可执行规范是 `SKILL.md`；本文档面向人类读者，解释设计意图与机制。

## 核心思想

- 共享目录是唯一协作总线；不依赖任何厂商的会话共享。
- 产物与状态分离：文件是产物，完成与否由结构化事件决定。
- 事件只追加、产物版本化、跨 session 从磁盘恢复。
- 逻辑角色（A/B/C）与模型厂商解耦，映射写在任务 `control.md`。

## 事件协议

事件以 Markdown 代码块形式只追加到 `coordination.md`：

```text
<!-- MMAC-EVENT-BEGIN -->
```json
{ ... }
```
<!-- MMAC-EVENT-END -->
```

必需字段与约束见 [references/event-schema.md](../references/event-schema.md)；
状态机见 [references/state-machine.md](../references/state-machine.md)；
评分量表见 [references/rubric.md](../references/rubric.md)。

## 安全发布（publish）

所有发布必须经过 `agent-dealer-cli publish` / `TaskStore.publish()`：

1. 原子目录锁（`os.mkdir`）；
2. 锁内重读链尾并回填 `previous_event_id`；
3. 候选事件只读预校验；
4. 产物 tmp → 哈希 → `os.replace` 原子固化；
5. 一次追加完整事件块 + fsync；
6. 发布后复核，失败截断回滚；
7. 释放锁。

Agent 不再手工编辑 `coordination.md`。

## 校验器规则分级

- **错误（exit 1）**：链断裂、分叉、哈希篡改、越权、占位 model（新事件）、非法流转等。
- **告警（exit 0）**：legacy 相对项目根路径、被 supersede 的旧哈希、
  `expected-warnings.json` 显式登记的 grandfather 项。

### grandfather 与 supersede

- **supersede**：同一逻辑路径被后续事件以更高版本或匹配当前文件的新哈希引用时，
  早期哈希不一致视为合法版本演进（告警）。
- **grandfather**：历史任务的已知问题写入任务目录的 `expected-warnings.json`
  （`{"downgrade": [{"event_id": "...", "rule": "..."}]}`），逐条降级为告警。
  未登记的错误不受影响。校验器对历史文件只读。

## 错误码

稳定错误码定义于 `src/agent_dealer/errors.py`：

| 码 | 含义 |
| --- | --- |
| MMAC-E101_INVALID_STATE | 非法状态流转 |
| MMAC-E102_INVALID_EVENT | 事件结构非法 |
| MMAC-E103_SCHEMA_VERSION | schema 版本不兼容 |
| MMAC-E104_BROKEN_CHAIN | 链断裂/分叉 |
| MMAC-E201_UNAUTHORIZED_ROLE | 角色越权 |
| MMAC-E202_PLACEHOLDER_MODEL | 占位 model |
| MMAC-E203_PATH_FORBIDDEN | 路径越权 |
| MMAC-E301_HASH_MISMATCH | 哈希不一致 |
| MMAC-E302_ARTIFACT_MISSING | 产物缺失 |
| MMAC-E401_LOCK_CONFLICT | 锁冲突 |
| MMAC-E402_STALE_LOCK | 过期锁 |
| MMAC-E501_APPROVAL_REQUIRED | 需人工审批 |
| MMAC-E502_UNSAFE_PROFILE | 不可信模式缺沙箱 |
| MMAC-E601_RUNNER | Runner/adapter 错误 |

## Runner

`agent-dealer-cli watch` 定时全量校验（不依赖易丢失的文件系统通知），
基于 `event_id` 去重并持久化到 `.runner-state.json`，重启不重复调度。
仅在事件合法、recipient 匹配 adapter、任务非终态时触发。
Runner 只唤醒和监控，不伪造业务审查。

## 质量门

默认 `target_score=90`、`max_revision_cycles=3`、`blocking_issues_must_be_zero`。
批准条件见 SKILL.md §12；校验器会强制：低分不得 APPROVED、blocking>0 不得 APPROVED、
返工超限必须 BLOCKED、REVIEW_APPROVED 必须引用版本化 review 产物。
