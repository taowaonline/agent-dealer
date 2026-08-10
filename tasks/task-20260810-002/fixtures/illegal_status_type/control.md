protocol:
  name: cross-model-file-collaboration
  version: 1.0
task:
  id: task-fixture-001
  owner: human
workflow:
  planning_agent: A
  default_executor: B
  multimodal_executor: C
  reviewer: A
  allow_parallel_execution: true
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
agents:
  A:
    provider: openai
  B:
    provider: moonshot
  C:
    provider: zhipu
