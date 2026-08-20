# Kimi 客户端指南

## 启动

```bash
kimi   # 在共享项目根目录启动
```

首条消息使用统一启动提示（见 claude-code.md）。

## 能力建议

- kimi-k2.5 具备视觉/多模态能力，适合角色 C，也可作为通用执行者 B。
- 发布事件一律使用 `agent-dealer publish`；事件发布后用 `agent-dealer validate` 自检。

## Runner adapter 占位符

command adapter 的 argv 支持 `{task_dir} {role} {model} {effort} {thinking} {permission_mode}`
占位符（档位来自任务 control.md），并注入 `MMAC_MODEL` / `MMAC_EFFORT` /
`MMAC_THINKING` / `MMAC_PERMISSION_MODE` 环境变量；原生档位参数以 Kimi CLI 文档为准。
