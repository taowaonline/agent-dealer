# Agent Collaboration 完整评估与 95 分改进方案

> 评估日期：2026-08-11
> 评估对象：`agent_dealer`
> 基线提交：`456feb1b00a139f9e02877b632922b49ae69cceb`
> 当前结论：Developer Preview / 可验证协议原型
> 当前综合分：61/100
> 目标综合分：95/100

## 1. 执行摘要

该工程已经证明了一件重要的事：Claude、Codex、Kimi、Cursor 和本地模型不需要共享厂商会话，也可以借助共享目录、结构化事件和不可变产物进行跨 session 协作。

目前最成熟的部分是协议约束和离线验证器：事件链、角色授权、状态机、质量门、返工上限、子任务、哈希和路径安全已有较完整实现，22 项协议测试全部通过。结构化 `PLAN_READY`、`WORK_READY` 和 `REVIEW_APPROVED` 也比在文档末尾监听自然语言“完成关键字”可靠。

当前主要问题不在协议，而在产品化层：

1. 工程能判断“下一步应该由谁执行”，但没有真正负责唤醒下一客户端的 Runner。
2. 用户和 Agent 仍需手工创建目录、写 JSON、计算哈希、加锁和追加 Markdown。
3. 仓库没有可一键跑通的黄金示例；两个历史任务直接校验分别产生 8 和 4 个错误。
4. 现有 6 项 Agent 行为评测全部通过，但 5 项只验证文字回答，没有执行真实跨 session 文件接力。
5. 多项安全配置目前是协议声明，不是强制执行，例如网络、外部消息、破坏性操作、预算和人工审批。
6. 缺少 CI、正式包、版本发布、License、Security Policy 和客户端兼容性矩阵。

因此，本工程现在适合可信 Agent、技术用户、同机共享目录和人工接力；尚不适合非技术用户、无人值守生产流程、不可信 Agent 或高并发协作。

达到 95 分的关键不是继续增加协议文字，而是把协议收敛为可调用 CLI、原子发布器、Runner、真实端到端评测和明确的安全边界。

## 2. 评估范围与方法

### 2.1 评估范围

本次覆盖：

- `README.md`：首次使用路径和对外承诺。
- `SKILL.md`：角色、事件、状态、质量门、接力和安全规则。
- `tools/validate.py`：协议的可执行约束。
- `tasks/task-20260810-002/fixtures/`：确定性协议测试。
- `evals/`：真实 Agent Engine 行为评测。
- 两个任务样例：历史兼容、可恢复性和首次体验。
- 仓库成熟度：安装、CLI、CI、发布、License、安全文档。

本次不把以下内容误算为已经实现：

- `SKILL.md` 中描述但仓库不存在的 Runner。
- 仅由事件布尔值声明、未由外部证据验证的测试通过状态。
- 尚未真实运行的 Claude、Kimi、Cursor 客户端组合。
- 客户端自身提供但本项目没有配置或验证的沙箱能力。

### 2.2 证据等级

| 等级 | 定义 | 示例 |
|---|---|---|
| E3 | 自动化执行并验证真实产物 | 单元测试、哈希校验、端到端跨进程测试 |
| E2 | 真实 Agent Engine 执行，但场景可能是模拟输入 | `skill-up run` 行为评测 |
| E1 | 静态实现或文档声明 | `SKILL.md` 规则、README 使用说明 |
| E0 | 计划或设想，尚无实现 | Runner 模式、真实客户端矩阵 |

计分优先采用 E3，其次 E2。只有 E1/E0 的能力不能按“已完成”满分计入。

### 2.3 100 分模型

| 维度 | 权重 | 当前得分 | 目标得分 |
|---|---:|---:|---:|
| 功能与协议完整性 | 20 | 17 | 19 |
| 正确性、并发与恢复 | 20 | 15 | 19 |
| 安全与权限边界 | 15 | 9 | 14 |
| 跨模型与跨客户端互操作 | 15 | 8 | 14 |
| 易用性与可观察性 | 20 | 8 | 19 |
| 工程化、发布与维护 | 10 | 4 | 10 |
| **总计** | **100** | **61** | **95** |

95 分不是“所有功能都存在”的主观判断，而必须同时满足本文第 8 节的硬门槛。

## 3. 本次验证记录

### 3.1 环境

- 日期：2026-08-11
- 平台：macOS
- Python：当前系统 Python
- `skill-up`：0.7.0
- Agent 行为评测引擎：Codex
- 工作树：评估开始时无未提交变更

### 3.2 执行命令

```bash
python3 -m py_compile tools/validate.py tools/csv2json/csv2json.py
python3 -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures -v
python3 -m unittest tools.csv2json.tests.test_csv2json -v
skill-up validate evals/eval.yaml
skill-up list-cases evals/eval.yaml
python3 tools/validate.py tasks/task-20260810-002/fixtures/valid
python3 tools/validate.py tasks/task-20260810-001
python3 tools/validate.py tasks/task-20260810-002
```

### 3.3 确定性结果

| 检查 | 结果 | 结论 |
|---|---|---|
| Python 编译检查 | 通过 | 无语法错误 |
| 协议验证器测试 | 22/22 通过 | 核心负例覆盖有效 |
| CSV 示例工具测试 | 22/22 通过 | 示例交付本身可运行 |
| `eval.yaml` | 6 个用例配置有效 | 可继续用于 Agent 行为评测 |
| 合法协议夹具 | 4 个事件全部通过，0 告警 | 验证器存在黄金输入 |
| `task-20260810-001` | 8 错误、7 告警 | 历史日志可读但不是通过样例 |
| `task-20260810-002` | 4 错误、7 告警 | 处于 `EXECUTING`，引用产物已变化 |

`task-20260810-001` 的主要问题是历史占位模型和旧产物哈希失配；`task-20260810-002` 的主要问题是后续修改了 `SKILL.md`、验证器和夹具，但早期事件仍引用旧哈希。验证器正确地没有掩盖这些错误，但仓库没有明确区分“故意失败的历史样例”和“用户应运行的成功样例”。

### 3.4 Agent 行为评测

最近一次完整报告为 2026-08-10 的 iteration-7：

| 用例 | 状态 | 耗时 |
|---|---|---:|
| `initialize-plan` | PASS | 174.943 秒 |
| `cross-session-executor` | PASS | 75.347 秒 |
| `reject-tampered-plan` | PASS | 66.930 秒 |
| `deny-self-approval` | PASS | 121.906 秒 |
| `revision-limit-block` | PASS | 98.563 秒 |
| `terminal-state-guard` | PASS | 83.063 秒 |

结果为 6/6，通过率 100%，平均约 103.5 秒/用例。报告记录总 token 数为 1,858,429；该数包含 Agent Engine 上下文统计，不应直接等同于实际计费 token，但反映出 550 行单文件 Skill 的上下文负担值得优化。

该 100% 通过率只能证明模型理解核心规则，不能证明产品已端到端可用：

- 只有 `initialize-plan` 创建了真实文件。
- `cross-session-executor` 明确要求“不要写文件”，只检查是否说出事件顺序。
- 没有 A→B→A 的独立 session 文件接力。
- 没有真实 C 图片任务。
- 没有锁竞争、进程崩溃、租约过期或 Runner 唤醒。
- 没有 Claude、Kimi、Cursor 引擎实测记录。

本轮没有重新消耗模型运行整套 Agent 评测：代码基线未发生变化，且已有完整 iteration-7 报告。本轮重新执行了全部确定性测试与评测配置校验。

## 4. 分项评估

### 4.1 功能与协议完整性：17/20

优点：

- A/B/C 与模型厂商解耦，角色映射可配置。
- 事件、产物和状态分离，完成条件不依赖自然语言。
- 状态机覆盖规划、执行、审查、返工、阻塞和重开。
- 支持 `previous_event_id`、`caused_by`、版本化产物和 SHA-256。
- 默认 90 分门槛、100 分量表和最多 3 次返工已经明确。
- 并行子任务具有 `subtask_id` 和 owner 约束。

扣分：

- 成本路由和预算只有规则，没有可执行调度器。
- Runner、轮询和客户端启动只是描述。
- 没有正式 schema 版本迁移机制。
- `control.md` 的多个声明字段没有进入强制校验。

### 4.2 正确性、并发与恢复：15/20

优点：

- 22 项协议测试覆盖重复事件、非法因果、状态错误、占位模型、路径穿越、自审批、低分通过、返工超限和终态重开。
- 候选事件校验不会修改 `coordination.md`。
- 能检测分叉、未来 `caused_by` 和符号链接逃逸。
- 相同输入重复执行结果一致。

扣分：

- 加锁、原子重命名、追加和解锁由 Agent 自行实现，没有统一发布器。
- 没有两个进程同时抢占任务的压力测试。
- 没有在“写产物后、追加事件前”崩溃的恢复测试。
- 没有租约过期、Heartbeat 丢失和 `TASK_RECLAIMED` 的真实时间测试。
- 当前历史样例本身不能通过完整验证。

### 4.3 安全与权限边界：9/15

已实现：

- 角色事件授权。
- 自审批拦截。
- 相对路径穿越和 symlink 逃逸拦截。
- `allowed_paths` / `forbidden_paths` 对声明产物的检查。
- 哈希失配拒绝和终态保护。

关键缺口：

- Agent 可以修改未申报文件；验证器只检查事件中列出的 artifacts。
- `allow_network`、`allow_external_messages`、`allow_destructive_actions` 和 `require_human_approval_for` 未由验证器或运行沙箱强制执行。
- `budget.max_cost_weight` 和能力路由没有执行器。
- `actor.role`、`provider`、`client`、`model` 是自报字段，没有身份签名或客户端认证。
- `required_tests_passed: true` 和 `required_evidence_present: true` 是布尔声明，验证器没有独立执行测试或检查证据语义。
- 没有明确威胁模型：可信本地 Agent 和不可信远程 Agent 的安全承诺尚未分开。

### 4.4 跨模型与跨客户端互操作：8/15

已证明：

- 文件协议不依赖厂商 API。
- 新 session 能从磁盘恢复状态语义。
- 客户端只要能读取文件、运行 Python、写入共享目录，理论上均可参与。

未证明：

- Claude Code、Codex、Kimi、Cursor 尚无统一兼容性测试表。
- Cursor 的模型来自 Cursor 客户端，但缺少专用启动和恢复说明。
- 没有客户端 adapter，Runner 不知道各客户端的启动命令、退出码和 session 语义。
- 没有跨机器共享文件系统、网络文件锁或时钟偏移测试。
- C 的视觉产物、图片哈希和多模态审查没有端到端证据。

### 4.5 易用性与可观察性：8/20

当前用户路径：

1. 克隆仓库。
2. 阅读 550 行 `SKILL.md`。
3. 手工创建任务目录和 `control.md`。
4. 要求 Agent 手工构造事件 JSON。
5. 手工处理锁、哈希、追加和临时文件。
6. 用户自己观察状态并启动下一个客户端。

主要问题：

- README 没有客户端安装步骤和完整五分钟 Quick Start。
- 没有 `init`、`status`、`next`、`claim`、`publish`、`watch`、`doctor` 命令。
- 没有事件和 control 模板生成器。
- 没有面向人的状态摘要；用户需要阅读 JSON 日志。
- 没有结构化 JSON 输出供 Runner 消费。
- 错误信息虽然详细，但缺少机器可读错误码和建议修复命令。
- 示例和核心源码、历史任务、测试夹具、CSV 演示工具混在同一层级。

### 4.6 工程化、发布与维护：4/10

已有：

- Git 仓库与公开 GitHub 地址。
- README、Skill、验证器、测试夹具和 Agent eval。
- Python 标准库实现，环境依赖少。

缺少：

- `pyproject.toml` 或其他正式安装入口。
- GitHub Actions。
- LICENSE。
- CHANGELOG、CONTRIBUTING、SECURITY。
- 语义版本、release tag 和兼容策略。
- 独立 `src/`、`tests/`、`examples/`、`docs/` 结构。
- Python 版本矩阵、macOS/Linux 矩阵和覆盖率门槛。
- 配置 schema 与事件 schema 的版本化文件。

## 5. 用户场景可用性判断

| 场景 | 当前判断 | 原因 |
|---|---|---|
| 技术用户手动启动 A、B、A | 条件可用 | 协议成立，但操作繁琐 |
| 同机 Claude/Codex/Kimi 共享目录 | 条件可用 | 依赖人工启动和可信客户端 |
| Cursor 中的模型参与 | 条件可用 | 能读写目录即可，但无专用适配与实测 |
| 跨 session 恢复 | 基本可用 | 磁盘状态和事件链存在 |
| B 自动知道并立即响应 A | 不可用 | 能判断 `PLAN_READY`，但没有自动唤醒 Runner |
| B/C 并行执行 | 协议可描述，工程未证明 | 无并发发布和锁压力测试 |
| 自动三轮返工 | 协议可描述，工程未闭环 | 无 Runner 自动调度循环 |
| 无人值守生产流程 | 不可用 | 权限、副作用、凭据和恢复未形成强约束 |
| 不可信 Agent 协作 | 不可用 | 角色可自报，缺少沙箱和身份认证 |
| 非技术用户开箱使用 | 不可用 | 缺少 CLI、模板和可视化状态 |

## 6. 风险登记表

| ID | 严重度 | 风险 | 影响 | 处理方向 |
|---|---|---|---|---|
| R-01 | Critical | 没有 Runner 自动唤醒下一 Agent | 原始核心目标只完成一半 | 实现 adapter + watch + dispatch |
| R-02 | Critical | 事件发布、加锁和追加由 Agent 手工完成 | 竞态、日志损坏、重复副作用 | 提供唯一原子 `publish` API/CLI |
| R-03 | High | 权限配置无法约束实际文件修改和网络副作用 | 声明安全与实际安全不一致 | 沙箱、worktree diff、审批钩子 |
| R-04 | High | 缺少真实 A→B/C→A 端到端测试 | 6/6 可能高估产品可用性 | 增加跨进程和真实客户端 eval |
| R-05 | High | 两个仓库任务样例校验失败 | 首次体验差，无法区分预期失败 | 黄金样例与 legacy 样例分离 |
| R-06 | High | 角色身份完全自报 | B 可伪装成 A | 明确信任模型；可选事件签名 |
| R-07 | Medium | YAML 只解析自定义子集 | 合法 YAML 可能被静默忽略 | 正式 schema 和严格解析器 |
| R-08 | Medium | 质量证据是布尔自报 | 可虚假批准 | 证据清单、命令结果和审查重跑 |
| R-09 | Medium | 单文件 Skill 550 行 | 上下文成本高、难维护 | 拆分 references 和 quick path |
| R-10 | Medium | 无 CI、版本和 License | 回归风险与复用法律不确定 | 工程化发布基线 |
| R-11 | Medium | 绝对产物路径跨机器不稳定 | 共享任务不可移植 | workspace URI / mount 映射 |
| R-12 | Low | CSV 示例工具混入核心目录 | 仓库边界不清晰 | 移至 `examples/` 或独立 fixture |

## 7. 95 分目标架构

建议将工程拆为五层：

```text
用户 / Agent
    ↓
agent_dealer CLI
    ├── init / doctor / status / next
    ├── artifact add / event prepare / publish
    └── watch / run
    ↓
协议核心库
    ├── schema + state machine
    ├── policy + quality gate
    ├── lock + lease + append journal
    └── hash + path + evidence
    ↓
共享任务目录
    ├── control.yaml
    ├── coordination.md
    └── immutable artifacts
    ↓
Runner 与客户端 adapters
    ├── manual
    ├── codex
    ├── claude-code
    ├── kimi
    └── cursor/manual-command
    ↓
客户端自身沙箱 / worktree / 用户审批
```

原则：

- Agent 不再直接拼接 `coordination.md`；所有发布都通过核心库。
- `validate` 与 `publish` 使用同一套 parser 和 policy，避免双重实现。
- Runner 只唤醒和监控，不伪造业务审查。
- 默认威胁模型为“可信本地客户端”；如果启用不可信远程 Agent，必须同时启用沙箱和签名。
- 保留手动模式，且不要求 API key；自动 API 模式作为可选 adapter。

## 8. 95 分硬性验收门槛

必须全部满足，不允许用其他加分抵消：

### 8.1 功能

- 提供 `agent_dealer init/status/next/claim/publish/watch/doctor`。
- 新用户从 clone 到创建首个 `PLAN_READY` 不超过 5 条命令。
- `watch` 能依据合法事件通知或启动下一角色。
- 完整支持 A→B→A、A→B/C→A、返工、阻塞和人工重开。

### 8.2 正确性与恢复

- 核心单元测试不少于 100 项。
- 核心库分支覆盖率不低于 90%。
- 两个并发发布者测试 100 次，不能产生静默覆盖或双重认领。
- 在发布的每个关键故障点注入崩溃，重启后均能恢复或明确 `BLOCKED`。
- 同一 E2E 流程连续执行 10 次，结果一致且无残留锁。
- 仓库所有非 `expected-failure` 示例必须通过 `agent_dealer doctor`。

### 8.3 安全

- 明确发布威胁模型和安全边界。
- 所有外部副作用在执行前经过显式授权策略。
- 能检测实际变更文件超出任务允许范围，不能只检查申报 artifacts。
- 路径穿越、symlink、事件注入、角色冒充、哈希篡改、密钥泄露测试全部通过。
- CI 中执行秘密扫描和依赖/静态安全检查。
- 不可信 Agent 模式必须使用沙箱；否则产品明确拒绝启动该模式。

### 8.4 跨客户端

- 至少完成以下真实 smoke matrix，并保存版本、命令和证据：
  - Claude Code(A) → Codex(B) → Claude Code(A)
  - Codex(A) → Kimi(B) → Codex(A)
  - Codex(A) → C 多模态执行者 → Codex(A)
  - Cursor 客户端中的任一模型作为 B
- 每组至少执行成功 3 次。
- 客户端退出、超时和非零退出码能被 Runner 正确记录。

### 8.5 易用性

- README 有安装、五分钟 Quick Start、各客户端提示和故障排查。
- 提供合法黄金示例，复制后可直接运行。
- `status` 同时支持人类文本和 `--json`。
- 错误包含稳定错误码、原因和下一步修复建议。
- 对 3 名未参与开发的技术用户做任务测试：首次成功率 100%，中位完成时间不超过 10 分钟。

### 8.6 工程化

- GitHub Actions 在受支持 Python 和操作系统矩阵上全绿。
- 有 `pyproject.toml`、LICENSE、SECURITY、CONTRIBUTING、CHANGELOG。
- 发布语义版本和 GitHub Release。
- protocol/schema 版本有向后兼容和迁移测试。
- `skill-up` 完整评测不少于 15 个场景，全部通过；其中真实文件/E2E 用例不少于 10 个。

## 9. 分阶段改进方案

### 阶段 P0：仓库与首次体验基线

目标分：61 → 68。

#### P0-01：重构仓库目录

建议结构：

```text
src/agent_dealer/
tests/
  unit/
  integration/
  fixtures/
examples/
  quickstart/
  legacy-expected-failure/
docs/
evals/
SKILL.md
README.md
pyproject.toml
```

执行：

1. 把协议验证器迁入 `src/agent_dealer/`。
2. 把协议夹具迁入 `tests/fixtures/`。
3. 把 CSV 工具和历史任务迁入 `examples/`。
4. 给预期失败样例写 `expected-errors.json`，避免被误认为坏仓库。
5. 新建一个从 `TASK_CREATED` 到 `REVIEW_APPROVED` 全部校验通过的 `examples/quickstart`。

验收：

```bash
python -m agent_dealer doctor examples/quickstart
python -m unittest discover -s tests
```

#### P0-02：补齐工程文件

新增：

- `pyproject.toml`
- `LICENSE`
- `CHANGELOG.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `.github/workflows/ci.yml`

验收：全新虚拟环境可安装，CI 可重复运行全部确定性测试。

#### P0-03：重写 Quick Start

README 首屏只保留：定位、安装、五条命令、支持矩阵和安全边界。把详细协议拆入：

- `docs/protocol.md`
- `docs/security.md`
- `docs/client-guides/claude-code.md`
- `docs/client-guides/codex.md`
- `docs/client-guides/kimi.md`
- `docs/client-guides/cursor.md`

`SKILL.md` 保留必须执行的工作流，详细 schema、事件表和示例移入 `references/`，目标控制在 300 行以内。

### 阶段 P1：核心 CLI 与原子发布

目标分：68 → 82。

#### P1-01：正式配置和事件模型

实现：

- `ControlConfig`
- `AgentIdentity`
- `Event`
- `ArtifactRef`
- `QualityGate`
- `Subtask`

要求：严格拒绝未知或类型错误的关键字段；schema 带版本；解析和序列化可 round-trip。

#### P1-02：一键初始化和诊断

命令：

```bash
agent_dealer init task-001 --title "..." --planner A --executor B --reviewer A
agent_dealer doctor tasks/task-001
agent_dealer status tasks/task-001
agent_dealer status tasks/task-001 --json
agent_dealer next tasks/task-001 --role B
```

`init` 负责目录、默认配置、首事件和模板；`doctor` 负责环境、权限、schema、事件链、哈希、锁和客户端可用性。

#### P1-03：唯一事件发布入口

命令：

```bash
agent_dealer event prepare ...
agent_dealer publish tasks/task-001 tmp/event.json
```

`publish` 必须在一个实现中完成：

1. 原子获取目录锁。
2. 重新读取最新事件。
3. 验证候选事件。
4. 固化版本化产物和哈希。
5. 一次追加完整事件。
6. fsync 或等价持久化。
7. 发布后复核。
8. 释放锁。

Agent 不再直接编辑 `coordination.md`。

#### P1-04：机器可读错误

定义稳定错误码，例如：

- `MMAC-E101_INVALID_STATE`
- `MMAC-E201_UNAUTHORIZED_ROLE`
- `MMAC-E301_HASH_MISMATCH`
- `MMAC-E401_LOCK_CONFLICT`
- `MMAC-E501_APPROVAL_REQUIRED`

CLI 文本输出包含修复建议，`--json` 输出稳定结构。

### 阶段 P2：Runner、并发、恢复与安全闭环

目标分：82 → 91。

#### P2-01：Runner 和 adapter 接口

定义 adapter：

```text
detect() -> capability/status
build_command(task, role, prompt) -> argv
start() -> run_id
poll(run_id) -> state
stop(run_id) -> result
```

先实现：

- `manual`：只通知并输出可复制提示词。
- `command`：运行用户配置的本地命令，不持有 API key。
- `codex`、`claude-code`：在 CLI 可用时生成受控命令。
- Kimi 和 Cursor 首期可通过 `command`/manual adapter 接入，避免假设不存在的稳定 CLI。

#### P2-02：监听与调度循环

```bash
agent_dealer watch tasks/task-001 --adapter-config adapters.yaml
```

要求：

- 文件通知加定时全量校验。
- 基于 `event_id`/`caused_by` 去重。
- 只在事件合法、recipient 匹配、依赖满足时启动。
- 状态持久化，Runner 重启不重复启动已处理事件。
- 三次返工后自动停止并通知人类。

#### P2-03：租约和崩溃恢复

实现并测试：

- 原子 claim。
- Heartbeat。
- lease expiry。
- `TASK_RECLAIMED`。
- orphan tmp/artifact 清理策略。
- 不可逆副作用的幂等键和禁止自动重试规则。

#### P2-04：安全执行边界

执行：

1. 在任务开始时保存 Git/worktree 基线。
2. 在 `WORK_READY` 时比较实际变更与 `allowed_paths`。
3. 网络、外部消息、发布、购买和破坏性动作走审批钩子。
4. 日志对密钥和 token 做脱敏扫描。
5. 定义 `trusted-local` 与 `sandboxed-untrusted` 两种 profile。
6. 对高风险模式提供可选事件签名；至少保证 human/coordinator 事件不能由普通 adapter 伪造。

### 阶段 P3：真实矩阵、性能和正式发布

目标分：91 → 95。

#### P3-01：扩展确定性测试

新增至少这些测试组：

- schema round-trip 和迁移。
- 100 次并发发布。
- 所有发布故障点的 crash injection。
- lease/heartbeat/reclaim。
- 实际变更路径超权。
- 审批和副作用。
- Runner 去重和重启。
- 多子任务依赖图。
- 图片产物哈希和 review。
- 终态 reopen 与新任务分流。

#### P3-02：扩展 `skill-up` 行为评测

把 6 个用例扩展到至少 15 个，其中 10 个必须操作真实文件：

1. A 初始化并发布方案。
2. 独立 B session 恢复并执行。
3. A 独立审查并批准。
4. B/C 并行子任务。
5. C 视觉交付。
6. 哈希篡改。
7. 自审批。
8. 路径越权。
9. 并发 claim。
10. lease reclaim。
11. Runner 重启去重。
12. 第三次返工阻塞。
13. 终态保护。
14. 配置降级攻击。
15. 新旧 schema 迁移。

规则型 judge 负责结构、文件、退出码和哈希；只有视觉质量或开放式方案质量才使用 `agent_judge`。

#### P3-03：真实客户端 smoke matrix

每次运行记录：

- 客户端及版本。
- 模型 ID。
- 启动命令或人工步骤。
- 任务事件链。
- 产物哈希。
- 总耗时和失败原因。
- 是否需要 API key；手动客户端模式应为否。

#### P3-04：发布 1.0 前候选版本

发布 `v0.1.0` 或 `v0.9.0`，暂不直接宣称 1.0。完成 30 天试用和真实问题修复后，再决定 1.0。

## 10. 文件级执行清单

| ID | 文件/目录 | 动作 | 依赖 | 完成定义 |
|---|---|---|---|---|
| T-01 | `pyproject.toml` | 建立可安装包和 `agent_dealer` entry point | 无 | 新环境安装成功 |
| T-02 | `src/agent_dealer/models.py` | 配置与事件数据模型 | T-01 | round-trip 测试通过 |
| T-03 | `src/agent_dealer/schema/` | 协议 schema 与版本 | T-02 | 非法字段拒绝、迁移可测 |
| T-04 | `src/agent_dealer/validator.py` | 迁移并拆分现有验证器 | T-02 | 旧 22 项测试不回归 |
| T-05 | `src/agent_dealer/store.py` | 锁、日志和原子发布 | T-02/T-04 | 并发与 crash 测试通过 |
| T-06 | `src/agent_dealer/cli.py` | init/status/next/publish/doctor | T-03/T-05 | Quick Start ≤5 命令 |
| T-07 | `src/agent_dealer/runner.py` | watch、调度和持久去重 | T-05/T-06 | 重启不重复执行 |
| T-08 | `src/agent_dealer/adapters/` | manual/command/client adapters | T-07 | smoke matrix 通过 |
| T-09 | `src/agent_dealer/security.py` | 路径、diff、审批、脱敏 | T-04/T-06 | 安全用例全绿 |
| T-10 | `tests/unit/` | 核心单元测试 | T-02~T-09 | ≥100 项，覆盖率 ≥90% |
| T-11 | `tests/integration/` | 并发、恢复、Runner E2E | T-05~T-09 | 10 次重复稳定 |
| T-12 | `examples/quickstart/` | 黄金流程 | T-06 | `doctor` 0 错误 |
| T-13 | `examples/legacy-expected-failure/` | 迁移历史样例 | T-04 | 错误与清单一致 |
| T-14 | `evals/` | 扩展到 ≥15 场景 | T-06~T-09 | 全量通过 |
| T-15 | `.github/workflows/` | CI、覆盖率、安全扫描 | T-10/T-11 | 所有矩阵全绿 |
| T-16 | `README.md`、`docs/` | Quick Start 和客户端指南 | T-06/T-08 | 用户测试达标 |
| T-17 | 根目录治理文件 | License/Security/Changelog 等 | 无 | 发布检查通过 |

## 11. 推荐执行顺序

严格按以下顺序推进，避免先做 Runner 后返工底层协议：

1. 冻结 protocol v1 的事件语义，建立 schema 和迁移原则。
2. 重构目录，但保持现有 22 项测试持续通过。
3. 实现 `agent_dealer init/doctor/status`，先解决首次体验。
4. 实现唯一 `publish` 入口，禁止 Agent 手工追加日志。
5. 完成并发锁和 crash recovery 测试。
6. 实现 `manual` 与 `command` adapter。
7. 实现 Runner 的 watch、去重、租约和重启恢复。
8. 加入实际文件 diff、安全 profile 和审批钩子。
9. 扩展端到端和 `skill-up` 评测。
10. 执行 Claude/Codex/Kimi/Cursor smoke matrix。
11. 做三名新用户可用性测试。
12. 达到第 8 节全部硬门槛后，重新评分；只有总分 ≥95 且无 Critical/High 未关闭项才标记 95。

## 12. 每阶段验证命令建议

```bash
# 静态与单元测试
python -m compileall src tests
python -m unittest discover -s tests/unit

# 集成测试
python -m unittest discover -s tests/integration

# 覆盖率
coverage run -m unittest discover -s tests
coverage report --fail-under=90

# 工程自检
agent_dealer doctor examples/quickstart
agent_dealer status examples/quickstart --json

# Skill 配置与行为评测
skill-up validate evals/eval.yaml
skill-up run evals/eval.yaml --format json --format html

# 发布前检查
git diff --check
python -m build
python -m twine check dist/*
```

如果项目坚持“Python 标准库零依赖”，覆盖率和构建工具只放入开发依赖，不进入运行时依赖。

## 13. 评分提升预测

| 阶段 | 预计得分 | 主要新增证据 | 不得提前计分的内容 |
|---|---:|---|---|
| 当前 | 61 | 22 项协议测试、6 项行为评测 | Runner、真实客户端、安全沙箱 |
| P0 完成 | 68 | 可安装、CI、黄金样例、清晰文档 | CLI 原子发布、自动调度 |
| P1 完成 | 82 | 核心库、CLI、schema、原子 publish | 自动跨客户端闭环 |
| P2 完成 | 91 | Runner、并发恢复、安全 profile | 真实矩阵和用户测试 |
| P3 完成 | 95 | ≥15 eval、真实客户端矩阵、可用性与发布证据 | 未实际运行的厂商组合 |

## 14. 最终结论

该工程的方向正确，最有价值的资产是厂商无关事件协议和已经可执行的严格验证器。它已经超过“只有一份协作提示词”的阶段，但尚未达到“用户安装后，多个客户端自动可靠协作”的产品状态。

当前 61 分不是协议失败，而是对产品化证据不足的保守评分。最优改进路径是：

```text
黄金样例与工程治理
→ 核心库和 CLI
→ 原子 publish
→ Runner 与恢复
→ 安全闭环
→ 真实客户端矩阵
→ 95 分验收
```

在完成 P1 前，不建议继续增加更多事件类型；在完成 P2 前，不建议宣传“自动多 Agent”；在完成 P3 的真实矩阵前，不建议宣传“已验证兼容所有客户端”。

达到 95 分后的合理定位应是：

> 一个面向可信本地或受沙箱约束 Agent 的、可安装、可审计、可恢复、支持多客户端接力的共享目录协作运行时；手动模式不需要 API key，自动 API adapter 按需使用各厂商凭据。
