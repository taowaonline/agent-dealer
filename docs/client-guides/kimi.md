# Kimi 客户端指南

## 启动

```bash
kimi   # 在共享项目根目录启动
```

首条消息使用统一启动提示（见 claude-code.md）。

## 能力建议

- kimi-k2.5 具备视觉/多模态能力，适合角色 C，也可作为通用执行者 B。
- 发布事件一律使用 `agent_dealer publish`；事件发布后用 `agent_dealer validate` 自检。
