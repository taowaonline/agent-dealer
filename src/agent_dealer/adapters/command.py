"""command adapter：运行用户配置的本地命令，不持有 API key。

prompt 通过环境变量 MMAC_PROMPT / MMAC_TASK_DIR / MMAC_ROLE 传递，
档位通过 MMAC_MODEL / MMAC_EFFORT / MMAC_THINKING / MMAC_PERMISSION_MODE 注入；
argv 中可用 {task_dir} {role} {model} {effort} {thinking} {permission_mode} 占位符。
非零退出码记录为 failed。
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

    def build_command(self, task_dir: str, role: str, prompt: str,
                      config: Optional[Dict[str, str]] = None) -> List[str]:
        cfg = config or {}
        values = {
            "task_dir": task_dir,
            "role": role,
            "model": cfg.get("model", ""),
            "effort": cfg.get("effort", ""),
            "thinking": cfg.get("thinking", ""),
            "permission_mode": cfg.get("permission_mode", ""),
        }
        replaced = []
        for a in self.argv:
            for key, val in values.items():
                a = a.replace("{%s}" % key, val)
            replaced.append(a)
        return replaced

    def start(self, task_dir: str, role: str, prompt: str,
              event: Dict[str, Any],
              config: Optional[Dict[str, str]] = None) -> AdapterResult:
        run_id = "cmd-%s" % uuid.uuid4()
        env = dict(os.environ)
        env.update({"MMAC_PROMPT": prompt, "MMAC_TASK_DIR": task_dir, "MMAC_ROLE": role})
        cfg = config or {}
        env.update({
            "MMAC_MODEL": cfg.get("model", ""),
            "MMAC_EFFORT": cfg.get("effort", ""),
            "MMAC_THINKING": cfg.get("thinking", ""),
            "MMAC_PERMISSION_MODE": cfg.get("permission_mode", ""),
        })
        # 子进程输出落盘到任务 tmp/，便于诊断失败；父进程句柄在 Popen 返回后即可关闭
        log_dir = os.path.join(task_dir, "tmp")
        log_path = os.path.join(log_dir, "adapter-%s.log" % run_id)
        try:
            os.makedirs(log_dir, exist_ok=True)
            with open(log_path, "ab") as log_fh:
                proc = subprocess.Popen(
                    self.build_command(task_dir, role, prompt, config),
                    cwd=task_dir, env=env,
                    stdout=log_fh, stderr=log_fh,
                )
        except OSError as ex:
            return AdapterResult(run_id, "failed", str(ex), exit_code=-1)
        self.processes[run_id] = proc
        import time
        self._started[run_id] = time.time()
        return AdapterResult(run_id, "started", "pid=%d log=%s" % (proc.pid, log_path))

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
