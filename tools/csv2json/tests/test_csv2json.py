"""csv2json 的 stdlib unittest 测试套件。

覆盖：
- convert() 核心转换逻辑（基本、自定义分隔符、缺列补齐、多列截断、空输入、中文）。
- main() CLI 端到端：基本 stdin/stdout、--pretty、自定义分隔符、stdin + 文件输出、
  不存在输入文件的错误码、空输入返回 []。
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# 让测试无论从 tests/ 还是仓库根运行都能导入到 csv2json
TOOL_DIR = Path(__file__).resolve().parent.parent
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import csv2json  # noqa: E402

CSV2JSON_SCRIPT = TOOL_DIR / "csv2json.py"
PY = sys.executable


def run_cli(args, stdin_data=None):
    """以子进程方式调用 csv2json CLI。"""
    cmd = [PY, str(CSV2JSON_SCRIPT), *args]
    return subprocess.run(
        cmd,
        input=stdin_data,
        capture_output=True,
        text=True,
    )


class ConvertTests(unittest.TestCase):
    def test_basic_conversion(self):
        lines = ["a,b\n", "1,2\n", "3,4\n"]
        self.assertEqual(
            csv2json.convert(lines),
            [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}],
        )

    def test_custom_delimiter(self):
        lines = ["a;b\n", "1;2\n"]
        self.assertEqual(csv2json.convert(lines, delimiter=";"), [{"a": "1", "b": "2"}])

    def test_short_row_padding(self):
        lines = ["a,b,c\n", "1\n"]
        self.assertEqual(csv2json.convert(lines), [{"a": "1", "b": "", "c": ""}])

    def test_extra_columns_ignored(self):
        lines = ["a,b\n", "1,2,3,4\n"]
        self.assertEqual(csv2json.convert(lines), [{"a": "1", "b": "2"}])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(csv2json.convert(iter([])), [])

    def test_header_only_returns_empty_list(self):
        lines = ["a,b\n"]
        self.assertEqual(csv2json.convert(lines), [])

    def test_chinese_non_ascii(self):
        lines = ["姓名,城市\n", "小明,北京\n", "小红,上海\n"]
        self.assertEqual(
            csv2json.convert(lines),
            [{"姓名": "小明", "城市": "北京"}, {"姓名": "小红", "城市": "上海"}],
        )

    def test_values_are_strings_no_type_inference(self):
        lines = ["n,f\n", "42,3.14\n"]
        out = csv2json.convert(lines)
        self.assertEqual(out, [{"n": "42", "f": "3.14"}])
        self.assertIsInstance(out[0]["n"], str)
        self.assertIsInstance(out[0]["f"], str)

    def test_accepts_stringio(self):
        # 验证 file-like 对象也能作为输入
        buf = io.StringIO("a,b\n1,2\n")
        self.assertEqual(csv2json.convert(buf), [{"a": "1", "b": "2"}])


class CLITests(unittest.TestCase):
    def test_basic_stdin_stdout(self):
        result = run_cli([], stdin_data="a,b\n1,2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"a": "1", "b": "2"}])

    def test_pretty_output(self):
        result = run_cli(["--pretty"], stdin_data="a,b\n1,2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        # pretty 应该使用缩进，包含换行与空格
        self.assertIn('  "a":', result.stdout)
        self.assertEqual(json.loads(result.stdout), [{"a": "1", "b": "2"}])

    def test_pretty_short_flag(self):
        result = run_cli(["-p"], stdin_data="a,b\n1,2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"a": "1", "b": "2"}])

    def test_custom_delimiter_cli(self):
        result = run_cli(["-d", ";"], stdin_data="a;b\n1;2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"a": "1", "b": "2"}])

    def test_short_row_padding_cli(self):
        result = run_cli([], stdin_data="a,b,c\n1\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"a": "1", "b": "", "c": ""}])

    def test_extra_columns_ignored_cli(self):
        result = run_cli([], stdin_data="a,b\n1,2,3,4\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [{"a": "1", "b": "2"}])

    def test_empty_input_outputs_empty_array(self):
        result = run_cli([], stdin_data="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")

    def test_chinese_cli_ensure_ascii_false(self):
        result = run_cli([], stdin_data="姓名,城市\n小明,北京\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        # ensure_ascii=False 应保留中文
        self.assertIn("小明", result.stdout)
        self.assertEqual(json.loads(result.stdout), [{"姓名": "小明", "城市": "北京"}])

    def test_input_file_to_stdout(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
            fh.write("a,b\n1,2\n3,4\n")
            path = fh.name
        try:
            result = run_cli(["-i", path])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}],
            )
        finally:
            os.unlink(path)

    def test_input_file_to_output_file_pretty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "in.csv")
            out_path = os.path.join(tmpdir, "out.json")
            with open(in_path, "w", encoding="utf-8", newline="") as fh:
                fh.write("a;b\n1;2\n")
            result = run_cli(["-i", in_path, "-o", out_path, "-d", ";", "-p"])
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(out_path, "r", encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn('"a":', text)
            self.assertEqual(json.loads(text), [{"a": "1", "b": "2"}])

    def test_missing_input_file_returns_nonzero(self):
        result = run_cli(["-i", "/this/path/should/not/exist.csv"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不存在", result.stderr)
        self.assertIn("/this/path/should/not/exist.csv", result.stderr)

    def test_invalid_delimiter_length_returns_nonzero(self):
        result = run_cli(["-d", ";;"], stdin_data="a,b\n1,2\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("分隔符", result.stderr)


class ExactOutputTests(unittest.TestCase):
    """针对 plan-v001.md 验收标准中给出的精确输出格式做断言。"""

    def test_acceptance_command_exact_output(self):
        # printf 'a,b\n1,2\n' | python3 csv2json.py
        # 期望输出：[{"a": "1", "b": "2"}]
        result = run_cli([], stdin_data="a,b\n1,2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '[{"a": "1", "b": "2"}]')


if __name__ == "__main__":
    unittest.main()
