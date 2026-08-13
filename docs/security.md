# 安全边界

与 [SECURITY.md](../SECURITY.md) 一致的工程视角说明。

## 两种信任 profile

| profile | 用途 | 强制 |
| --- | --- | --- |
| `trusted-local`（默认） | 同机可信客户端 | 协议校验 + 路径检查 |
| `sandboxed-untrusted` | 不可信/远程 Agent | 沙箱 + 事件签名，缺一拒绝启动（E502） |

## 分层防线

1. **协议层**：角色授权、状态机、质量门、终态保护——由校验器强制执行。
2. **产物层**：SHA-256、版本化、`..` 穿越与 symlink 逃逸拦截、allowed/forbidden paths。
3. **变更层**：基线快照（`security.snapshot_baseline`）+ 变更审计——发现"实际改了
   但没申报"的文件，不只信事件里的 artifacts 列表。
4. **凭据层**：`collab doctor` 内置密钥扫描（AWS key、私钥、token 等模式）；
   `security.redact` 用于日志脱敏。
5. **副作用层**：网络、外部消息、购买、发布、破坏性操作必须命中
   `require_human_approval_for` 人工审批清单；不可逆操作不得自动重试。

## 诚实声明（当前不做）

- 不拦截系统调用——网络/进程约束由客户端自身沙箱执行。
- 不签名事件——`actor` 是自报字段；不可信模式必须外加签名机制。
- 不独立执行测试——`required_tests_passed` 是声明，审查者必须按 SKILL.md §12 独立重跑。
