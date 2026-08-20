# agent-dealer-cli

[![npm version](https://img.shields.io/npm/v/@taowaonline%2Fagent-dealer)](https://www.npmjs.com/package/@taowaonline/agent-dealer)

**简体中文** · [English](#english)

<a id="简体中文"></a>

厂商无关的跨模型 Agent 协作运行时。Claude Code、Codex、Kimi、Cursor 或本地模型不需要共享厂商会话，只通过共享目录里的结构化事件、版本化产物和 SHA-256 哈希即可完成规划、执行、审查与返工。

**当前状态：Developer Preview（v0.5.0）。** 默认威胁模型为可信本地客户端（见 [SECURITY.md](SECURITY.md)）。

## 安装

npm 一行安装（零 Node 依赖的 wrapper，自动定位系统 Python ≥ 3.9，无需 pip）：

```bash
npm install -g @taowaonline/agent-dealer
agent-dealer-cli --version
```

或从源码安装（运行时零第三方依赖，Python ≥ 3.9）：

```bash
python -m venv .venv && .venv/bin/pip install -e .
```

要在任意目录、其他终端和新 session 中直接使用，执行一次：

```bash
./scripts/install-global.sh
agent-dealer-cli --version
```

默认安装到 `~/.local/share/agent_dealer/venv`，并在 `~/.local/bin` 创建
主命令 `agent-dealer-cli`，并保留旧版兼容命令 `agent_dealer`、`collab`。若 shell 找不到命令，把
`~/.local/bin` 加入 `PATH`。更新代码后重新运行安装脚本即可升级全局命令。

## 五分钟 Quick Start

```bash
# 0. 探测本机已安装的模型客户端及可用模型档位（gpt-5.6-sol high、glm-5.3 max 等）
agent-dealer-cli models          # 首次可先 agent-dealer-cli models --init 生成模型目录模板并编辑

# 1. 创建任务（目录、control.md、TASK_CREATED 事件一步到位）；
#    档位：--effort low|medium|high|max、--thinking on|off、
#    --permission-mode yolo|confirm（默认 yolo）、--role-config 角色:键=值 按角色覆盖
agent-dealer-cli init task-demo-001 --title "我的第一个协作任务" --model kimi-k2.5 \
  --effort high --thinking on --role-config A:model=gpt-5.6-luna

# 2. 诊断任务健康度
agent-dealer-cli doctor tasks/task-demo-001

# 3. 查看下一步该谁行动
agent-dealer-cli next tasks/task-demo-001

# 4. 准备并预校验一个事件（PLANNING_STARTED）
agent-dealer-cli event prepare tasks/task-demo-001 --type PLANNING_STARTED --role A --model gpt-5.6-luna --out tasks/task-demo-001/tmp/e.json
agent-dealer-cli publish --dry-run tasks/task-demo-001 tasks/task-demo-001/tmp/e.json

# 5. 原子发布（锁 + 预校验 + 追加 + 复核，一次完成）
agent-dealer-cli publish tasks/task-demo-001 tasks/task-demo-001/tmp/e.json --instance-id my-session

# 6. 任务报告：各 agent 贡献、评审评价与遗留 TODO（--json 机器可读）
agent-dealer-cli report tasks/task-demo-001
```

一个从 `TASK_CREATED` 到 `REVIEW_APPROVED` 全部校验通过的完整样例在 [`examples/quickstart`](examples/quickstart)：

```bash
agent-dealer-cli doctor examples/quickstart
```

## 角色与流程

- **A**：架构师与审查者——规划、拆分任务、严格审查（不接受执行者自评分）。
- **B**：通用执行者——代码、测试、文档。
- **C**：视觉与多模态执行者——图片与多模态任务。

```text
CREATED → PLANNING → PLAN_READY → CLAIMED → EXECUTING → WORK_READY → REVIEWING
        → APPROVED（终态）/ REVISION_REQUIRED（≤3 次返工）/ BLOCKED
```

完整协议见 [`SKILL.md`](SKILL.md)（Agent 必读）与 [`docs/protocol.md`](docs/protocol.md)（人类参考）。

## 客户端指南

| 客户端 | 指南 |
| --- | --- |
| Claude Code | [docs/client-guides/claude-code.md](docs/client-guides/claude-code.md) |
| Codex | [docs/client-guides/codex.md](docs/client-guides/codex.md) |
| Kimi | [docs/client-guides/kimi.md](docs/client-guides/kimi.md) |
| DeepSeek | [docs/client-guides/deepseek.md](docs/client-guides/deepseek.md) |
| z.ai (GLM) | [docs/client-guides/zai.md](docs/client-guides/zai.md) |
| Cursor | [docs/client-guides/cursor.md](docs/client-guides/cursor.md) |

手动模式不需要为本项目配置 API key——各客户端使用自己的登录状态。

## Runner（可选）

```bash
# adapters.json: {"B": {"type": "manual"}}
agent-dealer-cli watch tasks/task-demo-001 --adapters adapters.json
```

Runner 只负责唤醒与监控，不替 Agent 伪造审查。详见 [docs/protocol.md](docs/protocol.md#runner)。

## 故障排查

| 症状 | 处理 |
| --- | --- |
| `MMAC-E401_LOCK_CONFLICT` | 读 `locks/coordination.lock/owner.json`；租约过期可安全接管 |
| `MMAC-E301_HASH_MISMATCH` | 重算哈希 `shasum -a 256 <file>`；合法演进会被 supersede 规则降级为告警 |
| 历史任务校验报错 | 在任务目录写 `expected-warnings.json` 显式 grandfather（见 `tasks/task-20260810-001/`） |
| 校验器全部错误码 | [docs/protocol.md#错误码](docs/protocol.md) |

## 测试

```bash
python -m unittest discover -s tests        # 260 项核心测试
python -m unittest tools.csv2json.tests.test_csv2json  # 22 项示例测试
python -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures  # 22 项兼容测试
skill-up validate evals/eval.yaml           # Agent 行为评测配置
```

当前共 304 项确定性测试通过；核心包覆盖率 93%。

## 目录结构

```text
src/agent_dealer/   核心库与 CLI
src/agent_collaboration/   旧 Python 导入兼容层（deprecated）
tests/                     unit / integration / fixtures
examples/quickstart/       黄金样例（doctor 零错误）
examples/legacy-expected-failure/  故意失败样例（expected-errors.json 清单）
docs/                      协议、安全、客户端指南
references/                事件 schema、状态机、rubric 速查
tasks/                     真实协作任务工作区
evals/                     skill-up Agent 行为评测
```

---

# English

**English** · [简体中文](#简体中文)

A vendor-neutral runtime for cross-model agent collaboration. Claude Code, Codex, Kimi, Cursor, or local models never share a vendor session: they plan, execute, review, and rework purely through structured events, versioned artifacts, and SHA-256 hashes in a shared directory.

**Status: Developer Preview (v0.5.0).** The default threat model is trusted local clients (see [SECURITY.md](SECURITY.md)).

## Installation

One line via npm (a zero-dependency Node wrapper that locates system Python ≥ 3.9 — no pip needed):

```bash
npm install -g @taowaonline/agent-dealer
agent-dealer-cli --version
```

Or install from source (zero third-party runtime dependencies, Python ≥ 3.9):

```bash
python -m venv .venv && .venv/bin/pip install -e .
```

To use the command from any directory, other terminals, and new sessions, run once:

```bash
./scripts/install-global.sh
agent-dealer-cli --version
```

This installs to `~/.local/share/agent_dealer/venv` and creates the primary command
`agent-dealer-cli` in `~/.local/bin`, keeping the legacy aliases `agent_dealer` and `collab`.
If your shell cannot find the command, add `~/.local/bin` to your `PATH`.
Re-run the script after updating the code to upgrade the global command.

## Five-minute Quick Start

```bash
# 0. Probe installed model clients and available model tiers (e.g. gpt-5.6-sol high, glm-5.3 max)
agent-dealer-cli models          # first run: agent-dealer-cli models --init opens the interactive wizard

# 1. Create a task (directory, control.md, and the TASK_CREATED event in one step);
#    tiers: --effort low|medium|high|max, --thinking on|off,
#    --permission-mode yolo|confirm (default yolo), --role-config ROLE:key=value per-role overrides
agent-dealer-cli init task-demo-001 --title "My first collaboration task" --model kimi-k2.5 \
  --effort high --thinking on --role-config A:model=gpt-5.6-luna

# 2. Check task health
agent-dealer-cli doctor tasks/task-demo-001

# 3. See who should act next
agent-dealer-cli next tasks/task-demo-001

# 4. Prepare and pre-validate an event (PLANNING_STARTED)
agent-dealer-cli event prepare tasks/task-demo-001 --type PLANNING_STARTED --role A --model gpt-5.6-luna --out tasks/task-demo-001/tmp/e.json
agent-dealer-cli publish --dry-run tasks/task-demo-001 tasks/task-demo-001/tmp/e.json

# 5. Atomic publish (lock + pre-validation + append + re-check, all in one)
agent-dealer-cli publish tasks/task-demo-001 tasks/task-demo-001/tmp/e.json --instance-id my-session

# 6. Task report: per-agent contributions, review verdicts, and leftover TODOs (--json for machine output)
agent-dealer-cli report tasks/task-demo-001
```

A complete sample flowing from `TASK_CREATED` to `REVIEW_APPROVED` with every check passing lives in [`examples/quickstart`](examples/quickstart):

```bash
agent-dealer-cli doctor examples/quickstart
```

## Roles & Workflow

- **A** — architect & reviewer: planning, task decomposition, strict review (self-ratings from executors are never accepted).
- **B** — general executor: code, tests, documentation.
- **C** — visual & multimodal executor: image and multimodal tasks.

```text
CREATED → PLANNING → PLAN_READY → CLAIMED → EXECUTING → WORK_READY → REVIEWING
        → APPROVED (terminal) / REVISION_REQUIRED (≤3 rework rounds) / BLOCKED
```

Full protocol: [`SKILL.md`](SKILL.md) (required reading for agents) and [`docs/protocol.md`](docs/protocol.md) (human reference).

## Client Guides

| Client | Guide |
| --- | --- |
| Claude Code | [docs/client-guides/claude-code.md](docs/client-guides/claude-code.md) |
| Codex | [docs/client-guides/codex.md](docs/client-guides/codex.md) |
| Kimi | [docs/client-guides/kimi.md](docs/client-guides/kimi.md) |
| DeepSeek | [docs/client-guides/deepseek.md](docs/client-guides/deepseek.md) |
| z.ai (GLM) | [docs/client-guides/zai.md](docs/client-guides/zai.md) |
| Cursor | [docs/client-guides/cursor.md](docs/client-guides/cursor.md) |

Manual mode requires no API key for this project — every client uses its own login state.

## Runner (optional)

```bash
# adapters.json: {"B": {"type": "manual"}}
agent-dealer-cli watch tasks/task-demo-001 --adapters adapters.json
```

The Runner only wakes agents and monitors progress; it never fakes reviews on their behalf. See [docs/protocol.md](docs/protocol.md#runner).

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `MMAC-E401_LOCK_CONFLICT` | Read `locks/coordination.lock/owner.json`; an expired lease can be taken over safely |
| `MMAC-E301_HASH_MISMATCH` | Recompute the hash with `shasum -a 256 <file>`; legitimate evolution is downgraded to a warning by the supersede rule |
| Legacy task fails validation | Write an explicit `expected-warnings.json` grandfather in the task directory (see `tasks/task-20260810-001/`) |
| All validator error codes | [docs/protocol.md#错误码](docs/protocol.md) |

## Testing

```bash
python -m unittest discover -s tests        # 260 core tests
python -m unittest tools.csv2json.tests.test_csv2json  # 22 sample tests
python -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures  # 22 compatibility tests
skill-up validate evals/eval.yaml           # agent behavior eval config
```

304 deterministic tests pass in total; core package coverage is 93%.

## Directory Layout

```text
src/agent_dealer/   core library and CLI
src/agent_collaboration/   legacy Python import compat layer (deprecated)
tests/                     unit / integration / fixtures
examples/quickstart/       golden sample (doctor reports zero errors)
examples/legacy-expected-failure/  intentionally failing sample (expected-errors.json manifest)
docs/                      protocol, security, and client guides
references/                event schema, state machine, and rubric quick reference
tasks/                     real collaboration task workspaces
evals/                     skill-up agent behavior evals
```
