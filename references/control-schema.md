# control.md Schema 速查

control.md 为 fenced YAML（安全子集解析：嵌套 map、字符串数组、标量）。

```yaml
protocol:        # name + version
task:            # id / title / created_at / owner
workflow:        # planning_agent / default_executor / multimodal_executor / reviewer
                 # mode: multi（默认）| solo（单会话扮演全部角色）
                 # permission_mode: yolo（默认，自动执行）| confirm（可选，0.4.0+）
                 # allow_parallel_execution / poll_interval_seconds
                 # claim_lease_seconds / stale_agent_timeout_seconds
agents:          # 角色 → {provider, client, model, capabilities, cost_weight,
                 #            effort, thinking}（effort/thinking 可选，0.4.0+）
quality_gate:    # enabled / strict / target_score / max_score / max_revision_cycles
                 # blocking_issues_must_be_zero / require_tests_when_applicable / require_evidence
rubric:          # 权重均为整数且总和必须为 100
permissions:     # allowed_paths[] / forbidden_paths[] / allow_network
                 # allow_external_messages / allow_destructive_actions
                 # require_human_approval_for[]
budget:          # max_cost_weight / prefer_lowest_cost_capable_agent
```

## 校验器强制项

- `workflow` 四个角色字段齐全且为字符串。
- `workflow.mode`（缺省 `multi`）：`solo` 时角色授权放宽为「任一工作流角色
  可发布任意阶段事件」，但 `REVIEW_APPROVED` 必须带 `payload.self_review: true`
  与非空 `payload.reproduced_commands`（评审阶段独立重跑的命令清单）——
  用机械证据替代第二模型的独立判断；批准为临时性，可被后续独立审查覆盖。
- `agents.<role>.effort` ∈ {low, medium, high, max}、
  `agents.<role>.thinking` ∈ {on, off}、`workflow.permission_mode` ∈ {yolo, confirm}
  （均为可选字段，0.4.0+；缺失不报错，存在才校验枚举）。
- `quality_gate.target_score / max_score / max_revision_cycles` 为非负整数，
  target ≤ max。
- `permissions.allowed_paths / forbidden_paths` 为字符串数组。
- `rubric` 权重整数且总和 100。
- `agents` 角色映射非空（用于角色授权校验）。

## 修改纪律

创建后只允许用户或协调器修改配置；Agent 不得擅自降低质量标准或扩大权限。
角色映射变更应记录在 `mapping_history`。
