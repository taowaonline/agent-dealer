# Cursor 客户端指南

Cursor 中的模型没有稳定的独立 CLI，推荐使用 **manual adapter**：

1. Runner 配置：`{"B": {"type": "manual"}}`，`collab watch` 会把接力提示词打印出来。
2. 把提示词粘贴到 Cursor 的 Agent 对话中（确保 Cursor 打开了共享目录作为工作区）。
3. Cursor 中的模型按提示读取 SKILL.md、恢复状态、执行并用 `collab publish` 发布事件
   （Cursor 内终端可直接运行 `collab`，无需额外 API key）。

## 实测状态

当前兼容性基于"能读写目录 + 能运行 Python 即可参与"的协议设计；
Cursor 专属适配器与自动化启动在路线图中（见 docs/full-assessment-and-95-plan-2026-08-11.md P2/P3）。
