# Execution B v001 — task-20260810-002 / ST-B：SKILL.md 协议文档优化

- 执行者：角色 B（kimi-session-b-002，kimi-k2.5）
- 依据方案：artifacts/plans/plan-v001.md（SHA-256: 849b1099f35464832f9218b5bfca41ab7d09451c7363fe48127adce3937018fa，已校验一致）
- 文件所有权：仅修改 `SKILL.md`，未触碰 validate.py、task-001 文件、本任务 control.md 与 plan-v001.md

## 执行摘要

按 plan-v001 的 ST-B 五项要求，对 SKILL.md 做最小化精修（共两轮 9 处定点编辑：规划前补强 4 处 + 本轮 5 处），不引入新状态、新基础设施或第三方依赖，保持协议简单透明、向后兼容。

## 修改文件

| 文件 | 变更 |
| --- | --- |
| `SKILL.md`（绝对路径 /Users/tommacmini4/Documents/code/agent_collaboration/SKILL.md） | 6 个章节的定点补充，见下 |

具体修改点：

1. **§3 共享目录**：新增 `tools/validate.py` 强制校验要求；声明校验器对 legacy 相对项目根产物路径采用只读 fallback 并告警，绝不修改历史文件。
2. **§6 必需字段 `actor`**：`model` 必须填真实模型标识，禁止占位符；协作中模型变更须如实填写。
3. **§6 必需字段 `artifacts`**：路径统一相对任务目录；目录外用绝对路径；相对项目根的写法标记为 legacy（校验器只读解析并告警，新事件禁用）。
4. **§6 附加约束**（新增小节）：`status` 与 `type` 对应关系及 4 类状态保持事件；`recipient` 语义（未被指名不得认领）；`caused_by` 必须引用已存在事件；`revision_cycle` 递增规则；校验器错误（exit 1）与告警的区别及告警处理要求。
5. **§7 安全发布第 8 步**：发布后必须运行 `python3 tools/validate.py tasks/<task-id>`，校验通过前发布不算完成；明确残缺事件的合法修复方式（未被引用可删除重发，已被引用按 §15 处理）。
6. **§12 审查流程第 2 条**：执行者声明的运行版本/命令/环境必须由审查者独立重跑；路径基准、产物哈希与 legacy 兼容行为必须可复核。

## 关键决策

- 两轮修改合并交付：规划前的 4 处补强（已由 codex 在 plan-v001 中确认并纳入 ST-B 范围）与本轮 5 处编辑同属 ST-B，一并记录。
- 只补"task-001 实战暴露的歧义"，未改动状态机、质量门槛、角色职责等业务语义（遵守 plan 非目标）。
- 未新增任何事件类型或状态，避免与现有状态机重复。

## 测试与证据

1. 事件发布后校验（B 的 TASK_CLAIMED + EXECUTION_STARTED 之后）：

```text
$ python3 tools/validate.py tasks/task-20260810-002
校验 6 个事件：全部通过 ✓
当前状态：EXECUTING | 最新事件：EXECUTION_STARTED by kimi-session-b-002
```

2. 修改后 SKILL.md 结构完整性：全部 17 节标题保持原有编号与顺序（grep 验证，见下）；新增内容均以追加句/小节方式插入，未删除任何既有规则。

```text
$ grep -c '^## ' SKILL.md  → 17（修改前后一致）
```

3. WORK_READY 发布后将再次运行 validate.py 并在事件 payload 记录结果。

## 与方案的偏差

无。ST-B 五项要求全部覆盖：路径规则+legacy 标记（修改点 3、1）、发布后强制校验顺序（修改点 5）、字段/角色/model/caused_by/revision_cycle/recipient 约束（修改点 2、4）、审查证据独立重跑（修改点 6）、告警与失败处理且不增基础设施（修改点 1、4、5）。

## 已知限制

- SKILL.md 未被 git 跟踪（仓库仅初始提交），无法提供 git diff；修改点以逐条文字说明 + 文件哈希代替。
- task-001 历史事件中的 legacy 路径与占位 model 属只追加历史，不修复，由 C 的校验器 fallback/告警覆盖。

## 待审查事项

- 请 A 独立复核：SKILL.md 全文一致性（重点 §6 附加约束与 §5 状态机、§7 发布流程是否自洽）；
- 请 A 运行 validate.py 校验本任务新事件，并在 C 交付后验证 legacy fallback 对 task-001 的行为与本文档描述一致。
