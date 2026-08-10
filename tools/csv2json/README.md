# csv2json

一个使用 Python 标准库实现的命令行工具：将 CSV 转换为 JSON 数组。每行 CSV 数据对应 JSON 数组中的一个对象，键取自 CSV 首行表头。所有值按字符串处理，不做类型推断。

## 特性

- 纯 Python 标准库（`csv`、`json`、`argparse`），无第三方依赖。
- 支持从文件或标准输入读取 CSV。
- 支持将 JSON 写入文件或标准输出。
- 支持自定义列分隔符（默认 `,`）。
- 支持美化输出（缩进 2 空格）。
- 列数不足的行以空字符串补齐；多余列被忽略。
- 中文等非 ASCII 字符原样输出（`ensure_ascii=False`）。

## 环境要求

- Python 3.8+
- 仅使用标准库

## 用法

```
python3 csv2json.py [-i INPUT] [-o OUTPUT] [-d DELIMITER] [-p]
```

### 参数

| 参数 | 长形式 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `-i` | `--input` | 标准输入 | 输入 CSV 文件路径；未指定时从 stdin 读取 |
| `-o` | `--output` | 标准输出 | 输出 JSON 文件路径；未指定时写入 stdout |
| `-d` | `--delimiter` | `,` | CSV 列分隔符，必须为单个字符 |
| `-p` | `--pretty` | 关闭 | 美化输出（缩进 2 空格，保留非 ASCII） |

### 退出码

- `0`：成功
- `1`：输入文件不存在或无法打开、输出文件无法写入
- `2`：参数错误（如分隔符不是单个字符）

## 示例

### 1. 从 stdin 读取，写入 stdout

```bash
printf 'a,b\n1,2\n' | python3 csv2json.py
```

输出：

```json
[{"a": "1", "b": "2"}]
```

### 2. 美化输出

```bash
printf 'a,b\n1,2\n3,4\n' | python3 csv2json.py --pretty
```

输出：

```json
[
  {
    "a": "1",
    "b": "2"
  },
  {
    "a": "3",
    "b": "4"
  }
]
```

### 3. 自定义分隔符 + 文件输入 + 文件输出

```bash
printf 'a;b\n1;2\n' > /tmp/sample.csv
python3 csv2json.py -i /tmp/sample.csv -o /tmp/out.json -d ';' -p
cat /tmp/out.json
```

### 4. 中文输出

```bash
printf '姓名,城市\n小明,北京\n' | python3 csv2json.py
```

输出：

```json
[{"姓名": "小明", "城市": "北京"}]
```

### 5. 缺列补齐与多列截断

```bash
printf 'a,b,c\n1\n' | python3 csv2json.py
# [{"a": "1", "b": "", "c": ""}]

printf 'a,b\n1,2,3,4\n' | python3 csv2json.py
# [{"a": "1", "b": "2"}]  —— 多余列忽略
```

## 测试

测试基于 stdlib `unittest`，覆盖：基本转换、自定义分隔符、缺列补齐、多列截断、空输入、中文等非 ASCII 内容、CLI 端到端（subprocess 调用，含 `--pretty` 与 stdin 输入）、输入文件不存在时的错误码。

在仓库根目录运行：

```bash
cd tools/csv2json && python3 -m unittest discover -s tests -v
```

或单文件：

```bash
python3 -m unittest tests.test_csv2json -v
```

## 文件结构

```
tools/csv2json/
├── README.md
├── csv2json.py
└── tests/
    └── test_csv2json.py
```

## 限制

- 不做类型推断（所有值都是字符串）。
- 不支持 CSV 写回或 JSON→CSV 反向转换。
- 不进行 pip 打包或 PyPI 发布。
- 不读取 BOM；如需处理 BOM 请先自行去除。
