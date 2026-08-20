"""客户端 adapter 基类（P2-01）。

Runner 通过 adapter 唤醒下一角色；adapter 不持有业务判断，不伪造审查。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class AdapterResult:
    def __init__(self, run_id: str, state: str, detail: str = "",
                 exit_code: Optional[int] = None) -> None:
        self.run_id = run_id
        self.state = state  # started | completed | failed | notified
        self.detail = detail
        self.exit_code = exit_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state": self.state,
            "detail": self.detail,
            "exit_code": self.exit_code,
        }


class Adapter:
    name = "base"

    def detect(self) -> bool:
        """客户端/通道是否可用。"""
        return True

    def build_command(self, task_dir: str, role: str, prompt: str,
                      config: Optional[Dict[str, str]] = None) -> Optional[List[str]]:
        return None

    def start(self, task_dir: str, role: str, prompt: str,
              event: Dict[str, Any],
              config: Optional[Dict[str, str]] = None) -> AdapterResult:
        raise NotImplementedError

    def poll(self, run_id: str) -> str:
        return "unknown"

    def stop(self, run_id: str) -> AdapterResult:
        return AdapterResult(run_id, "stopped")
