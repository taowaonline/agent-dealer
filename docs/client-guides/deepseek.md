# DeepSeek 客户端指南

DeepSeek 模型可作为角色 B（通用执行者）或 A（规划/审查）参与协作。

## 接入方式

- 通过支持 DeepSeek 的客户端接入（如 Claude Code 配置 DeepSeek 兼容端点，或任何
  能读写共享目录 + 运行 Python 的终端客户端）。
- 首条消息使用统一启动提示（见 claude-code.md）。

## 事件与身份

- `actor.model` 填真实模型 ID（如 `deepseek-chat` / `deepseek-reasoner`），不要用占位符。
- `actor.provider` 填 `deepseek`，`actor.client` 填实际使用的客户端名。

## 档位说明

- reasoning 模型（deepseek-reasoner 等）的原生推理深度参数以 DeepSeek 官方文档为准，
  本协议只透传 `MMAC_MODEL` / `MMAC_EFFORT` / `MMAC_THINKING` / `MMAC_PERMISSION_MODE`
  与 argv 占位符 `{model} {effort} {thinking} {permission_mode}`，不编造客户端参数。

## Runner adapter 占位符

command adapter 的 argv 支持 `{task_dir} {role} {model} {effort} {thinking}
{permission_mode}` 占位符（档位来自任务 control.md）；无独立 CLI 时用
`{"B": {"type": "manual"}}` 人工接力。
