```yaml
protocol:
  name: cross-model-file-collaboration
  version: 1.0

task:
  id: task-20260810-002
  title: 优化 SKILL.md 协作协议自身（自举迭代）
  created_at: 2026-08-10T13:02:41+08:00
  owner: human

workflow:
  planning_agent: A
  default_executor: B
  multimodal_executor: C
  reviewer: A
  allow_parallel_execution: true
  poll_interval_seconds: 5
  claim_lease_seconds: 900
  stale_agent_timeout_seconds: 1200

agents:
  A:
    provider: openai
    client: codex
    model: gpt-5.6-luna
    capabilities: [architecture, planning, review, reasoning, task-assignment]
    cost_weight: 2
  B:
    provider: moonshot
    client: kimi-cli
    model: kimi-k2.5
    capabilities: [coding, testing, documentation, protocol-design]
    cost_weight: 1
  C:
    provider: zhipu
    client: claude
    model: glm-5.2
    capabilities: [coding, testing, documentation, file-processing]
    cost_weight: 1

quality_gate:
  enabled: true
  strict: true
  target_score: 90
  max_score: 100
  max_revision_cycles: 3
  blocking_issues_must_be_zero: true
  require_tests_when_applicable: true
  require_evidence: true

rubric:
  requirement_fulfillment: 30
  correctness: 25
  tests_and_verification: 20
  maintainability: 10
  security_and_risk: 10
  documentation: 5

permissions:
  allowed_paths: ["./"]
  forbidden_paths: [".git/"]
  allow_network: false
  allow_external_messages: false
  allow_destructive_actions: false
  require_human_approval_for:
    - credential_use
    - production_change
    - purchase
    - publication
    - destructive_action

budget:
  max_cost_weight: 30
  prefer_lowest_cost_capable_agent: true

notes:
  goal: 基于 task-20260810-001 的实战经验，审查并优化 SKILL.md 协作协议与 tools/validate.py，提升健壮性、清晰度与可执行性
  evidence_task: task-20260810-001
  constraint: 保持协议简单透明，不做过度设计；改动须向后兼容（不破坏 task-001 的历史事件可读性）
```
