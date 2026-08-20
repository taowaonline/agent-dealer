# Agent Dealer

厂商无关的跨模型 Agent 协作运行时。Claude Code、Codex、Kimi、Cursor 或本地模型不需要共享厂商会话，只通过共享目录里的结构化事件、版本化产物和 SHA-256 哈希即可完成规划、执行、审查与返工。

**当前状态：Developer Preview（v0.2.1）。** 默认威胁模型为可信本地客户端（见 [SECURITY.md](SECURITY.md)）。

## 安装

```bash
python -m venv .venv && .venv/bin/pip install -e .
```

运行时零第三方依赖，Python ≥ 3.9。

要在任意目录、其他终端和新 session 中直接使用，执行一次：

```bash
./scripts/install-global.sh
agent_dealer --version
```

默认安装到 `~/.local/share/agent_dealer/venv`，并在 `~/.local/bin` 创建
主命令 `agent_dealer`，并保留旧版兼容命令 `collab`。若 shell 找不到命令，把
`~/.local/bin` 加入 `PATH`。更新代码后重新运行安装脚本即可升级全局命令。

也可以通过 npm 安装（自动定位系统 Python ≥ 3.9，无需 pip）：

```bash
npm install -g agent-dealer-cli
agent-dealer --version
```

## 五分钟 Quick Start

```bash
# 0. 探测本机已安装的模型客户端及可用模型档位（gpt-5.6-sol high、glm-5.3 max 等）
agent_dealer models          # 首次可先 agent_dealer models --init 生成模型目录模板并编辑

# 1. 创建任务（目录、control.md、TASK_CREATED 事件一步到位）；
#    档位：--effort low|medium|high|max、--thinking on|off、
#    --permission-mode yolo|confirm（默认 yolo）、--role-config 角色:键=值 按角色覆盖
agent_dealer init task-demo-001 --title "我的第一个协作任务" --model kimi-k2.5 \
  --effort high --thinking on --role-config A:model=gpt-5.6-luna

# 2. 诊断任务健康度
agent_dealer doctor tasks/task-demo-001

# 3. 查看下一步该谁行动
agent_dealer next tasks/task-demo-001

# 4. 准备并预校验一个事件（PLANNING_STARTED）
agent_dealer event prepare tasks/task-demo-001 --type PLANNING_STARTED --role A --model gpt-5.6-luna --out tasks/task-demo-001/tmp/e.json
agent_dealer publish --dry-run tasks/task-demo-001 tasks/task-demo-001/tmp/e.json

# 5. 原子发布（锁 + 预校验 + 追加 + 复核，一次完成）
agent_dealer publish tasks/task-demo-001 tasks/task-demo-001/tmp/e.json --instance-id my-session

# 6. 任务报告：各 agent 贡献、评审评价与遗留 TODO（--json 机器可读）
agent_dealer report tasks/task-demo-001
```

一个从 `TASK_CREATED` 到 `REVIEW_APPROVED` 全部校验通过的完整样例在 [`examples/quickstart`](examples/quickstart)：

```bash
agent_dealer doctor examples/quickstart
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
| Cursor | [docs/client-guides/cursor.md](docs/client-guides/cursor.md) |

手动模式不需要为本项目配置 API key——各客户端使用自己的登录状态。

## Runner（可选）

```bash
# adapters.json: {"B": {"type": "manual"}}
agent_dealer watch tasks/task-demo-001 --adapters adapters.json
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
python -m unittest discover -s tests        # 206 项核心测试
python -m unittest tools.csv2json.tests.test_csv2json  # 22 项示例测试
python -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures  # 22 项兼容测试
skill-up validate evals/eval.yaml           # Agent 行为评测配置
```

当前共 250 项确定性测试通过；核心包覆盖率 91%。

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
