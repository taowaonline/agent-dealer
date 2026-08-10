#!/usr/bin/env python3
"""csv2json — 将 CSV 转换为 JSON 数组的纯标准库命令行工具。

读取 CSV（文件或标准输入），输出 JSON 数组：每行一个对象，键取自 CSV 首行表头。
所有值均按字符串处理，不做类型推断。

用法示例：
    printf 'a,b\\n1,2\\n' | python3 csv2json.py
    python3 csv2json.py -i input.csv -o output.json --pretty -d ';'
"""

import argparse
import csv
import json
import sys
from typing import Iterable, List, Optional, Sequence


def convert(lines: Iterable[str], delimiter: str = ",") -> List[dict]:
    """将 CSV 文本行序列转换为字典列表。

    参数：
        lines: 一个迭代器，产出字符串行（每行带或不带换行符均可）。
                典型来源：open(...).readlines()、io.StringIO、sys.stdin、
                或测试中构造的 ["a,b\n", "1,2\n"]。
        delimiter: CSV 列分隔符，默认为逗号 ','。

    返回：
        list[dict]：每个 dict 对应一条数据行，键取自 CSV 首行表头。

    规则：
        - 第一行作为表头；列名取自表头。
        - 列数不足的行以空字符串补齐；多余列忽略。
        - 所有值按字符串处理，不做类型推断。
        - 空输入（无任何行）返回空列表。
        - 只有表头没有数据行时返回空列表。
    """
    reader = csv.reader(lines, delimiter=delimiter)
    headers: Optional[List[str]] = None
    result: List[dict] = []
    for raw_row in reader:
        if headers is None:
            headers = list(raw_row)
            continue
        if not raw_row:
            # csv.reader 通常不会产出空列表，但防御性处理：空行按全空值返回
            result.append({h: "" for h in (headers or [])})
            continue
        row_len = len(raw_row)
        header_len = len(headers) if headers else 0
        obj = {}
        for idx in range(header_len):
            obj[headers[idx]] = raw_row[idx] if idx < row_len else ""
        # 多余列忽略（不写入任何键）
        result.append(obj)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csv2json",
        description="将 CSV（文件或标准输入）转换为 JSON 数组。",
    )
    parser.add_argument(
        "-i", "--input",
        help="输入 CSV 文件路径；未指定时从标准输入读取。",
        default=None,
    )
    parser.add_argument(
        "-o", "--output",
        help="输出 JSON 文件路径；未指定时写入标准输出。",
        default=None,
    )
    parser.add_argument(
        "-d", "--delimiter",
        help="CSV 列分隔符，默认为逗号 ','。",
        default=",",
    )
    parser.add_argument(
        "-p", "--pretty",
        help="美化输出（缩进 2 空格，保留非 ASCII 字符）。",
        action="store_true",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    delimiter = args.delimiter
    if len(delimiter) != 1:
        print(f"csv2json: 错误：分隔符必须是单个字符，收到 {delimiter!r}", file=sys.stderr)
        return 2

    # 打开输入
    if args.input is None:
        rows_source = sys.stdin
        close_input = False
    else:
        try:
            rows_source = open(args.input, "r", encoding="utf-8", newline="")
        except FileNotFoundError:
            print(f"csv2json: 错误：输入文件不存在：{args.input}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"csv2json: 错误：无法打开输入文件 {args.input!r}：{exc}", file=sys.stderr)
            return 1
        close_input = True

    try:
        data = convert(rows_source, delimiter=delimiter)
    finally:
        if close_input:
            rows_source.close()

    if args.pretty:
        json_text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        json_text = json.dumps(data, ensure_ascii=False)

    if args.output is None:
        print(json_text)
    else:
        try:
            with open(args.output, "w", encoding="utf-8") as out_fh:
                out_fh.write(json_text)
                out_fh.write("\n")
        except OSError as exc:
            print(f"csv2json: 错误：无法写入输出文件 {args.output!r}：{exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
