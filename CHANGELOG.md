# Changelog

本项目遵循语义版本（SemVer）。

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
