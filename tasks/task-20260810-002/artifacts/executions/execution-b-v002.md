# Execution B v002 — task-20260810-002 / ISSUE-002 返工（revision_cycle=1）

- 执行者：角色 B（kimi-session-b-002，kimi-k2.5）
- 触发：REVISION_REQUIRED（c0a4f0ba-02e2-4f11-9a24-0b199bc2d4c6），ISSUE-002，扣 6 分
- 文件所有权：仅修改 `SKILL.md`

## 执行摘要

按 review-v001 的 Required change 完成 4 处定点编辑：消除重复、统一错误/告警语义、新增 grandfather 与 supersede 规则的唯一定义点、明确审查者记录义务。

## 修改文件

`SKILL.md`（/Users/tommacmini4/Documents/code/agent_collaboration/SKILL.md）：

1. **§3**：删除与 §6 重复的 legacy fallback 描述，改为指向"第 6 节附加约束统一定义"。
2. **§6 artifacts 字段**：删除重复的"只读解析并告警"句，保留路径基准规则并指向附加约束。
3. **§6 附加约束**（唯一定义点，4 条规则）：
   - 错误（exit 1，必须修复）vs 告警（不阻塞但不得静默忽略）；
   - **legacy grandfather**：历史任务的相对项目根路径、历史事件占位 model 只产生告警，不得使历史校验失败；新事件中二者一律为错误；校验器对历史文件只读；
   - **supersede 版本演进**：同一逻辑路径在后续链上事件中以更高版本号+新哈希明确取代时，早期哈希不一致降为告警；无 supersede 证据的 mismatch 视为篡改（错误）；新事件优先绝对路径/不可变版本产物；
   - 审查者须在审查记录逐条列出 legacy 告警及依据，不得以告警掩盖新事件错误。
4. **§12 审查第 2 条**：补充"审查记录须逐条列出 legacy 告警及其 grandfather/supersede 依据"。

## 关键决策

- 与 ISSUE-001（C 的校验器实现）的语义严格对齐：新事件占位 model=error、历史=warning、supersede 证据存在=warning、无证据=error——与 review-v001 的「关键裁决」逐字对应。
- 规则集中于 §6 附加约束单点定义，§3/§6-artifacts 只做引用，消除"重复约束行"（回应 rubric maintainability 扣分）。

## 测试与证据

```text
$ python3 tools/validate.py tasks/task-20260810-002   # REVISION_STARTED 发布后
校验 13 个事件：全部通过 ✓（0 个告警）
当前状态：EXECUTING | 最新事件：REVISION_STARTED by kimi-session-b-002
```

WORK_READY 发布后再次校验并记录。

## 与方案的偏差

无。仅修复 ISSUE-002 列出的问题，未扩大范围。

## 已知限制

- 文档与 C 端实现的一致性需 A 在 C 交付后联合复核（validate.py 行为 vs §6 附加约束）。
- v001 执行记录中"17 节标题"的表述（实际 grep 为 18，多出的为 §12 预置 `## ISSUE-<编号>` 模板）在此更正说明。

## 待审查事项

- §6 附加约束 4 条规则与 validate.py 修复后行为是否逐项一致；
- 是否仍存在遗漏的重复/冲突表述。
