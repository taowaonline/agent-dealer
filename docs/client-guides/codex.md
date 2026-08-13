# Codex 客户端指南

## 启动

```bash
codex -a never -s workspace-write   # 工作区可写、免逐条审批
```

首条消息使用统一启动提示（见 claude-code.md）。

## 注意

- Codex TUI 的"轮询"只在工作回合内有效；回合结束后需要外部 Runner 或人工唤醒。
  这正是 `collab watch` 的用武之地。
- `actor.model` 填真实模型 ID（如 `gpt-5.6-luna`），不要用占位符。
- 审查者角色请使用高推理档位；低成本模型适合执行角色。
