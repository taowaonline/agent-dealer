#!/usr/bin/env python3
"""兼容 shim：转发到 agent_collaboration.validator。

新代码请使用 `python3 -m agent_collaboration validate <task-dir>` 或 `collab validate`。
保留本文件以兼容既有文档与脚本中的 `python3 tools/validate.py` 调用形式。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from agent_collaboration.validator import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
