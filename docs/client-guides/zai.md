# z.ai（GLM）客户端指南

GLM 系列模型（智谱 z.ai）可作为任何角色参与协作；GLM-4.5V 及后续多模态版本
也适合角色 C（视觉/多模态执行者）。

## 接入方式

- 通过支持 z.ai 端点的客户端接入（如 Claude Code 配置 z.ai 兼容端点、GLM Coding Plan 等）。
- 首条消息使用统一启动提示（见 claude-code.md）。

## 事件与身份

- `actor.model` 填真实模型 ID（如 `glm-5.3`、`glm-4.5v`），不要用占位符。
- `actor.provider` 填 `zai`（或 `zhipu`），`actor.client` 填实际使用的客户端名。

## 档位说明

- GLM 的 thinking 开关与 effort 档位（low/medium/high/max）以 z.ai 官方文档为准；
  本协议只透传 `MMAC_MODEL` / `MMAC_EFFORT` / `MMAC_THINKING` / `MMAC_PERMISSION_MODE`
  与 argv 占位符 `{model} {effort} {thinking} {permission_mode}`，不编造客户端参数。
- 模型目录（`agent-dealer-cli models`）显示的各模型可用档位来自
  `~/.agent_dealer/models.json`，按本机订阅实际情况填写。

## Runner adapter 占位符

command adapter 的 argv 支持 `{task_dir} {role} {model} {effort} {thinking}
{permission_mode}` 占位符；无独立 CLI 时用 `{"B": {"type": "manual"}}` 人工接力。
