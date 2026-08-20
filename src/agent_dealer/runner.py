"""Runner：watch 监听与调度循环（P2-02）。

- 定时全量校验（不依赖易丢失的文件系统通知）；
- 基于 event_id 去重，状态持久化到 .runner-state.json，重启不重复处理；
- 只在事件合法、recipient 匹配 adapter、任务非终态时调度；
- 达到最大返工次数或终态时停止并通知人类（打印 + 状态记录）。

Runner 只负责唤醒、超时与进程管理，不替 Agent 伪造审查结果。
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from . import validator
from .adapters.base import Adapter, AdapterResult
from .errors import E601_RUNNER, MMACError
from .store import TaskStore

STATE_FILENAME = ".runner-state.json"

# recipient 角色 -> 应触发动作的事件类型
ACTIONABLE = {
    "PLAN_READY": "execute",
    "WORK_READY": "review",
    "REVISION_REQUIRED": "revise",
}


class RunnerState:
    def __init__(self, path: str) -> None:
        self.path = path
        self.processed: List[str] = []
        self.started_at: Optional[str] = None
        self.last_event_id: Optional[str] = None
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.processed = list(data.get("processed", []))
            self.started_at = data.get("started_at")
            self.last_event_id = data.get("last_event_id")
        except (OSError, json.JSONDecodeError):
            pass

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({
                "processed": self.processed,
                "started_at": self.started_at,
                "last_event_id": self.last_event_id,
            }, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def mark(self, event_id: str) -> None:
        if event_id not in self.processed:
            self.processed.append(event_id)
        self.last_event_id = event_id
        self.save()


class Runner:
    def __init__(self, task_dir: str, adapters: Dict[str, Adapter],
                 poll_interval: float = 5.0, max_idle_cycles: Optional[int] = None) -> None:
        self.store = TaskStore(task_dir)
        self.adapters = adapters
        self.poll_interval = poll_interval
        self.max_idle_cycles = max_idle_cycles  # 测试用：None = 永久
        self.state = RunnerState(os.path.join(self.store.task_dir, STATE_FILENAME))

    def pending_action(self, report: Optional[validator.ValidationReport] = None
                       ) -> Optional[Dict[str, Any]]:
        """返回需要调度的最新可行动事件（未处理、非终态、校验通过）。

        report 允许复用本周期已生成的校验结果，避免每个轮询周期重复
        全量校验（每次校验都会重读并重哈希全部产物）。
        """
        if report is None:
            report = self.store.validate()
        if not report.ok:
            return None  # 链损坏：停止自动推进，等待人工
        if report.final_status in validator.TERMINAL:
            return None
        if not report.events:
            return None
        last = report.events[-1]
        etype = last.get("type")
        if etype not in ACTIONABLE:
            return None
        eid = last.get("event_id")
        if not isinstance(eid, str) or eid in self.state.processed:
            return None
        recipient = (last.get("recipient") or {}).get("role")
        if not isinstance(recipient, str) or recipient not in self.adapters:
            return None
        return last

    def read_control(self) -> Dict[str, Any]:
        """轻量读取 control.md（不走全量校验；报错进 report 但这里忽略）。"""
        return validator.parse_control(
            self.store.task_dir, validator.ValidationReport(self.store.task_dir))

    def role_config(self, recipient: str) -> Dict[str, str]:
        """从 control.md 取角色档位（agents_detail + workflow.permission_mode）。"""
        control = self.read_control()
        detail = (control.get("agents_detail") or {}).get(recipient) or {}
        model = detail.get("model")
        if not isinstance(model, str) or validator.is_placeholder_model(model):
            model = ""  # 未配置真实 model 时留空，不注入占位符
        return {
            "model": model,
            "effort": detail.get("effort") if isinstance(detail.get("effort"), str) else "medium",
            "thinking": detail.get("thinking") if isinstance(detail.get("thinking"), str) else "off",
            "permission_mode": (control.get("workflow") or {}).get("permission_mode", "yolo"),
        }

    def dispatch(self, event: Dict[str, Any]) -> AdapterResult:
        recipient = (event.get("recipient") or {}).get("role")
        adapter = self.adapters.get(recipient)
        if adapter is None:
            raise MMACError(E601_RUNNER, "没有处理角色 %r 的 adapter" % recipient)
        config = self.role_config(recipient) if isinstance(recipient, str) else {}
        prompt = self.build_prompt(event, config)
        result = adapter.start(self.store.task_dir, recipient, prompt, event, config)
        self.state.mark(event["event_id"])
        return result

    def build_prompt(self, event: Dict[str, Any],
                     config: Optional[Dict[str, str]] = None) -> str:
        recipient = (event.get("recipient") or {}).get("role", "?")
        cfg = config or {}
        return (
            "读取共享目录中的 SKILL.md 和任务 %s 的 control.md、coordination.md。\n"
            "你当前担任角色 %s。验证协议状态（python3 -m agent_dealer validate %s），"
            "只处理发送给该角色且尚未处理的最新事件（event_id=%s，type=%s）。\n"
            "模型档位：model=%s effort=%s thinking=%s permission_mode=%s"
            "（按客户端原生参数启用；permission_mode=yolo 时无需确认直接执行）。\n"
            "完成一次合法状态转换后写入产物和事件，然后退出。"
            % (os.path.basename(self.store.task_dir), recipient,
               self.store.task_dir, event.get("event_id"), event.get("type"),
               cfg.get("model") or "(未配置)", cfg.get("effort", "medium"),
               cfg.get("thinking", "off"), cfg.get("permission_mode", "yolo"))
        )

    def run_once(self, report: Optional[validator.ValidationReport] = None
                 ) -> Optional[AdapterResult]:
        event = self.pending_action(report)
        if event is None:
            return None
        return self.dispatch(event)

    def run(self, on_event: Optional[Any] = None) -> None:
        idle = 0
        while True:
            report = self.store.validate()
            if report.final_status in validator.TERMINAL:
                if on_event:
                    on_event("terminal", {"status": report.final_status})
                return
            result = self.run_once(report)
            if result is not None:
                idle = 0
                if on_event:
                    on_event("dispatch", result.to_dict())
            else:
                idle += 1
                if self.max_idle_cycles is not None and idle >= self.max_idle_cycles:
                    return
            time.sleep(self.poll_interval)


def load_adapters(config_path: str) -> Dict[str, Adapter]:
    """从 JSON 配置加载角色 -> adapter 映射。

    格式：{"B": {"type": "manual"}, "A": {"type": "command", "argv": ["..."]}}
    """
    from .adapters.command import CommandAdapter
    from .adapters.manual import ManualAdapter

    with open(config_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    adapters: Dict[str, Adapter] = {}
    for role, spec in raw.items():
        if not isinstance(spec, dict):
            raise MMACError(E601_RUNNER, "adapter 配置项必须为对象: %s" % role)
        atype = spec.get("type")
        if atype == "manual":
            adapters[role] = ManualAdapter()
        elif atype == "command":
            argv = spec.get("argv")
            if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
                raise MMACError(E601_RUNNER, "command adapter 需要 argv 字符串数组: %s" % role)
            adapters[role] = CommandAdapter(argv, timeout=spec.get("timeout", 1800))
        else:
            raise MMACError(E601_RUNNER, "未知 adapter 类型 %r（角色 %s）" % (atype, role))
    return adapters
