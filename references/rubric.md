# Rubric 与审查纪律速查

## 默认 rubric（满分 100）

| 维度 | 权重 |
| --- | --- |
| requirement_fulfillment | 30 |
| correctness | 25 |
| tests_and_verification | 20 |
| maintainability | 10 |
| security_and_risk | 10 |
| documentation | 5 |

## 批准条件（同时满足）

```text
score >= target_score          （默认 90）
AND blocking_issues == 0
AND required_tests_passed == true
AND required_evidence_present == true
```

## 问题格式

```markdown
## ISSUE-<编号>

- Severity: blocking | major | minor
- Owner: B | C
- Evidence: 可定位的文件、测试结果或视觉证据
- Deduction: 扣分
- Required change: 必须完成的修改
- Acceptance: 可验证的通过条件
```

## 审查纪律

- 不接受执行者自报分数；审查者必须独立重跑执行者声明的版本、命令与环境。
- 每个扣分项写成可追踪 ISSUE。
- 审查记录逐条列出 legacy 告警及其 grandfather/supersede 依据，不得以告警掩盖新事件错误。
- 不得把 BLOCKED 写成 APPROVED；达到返工上限仍未通过必须 TASK_BLOCKED 并提示人工介入。
