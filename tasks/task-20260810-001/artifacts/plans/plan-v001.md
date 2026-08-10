# Plan v001 — task-20260810-001：实现 csv2json 命令行工具

- 任务 ID：task-20260810-001
- 方案版本：v001
- 制定者：角色 A（kimi-session-a-001）
- 制定时间：2026-08-10T12:29:47+08:00

## 目标

在项目内实现一个纯 Python 标准库的命令行工具 `csv2json`：

1. 从 CSV 文件或标准输入读取数据，输出 JSON 数组（每行一个对象，键为表头）。
2. 支持参数：`--input/-i`（输入文件，缺省读 stdin）、`--output/-o`（输出文件，缺省写 stdout）、`--delimiter/-d`（列分隔符，默认 `,`）、`--pretty/-p`（缩进美化输出）。
3. 附带基于 stdlib `unittest` 的单元测试（不引入第三方依赖）。
4. 附带 README 说明用法。

交付目录：`tools/csv2json/`（相对项目根 `/Users/tommacmini4/Documents/code/agent_collaboration`）。

## 非目标

- 不做 CSV 写回、不做 JSON→CSV 反向转换。
- 不引入第三方包（如 pandas），不使用网络。
- 不做 pip 打包 / PyPI 发布。
- 不处理图片或任何多模态内容（因此无需角色 C）。

## 已知约束

- 仅使用 Python 3 标准库（`csv`、`json`、`argparse`、`unittest` 等）。
- 遵守 `control.md` 权限：`allowed_paths: ["./"]`，禁止触碰 `.git/`，禁止网络与破坏性操作。
- 环境中 python3 可用（/usr/bin/python3 或同级）。
- 本任务由用户明确授权为协议演示任务，目标由 A 自拟。

## 方案

在 `tools/csv2json/` 下创建 3 个文件：

1. `csv2json.py`
   - 函数 `convert(reader_rows, ...) -> list[dict]`：核心转换逻辑，可独立测试。
   - `main(argv)` 解析参数；读取输入（文件不存在时返回非零退出码并在 stderr 给出错误信息）；空输入（无表头）输出 `[]`。
   - 使用 `csv.reader` 读取，首行为表头；列数不足的行以空字符串补齐，多余列忽略；所有值按字符串处理（不做类型推断）。
   - `--pretty` 时 `json.dumps(..., indent=2, ensure_ascii=False)`，否则紧凑输出。
2. `tests/test_csv2json.py`（位于 `tools/csv2json/tests/`）
   - 覆盖：基本转换、自定义分隔符（如 `;`）、缺列补齐、多列截断、空输入、中文等非 ASCII 内容、CLI 端到端（subprocess 调用，含 `--pretty` 与 stdin 输入）、输入文件不存在时的错误码。
3. `README.md`：用法、参数表、示例、测试运行方式。

## 子任务与负责人

| 子任务 | 负责人 | 说明 |
| --- | --- | --- |
| ST-1 实现与测试 | B | 全部代码、测试、README；纯编码任务，按路由规则不调用 C |

## 文件所有权

- B 独占：`tools/csv2json/**`（新建目录，与现有文件无冲突）。
- 任何人不得修改：`.git/**`、本任务 `artifacts/plans/plan-v001.md`、已发布事件。

## 执行顺序与依赖

1. B 校验本方案哈希 → 发布 `TASK_CLAIMED` + `EXECUTION_STARTED`。
2. B 实现上述 3 个文件并运行全部测试。
3. B 写入 `artifacts/executions/execution-b-v001.md` 并发布 `WORK_READY`。
4. A 复审（rubric 100 分制，≥90 且无 blocking 才通过）。

无并行子任务，无跨角色依赖。

## 验收标准

1. `cd tools/csv2json && python3 -m unittest discover -s tests -v` 全部通过。
2. 手工验证：`printf 'a,b\n1,2\n' | python3 tools/csv2json/csv2json.py` 输出 `[{"a": "1", "b": "2"}]`。
3. `python3 tools/csv2json/csv2json.py -d ';' -i <含分号分隔的样例文件> -p` 输出缩进 JSON。
4. 不存在的输入文件返回非零退出码且 stderr 有可读错误。
5. 仅使用标准库；未修改 `tools/csv2json/` 以外的任何文件。
6. 执行记录包含测试输出原文作为证据。

## 测试方法

- 单元测试 + CLI 端到端（subprocess）测试，由 B 运行并粘贴完整输出。
- A 复审时独立重新运行上述命令复核，不接受 B 的自评分。

## 风险与回退

| 风险 | 应对 |
| --- | --- |
| 环境 python3 版本差异 | 代码兼容 Python 3.8+；B 在执行记录中注明实际版本 |
| CSV 边界 case 遗漏 | 测试清单已在方案中列明；A 审查时可追加 case，作为 REVISION_REQUIRED 项 |
| 实现不可行 | B 发布 `TASK_BLOCKED` 并说明原因，不得擅自扩大范围 |

回退方式：交付物全部为新建文件，删除 `tools/csv2json/` 即可完全回退，无外部副作用。
