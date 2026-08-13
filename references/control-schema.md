# control.md Schema 速查

control.md 为 fenced YAML（安全子集解析：嵌套 map、字符串数组、标量）。

```yaml
protocol:        # name + version
task:            # id / title / created_at / owner
workflow:        # planning_agent / default_executor / multimodal_executor / reviewer
                 # allow_parallel_execution / poll_interval_seconds
                 # claim_lease_seconds / stale_agent_timeout_seconds
agents:          # 角色 → {provider, client, model, capabilities, cost_weight}
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
- `quality_gate.target_score / max_score / max_revision_cycles` 为非负整数，
  target ≤ max。
- `permissions.allowed_paths / forbidden_paths` 为字符串数组。
- `rubric` 权重整数且总和 100。
- `agents` 角色映射非空（用于角色授权校验）。

## 修改纪律

创建后只允许用户或协调器修改配置；Agent 不得擅自降低质量标准或扩大权限。
角色映射变更应记录在 `mapping_history`。
