# Review v001 — task-20260810-002

- 审查者：角色 A（codex-session-a-002）
- 触发 WORK_READY：B=88ce931f-df84-4212-ac4b-b6da32501536；C=04c8995e-c9d7-408e-98f6-3850f9bdb012
- 审查事件：5a9b44f0-0fe6-4b1e-9fed-df5d7c123b80
- revision_cycle：0
- 结论：REVISION_REQUIRED
- 总分：74/100
- Blocking issues：2

## 事件与产物校验

11 个事件链连续、无分叉；B/C 的 WORK_READY 均已收到。所有引用产物 SHA-256 均匹配，且 task-001/task-002 文件未被本轮修改。

## 独立验证

- python3 tools/validate.py tasks/task-20260810-002：退出码 0，11 个事件通过。
- python3 tools/validate.py tasks/task-20260810-001：退出码 1，最终状态仍可解析为 APPROVED；报告 8 个错误、6 个 legacy 路径告警。
- python3 tasks/task-20260810-002/fixtures/test_validate_fixtures.py：13 个用例全部通过。
- 逐项抽查 duplicate_event_id、path_traversal、placeholder_model、bad_caused_by、illegal_status_type、bad_hash、fork_previous、bad_iso_timestamp、missing_required_field：均按预期退出码 1，并输出可定位错误。
- 代码使用 Python 3.8+ 标准库；当前 task-002 校验及夹具套件通过。

## 关键裁决

### 历史 placeholder model

新规则要求真实 model，适用于新发布事件；但 task-001 已是不可修改的历史链，且其 configured-model 来自旧协议示例。为了满足向后兼容，历史 legacy 事件应 grandfather 为告警，不能使历史任务校验退出码变为 1。新任务/新事件仍必须对占位 model 报错。

### 可变项目文件哈希演进

task-001 cycle=0 的 tools/csv2json/csv2json.py 哈希与当前文件不同，是 cycle=1 合法修复造成的版本演进，不应被简单当作篡改。若同一逻辑路径在后续链事件中以更高版本/新哈希明确 supersede，早期哈希差异应标为 legacy/superseded 告警；没有后续 superseding 证据的 mismatch 仍必须报错。新事件中应优先使用绝对路径或不可变版本产物，保持严格哈希验证。

## Rubric 评分

| 项目 | 得分 | 满分 | 依据 |
| --- | ---: | ---: | --- |
| requirement_fulfillment | 20 | 30 | 新校验能力覆盖面大，但向后兼容验收未真正通过，且文档与实现冲突。 |
| correctness | 16 | 25 | 新任务与负例正确；历史事件被错误阻断，合法返工哈希演进被误报错误。 |
| tests_and_verification | 17 | 20 | 13 个夹具和指定负例充分；但兼容测试把已知错误当作预期，未验证批准的 grandfather 语义。 |
| maintainability | 8 | 10 | 分层清晰、标准库兼容；SKILL.md 有重复约束行，legacy 规则未集中定义。 |
| security_and_risk | 10 | 10 | 路径穿越、字段格式、分叉和哈希基础检查健壮，无网络/凭据/破坏性操作。 |
| documentation | 3 | 5 | SKILL.md 说明占位符为告警，但 C 实现升级为错误；未说明可变产物 supersede 规则。 |
| **总计** | **74** | **100** | 低于 90 分门槛。 |

## ISSUE-001

- Severity: blocking
- Owner: C
- Evidence: tools/validate.py 对 task-001 的 7 个 configured-model 全部调用 fail；cycle=0 的旧 csv2json.py 哈希与 cycle=1 当前文件差异也调用 fail。独立命令退出码 1。
- Deduction: 20
- Required change: 增加明确、受限的 legacy grandfather 规则：对旧式相对项目根产物/历史事件中的占位 model 输出 warning；同一逻辑路径存在后续链上更高版本且哈希已更新的 supersede 证据时，早期 mismatch 输出 warning；无 supersede 证据或新事件仍为 error。不得通过全局关闭哈希或 model 检查。
- Acceptance: python3 tools/validate.py tasks/task-20260810-001 返回 0，最终 APPROVED 可读，并对 8 个已知历史问题只输出 warning；所有现有负例（包括 placeholder_model 与 bad_hash）仍返回 1；新增一个合法演进夹具覆盖旧哈希→新版本哈希。

## ISSUE-002

- Severity: blocking
- Owner: B
- Evidence: SKILL.md §6 附加约束两次重复同一“错误/告警”句；文档称占位符模型为告警，但 C 的实现和 C 执行记录称其为错误。SKILL.md 未定义可变项目文件的 supersede/版本演进判定。
- Deduction: 6
- Required change: 删除重复句，统一文档：新事件占位 model 为 error；明确标记的 legacy 历史占位 model 与有链上 supersede 证据的旧哈希为 warning；无证据的 mismatch 仍为 error。说明审查者如何记录 legacy 告警而不掩盖新事件问题。
- Acceptance: SKILL.md 全文规则与 validate.py 行为一致；task-001 兼容性、合法演进和负例验收命令与规则逐项对应。

## 质量门槛判定

score 74 < 90，blocking_issues=2，required_tests_passed=false（历史兼容验收未通过），required_evidence_present=true。因此不得批准；首次审查未超过最大返工次数，应发布 REVISION_REQUIRED，分别指派 C 修复校验器、B 修正文档。
