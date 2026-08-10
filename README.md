# Agent Collaboration

一个厂商无关的多 Agent 协作 Skill。Claude、Codex、Kimi、Cursor 或本地模型可以通过同一个共享目录，在不同客户端、不同 session 之间规划、执行、审查和返工。

它不依赖某家模型的 Agent Team 或会话共享能力。协作状态由只追加事件、版本化产物、SHA-256 哈希和 `control.md` 策略共同维护。

## 核心能力

- A 负责方案和审查，B 负责通用执行，C 负责视觉与多模态执行
- 支持跨模型、跨客户端、跨 session 恢复
- 结构化事件代替不可靠的文末“完成关键字”
- 角色权限、质量门、自审批拦截和终态保护
- 默认 90/100 达标，最多 3 次自动返工
- 产物哈希、事件因果链、路径权限和符号链接逃逸检查
- 候选事件发布前验证，避免污染只追加日志
- 支持并行子任务的认领、完成和汇总审查

## 使用方式

让参与协作的客户端都能读写同一个项目目录，并要求每个 Agent 首先阅读 [`SKILL.md`](SKILL.md)。

例如，对新的 B Agent 说：

> 请阅读本项目的 SKILL.md。你担任 B，从共享目录恢复任务状态，验证 control.md、coordination.md 和所有产物哈希；只处理 recipient 指向 B 且权限允许的任务。发布事件前先运行候选校验。

验证任务事件链：

```bash
python3 tools/validate.py tasks/<task-id>
```

发布新事件前进行只读候选校验：

```bash
python3 tools/validate.py tasks/<task-id> --candidate tasks/<task-id>/tmp/event.json
```

验证器仅使用 Python 标准库。

## 测试

```bash
python3 -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures -v
skill-up validate evals/eval.yaml
skill-up run evals/eval.yaml
```

当前回归结果：22 项协议测试通过，6 项 Agent 行为评测通过。

## API key

手动使用 Claude、Codex、Kimi 或 Cursor 客户端协作时，不需要给这个 Skill 配置 API key，各客户端继续使用自己的登录状态。只有外部 runner 需要直接调用厂商 API 时，才需要在 runner 的安全凭据存储中配置相应密钥；不要把密钥写入协作事件或产物。

