"""command adapter：运行用户配置的本地命令，不持有 API key。

prompt 通过环境变量 MMAC_PROMPT / MMAC_TASK_DIR / MMAC_ROLE 传递，
argv 中可用 {task_dir} {role} 占位符。非零退出码记录为 failed。
"""
from __future__ import annotations

import os
import subprocess
import uuid
from typing import Any, Dict, List, Optional

from .base import Adapter, AdapterResult


class CommandAdapter(Adapter):
    name = "command"

    def __init__(self, argv: List[str], timeout: int = 1800) -> None:
        self.argv = argv
        self.timeout = timeout
        self.processes: Dict[str, subprocess.Popen] = {}
        self._started: Dict[str, float] = {}

    def detect(self) -> bool:
        return bool(self.argv)

    def build_command(self, task_dir: str, role: str, prompt: str) -> List[str]:
        return [a.replace("{task_dir}", task_dir).replace("{role}", role) for a in self.argv]

    def start(self, task_dir: str, role: str, prompt: str,
              event: Dict[str, Any]) -> AdapterResult:
        run_id = "cmd-%s" % uuid.uuid4()
        env = dict(os.environ)
        env.update({"MMAC_PROMPT": prompt, "MMAC_TASK_DIR": task_dir, "MMAC_ROLE": role})
        try:
            proc = subprocess.Popen(
                self.build_command(task_dir, role, prompt),
                cwd=task_dir, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as ex:
            return AdapterResult(run_id, "failed", str(ex), exit_code=-1)
        self.processes[run_id] = proc
        import time
        self._started[run_id] = time.time()
        return AdapterResult(run_id, "started", "pid=%d" % proc.pid)

    def poll(self, run_id: str) -> str:
        proc = self.processes.get(run_id)
        if proc is None:
            return "unknown"
        code = proc.poll()
        if code is None:
            import time
            started = self._started.get(run_id)
            if started is not None and time.time() - started > self.timeout:
                proc.terminate()
                return "timeout"
            return "running"
        return "completed" if code == 0 else "failed"

    def stop(self, run_id: str) -> AdapterResult:
        proc = self.processes.pop(run_id, None)
        self._started.pop(run_id, None)
        if proc is None:
            return AdapterResult(run_id, "unknown")
        if proc.poll() is None:
            proc.terminate()
        return AdapterResult(run_id, "stopped", exit_code=proc.poll())
