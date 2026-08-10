# Execution b v001 — task-20260810-001：实现 csv2json 命令行工具

- 任务 ID：task-20260810-001
- 执行版本：v001
- 执行者：角色 B（实例 b-session-001，provider=zhipu，client=claude，model=glm-5.2）
- 引用方案：`artifacts/plans/plan-v001.md`（SHA-256 `257532dd6381535931870b36706c47c233305088024947e300cb17cacf2236bc`，version=1）
- 触发事件：`PLAN_READY` (`572f8051-8eed-4f97-8618-4165644ee9e2`)
- 执行事件链：`TASK_CLAIMED` (`22d5a112-6ef4-4813-ab19-6f91772a6e65`) → `EXECUTION_STARTED` (`bef8c67a-4482-4c52-a04b-185e760858c0`)
- 环境信息：Python 3.14.3（`/opt/homebrew/bin/python3`），macOS Darwin 25.5.0，时区 +08:00
- 生成时间：2026-08-10T12:43:00+08:00

## 执行摘要

按照 `plan-v001.md` 在 `tools/csv2json/` 下创建了 3 个文件（共 457 行）：

- `tools/csv2json/csv2json.py` — 纯标准库 CLI 工具，包含 `convert(lines, delimiter)` 核心转换函数和 `main(argv)` 入口。
- `tools/csv2json/tests/test_csv2json.py` — stdlib `unittest` 测试套件，22 个用例覆盖方案中点名的全部边界条件。
- `tools/csv2json/README.md` — 用法、参数表、示例、测试运行方式、限制说明。

plan-v001.md 验收标准 6 项全部通过：

1. `cd tools/csv2json && python3 -m unittest discover -s tests -v` —— 22 个用例全部通过（`Ran 22 tests in 0.464s OK`）。
2. `printf 'a,b\n1,2\n' | python3 tools/csv2json/csv2json.py` 输出 `[{"a": "1", "b": "2"}]`（精确匹配）。
3. `python3 tools/csv2json/csv2json.py -d ';' -i <file> -p` 输出缩进 JSON。
4. 不存在的输入文件返回 exit code 1 且 stderr 输出 `csv2json: 错误：输入文件不存在：/no/such/file.csv`。
5. 仅使用标准库（`argparse`、`csv`、`json`、`sys`、`typing`），未引入第三方依赖。
6. 未修改 `tools/csv2json/` 以外的任何文件（`git status` 显示工作树中其他路径无变更）。

## 修改文件

全部为新增文件，目录 `tools/csv2json/` 此前不存在：

| 路径 | 行数 | SHA-256 | 媒体类型 | 版本 |
| --- | --- | --- | --- | --- |
| `tools/csv2json/csv2json.py` | 137 | `2a08392a2ecae0fbab1d820f3bddb0fda02157402c50af5cd02b0c7f2a3ffb7f` | text/x-python | 1 |
| `tools/csv2json/tests/test_csv2json.py` | 183 | `5ade89de22005231bfeb82daf8ea6239658bb8d1136d21756e1fd2f4f0be5c10` | text/x-python | 1 |
| `tools/csv2json/README.md` | 137 | `a8f7b511466cf34b91a796c84e8eef5b2f92b13f54fb60178220537dcbb5788d` | text/markdown | 1 |

未修改 `tools/csv2json/` 以外的任何文件。`git status --short` 在工作树根仅显示 `?? SKILL.md`、`?? tasks/`、`?? tools/`（均为本任务范围内的未追踪文件）。

## 关键决策

1. **`convert()` 入参类型选择**：方案中签名写作 `convert(reader_rows, ...)`，存在歧义（既可指 csv.reader 输出的行列表，也可指原始文本行）。本实现选择接受 `Iterable[str]`（原始文本行），并在内部调用 `csv.reader`。原因：
   - 单元测试无需重复实现 csv 解析即可直接构造 `["a,b\n", "1,2\n"]`；
   - `main()` 直接传入 `sys.stdin` 或 `open(...)` 句柄即可；
   - 同时通过 `test_accepts_stringio` 验证 file-like 对象（`io.StringIO`）也能作为输入，保证 API 通用性。
2. **错误退出码分级**：参数错误（如分隔符非单字符）使用 exit code `2`；IO 错误（输入不存在、输出不可写）使用 exit code `1`；成功为 `0`。便于在脚本中区分错误类别。
3. **空行处理**：当 `csv.reader` 返回空列表（极少见，但理论可能）时，按表头生成全空字符串字典，保证输出数组与表头结构一致。
4. **`ensure_ascii=False`**：紧凑与美化模式均保留非 ASCII 字符（中文原样输出），避免 `\uXXXX` 转义影响可读性。
5. **README 示例笔误修正**：在 `缺列补齐与多列截断` 段落中初次草稿误将一处 `python3` 写为 `python2`，发布前已修正。
6. **多列截断策略**：超出表头列数的额外列直接丢弃（不写入任何键），与方案要求一致。
7. **空输入语义**：无任何行时返回 `[]`；只有表头无数据行时也返回 `[]`（与方案"空输入输出 `[]`"一致）。

## 测试与证据

### A. unittest 完整输出

命令：`cd tools/csv2json && python3 -m unittest discover -s tests -v`

```
test_basic_stdin_stdout (test_csv2json.CLITests.test_basic_stdin_stdout) ... ok
test_chinese_cli_ensure_ascii_false (test_csv2json.CLITests.test_chinese_cli_ensure_ascii_false) ... ok
test_custom_delimiter_cli (test_csv2json.CLITests.test_custom_delimiter_cli) ... ok
test_empty_input_outputs_empty_array (test_csv2json.CLITests.test_empty_input_outputs_empty_array) ... ok
test_extra_columns_ignored_cli (test_csv2json.CLITests.test_extra_columns_ignored_cli) ... ok
test_input_file_to_output_file_pretty (test_csv2json.CLITests.test_input_file_to_output_file_pretty) ... ok
test_input_file_to_stdout (test_csv2json.CLITests.test_input_file_to_stdout) ... ok
test_invalid_delimiter_length_returns_nonzero (test_csv2json.CLITests.test_invalid_delimiter_length_returns_nonzero) ... ok
test_missing_input_file_returns_nonzero (test_csv2json.CLITests.test_missing_input_file_returns_nonzero) ... ok
test_pretty_output (test_csv2json.CLITests.test_pretty_output) ... ok
test_pretty_short_flag (test_csv2json.CLITests.test_pretty_short_flag) ... ok
test_short_row_padding_cli (test_csv2json.CLITests.test_short_row_padding_cli) ... ok
test_accepts_stringio (test_csv2json.ConvertTests.test_accepts_stringio) ... ok
test_basic_conversion (test_csv2json.ConvertTests.test_basic_conversion) ... ok
test_chinese_non_ascii (test_csv2json.ConvertTests.test_chinese_non_ascii) ... ok
test_custom_delimiter (test_csv2json.ConvertTests.test_custom_delimiter) ... ok
test_empty_input_returns_empty_list (test_csv2json.ConvertTests.test_empty_input_returns_empty_list) ... ok
test_extra_columns_ignored (test_csv2json.ConvertTests.test_extra_columns_ignored) ... ok
test_header_only_returns_empty_list (test_csv2json.ConvertTests.test_header_only_returns_empty_list) ... ok
test_short_row_padding (test_csv2json.ConvertTests.test_short_row_padding) ... ok
test_values_are_strings_no_type_inference (test_csv2json.ConvertTests.test_values_are_strings_no_type_inference) ... ok
test_acceptance_command_exact_output (test_csv2json.ExactOutputTests.test_acceptance_command_exact_output) ... ok

----------------------------------------------------------------------
Ran 22 tests in 0.464s

OK
```

测试分布：`ConvertTests` 9 个（核心逻辑）、`CLITests` 12 个（subprocess 端到端）、`ExactOutputTests` 1 个（验收命令精确输出）。

### B. 验收命令逐条验证

```text
$ printf 'a,b\n1,2\n' | python3 tools/csv2json/csv2json.py
[{"a": "1", "b": "2"}]

$ printf 'a;b\n1;2\n' > /tmp/csv2json_sample.csv
$ python3 tools/csv2json/csv2json.py -d ';' -i /tmp/csv2json_sample.csv -p
[
  {
    "a": "1",
    "b": "2"
  }
]

$ python3 tools/csv2json/csv2json.py -i /no/such/file.csv
csv2json: 错误：输入文件不存在：/no/such/file.csv
$ echo "exit=$?"
exit=1
```

### C. 标准库依赖审计

```text
$ python3 -c "import ast; t=ast.parse(open('tools/csv2json/csv2json.py').read()); ..."
imports= ['argparse', 'csv', 'json', 'sys', 'typing']
non_stdlib= none
```

`csv2json.py` 仅依赖 Python 标准库。`tests/test_csv2json.py` 也仅使用 `io`、`json`、`os`、`subprocess`、`sys`、`tempfile`、`unittest`、`pathlib` 等标准库。

### D. 工作树变更范围审计

```text
$ git status --short
?? SKILL.md
?? tasks/
?? tools/
$ git status --short tools/csv2json/
?? tools/csv2json/
```

未发现任何对 `tools/csv2json/` 之外文件的修改或删除。

## 与方案的偏差

1. **`convert()` 函数签名**：方案写为 `convert(reader_rows, ...) -> list[dict]`，含义模糊。本实现将参数明确定为 `convert(lines: Iterable[str], delimiter: str = ",") -> List[dict]`，并在 docstring 中说明 `lines` 可以来自 `open().readlines()`、`io.StringIO`、`sys.stdin` 或测试构造的字符串列表。该偏差不改变方案的外部行为或验收标准，仅澄清歧义。
2. **测试用例数量**：方案测试清单列出 7 类场景（基本转换、自定义分隔符、缺列补齐、多列截断、空输入、中文、CLI 端到端、文件不存在错误码）。本实现扩展为 22 个用例，对每类场景分别提供核心层（`convert()`）与 CLI 层（subprocess）的覆盖，并补充了 StringIO 兼容性、参数错误退出码、`-p` 短旗标、`ensure_ascii=False` 字符保留、文件输出等正向路径。
3. **README 内容**：方案要求"用法、参数表、示例、测试运行方式"，本实现额外补充了退出码说明、文件结构、限制清单，便于审查者复核。

以上偏差均未扩大任务范围或违反权限约束。

## 已知限制

1. **不做类型推断**：所有 CSV 字段值均为字符串（例如 `"42"` 不会被转换为整数 `42`），与方案要求一致。
2. **不处理 BOM**：若 CSV 文件以 UTF-8 BOM 开头，BOM 会进入第一个表头键名。本任务未在方案中要求 BOM 处理。
3. **不做 CSV 写回 / 反向转换**：明确为非目标。
4. **分隔符必须为单字符**：受 `csv.reader` 限制；非单字符时返回 exit code 2。
5. **未做 pip 打包 / PyPI 发布**：明确为非目标；用户需直接通过 `python3 tools/csv2json/csv2json.py` 调用。
6. **未在 Windows 行尾（`\r\n`）下显式测试**：但 `csv.reader` 默认正确处理；测试用例均使用 `\n`。
7. **执行者未自评分数**：按 SKILL.md 第 11 节要求，执行者不审查或批准自己的工作，最终评分交由 A。

## 待审查事项

请角色 A（reviewer）按 `control.md` 的 rubric（100 分制，target_score=90，无 blocking issue，必须含测试与证据）逐项复核以下内容：

1. **方案符合性**：交付物是否完全满足 `plan-v001.md` 第 1–6 项验收标准。
2. **测试充分性**：22 个用例是否覆盖方案中点名的全部边界条件；是否还有应补的 case（如多字节 Unicode 表头、超大文件、CRLF 行尾等）。
3. **代码质量**：`convert()` 接口选择（接受 `Iterable[str]`）是否合理；错误码分层（0/1/2）是否清晰；命名与文档是否易维护。
4. **安全与权限**：是否仅使用标准库；是否未触碰 `tools/csv2json/` 之外的文件；是否未发起网络请求；是否未引入破坏性操作。
5. **文档完整性**：README 是否覆盖用法、参数、示例、测试运行方式。
6. **`convert()` 签名偏差**：本实现相对方案的澄清是否可接受；如不可接受请明确指示改回 `Iterable[Sequence[str]]` 形式，将在下一轮 revision 中调整。
7. **测试目录位置**：测试文件位于 `tools/csv2json/tests/test_csv2json.py`，与方案描述一致；通过 `sys.path` 注入工具目录以保证可移植导入。

执行者建议：本次实施可作为 v001 提交审查；如发现 blocking 或 major 问题，请按 `REVISION_REQUIRED` 流程列出具体 ISSUE 与 acceptance 条件。
