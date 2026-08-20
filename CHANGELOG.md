# Changelog

本项目遵循语义版本（SemVer）。

## [0.5.2] - 2026-08-20

### 变更

- 移除 `agent-dealer-cli` 兼容别名（npm bin、pip scripts、install-global.sh），
  唯一命令为 `agent-dealer`；旧版兼容命令仅保留 `agent_dealer`、`collab`。

## [0.5.1] - 2026-08-20

### 变更

- 全局主命令改为 **agent-dealer**：npm bin、pip scripts、CLI prog、文档与
  install-global.sh 统一；`agent-dealer-cli`、`agent_dealer`、`collab` 保留为兼容别名。
- pip 分发名同步改为 `agent-dealer`（Python 模块名仍为 `agent_dealer` 不变）。
- npm 分发名不变：`@taowaonline/agent-dealer`。
- 移除 install-global.sh 中 v0.2.0 时代对 `agent-dealer` 符号链接的历史清理逻辑
  （该命令现为主命令）。

## [0.5.0] - 2026-08-20

### 变更

- 项目与命令更名为 **agent-dealer-cli**：pip 分发名、主命令、skill/plugin 名称统一为
  `agent-dealer-cli`（Python 模块名仍为 `agent_dealer`，`python -m agent_dealer` 不变；
  旧命令 `agent_dealer`、`collab` 保留为兼容别名）。

### 新增

- npm 发行：`npm install -g @taowaonline/agent-dealer`（零 Node 依赖 shim 定位系统 Python ≥ 3.9
  运行包内源码，命令 `agent-dealer-cli`）。
- 客户端注册表扩展：探测覆盖 Claude Code、Codex、Kimi、DeepSeek、z.ai (GLM)、Cursor
  （`cursor-agent`/`cursor`）、Gemini；每客户端支持多候选命令名（如 zai 的 `zai`/`glm`）。
- 模型目录（不预填）：`models --init` 交互式选择本机可用模型（客户端/模型/effort 档位/
  thinking，选完保存到 `~/.agent_dealer/models.json`，`MMAC_MODELS_FILE` 可覆盖路径）；
  或 `models --add client:model[:efforts[:thinking]]` 直接指定（upsert，可多次）。
  `agent-dealer-cli models` 合并显示已装客户端与本机可用模型（如 gpt-5.6-sol high、
  glm-5.3 max）。
- 新增 DeepSeek 与 z.ai (GLM) 客户端指南（`docs/client-guides/`）。

## [0.4.0] - 2026-08-20

### 新增

- `agent_dealer models`：探测本机已安装的模型客户端 CLI 及版本（`--json` 机器可读；
  探测失败降级为 `unknown`，不阻塞）。`doctor` 复用同一探测，输出文案不变。
- 协同 Agent 档位选择：`init --effort {low,medium,high,max}`、`--thinking {on,off}`、
  `--permission-mode {yolo,confirm}`（默认 yolo，自动执行无需确认）、
  `--role-config 角色:键=值`（键：effort/thinking/model）按角色覆盖；全部写入 control.md。
- validator 新增 `agents_detail` 解析与枚举校验（`control-effort-invalid` /
  `control-thinking-invalid` / `control-permission-mode-invalid`）；字段可选，旧 control.md 零影响。
- Runner/command adapter 档位注入：argv 占位符 `{model} {effort} {thinking} {permission_mode}`
  与环境变量 `MMAC_MODEL` / `MMAC_EFFORT` / `MMAC_THINKING` / `MMAC_PERMISSION_MODE`；
  唤醒提示词附带档位行；占位 model 不注入。
- `agent_dealer report`：任务报告——各 agent 的事件/产物贡献、最新评审评分与问题、
  遗留 TODO（未消化的 REVISION_REQUIRED 问题、solo 临时批准待独立复核、BLOCKED 原因）；
  `watch` 到达终态时自动打印报告摘要。

## [0.3.0] - 2026-08-20

### 新增

- 单会话模式（solo）：`agent_dealer init --solo`，一个客户端/模型扮演 planner/executor/reviewer
  全部职责（control.md `workflow.mode: solo`）。
- solo 模式补偿性证据门槛（validator 强制）：`REVIEW_APPROVED` 必须带
  `payload.self_review: true` 与非空 `payload.reproduced_commands`（`solo-review` 错误码）；
  `status` 标注"临时批准"性质。multi 模式行为不变。

## [0.2.1] - 2026-08-13

### 修正

- 按项目命名约定将文档、CLI 帮助、错误提示和全局入口统一为 `agent_dealer`。
- 移除误加的 `agent-dealer` CLI 入口；安装脚本会安全清理此前创建的同名符号链接。
- Codex Skill 的内部机器标识仍为 `agent-dealer`，因为平台只接受小写字母、数字和连字符。

## [0.2.0] - 2026-08-13

### 变更

- 项目、Python 发行包和核心模块更名为 Agent Dealer / `agent_dealer`。
- 全局主命令改为 `agent_dealer`；仅保留旧版 `collab` 兼容命令。
- 保留 `collab` 命令与 `agent_collaboration` Python 包兼容层，便于既有脚本平滑迁移。
- 新增 `scripts/install-global.sh`，无需 API key，可将命令安装到用户级目录并供其他 session 使用。
- 项目和 CLI 对外统一使用 `agent_dealer`。Codex Skill 的机器标识因平台命名规范保留为 `agent-dealer`。

## [0.1.0] - 2026-08-11

首个公开候选版本（Developer Preview）。

### 新增

- `agent_dealer` CLI：`init / doctor / status / next / claim / event prepare / publish / artifact add / validate / watch`。
- 核心库 `agent_collaboration`：严格数据模型（schema v1.0，round-trip）、原子发布（目录锁 + 预校验 + fsync + 回滚）、租约与崩溃恢复、稳定错误码（MMAC-Exxx）。
- 校验器包内核化：事件链、状态机、角色授权、质量门、子任务、哈希、路径安全、symlink 逃逸；新增 legacy grandfather（expected-warnings.json）与 supersede（版本演进）规则；`--json` 机器可读输出。
- Runner 与 adapter 接口：`manual`（人工接力）与 `command`（本地命令）adapter；watch 去重持久化，重启不重复调度。
- 安全模块：基线快照/变更审计、密钥脱敏扫描、trusted-local / sandboxed-untrusted profile。
- 黄金示例 `examples/quickstart`（全链路校验通过）与 legacy 样例 `expected-warnings.json` 机制。
- 治理文件：LICENSE、CHANGELOG、CONTRIBUTING、SECURITY、CI workflow。

### 兼容说明

- `tools/validate.py` 保留为兼容 shim，转发到包内核。
- 历史任务 task-20260810-001/002 的事件链可读；历史占位 model 经 expected-warnings.json 显式降级。
