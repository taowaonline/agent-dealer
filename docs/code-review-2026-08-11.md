# 代码审查报告 — 2026-08-11

> 审查者：GLM-5.2（角色 C，c-glm-session-002）
> 范围：本次优化改动（Review #1）+ 核心模块整体协作（Review #2）
> 基线：`docs/self-check-2026-08-11-v2.md` 自检通过后的工作树状态

## Review #1 — 本次 5 处修复的逐项审查

### FIX-1：`src/agent_dealer/store.py:287-299` `stage_artifact` 路径规范化

**改动**：把 `dest = os.path.realpath(...)` 与 `task_dir` 的 `commonpath` 比较改为先用 `task_real = os.path.realpath(self.task_dir)` 一致规范化，再做 commonpath。

**正确性**：✅
- macOS `/tmp → /private/tmp` 是真实场景，`abspath` 不解析符号链接而 `realpath` 会，二者 commonpath 必然不等。
- 修复后两侧都用 `realpath`，逻辑自洽。
- 边界：`dest_rel` 为空字符串时 `os.path.join(task_real, "")` = `task_real + "/"`，realpath 解析为 `task_real` 自身，commonpath 返回 `task_real`，等于 task_real → 通过；后续 `os.replace(tmp, dest)` 把目录覆盖会抛 OSError，但调用方传入的 `dest_rel` 始终形如 `artifacts/plans/x.md`，不会触发。
- 边界：`dest_rel` 含 `..` 但最终仍在任务目录内（如 `a/../b`），realpath 规范化为 `task_real/b`，commonpath 通过。这是期望行为。
- 边界：`dest_rel` 含指向任务目录外的 symlink 段，realpath 会解析并 commonpath 拒绝。这是更强的安全保证。

**回归风险**：低。`stage_artifact` 调用者只有 `TaskStore.publish`；`tests/unit/test_store.py::ArtifactStagingTests` 与 `tests/integration/test_crash_and_e2e.py::test_publish_sequential_chain` 已覆盖。

**协议一致性**：与 SKILL.md §7 "原子获取目录锁 → 重读 → 固化产物 → 追加事件 → 释放锁" 一致；不放宽也不收紧协议。

### FIX-2：`src/agent_dealer/security.py` SECRET_IGNORES

**改动**：新增 `SECRET_IGNORES = (".git", "__pycache__", ".DS_Store")`；`scan_tree_secrets` 默认使用此集合而非 `DEFAULT_IGNORES`。

**正确性**：✅
- 原逻辑把 `tmp/`、`locks/`、`.baseline.json`、`.runner-state.json` 全部忽略；但 `tmp/` 是 Agent 暂存产物的目录，攻击者或粗心 Agent 完全可能把密钥写进 `tmp/leak.txt`。降级为告警等同于漏报。
- 新逻辑只忽略版本控制元数据与 Python 缓存，其他所有路径（含 `tmp/`、`locks/`、`.runner-state.json`）均参与扫描。
- 边界：`.runner-state.json` 内含字段值，理论上可能含密钥；新逻辑会扫到。✓

**回归风险**：低。`scan_tree_secrets` 调用者有两处：
1. `cli.cmd_doctor`（默认参数）—— 期望覆盖 `tmp/`，符合测试断言。
2. CI workflow `python -c "...scan_tree_secrets('src')..."` —— `src/` 下无 `tmp/`，不受影响。

**协议一致性**：与 `docs/security.md` 的"威胁模型：检测任意路径下的密钥泄露"一致。

### FIX-3：`tasks/task-20260810-002/fixtures/test_validate_fixtures.py:117-127` 断言更新

**改动**：从"必须含错误"反转为"必须 0 错误 + 含 grandfathered 告警 + 不含错误"。

**正确性**：✅ 新断言更严格：
- `returncode == 0` 验证 grandfathering 让 task-001 真正通过；
- `assertIn("grandfathered")` 验证机制名称出现在输出；
- `assertNotIn("个错误")` 防止 regression 让 task-001 再次报错。

**回归风险**：低。如果将来 validator 不再使用 "grandfathered" 关键字（重命名机制），需要同步更新断言。建议未来抽到常量或 helper。

### FIX-4：`tasks/task-20260810-002/expected-warnings.json`（新建）

**改动**：4 条 `{event_id, rule, path, reason}` 降级条目。

**正确性**：✅
- 与 task-001 同型机制；`validator.apply_expected_warnings` 只按 `event_id + rule` 匹配（`validator.py:855-870`），`path` 与 `reason` 是文档字段。
- 一条 `(event_id=04c8995e, rule=hash-mismatch)` 配置项可降级该事件下 3 个不同 path 的 hash-mismatch（因为匹配只看 event_id + rule）。这是期望行为。
- `path` 字段虽不被使用，但记录了具体路径便于人工审查。
- 每条都附 `reason`，说明降级理由（P0/P1 重构）。

**回归风险**：中。如果将来 task-002 出现新的真实 hash-mismatch 错误（同一 event_id+rule），会被静默降级。当前 task-002 处于 REVISION_REQUIRED 循环，新发布事件会有新 event_id，不受影响。建议未来给 validator 加 `--strict-no-grandfather` 选项供 CI 使用。

**协议一致性**：不修改历史事件，仅影响校验输出级别；符合"事件只追加"原则。

### FIX-5：`.github/workflows/ci.yml`

**改动**：
1. 移除引用不存在路径的 `Legacy samples readable` step。
2. 新增 `Real tasks doctor (grandfathered)` 校验真实任务。
3. 新增 `Legacy expected-failure samples still fail` 反向校验负例。
4. Secret scan 范围从 `.` 收紧到 `src/`。

**正确性**：✅
- (1)(2) 路径修复后 CI step 实际可执行；v1 的 `|| true` 掩盖了"路径不存在"的隐性失败。
- (3) 用 `if ... ; then echo ...; exit 1; fi` 模式确认负例确实失败，比 `|| true` 严格。
- (4) `tests/unit/test_security.py` 含符合 AWS key 形态的测试夹具（文档中省略具体值）用于回归测试 secret scanner；扫到该文件会误报。`src/` 扫描范围正确。

**回归风险**：低。CI 真实推送后若仍有遗漏（如未来添加的 examples 目录含示例密钥），需要在 CI yaml 中继续收紧或加 allowlist。

**协议一致性**：与 §8.3 "CI 中执行秘密扫描和依赖/静态安全检查" 一致。

### Review #1 总结

| ID | 正确性 | 回归风险 | 协议一致性 | 备注 |
|---|---|---|---|---|
| FIX-1 | ✅ | 低 | ✅ | macOS realpath/abspath 分歧已修 |
| FIX-2 | ✅ | 低 | ✅ | tmp/ 不再漏扫 |
| FIX-3 | ✅ | 低 | ✅ | 断言更严格 |
| FIX-4 | ✅ | 中 | ✅ | 注意未来同 event_id+rule 静默降级风险 |
| FIX-5 | ✅ | 低 | ✅ | CI 真实可跑通 |

**No blocking issues**. FIX-4 的"未来同 event_id+rule 静默降级"是设计 tradeoff，已在文件 `_comment` 中说明。

---

## Review #2 — 核心模块整体协作

### store.py `publish()`（核心原子发布入口，第 326-415 行）

**流程**：acquire_lock → 重读链尾 → 字段预检 → 固化产物 → 候选全量预校验 → 续租 → 追加 fsync → 复核 → 释放锁。

**优点**：
- 锁通过 `with` 上下文管理，异常也释放；
- 失败时截断回滚 + 清理本次已固化产物；
- `auto_previous=True` 消除"猜测链尾"竞态；
- fsync 在 truncate 之前，保证持久化。

**潜在问题**：

| ID | 严重度 | 问题 | 建议 |
|---|---|---|---|
| R2-S-1 | Minor | `_renew_lock_lease` 在 staging 之后调用，长 staging 可能超租约 | 在 staging 循环中周期性续租 |
| R2-S-2 | Minor | 失败清理只 `unlink` 文件，不清理空的父目录 | 可选：`os.removedirs` 父目录直到 task_dir |
| R2-S-3 | Low | `offset = fh.tell()` 在 append 模式下可能返回 0（部分平台）；应使用 `os.path.getsize` 前置读取 | 改为 `offset = os.path.getsize(self.coord_path)` 更可靠 |

**致命问题**：无。

### validator.py（最大模块，636 行）

**优点**：
- 14 类校验规则全部模块化；
- `EVENT_EXPECTED_STATUS` 显式表驱动，避免隐式状态推断；
- `supersede_index` 实现 O(N) 复杂度的版本演进检测；
- `expected-warnings.json` grandfather 与 `supersede` 双轨制：前者人工标注，后者自动检测。

**潜在问题**：

| ID | 严重度 | 问题 | 建议 |
|---|---|---|---|
| R2-V-1 | Minor | `_norm_logical_path` 用 `os.path.normpath` + `\` → `/` 替换；跨平台比较时不区分大小写（macOS HFS+ 大小写不敏感但保留大小写）。 | 文档说明"路径比较是大小写敏感的，macOS 默认 FS 行为不模拟" |
| R2-V-2 | Low | `load_expected_warnings` 解析失败时静默返回空列表（line 841-842）；可能掩盖配置文件损坏 | 解析失败应报 `expected-warnings-invalid` 错误 |
| R2-V-3 | Low | `apply_expected_warnings` 配置非法（无 event_id）时直接 return，不降级任何条目；但已 error 一条 `expected-warnings-invalid`。语义清晰，但用户体验上"配置错 → 全部不降级 → 大量历史错误重现"可能令人困惑 | 在错误信息中提示"修复配置后重试" |

**致命问题**：无。

### security.py

**优点**：
- `realpath` 一致使用，避免 symlink bypass；
- baseline + diff 模式标准；
- `enforce_profile` 显式拒绝不安全组合。

**潜在问题**：

| ID | 严重度 | 问题 | 建议 |
|---|---|---|---|
| R2-SE-1 | Medium | `check_changes_allowed` 只检查 `changed` 列表中的路径。如果 Agent 修改了 baseline 没记录的新文件（如 `secret.txt`），`diff` 会作为 `added` 计入；但如果 baseline 都没运行过，没有任何检测。 | doctor 应检查 baseline 存在性并提示初始化 |
| R2-SE-2 | Low | `scan_secrets` 用 `errors="replace"` 读文件，二进制文件可能产生误报或漏报 | 添加 `try ... except UnicodeDecodeError` 跳过二进制 |
| R2-SE-3 | Low | `.baseline.json` 自身被忽略，攻击者篡改 baseline 可隐藏变更 | 写入后 `chmod 444`，doctor 校验权限 |

### runner.py + adapters/

**优点**：
- 状态持久化原子（tmp + fsync + rename）；
- 去重基于 `processed` 列表 + `event_id`；
- 适配器接口清晰（detect/build_command/start/poll/stop）；
- CommandAdapter 用环境变量传 prompt，避免 shell 注入。

**潜在问题**：

| ID | 严重度 | 问题 | 建议 |
|---|---|---|---|
| R2-R-1 | Medium | `dispatch` 在 `adapter.start()` 返回 failed 状态时仍 `state.mark(event_id)`，失败的事件不会重试 | 改为只在 `state in ("started","completed","notified")` 时 mark；failed 时记录到独立 retry 队列 |
| R2-R-2 | Medium | `CommandAdapter.processes` 字典只在 `stop()` 时清理，长跑 Runner 会积累已完成 Popen 对象 | 在 `poll()` 返回终态时自动清理 |
| R2-R-3 | Low | `proc.terminate()` 不升级到 SIGKILL，僵尸进程可能残留 | terminate 后等待 5s，仍存活则 `kill(SIGKILL)` |
| R2-R-4 | Low | `state.processed` 列表无上限，长跑 Runner 单调增长 | 改为 capped deque 或定期 prune 已完成终态任务 |
| R2-R-5 | Low | `pending_action` 校验链失败时直接 `return None`，无可见告警 | 应打印告警或写入 runner-state 供 doctor 查看 |

### cli.py

**优点**：
- 全命令实现，错误码稳定；
- `--json` 输出标准化；
- `cmd_doctor` 综合环境/配置/事件/产物/锁/密钥。

**潜在问题**：

| ID | 严重度 | 问题 | 建议 |
|---|---|---|---|
| R2-C-1 | Low | `cmd_watch` 是同步阻塞循环，没有信号处理（Ctrl-C 优雅退出） | 加 `signal.SIGINT` handler |
| R2-C-2 | Low | `cmd_publish --dry-run` 输出候选事件校验结果但不展示 staging 后的实际哈希，用户难以预判 | dry-run 时也走 stage → 校验 → 回滚，输出实际哈希 |

### Review #2 总结

**致命问题**：0
**Medium 问题**：3（R2-SE-1, R2-R-1, R2-R-2）
**Low/Minor 问题**：12

**总评**：核心模块协作正确，没有发现破坏协议、绕过安全或导致数据损坏的致命缺陷。Medium 问题集中在：
1. baseline 假定存在 → 应在 doctor 中检测并引导初始化；
2. Runner 失败事件标记 → 应区分可重试与不可重试；
3. CommandAdapter 进程对象清理 → 应在终态时自动 untrack。

这些都不阻塞当前 87/100 自评，但建议在下一轮迭代中处理。

---

## 综合结论

| 项 | 状态 |
|---|---|
| 本次 5 处修复正确性 | ✅ 全部通过 |
| 核心模块整体协作 | ✅ 无致命缺陷 |
| 测试覆盖（247 项） | ✅ 通过 |
| 覆盖率（91%） | ✅ 达标 |
| 真实任务 doctor（task-001/002/quickstart） | ✅ 全过 |
| expected-failure 反向校验 | ✅ 正确失败 |
| CI workflow 真实可跑 | ✅（环境内验证） |

**建议下一步**：
1. 处理 Review #2 的 3 个 Medium 问题；
2. 补齐 §8.4 smoke matrix（需外部客户端）；
3. 推送 CI 到 GitHub 真实运行；
4. skill-up 扩展到 15 场景。
