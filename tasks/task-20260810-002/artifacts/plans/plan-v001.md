# Plan v001 — task-20260810-002：优化协作协议与校验器

## 目标

基于 task-20260810-001 的真实运行记录，提升 SKILL.md 的协议清晰度与 tools/validate.py 的健壮性，同时保持简单透明、向后兼容。只修改 SKILL.md、tools/validate.py，并新增本任务的方案/执行/审查等协议产物或测试夹具。

## 非目标

- 不修改 task-001 的历史事件、代码、执行记录或审查记录。
- 不引入数据库、消息队列、网络服务、第三方依赖或复杂迁移工具。
- 不改变既有状态机的业务含义、质量门槛或角色职责。

## 已知约束与 task-001 证据

- task-001 中项目交付物使用了相对项目根的 tools/... 路径，而当前协议示例规定任务目录相对路径；校验器若只按任务目录解析会误报历史产物缺失。
- task-001 暴露了 Python 3.9 下缺失类型名导致模块加载失败，说明执行记录必须覆盖声明的兼容版本，校验器和协议文档应明确证据要求。
- 现有校验器主要检查标记、链和哈希，但不严格验证事件 ID 唯一性、JSON 字段类型、状态与事件类型对应关系、caused_by 引用、actor/recipient 权限、路径安全或 SHA-256 格式。

## 方案

### B：协议文档（kimi-k2.5）

仅修改 SKILL.md。明确并统一：

1. 产物路径规则：任务目录内产物使用相对路径；任务目录外项目文件使用绝对路径；为兼容 task-001，校验器对历史相对项目路径采用只读 fallback，并在文档中标记为 legacy。
2. 事件发布后的强制校验顺序：运行 python3 tools/validate.py tasks/<task-id>，失败不得继续；说明锁、临时产物、原子重命名、尾部复读和释放锁。
3. 事件字段、角色映射、真实 model 标识、caused_by、revision_cycle、recipient 与状态/事件类型的约束。
4. 审查证据要求：执行者声明的版本必须由审查者独立重跑；路径基准、哈希和旧任务兼容性必须可复核。
5. 简洁记录兼容 fallback、告警与失败处理，不增加新的基础设施或状态。

### C：校验器（glm-5.2）

仅修改 tools/validate.py，可在 tasks/task-20260810-002/fixtures/ 新增小型协议夹具与在执行记录中引用。保持 Python 3.8+ 标准库兼容、现有 CLI 与退出码兼容。增加：

1. 唯一 event_id、previous_event_id/caused_by 引用关系、同一 previous 的分叉检测。
2. 必需字段及基本类型/格式检查（含 actor、recipient、ISO 时间、revision_cycle、SHA-256），actor.model 缺失或占位符为错误而非仅告警。
3. 状态与标准事件类型一致性、首事件/终态后事件、task_id 一致性检查；保留 HEARTBEAT、TASK_DECOMPOSED 等状态保持事件语义。
4. 产物路径安全检查（拒绝任务目录外的相对 .. 穿越）；相对路径先按当前协议解析，并对 task-001 这类 legacy 相对项目路径提供明确、可审计的只读 fallback/告警。
5. 读取文件使用安全上下文；保留清晰中文错误、退出码 0/1 和现有调用方式。
6. 用夹具测试通过与失败场景，至少覆盖：task-001 历史日志可读、重复 ID、错误 caused_by、非法状态/类型、坏哈希、路径穿越、占位 model、合法新日志。

## 子任务与负责人

| 子任务 | 负责人 | 文件所有权 | 输出 |
| --- | --- | --- | --- |
| ST-B 文档协议优化 | B（kimi-k2.5） | SKILL.md；本任务 B 执行记录 | artifacts/executions/execution-b-v001.md，文档 diff 与验证证据 |
| ST-C 校验器优化 | C（glm-5.2） | tools/validate.py、tasks/task-20260810-002/fixtures/**（如需）及本任务 C 执行记录 | artifacts/executions/execution-c-v001.md，测试输出与兼容性证据 |

B/C 不得修改对方所有权文件、task-001 历史文件或本方案；两项可并行。

## 执行顺序与依赖

1. B/C 各自校验本方案哈希，发布 TASK_CLAIMED + EXECUTION_STARTED。
2. B 修改 SKILL.md；C 修改 validate.py 与夹具并运行测试。
3. 各自写入执行记录并发布独立 WORK_READY。A 收齐两者后统一审查。

## 验收标准

1. python3 tools/validate.py tasks/task-20260810-002 在新增事件后通过；每次事件发布后均运行并记录校验输出。
2. python3 tools/validate.py tasks/task-20260810-001 对历史日志不因相对项目根产物路径误报失败（允许明确 legacy 告警）；task-001 的最终 APPROVED 状态可读。
3. 合法新事件链通过；重复 event_id、分叉 previous、未知 caused_by、task_id 不一致、非法状态/类型、坏 SHA-256、路径穿越、占位 actor.model 必须失败并返回退出码 1。
4. 现有 CLI 调用形式和 0/1 退出码兼容；仅使用 Python 3.8+ 标准库，无网络。
5. SKILL.md 明确路径基准、真实 model、发布后 validate、兼容 fallback、审查独立证据及返工/终态规则，且不引入与状态机重复的新状态。
6. C 的测试/夹具与 B 的文档证据均包含原文输出；不得修改 task-001 文件或本任务 control.md。

## 测试方法

- C：运行 python3 tools/validate.py 针对合法与恶意夹具；运行 task-001/task-002 校验；若增加测试脚本，使用 stdlib unittest。
- A：独立运行 python3 tools/validate.py tasks/task-20260810-001、tasks/task-20260810-002，执行夹具负例并检查退出码/错误信息，审阅 SKILL.md diff 和所有哈希；不接受 B/C 自评分。

## 风险与回退

| 风险 | 应对 |
| --- | --- |
| legacy 相对路径与新路径歧义 | 仅在任务目录解析失败时尝试受限项目根 fallback，并打印 legacy 告警；绝不覆盖或修改历史文件 |
| 校验过严破坏历史日志 | 夹具先覆盖 task-001 全链；对旧字段采用明确兼容规则，不降低新事件安全检查 |
| 校验器误读嵌套 JSON/标记 | 保持现有简单事件块格式，增加负例测试而不引入复杂解析器 |
| 两项并行修改冲突 | B 只改 SKILL.md，C 只改 validate.py/fixtures，禁止交叉写入 |

回退方式：按版本化产物恢复 SKILL.md 或 tools/validate.py；不删除历史事件。
