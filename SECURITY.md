# Security Policy

## 威胁模型

本项目的默认信任模型是 **trusted-local**：参与协作的 Agent 客户端运行在同一台可信机器上，
由同一用户启动，共享同一个文件系统目录。协议的事件链、哈希与权限检查用于防错与审计，
不是对抗恶意 Agent 的安全边界。

提供两种 profile：

| profile | 适用 | 强制要求 |
| --- | --- | --- |
| `trusted-local` | 本机可信客户端（默认） | 协议校验 + 路径检查 |
| `sandboxed-untrusted` | 不可信/远程 Agent | 必须同时启用 OS 级沙箱与事件签名，否则 Runner 拒绝启动（MMAC-E502） |

## 当前安全能力

- 角色事件授权（planner/executor/reviewer 分离，执行者不得自审）。
- 产物 SHA-256 校验、路径穿越与符号链接逃逸拦截、`allowed_paths`/`forbidden_paths` 检查。
- 文件基线快照与变更审计（发现实际修改超出申报范围）。
- 密钥/令牌脱敏扫描（`agent_dealer doctor` 内含）。
- 终态保护、返工上限、人工审批清单（`require_human_approval_for`）。

## 已知边界（诚实声明）

- `actor` 身份为自报字段，无密码学签名（sandboxed-untrusted 模式必须外加签名）。
- `allow_network`、`allow_external_messages` 等声明由客户端自身沙箱执行，本项目不拦截系统调用。
- 质量证据（测试通过等）是事件中的布尔声明，审查者必须按 SKILL.md §12 独立重跑验证。

## 报告漏洞

请通过 GitHub Security Advisory 私密报告，勿在公开 issue 披露细节。
不要在任何事件、产物或 issue 中粘贴真实凭据。
