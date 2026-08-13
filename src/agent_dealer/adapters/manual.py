"""manual adapter：不启动任何进程，输出可复制的接力提示词。

适用于无 CLI 的客户端（如 Cursor 中的模型）或纯人工接力模式。
不需要 API key。
"""
from __future__ import annotations

import sys
from typing import Any, Dict

from .base import Adapter, AdapterResult


class ManualAdapter(Adapter):
    name = "manual"

    def __init__(self, stream: Any = None) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self.notified: list = []

    def start(self, task_dir: str, role: str, prompt: str,
              event: Dict[str, Any]) -> AdapterResult:
        run_id = "manual-%s" % event.get("event_id", "unknown")
        text = "\n".join([
            "=" * 60,
            "[manual adapter] 请把以下提示词发给角色 %s 的客户端：" % role,
            "-" * 60,
            prompt,
            "=" * 60,
        ])
        print(text, file=self.stream)
        self.notified.append(run_id)
        return AdapterResult(run_id, "notified", "等待人工接力")
