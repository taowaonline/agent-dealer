# Claude Code 客户端指南

## 启动

在共享项目根目录启动 Claude Code，首条消息使用统一启动提示：

```text
读取 <共享目录>/SKILL.md 和任务 <task-id> 的 control.md、coordination.md。
你当前担任角色 <A|B|C>，实例 ID 为 <instance-id>。
先运行 agent-dealer validate tasks/<task-id>（或 python -m agent-dealer validate）验证协议状态，
只处理发送给该角色且尚未处理的最新事件。
完成一次合法状态转换后写入产物和事件，然后退出。
```

## 建议参数

- 无人值守接力：`claude --permission-mode acceptEdits`（仍有高危操作拦截）。
- 发布事件一律使用 `agent-dealer publish`，不要手工编辑 coordination.md。

## Runner adapter 示例

`adapters.json` 支持 `{task_dir} {role} {model} {effort} {thinking} {permission_mode}`
占位符，档位值来自任务 control.md（init 的 `--effort/--thinking/--permission-mode/--role-config`）：

```json
{
  "A": {"type": "command", "argv": ["claude", "--model", "{model}", "--permission-mode", "acceptEdits", "--print", "{task_dir}"]},
  "B": {"type": "command", "argv": ["claude", "--model", "{model}", "--permission-mode", "acceptEdits", "--print", "{task_dir}"]}
}
```

同时注入环境变量 `MMAC_MODEL` / `MMAC_EFFORT` / `MMAC_THINKING` / `MMAC_PERMISSION_MODE`。

## 恢复

新 session 不依赖聊天上下文：从磁盘读取 control.md + coordination.md 即可恢复全部状态。
