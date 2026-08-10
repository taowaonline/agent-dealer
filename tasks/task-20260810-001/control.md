```yaml
protocol:
  name: cross-model-file-collaboration
  version: 1.0

task:
  id: task-20260810-001
  title: 实现 csv2json 命令行工具（协议演示任务）
  created_at: 2026-08-10T12:29:47+08:00
  owner: human

workflow:
  planning_agent: A
  default_executor: B
  multimodal_executor: C
  reviewer: A
  allow_parallel_execution: false
  poll_interval_seconds: 5
  claim_lease_seconds: 900
  stale_agent_timeout_seconds: 1200

agents:
  A:
    provider: openai
    client: codex
    model: configured-model
    capabilities: [architecture, planning, review, reasoning]
    cost_weight: 5
  B:
    provider: zhipu
    client: claude
    model: glm-5.2
    capabilities: [coding, testing, documentation, file-processing]
    cost_weight: 1
  C:
    provider: moonshot
    client: kimi-cli
    model: configured-model
    capabilities: [vision, image-analysis, multimodal, coding]
    cost_weight: 3

mapping_history:
  - at: 2026-08-10T12:29:47+08:00
    note: 初始映射 A=kimi-cli，由 kimi 完成规划阶段
  - at: 2026-08-10T12:35:00+08:00
    note: 用户授权改为 A=codex（顶层设计/审查）、B=claude 客户端运行的 glm-5.2（通用执行）、C=kimi-cli（视觉/多模态及备用执行）；规划产物 plan-v001 保持有效

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
```
