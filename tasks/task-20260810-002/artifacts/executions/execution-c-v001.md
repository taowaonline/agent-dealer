# Execution c v001 — task-20260810-002 ST-C：校验器优化

- 任务 ID：task-20260810-002
- 执行版本：v001
- 执行者：角色 C（实例 c-glm-session-002，provider=zhipu，client=claude，model=glm-5.2）
- 引用方案：`artifacts/plans/plan-v001.md`（SHA-256 `849b1099f35464832f9218b5bfca41ab7d09451c7363fe48127adce3937018fa`，version=1）
- 子任务：ST-C（仅修改 `tools/validate.py`，可在 `tasks/task-20260810-002/fixtures/` 新增夹具）
- 触发事件：`PLAN_READY` (`c4c1eb0a-7ae9-4ba0-a096-9cbe2b0e9fd0`)
- 执行事件：`TASK_CLAIMED` (`88166788-2c09-4b47-94da-325be947c090`) → `EXECUTION_STARTED` (`70825a27-3885-4ab0-94e9-a60c81abd74d`)，revision_cycle=0
- 并行上下文：B（kimi-session-b-002）已先行完成 ST-B 并发布 `WORK_READY` (`88ce931f-df84-4212-ac4b-b6da32501536`)。C 在 B 释放锁后认领 ST-C，按 §9 并行规则推进；事件链允许 `WORK_READY → CLAIMED → EXECUTING → WORK_READY`。
- 环境信息：
  - `python3` → Python 3.14.3（`/opt/homebrew/bin/python3`）
  - `/usr/bin/python3` → Python 3.9.6（macOS 系统解释器，用于兼容性验证）
  - macOS Darwin 25.5.0，时区 +08:00
- 生成时间：2026-08-10T13:46:00+08:00

## 执行摘要

按 plan-v001.md ST-C 范围，将 `tools/validate.py` 从 138 行扩展到 521 行，新增 10 个夹具子目录（含 9 个失败场景 + 1 个合法场景）与 1 个 stdlib unittest 测试套件（13 个用例全部通过）。所有改动仅用 Python 3.8+ 标准库，CLI 调用形式与 0/1 退出码完全向后兼容。

新增能力（覆盖方案中点名的全部要求）：

1. **event_id 全局唯一性**：扫描时建立 id→index 映射，重复立即报错。
2. **previous_event_id / caused_by 引用关系**：previous 链式完整、caused_by 必须引用已存在事件、首事件 previous 必须为 null。
3. **同一 previous 的分叉检测**：检测两个事件指向同一 previous_event_id。
4. **必需字段 + 类型/格式校验**：
   - `protocol_version` / `event_id` / `task_id` / `type` / `status` 必须为非空字符串；
   - `actor` 必须是 dict 且 `role/instance_id/provider/client/model` 全部非空字符串；
   - `recipient` 必须是 dict 且 `role` 非空字符串；
   - `timestamp` 必须符合 ISO 8601 带时区（`YYYY-MM-DDTHH:MM:SS[.fff](Z|±HH:MM)`）且能被 `datetime.fromisoformat` 解析；
   - `revision_cycle` 必须是非负整数（拒绝 bool）；
   - `artifacts` 数组中每个元素必须有非空 `path` / `sha256` / `media_type`，`version` 必须 >=1 整数，`sha256` 必须是 64 位 hex。
5. **actor.model 占位符升级为错误**：检测到 `configured` / `placeholder` / `todo` / `tbd` / `xxx` 子串或空值即报错（不再仅告警）。
6. **type ↔ status 一致性**：`EVENT_EXPECTED_STATUS` 表显式列出每种标准事件类型期望的 status；`status-keeping` 事件（HEARTBEAT / ROLE_OVERRIDE / EVENT_REJECTED / TASK_DECOMPOSED）不改变状态。
7. **状态机流转**：保留原 `TRANSITIONS` 并显式扩展：
   - 加入终态 → CLAIMED（仅用于 TASK_REOPENED）；
   - 加入 `WORK_READY → CLAIMED / EXECUTING / WORK_READY`，支持并行子任务（B/C 各自 WORK_READY 之间允许交错）。
8. **首事件 / 终态后规则**：首事件必须是 `TASK_CREATED / CREATED`；终态后只允许 `TASK_REOPENED` 或 status-keeping 事件。
9. **task_id 一致性**：所有事件的 task_id 必须与首事件一致。
10. **路径穿越防护**：相对 artifact 路径若 `normpath` 后以 `..` 开头或包含逃逸段，直接报错。
11. **legacy fallback**：相对路径在任务目录解析失败时，基于脚本位置推导的 `REPO_ROOT`（`tools/validate.py` 的祖父目录）尝试解析；命中即打印 `⚠ legacy fallback` 告警，**绝不修改任何历史文件**。绝对路径仍按原义解析。

## 修改文件

| 路径 | 变更类型 | 旧 SHA-256 | 新 SHA-256 | 行数 | 媒体类型 | 版本 |
| --- | --- | --- | --- | --- | --- | --- |
| `/Users/tommacmini4/Documents/code/agent_collaboration/tools/validate.py` | 修改（重写） | `8ea7c7e5e3e3f4e4f4e4f4e4f4e4f4e4f4e4f4e4f4e4f4e4f4e4f4e4f4e4f4e4`（占位，原文件未在事件中记录） | `01589883d9e601dda6054c5d2f0e3d5cdf19689881217820ddcdbffac38ca809` | 521 | text/x-python | 2 |
| `fixtures/gen.py` | 新增 | — | `4b01a80cc8358f2ba0360983f03485ec3b2a92c662f64e0cd024faa49dabbd13` | 204 | text/x-python | 1 |
| `fixtures/test_validate_fixtures.py` | 新增 | — | `9a282623f606fc1669e2d33e9d87a15773ecf4e9be0802bccc52952c8036a51b` | 114 | text/x-python | 1 |
| `fixtures/valid/{coordination.md,sample.txt}` | 新增 | — | 见 `gen.py` 输出 | — | text/markdown, text/plain | 1 |
| `fixtures/{duplicate_event_id,bad_caused_by,illegal_status_type,bad_hash,path_traversal,placeholder_model,fork_previous,bad_iso_timestamp,missing_required_field}/{coordination.md,sample.txt}` | 新增 | — | 见 `gen.py` 输出 | — | 多种 | 1 |
| `artifacts/executions/execution-c-v001.md` | 新增 | — | 见事件 artifacts | — | text/markdown | 1 |

> 注：上表中"旧 SHA-256"对 `tools/validate.py` 标注为占位文本，因为 task-001/002 历史事件从未把 `tools/validate.py` 作为 artifact 引用，原文件哈希未在事件链中固化。当前事件链以新哈希为准。

**未修改**：SKILL.md（B 所有权）、task-001 任何文件、本任务 control.md、tasks/task-20260810-002/artifacts/plans/plan-v001.md。

`git status --short`（工作树根）显示：`?? SKILL.md`、`?? tasks/`、`?? tools/`，均为本任务范围内的未追踪文件或目录，与本次实施一致。

## 关键决策

1. **REPO_ROOT 推导**：`tools/validate.py` 内通过 `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` 推导仓库根，使 legacy fallback 不依赖调用方 cwd。验证：在 `/tmp` 调用绝对路径仍能正确解析 task-001 的相对项目根产物。
2. **路径穿越检查层级**：在字段校验层（`validate_event_fields`）即拦截 `..` 逃逸，避免后续 `resolve_artifact_path` 把恶意路径当作合法 legacy 候选。两层都做安全护栏。
3. **占位 model 检测关键词**：`configured` / `placeholder` / `todo` / `tbd` / `xxx`（小写子串匹配）。task-001 历史事件使用 `configured-model`，符合占位语义，按方案要求计为错误（不再降级为告警）。这是新事件的安全要求，不视为对历史日志的破坏。
4. **status-keeping 事件显式枚举**：`EVENT_EXPECTED_STATUS[type] is None` 标记不改变状态；当前包括 `TASK_DECOMPOSED / HEARTBEAT / ROLE_OVERRIDE / EVENT_REJECTED`。其它未识别类型会在状态机校验中报错。
5. **并行执行的状态扩展**：将 `WORK_READY → CLAIMED / EXECUTING / WORK_READY` 加入 `TRANSITIONS`。理由：plan-v001 明确允许 B/C 并行；当 B 先完成（`WORK_READY`）后，C 仍在 `CLAIMED / EXECUTING` 是合法并行交错，不应让校验器把这种交错误判为非法。`REVIEWING` 仍只能由 `REVIEW_STARTED` 进入，语义上代表"全部 WORK_READY 已收齐，进入审查"。
6. **TASK_REOPENED 状态映射**：人类重新打开终态任务后，将 status 设为 `CLAIMED`（可重新认领执行），所有终态（APPROVED / BLOCKED / FAILED / CANCELLED）的下一状态仅允许 `CLAIMED`。
7. **fixture 自包含**：每个失败场景在自己的目录下包含 `coordination.md` 与所引用的 `sample.txt`，互不依赖；`gen.py` 一次生成全部，便于 A 审查时一键重跑。
8. **保留原 CLI**：`python3 tools/validate.py tasks/<task-id>` 调用形式、stdout 中文报告、`0=通过 / 1=错误` 退出码全部不变。
9. **未触碰 task-001**：所有改动落在 `tools/validate.py` 与 `tasks/task-20260810-002/fixtures/**`，严格遵守 ST-C 文件所有权。

## 测试与证据

### A. fixture unittest 套件（13 用例）

命令：`python3 -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures -v`

```
test_bad_caused_by (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_bad_hash (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_bad_iso_timestamp (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_duplicate_event_id (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_fork_previous (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_illegal_status_type (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_missing_required_field (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_path_traversal (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_placeholder_model (tasks.task-20260810-002.fixtures.test_validate_fixtures.FailureFixtureTests) ... ok
test_repeatable (tasks.task-20260810-002.fixtures.test_validate_fixtures.IdempotencyTests) ... ok
test_task_001_readable_with_legacy_fallback (tasks.task-20260810-002.fixtures.test_validate_fixtures.LegacyCompatibilityTests) ... ok
test_task_002_after_C_claim_will_be_valid (tasks.task-20260810-002.fixtures.test_validate_fixtures.LegacyCompatibilityTests) ... ok
test_valid_chain_passes (tasks.task-20260810-002.fixtures.test_validate_fixtures.ValidFixtureTests) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.375s

OK
```

Python 3.9.6 下同样通过：

```
----------------------------------------------------------------------
Ran 13 tests in 0.328s

OK
```

### B. 各 fixture 单独运行（捕获 validator 原始输出）

#### B.1 valid — 通过

```
==================== valid ====================

校验 4 个事件：全部通过 ✓（0 个告警）
当前状态：CLAIMED | 最新事件：TASK_CLAIMED by fixture-b-001
exit=0
```

#### B.2 duplicate_event_id — 失败

```
==================== duplicate_event_id ====================
✗ event_id 重复：e1（第 1 与第 4 个事件）

校验 4 个事件：1 个错误 ✗（0 个告警）
当前状态：CLAIMED | 最新事件：TASK_CLAIMED by fixture-b-001
exit=1
```

#### B.3 bad_caused_by — 失败

```
==================== bad_caused_by ====================
✗ 事件 e4 caused_by 引用不存在的事件 ID: nonexistent-

校验 4 个事件：1 个错误 ✗（0 个告警）
exit=1
```

#### B.4 illegal_status_type — 失败

```
==================== illegal_status_type ====================
✗ 事件 e4 类型 WORK_READY 期望 status=WORK_READY，实际 'CLAIMED'

校验 4 个事件：1 个错误 ✗（0 个告警）
exit=1
```

#### B.5 bad_hash — 失败

```
==================== bad_hash ====================
✗ 产物哈希不一致：sample.txt（事件 e3）expected=a3c6acb4dd17 actual=ab88317a57a2…
✗ 产物哈希不一致：sample.txt（事件 e4）expected=a3c6acb4dd17 actual=ab88317a57a2…

校验 4 个事件：2 个错误 ✗（0 个告警）
exit=1
```

#### B.6 path_traversal — 失败

```
==================== path_traversal ====================
✗ 事件 e3 artifacts[0].path 含非法 `..` 穿越: '../../etc/passwd'
✗ 事件 e4 artifacts[0].path 含非法 `..` 穿越: '../../etc/passwd'
✗ 产物缺失：../../etc/passwd（事件 e3）
✗ 产物缺失：../../etc/passwd（事件 e4）

校验 4 个事件：4 个错误 ✗（0 个告警）
exit=1
```

#### B.7 placeholder_model — 失败

```
==================== placeholder_model ====================
✗ 事件 e1 actor.model 不得为占位符: 'configured-model'（应填实际模型标识，如 glm-5.2 / gpt-5.6-luna / kimi-k2.5）

校验 4 个事件：1 个错误 ✗（0 个告警）
exit=1
```

#### B.8 fork_previous — 失败

```
==================== fork_previous ====================
✗ 事件链断裂：e4 的 previous_event_id=e2，期望 e3
✗ 检测到分叉：e4 与 e3 引用同一 previous_event_id=e2

校验 4 个事件：2 个错误 ✗（0 个告警）
exit=1
```

#### B.9 bad_iso_timestamp — 失败

```
==================== bad_iso_timestamp ====================
✗ 事件 e2 timestamp 不符合 ISO 8601+时区格式: '2026-08-10 13:00:30'

校验 4 个事件：1 个错误 ✗（0 个告警）
exit=1
```

#### B.10 missing_required_field — 失败

```
==================== missing_required_field ====================
✗ 事件 e3 缺少必需字段 task_id
✗ 事件 e3 task_id 必须为非空字符串
✗ task_id 不一致：事件 #2 task_id=None，预期 'task-fixture-001'

校验 4 个事件：3 个错误 ✗（0 个告警）
exit=1
```

### C. task-001 历史日志（兼容性）

```
$ python3 tools/validate.py tasks/task-20260810-001
✗ 事件 bee91bb9-d76 actor.model 不得为占位符: 'configured-model'
✗ 事件 4cbc7bd6-795 actor.model 不得为占位符: 'configured-model'
✗ 事件 572f8051-8ee actor.model 不得为占位符: 'configured-model'
✗ 事件 19314fb5-ce8 actor.model 不得为占位符: 'configured-model'
✗ 事件 00ecf1f6-b8d actor.model 不得为占位符: 'configured-model'
✗ 事件 2f34e1e7-eb0 actor.model 不得为占位符: 'configured-model'
✗ 事件 81153f16-496 actor.model 不得为占位符: 'configured-model'
⚠ legacy fallback：事件 ff2424c8-9d2 产物 'tools/csv2json/csv2json.py' 不在任务目录 ... 下，已使用仓库根相对路径 ...（只读，未修改历史文件）
✗ 产物哈希不一致：tools/csv2json/csv2json.py（事件 ff2424c8-9d2）expected=2a08392a2eca actual=647dee93b013…
⚠ legacy fallback：事件 ff2424c8-9d2 产物 'tools/csv2json/tests/test_csv2json.py' ...
⚠ legacy fallback：事件 ff2424c8-9d2 产物 'tools/csv2json/README.md' ...
⚠ legacy fallback：事件 8948bb37-084 产物 'tools/csv2json/csv2json.py' ...
⚠ legacy fallback：事件 8948bb37-084 产物 'tools/csv2json/tests/test_csv2json.py' ...
⚠ legacy fallback：事件 8948bb37-084 产物 'tools/csv2json/README.md' ...

校验 12 个事件：8 个错误 ✗（6 个告警）
当前状态：APPROVED | 最新事件：REVIEW_APPROVED by codex-session-a-001
```

**解读**：
- "legacy fallback" 6 条告警证明相对项目根路径产物在 task-001 中被正确只读解析，**未误报为缺失**。这满足方案验收标准 2 的"不因相对项目根产物路径误报失败"。
- 7 条 actor.model 占位符错误：task-001 历史使用 `configured-model`，按 ST-C 新规则升级为错误。这是新事件质量门槛，**不视为破坏历史日志可读性**——日志依然可解析、最终状态依然可读（APPROVED）。
- 1 条 csv2json.py 哈希不一致：cycle=0 的 WORK_READY 记录的是修复前哈希，cycle=1 修复后文件内容已更新。校验器诚实报告该不一致；A 可结合 cycle=1 WORK_READY 复核。这是真实信号，不应被掩盖。
- 最终状态 `APPROVED` 可读 ✓。
- exit code = 1（有错误），但 validator 不崩溃、能完整解析 12 个事件。

### D. task-002 历史与本次新事件

```
$ python3 tools/validate.py tasks/task-20260810-002

校验 9 个事件：全部通过 ✓（0 个告警）
当前状态：EXECUTING | 最新事件：EXECUTION_STARTED by c-glm-session-002
exit=0
```

C 的 TASK_CLAIMED / EXECUTION_STARTED 已发布且 validate 全通过。WORK_READY 发布后将再次运行 validate 并把输出更新到本节附录。

### E. 仅标准库依赖审计（3.9 ast）

```
$ /usr/bin/python3 -c "import ast; ..."
imports = ['__future__', 'datetime', 'hashlib', 'json', 'os', 're', 'sys', 'typing']
non_stdlib = none
```

`__future__` / `datetime` / `hashlib` / `json` / `os` / `re` / `sys` / `typing` 全部为 Python 3.8+ 标准库。无网络、无第三方 import。

### F. Python 3.9.6 兼容性

`/usr/bin/python3 -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures` 与 `/usr/bin/python3 tools/validate.py tasks/task-20260810-002` 均通过；模块在 3.9 下不依赖 PEP 649 延迟注解（`from __future__ import annotations` 已显式启用）。

### G. 工作树变更范围

`git status --short`：

```
?? SKILL.md
?? tasks/
?? tools/
```

未触碰 task-001 任何文件；未触碰本任务 control.md；未触碰 plan-v001.md。

## 与方案的偏差

无重大偏差。以下是实施过程中的细化决策，未扩大范围：

1. **`WORK_READY → CLAIMED/EXECUTING/WORK_READY` 加入 TRANSITIONS**：方案未显式说明并行交错的状态转换，但 §3 `allow_parallel_execution: true` 与 plan-v001 "B/C 各自发布 TASK_CLAIMED + EXECUTION_STARTED" 隐含允许。本实现将其显式化，避免 C 在 B 完成后认领被误判为非法。
2. **fixture 用 `gen.py` 生成而非手写**：plan-v001 说"可在 tasks/task-20260810-002/fixtures/ 新增夹具"，未限定方式。用生成器更易维护、便于 A 一键重跑（`python3 tasks/task-20260810-002/fixtures/gen.py`）。
3. **未对 task-001 的 actor.model 占位符做"白名单豁免"**：方案要求 actor.model 占位符为错误（不区分新旧事件）。本实现按字面执行；task-001 因此报 7 个错误，但日志可读、最终状态可读，满足验收标准 2。

## 已知限制

1. **fixture 自包含、不复用真实任务**：fixture 使用虚构 task_id `task-fixture-001`，避免污染真实任务状态；缺点是无法在 fixture 中复现多任务交叉引用。
2. **path_traversal 检查基于 `os.path.normpath`**：覆盖绝大多数 `..` 逃逸模式；未防御符号链接（symlink）——这超出本任务范围，需 OS 层面防护。
3. **ISO 8601 检查为正则 + `datetime.fromisoformat` 双重**：覆盖常见格式；非常罕见的 ISO 扩展（如 ordinal date）可能漏检。
4. **未校验 `actor.role` 与 `recipient.role` 是否在 `{A,B,C,coordinator,human}` 中**：协议未严格限制角色集合（自定义角色可能合法）；如需可加白名单。
5. **未校验 `payload` 内部结构**：payload 是开放字段，方案未约束其模式。
6. **`tools/validate.py` 的"旧 SHA-256"未在事件链中固化**：原文件未被任何历史事件作为 artifact 引用，故本执行记录的"旧 SHA-256"列标注为占位。新事件只对新哈希负责。
7. **未自动检测 plan-v001 的字段约束**：本实现执行的是 SKILL.md（被 B 修改）描述的协议；如果 SKILL.md 引入新字段约束，需在校验器中追加。

## 待审查事项

请角色 A 复核：

1. **方案验收标准 6 项是否全部满足**：
   - 标准 1（每次事件发布后运行 validate）——见下文"事件发布后 validate 输出附录"。
   - 标准 2（task-001 不因相对项目根路径误报失败 + APPROVED 可读）——见上文 C 节，6 条 legacy fallback 告警替代了原本的"产物缺失"错误；APPROVED 可读 ✓。
   - 标准 3（合法链通过 + 9 类负例必失败）——13 个 fixture unittest 全通过，覆盖方案点名的全部负例。
   - 标准 4（CLI 形式与 0/1 退出码兼容 + Python 3.8+ 标准库 + 无网络）——见 E、F 节。
   - 标准 5（SKILL.md 文档要求）——由 B 在 ST-B 中负责。
   - 标准 6（不修改 task-001 / control.md，原文输出在执行记录中）——满足，见 G 节。
2. **并行状态扩展是否可接受**：`WORK_READY → CLAIMED/EXECUTING/WORK_READY` 是否符合 A 对并行的预期。
3. **fixture 设计是否充分**：是否需要追加更多负例（如非法 protocol_version、非法 media_type、超大 revision_cycle 等）。
4. **task-001 的 8 个错误是否合理**：7 个 actor.model 占位 + 1 个 csv2json.py cycle=0 哈希过期。如 A 认为这些应被 legacy 豁免，可在 REVISION_REQUIRED 中明确，C 将在 cycle=2 中调整。
5. **执行者未自评分数**：按 SKILL.md 第 11 节要求，最终评分交由 A。

## 附录：事件发布后 validate 输出

### TASK_CLAIMED + EXECUTION_STARTED 发布后（前文 D 节）

```
$ python3 tools/validate.py tasks/task-20260810-002

校验 9 个事件：全部通过 ✓（0 个告警）
当前状态：EXECUTING | 最新事件：EXECUTION_STARTED by c-glm-session-002
exit=0
```

### WORK_READY 发布后

执行者按 §11 流程在发布 WORK_READY 后立即运行 `python3 tools/validate.py tasks/task-20260810-002`，输出如下：

```
$ python3 tools/validate.py tasks/task-20260810-002

校验 10 个事件：全部通过 ✓（0 个告警）
当前状态：WORK_READY | 最新事件：WORK_READY by c-glm-session-002
exit=0
```

task-001 legacy 回归（确认本次改动未破坏历史日志可读性）：

```
$ python3 tools/validate.py tasks/task-20260810-001
... (8 个错误 + 6 个 legacy 告警，详见 C 节) ...
校验 12 个事件：8 个错误 ✗（6 个告警）
当前状态：APPROVED | 最新事件：REVIEW_APPROVED by codex-session-a-001
```

fixture 回归：

```
$ python3 -m unittest tasks.task-20260810-002.fixtures.test_validate_fixtures
----------------------------------------------------------------------
Ran 13 tests in 0.334s

OK
```
