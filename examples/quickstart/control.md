```yaml
protocol:
  name: cross-model-file-collaboration
  version: "1.0"

task:
  id: task-quickstart
  title: 黄金示例：五步最小协作流程
  created_at: 2026-08-11T12:08:59+08:00
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
    provider: configurable
    client: configurable
    model: configurable
    capabilities: [architecture, planning, review, reasoning]
    cost_weight: 5
  B:
    provider: configurable
    client: configurable
    model: configurable
    capabilities: [coding, testing, documentation, file-processing]
    cost_weight: 1
  C:
    provider: configurable
    client: configurable
    model: configurable
    capabilities: [vision, image-analysis, multimodal]
    cost_weight: 3

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

budget:
  max_cost_weight: 30
  prefer_lowest_cost_capable_agent: true
```
