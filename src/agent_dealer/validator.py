"""MMAC 协议校验器（包内核，P1/T-04）。

由 tools/validate.py 迁移而来并扩展：
- validate_task() 可编程 API，返回 ValidationReport（不直接打印）；
- 每个问题携带稳定 rule id 与错误码（见 errors.py）；
- legacy grandfather：任务目录可放 expected-warnings.json，将已知历史问题
  （占位 model / legacy 路径 / 哈希漂移）显式降级为告警，不削弱新事件检查；
- supersede 规则：同一逻辑路径被后续链上事件以更高 version + 新哈希明确取代时，
  早期哈希不一致降级为告警；无 supersede 证据仍为错误；
- --json 机器可读输出；--candidate 只读预校验，不修改文件。

退出码：0 = 无错误（允许告警）；1 = 存在错误；2 = 用法错误。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

REQUIRED_FIELDS = [
    "event_id", "previous_event_id", "task_id", "type", "status",
    "actor", "recipient", "timestamp", "artifacts", "caused_by",
    "revision_cycle", "protocol_version",
]

EVENT_EXPECTED_STATUS: Dict[str, Optional[str]] = {
    "TASK_CREATED": "CREATED",
    "PLANNING_STARTED": "PLANNING",
    "PLAN_READY": "PLAN_READY",
    "TASK_DECOMPOSED": None,
    "TASK_CLAIMED": "CLAIMED",
    "TASK_RECLAIMED": "CLAIMED",
    "EXECUTION_STARTED": "EXECUTING",
    "REVISION_STARTED": "EXECUTING",
    "HEARTBEAT": None,
    "WORK_READY": "WORK_READY",
    "REVIEW_STARTED": "REVIEWING",
    "REVIEW_APPROVED": "APPROVED",
    "REVISION_REQUIRED": "REVISION_REQUIRED",
    "TASK_BLOCKED": "BLOCKED",
    "TASK_FAILED": "FAILED",
    "TASK_CANCELLED": "CANCELLED",
    "TASK_REOPENED": "CLAIMED",
    "ROLE_OVERRIDE": None,
    "EVENT_REJECTED": None,
}

TRANSITIONS: Dict[str, set] = {
    "CREATED": {"PLANNING", "CANCELLED"},
    "PLANNING": {"PLAN_READY", "BLOCKED", "FAILED", "CANCELLED"},
    "PLAN_READY": {"CLAIMED", "CANCELLED", "FAILED"},
    "CLAIMED": {"EXECUTING", "CLAIMED", "FAILED", "CANCELLED", "BLOCKED"},
    "EXECUTING": {"WORK_READY", "BLOCKED", "FAILED", "CANCELLED"},
    "WORK_READY": {"REVIEWING", "CLAIMED", "EXECUTING", "WORK_READY", "CANCELLED", "FAILED"},
    "REVIEWING": {"APPROVED", "REVISION_REQUIRED", "BLOCKED", "FAILED", "CANCELLED"},
    "REVISION_REQUIRED": {"CLAIMED", "EXECUTING", "BLOCKED", "FAILED", "CANCELLED"},
    "APPROVED": {"CLAIMED"},
    "BLOCKED": {"CLAIMED"},
    "FAILED": {"CLAIMED"},
    "CANCELLED": {"CLAIMED"},
}

TERMINAL = {"APPROVED", "BLOCKED", "FAILED", "CANCELLED"}
PLACEHOLDER_MODEL_TOKENS = ("configured", "configurable", "placeholder", "todo",
                            "tbd", "xxx", "unknown")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)
EVENT_RE = re.compile(
    r"<!-- MMAC-EVENT-BEGIN -->\s*```json\s*(\{.*?\})\s*```\s*<!-- MMAC-EVENT-END -->",
    re.S,
)

EVENT_BEGIN = "<!-- MMAC-EVENT-BEGIN -->"
EVENT_END = "<!-- MMAC-EVENT-END -->"


class Issue:
    """单条校验问题。rule 为稳定机读标识。"""

    def __init__(self, rule: str, message: str, event_id: Optional[str] = None) -> None:
        self.rule = rule
        self.message = message
        self.event_id = event_id

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        return {"rule": self.rule, "message": self.message, "event_id": self.event_id}

    def __eq__(self, other: Any) -> bool:
        return (isinstance(other, Issue) and self.rule == other.rule
                and self.message == other.message)


class ValidationReport:
    def __init__(self, task_dir: str) -> None:
        self.task_dir = task_dir
        self.errors: List[Issue] = []
        self.warnings: List[Issue] = []
        self.events: List[Dict[str, Any]] = []
        self.final_status: Optional[str] = None
        self.control: Dict[str, Any] = {}

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, rule: str, message: str, event_id: Optional[str] = None) -> None:
        self.errors.append(Issue(rule, message, event_id))

    def warn(self, rule: str, message: str, event_id: Optional[str] = None) -> None:
        self.warnings.append(Issue(rule, message, event_id))

    def to_dict(self) -> Dict[str, Any]:
        last = self.events[-1] if self.events else {}
        return {
            "task_dir": self.task_dir,
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
            "event_count": len(self.events),
            "final_status": self.final_status,
            "last_event_type": last.get("type"),
            "last_actor": (last.get("actor") or {}).get("instance_id"),
        }


def _short(value: Any) -> str:
    s = str(value)
    return s if len(s) <= 12 else s[:12]


def is_placeholder_model(model: Any) -> bool:
    if not isinstance(model, str) or not model.strip():
        return True
    low = model.strip().lower()
    return any(tok in low for tok in PLACEHOLDER_MODEL_TOKENS)


# ---------------------------------------------------------------- control.md

def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value in ("true", "false"):
        return value == "true"
    if value in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith("[") and value.endswith("]"):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else value
        except json.JSONDecodeError:
            return [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
    return value.strip("'\"")


def _section_map(text: str, name: str) -> Dict[str, Any]:
    match = re.search(
        rf"(?m)^{re.escape(name)}:\s*\n((?:^[ \t]+[^\n]*(?:\n|$))*)",
        text,
    )
    if not match:
        return {}
    result: Dict[str, Any] = {}
    for line in match.group(1).splitlines():
        field = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
        if field:
            result[field.group(1)] = _parse_scalar(field.group(2))
    return result


def _parse_agents(text: str) -> Dict[str, Dict[str, Any]]:
    match = re.search(r"(?m)^agents:\s*\n((?:^[ \t]+[^\n]*(?:\n|$))*)", text)
    if not match:
        return {}
    detail: Dict[str, Dict[str, Any]] = {}
    current: Optional[str] = None
    for line in match.group(1).splitlines():
        role = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", line)
        if role:
            current = role.group(1)
            detail.setdefault(current, {})
            continue
        field = re.match(r"^    ([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
        if field and current:
            detail[current][field.group(1)] = _parse_scalar(field.group(2))
    return detail


def parse_control(task_dir: str, report: ValidationReport) -> Dict[str, Any]:
    path = os.path.join(task_dir, "control.md")
    if not os.path.isfile(path):
        report.error("control-missing", "找不到 control.md: %s" % path)
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as ex:
        report.error("control-unreadable", "control.md 读取失败: %s" % ex)
        return {}

    agents_block = re.search(r"(?m)^agents:\s*\n((?:^[ \t]+[^\n]*(?:\n|$))*)", text)
    agent_roles: List[str] = []
    if agents_block:
        agent_roles = re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$", agents_block.group(1))

    control = {
        "task": _section_map(text, "task"),
        "workflow": _section_map(text, "workflow"),
        "quality_gate": _section_map(text, "quality_gate"),
        "rubric": _section_map(text, "rubric"),
        "permissions": _section_map(text, "permissions"),
        "agent_roles": agent_roles,
        "agents_detail": _parse_agents(text),
    }
    if not agent_roles:
        report.error("control-agents-missing",
                     "control.md 缺少 agents 角色映射，无法执行角色授权校验")
    required = {
        "workflow": ("planning_agent", "default_executor", "multimodal_executor", "reviewer"),
        "quality_gate": ("target_score", "max_score", "max_revision_cycles"),
        "permissions": ("allowed_paths", "forbidden_paths"),
    }
    for section, fields in required.items():
        for field in fields:
            if field not in control[section]:
                report.error("control-field-missing", "control.md 缺少 %s.%s" % (section, field))
    for field in ("planning_agent", "default_executor", "multimodal_executor", "reviewer"):
        if field in control["workflow"] and not isinstance(control["workflow"][field], str):
            report.error("control-field-type", "control.md workflow.%s 必须为字符串" % field)
    for field in ("target_score", "max_score", "max_revision_cycles"):
        value = control["quality_gate"].get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            report.error("control-field-type",
                         "control.md quality_gate.%s 必须为非负整数" % field)
    if (isinstance(control["quality_gate"].get("target_score"), int)
            and isinstance(control["quality_gate"].get("max_score"), int)
            and not isinstance(control["quality_gate"].get("target_score"), bool)
            and control["quality_gate"]["target_score"] > control["quality_gate"]["max_score"]):
        report.error("control-field-range", "control.md target_score 不得高于 max_score")
    for field in ("allowed_paths", "forbidden_paths"):
        value = control["permissions"].get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            report.error("control-field-type",
                         "control.md permissions.%s 必须为字符串数组" % field)
    rubric = control["rubric"]
    if rubric and (not all(isinstance(v, int) and not isinstance(v, bool) for v in rubric.values())
                   or sum(rubric.values()) != 100):
        report.error("control-rubric", "control.md rubric 权重必须全部为整数且总和为 100")
    for role, detail in control["agents_detail"].items():
        if "effort" in detail and detail["effort"] not in ("low", "medium", "high", "max"):
            report.error("control-effort-invalid",
                         "control.md agents.%s.effort 必须为 low/medium/high/max" % role)
        if "thinking" in detail and detail["thinking"] not in ("on", "off"):
            report.error("control-thinking-invalid",
                         "control.md agents.%s.thinking 必须为 on/off" % role)
    if ("permission_mode" in control["workflow"]
            and control["workflow"]["permission_mode"] not in ("yolo", "confirm")):
        report.error("control-permission-mode-invalid",
                     "control.md workflow.permission_mode 必须为 yolo/confirm")
    return control

# ---------------------------------------------------------------- 字段层

def validate_event_fields(idx: int, e: Dict[str, Any], report: ValidationReport) -> None:
    eid = e.get("event_id", "#%d" % idx)
    sid = _short(eid)

    for f in REQUIRED_FIELDS:
        if f not in e:
            report.error("missing-field", "事件 %s 缺少必需字段 %s" % (sid, f), eid if isinstance(eid, str) else None)

    eid_val = e.get("event_id")
    if not isinstance(eid_val, str) or not eid_val.strip():
        report.error("bad-event-id", "事件 #%d event_id 必须为非空字符串，实际类型 %s"
                     % (idx, type(eid_val).__name__))

    tid = e.get("task_id")
    if not isinstance(tid, str) or not tid.strip():
        report.error("bad-task-id", "事件 %s task_id 必须为非空字符串" % sid)

    for f in ("type", "status"):
        v = e.get(f)
        if not isinstance(v, str) or not v.strip():
            report.error("bad-field-type", "事件 %s %s 必须为非空字符串" % (sid, f))

    pv = e.get("protocol_version")
    if not isinstance(pv, str) or not pv.strip():
        report.error("bad-protocol-version", "事件 %s protocol_version 必须为非空字符串" % sid)

    ts = e.get("timestamp")
    if isinstance(ts, str):
        if not ISO_RE.match(ts):
            report.error("bad-timestamp", "事件 %s timestamp 不符合 ISO 8601+时区格式: %r" % (sid, ts))
        else:
            try:
                datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError as ex:
                report.error("bad-timestamp", "事件 %s timestamp 无法解析: %r (%s)" % (sid, ts, ex))
    else:
        report.error("bad-timestamp", "事件 %s timestamp 必须为字符串" % sid)

    rc = e.get("revision_cycle")
    if not isinstance(rc, int) or isinstance(rc, bool) or rc < 0:
        report.error("bad-revision-cycle", "事件 %s revision_cycle 必须为非负整数，实际 %r" % (sid, rc))

    actor = e.get("actor")
    if not isinstance(actor, dict):
        report.error("bad-actor", "事件 %s actor 必须为对象" % sid)
    else:
        for k in ("role", "instance_id", "provider", "client", "model"):
            v = actor.get(k)
            if not isinstance(v, str) or not v.strip():
                report.error("bad-actor", "事件 %s actor.%s 必须为非空字符串" % (sid, k))
        if isinstance(actor.get("model"), str) and is_placeholder_model(actor.get("model")):
            report.error(
                "placeholder-model",
                "事件 %s actor.model 不得为占位符: %r（应填实际模型标识，如 glm-5.2 / gpt-5.6-luna / kimi-k2.5）"
                % (sid, actor.get("model")),
                eid if isinstance(eid, str) else None,
            )

    recipient = e.get("recipient")
    if not isinstance(recipient, dict):
        report.error("bad-recipient", "事件 %s recipient 必须为对象" % sid)
    else:
        rr = recipient.get("role")
        if not isinstance(rr, str) or not rr.strip():
            report.error("bad-recipient", "事件 %s recipient.role 必须为非空字符串" % sid)

    pe = e.get("previous_event_id")
    if not (pe is None or (isinstance(pe, str) and pe.strip())):
        report.error("bad-previous", "事件 %s previous_event_id 必须为字符串或 null" % sid)

    cb = e.get("caused_by")
    if not (cb is None or (isinstance(cb, str) and cb.strip())):
        report.error("bad-caused-by", "事件 %s caused_by 必须为字符串或 null" % sid)

    arts = e.get("artifacts")
    if not isinstance(arts, list):
        report.error("bad-artifacts", "事件 %s artifacts 必须为数组" % sid)
        return
    for j, a in enumerate(arts):
        if not isinstance(a, dict):
            report.error("bad-artifact", "事件 %s artifacts[%d] 必须为对象" % (sid, j))
            continue
        for k in ("path", "sha256", "media_type"):
            v = a.get(k)
            if not isinstance(v, str) or not v.strip():
                report.error("bad-artifact", "事件 %s artifacts[%d].%s 必须为非空字符串" % (sid, j, k))
        ver = a.get("version")
        if not isinstance(ver, int) or isinstance(ver, bool) or ver < 1:
            report.error("bad-artifact-version", "事件 %s artifacts[%d].version 必须为 >=1 的整数" % (sid, j))
        sh = a.get("sha256")
        if isinstance(sh, str) and not SHA256_RE.match(sh):
            report.error("bad-sha256", "事件 %s artifacts[%d].sha256 不是合法的 SHA-256 hex: %r" % (sid, j, sh))
        p = a.get("path")
        if isinstance(p, str) and not os.path.isabs(p):
            norm = os.path.normpath(p)
            if norm.startswith("../") or norm == ".." or "/.." in norm:
                report.error("path-traversal", "事件 %s artifacts[%d].path 含非法 `..` 穿越: %r" % (sid, j, p))


# ---------------------------------------------------------------- 引用与链

def validate_references(events: List[Dict[str, Any]], report: ValidationReport) -> None:
    id_set: Dict[str, int] = {}
    for i, e in enumerate(events):
        eid = e.get("event_id")
        if not isinstance(eid, str):
            continue
        if eid in id_set:
            report.error("duplicate-event-id",
                         "event_id 重复：%s（第 %d 与第 %d 个事件）" % (eid, id_set[eid] + 1, i + 1))
        else:
            id_set[eid] = i

    prev: Optional[str] = None
    seen_prev: Dict[str, str] = {}
    for i, e in enumerate(events):
        eid = e.get("event_id", "#%d" % i)
        pe = e.get("previous_event_id")
        if i == 0:
            if pe is not None:
                report.error("broken-chain", "首个事件 %s 的 previous_event_id 必须为 null，实际 %s"
                             % (_short(eid), _short(pe)))
        else:
            if not isinstance(pe, str):
                report.error("broken-chain", "事件 %s previous_event_id 必须为字符串（首事件之后）" % _short(eid))
            elif pe != prev:
                report.error("broken-chain", "事件链断裂：%s 的 previous_event_id=%s，期望 %s"
                             % (_short(eid), _short(pe), _short(prev)))
            if pe in seen_prev:
                report.error("fork", "检测到分叉：%s 与 %s 引用同一 previous_event_id=%s"
                             % (_short(eid), _short(seen_prev[pe]), _short(pe)))
            else:
                seen_prev[pe] = eid if isinstance(eid, str) else str(eid)
        prev = eid if isinstance(eid, str) else prev

    prior_ids: set = set()
    for i, e in enumerate(events):
        eid = e.get("event_id", "#%d" % i)
        cb = e.get("caused_by")
        if cb is not None and isinstance(cb, str) and cb not in prior_ids:
            report.error("bad-caused-by",
                         "事件 %s caused_by 必须引用更早事件，实际为不存在或未来事件: %s"
                         % (_short(eid), _short(cb)))
        if isinstance(eid, str):
            prior_ids.add(eid)


# ---------------------------------------------------------------- 状态机

def validate_state_machine(events: List[Dict[str, Any]], report: ValidationReport) -> Optional[str]:
    if not events:
        return None

    base_tid = events[0].get("task_id")
    for i, e in enumerate(events[1:], 1):
        if e.get("task_id") != base_tid:
            report.error("task-id-mismatch", "task_id 不一致：事件 #%d task_id=%r，预期 %r"
                         % (i, e.get("task_id"), base_tid))

    status: Optional[str] = None
    for i, e in enumerate(events):
        eid = e.get("event_id", "#%d" % i)
        etype = e.get("type")
        new_status = e.get("status")

        if isinstance(etype, str) and etype in EVENT_EXPECTED_STATUS:
            expected = EVENT_EXPECTED_STATUS[etype]
            if expected is not None and new_status != expected:
                report.error("type-status-mismatch",
                             "事件 %s 类型 %s 期望 status=%s，实际 %r"
                             % (_short(eid), etype, expected, new_status))

        if i == 0:
            if etype != "TASK_CREATED":
                report.error("first-event", "首个事件必须为 TASK_CREATED，实际 %r" % etype)
            if new_status != "CREATED":
                report.error("first-event", "首个事件 status 必须为 CREATED，实际 %r" % new_status)

        if isinstance(etype, str) and etype not in EVENT_EXPECTED_STATUS:
            report.error("unknown-event-type", "事件 %s 类型 %s 未在 EVENT_EXPECTED_STATUS 中定义"
                         % (_short(eid), etype))
            continue

        if isinstance(etype, str) and EVENT_EXPECTED_STATUS.get(etype) is None:
            if status is None or new_status != status:
                report.error("status-keeping-violation",
                             "状态保持事件 %s %s 不得改变 status：当前 %r，事件填写 %r"
                             % (_short(eid), etype, status, new_status))
            continue

        if status is None:
            pass
        elif status in TERMINAL:
            if etype != "TASK_REOPENED":
                report.error("terminal-guard",
                             "终态 %s 之后仍出现状态变更事件 %s -> %s（事件 %s）"
                             % (status, etype, new_status, _short(eid)))
        elif new_status != status and new_status not in TRANSITIONS.get(status, set()):
            report.error("illegal-transition", "非法状态流转：%s -> %s（事件 %s %s）"
                         % (status, new_status, _short(eid), etype))

        if isinstance(new_status, str):
            status = new_status

    return status

# ---------------------------------------------------------------- control 策略

def _event_payload(e: Dict[str, Any]) -> Dict[str, Any]:
    payload = e.get("payload")
    return payload if isinstance(payload, dict) else {}


def validate_control_policy(events: List[Dict[str, Any]], control: Dict[str, Any],
                            report: ValidationReport) -> None:
    if not control:
        return
    workflow = control.get("workflow", {})
    quality = control.get("quality_gate", {})
    planner = workflow.get("planning_agent")
    reviewer = workflow.get("reviewer")
    executors = {workflow.get("default_executor"), workflow.get("multimodal_executor")}
    executors.discard(None)
    registered = set(control.get("agent_roles", [])) | {"human", "coordinator"}

    planner_types = {"PLANNING_STARTED", "PLAN_READY", "TASK_DECOMPOSED"}
    reviewer_types = {"REVIEW_STARTED", "REVIEW_APPROVED", "REVISION_REQUIRED"}
    executor_types = {
        "TASK_CLAIMED", "TASK_RECLAIMED", "EXECUTION_STARTED",
        "REVISION_STARTED", "HEARTBEAT", "WORK_READY",
    }

    # Solo 模式（workflow.mode == "solo"）：单个会话/客户端扮演全部角色。
    # 角色门槛放宽为「任一工作流角色」，但 REVIEW_APPROVED 的证据门槛
    # 提高（self_review + reproduced_commands，见下）——用机械证据替代
    # 第二模型的独立判断。默认 multi 模式行为不变。
    solo = workflow.get("mode", "multi") == "solo"
    solo_roles = {planner, reviewer} | executors

    subtasks: Dict[str, Optional[str]] = {}
    for e in events:
        payload = _event_payload(e)
        values = payload.get("subtasks")
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, str) and item:
                subtasks.setdefault(item, None)
            elif isinstance(item, dict):
                sid = item.get("id") or item.get("subtask_id")
                owner = item.get("owner") or item.get("recipient")
                if isinstance(sid, str) and sid:
                    subtasks[sid] = owner if isinstance(owner, str) else subtasks.get(sid)

    ready_subtasks: set = set()
    override_roles: set = set()
    previous_cycle = 0

    def _int(value: Any, default: int) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    max_cycles = _int(quality.get("max_revision_cycles", 3), 3)
    target_score = _int(quality.get("target_score", 90), 90)
    max_score = _int(quality.get("max_score", 100), 100)
    require_subtask_ids = workflow.get("require_subtask_ids", False) is True

    for index, e in enumerate(events):
        eid = e.get("event_id", "#%d" % index)
        sid = _short(eid)
        etype = e.get("type")
        actor = e.get("actor") if isinstance(e.get("actor"), dict) else {}
        role = actor.get("role")
        recipient = e.get("recipient") if isinstance(e.get("recipient"), dict) else {}
        recipient_role = recipient.get("role")
        payload = _event_payload(e)
        cycle = e.get("revision_cycle")

        if isinstance(role, str) and registered and role not in registered:
            report.error("unregistered-role", "事件 %s actor.role=%r 未在 control.md 注册" % (sid, role))
        if isinstance(recipient_role, str) and registered and recipient_role not in registered:
            report.error("unregistered-role", "事件 %s recipient.role=%r 未在 control.md 注册" % (sid, recipient_role))

        if etype == "TASK_CREATED" and role not in {planner, "human", "coordinator"}:
            report.error("unauthorized-role",
                         "事件 %s TASK_CREATED 只能由 planning_agent、人类或协调器发布" % sid)
        if etype in planner_types and role != planner and not (solo and role in solo_roles):
            report.error("unauthorized-role",
                         "事件 %s %s 只能由 planning_agent=%s 发布，实际 %s" % (sid, etype, planner, role))
        if etype in reviewer_types and role != reviewer and not (solo and role in solo_roles):
            report.error("unauthorized-role",
                         "事件 %s %s 只能由 reviewer=%s 发布，实际 %s" % (sid, etype, reviewer, role))
        if etype == "TASK_REOPENED" and role not in {"human", "coordinator"}:
            report.error("unauthorized-role", "事件 %s TASK_REOPENED 只能由 human/coordinator 发布" % sid)
        if etype == "ROLE_OVERRIDE":
            if role not in {"human", "coordinator"}:
                report.error("unauthorized-role", "事件 %s ROLE_OVERRIDE 只能由 human/coordinator 发布" % sid)
            granted = payload.get("role") or payload.get("allow_role")
            if isinstance(granted, str):
                override_roles.add(granted)
        if etype in executor_types and role not in executors | override_roles and not (solo and role in solo_roles):
            report.error("unauthorized-role",
                         "事件 %s %s 只能由执行角色 %s 发布，实际 %s"
                         % (sid, etype, sorted(executors | override_roles), role))

        if isinstance(cycle, int) and not isinstance(cycle, bool):
            if cycle > max_cycles:
                report.error("revision-limit", "事件 %s revision_cycle=%d 超过上限 %d" % (sid, cycle, max_cycles))
            if cycle < previous_cycle or cycle > previous_cycle + 1:
                report.error("revision-jump", "事件 %s revision_cycle 非法跳变：%d -> %d"
                             % (sid, previous_cycle, cycle))
            previous_cycle = cycle

        subtask_id = payload.get("subtask_id")
        if subtask_id is None and isinstance(payload.get("subtask"), str):
            subtask_id = payload.get("subtask")
            report.warn("legacy-subtask-field",
                        "legacy 子任务字段：事件 %s 使用 payload.subtask；新事件改用 subtask_id" % sid)
        if isinstance(subtask_id, str):
            if subtasks and subtask_id not in subtasks:
                report.error("unknown-subtask", "事件 %s 引用未声明子任务 %r" % (sid, subtask_id))
            owner = subtasks.get(subtask_id)
            if owner and etype in executor_types and role != owner:
                report.error("subtask-owner-mismatch",
                             "事件 %s 子任务 %s owner=%s，实际 actor=%s" % (sid, subtask_id, owner, role))
            if etype == "WORK_READY":
                ready_subtasks.add(subtask_id)
        elif len(subtasks) == 1 and etype == "WORK_READY":
            ready_subtasks.update(subtasks)
        elif len(subtasks) > 1 and etype in executor_types:
            message = "并行任务事件 %s %s 缺少 payload.subtask_id" % (sid, etype)
            if require_subtask_ids:
                report.error("missing-subtask-id", message)
            else:
                report.warn("missing-subtask-id", "legacy " + message)

        if etype == "REVIEW_STARTED" and subtasks:
            missing = sorted(set(subtasks) - ready_subtasks)
            if missing:
                report.error("premature-review",
                             "事件 %s 在子任务全部 WORK_READY 前开始审查，缺少 %s" % (sid, missing))

        if etype == "REVISION_REQUIRED":
            if isinstance(cycle, int) and not isinstance(cycle, bool) and cycle >= max_cycles:
                report.error("revision-limit", "事件 %s 已达返工上限 %d，必须 TASK_BLOCKED" % (sid, max_cycles))
            next_cycle = payload.get("next_revision_cycle")
            if not isinstance(next_cycle, int) or next_cycle != cycle + 1:
                report.error("bad-next-cycle", "事件 %s next_revision_cycle 必须等于 %s" % (sid, cycle + 1))

        if etype in {"REVIEW_APPROVED", "REVISION_REQUIRED"} and quality.get("enabled", True):
            score = payload.get("score")
            blocking = payload.get("blocking_issues")
            tests_passed = payload.get("required_tests_passed")
            evidence_present = payload.get("required_evidence_present")
            if not isinstance(score, int) or isinstance(score, bool) or score < 0 or score > max_score:
                report.error("bad-score", "事件 %s payload.score 必须是 0..%d 整数" % (sid, max_score))
            payload_target = payload.get("target_score")
            if payload_target is not None and payload_target != target_score:
                report.error("score-mismatch", "事件 %s target_score=%s 与 control.md=%s 不一致"
                             % (sid, payload_target, target_score))
            if not isinstance(blocking, int) or isinstance(blocking, bool) or blocking < 0:
                report.error("bad-blocking", "事件 %s blocking_issues 必须为非负整数" % sid)
            if not isinstance(tests_passed, bool) or not isinstance(evidence_present, bool):
                report.error("bad-evidence-flags", "事件 %s 测试与证据标志必须为布尔值" % sid)

            if etype == "REVIEW_APPROVED":
                if isinstance(score, int) and not isinstance(score, bool) and score < target_score:
                    report.error("quality-gate", "事件 %s 审批分数 %d 低于门槛 %d" % (sid, score, target_score))
                if quality.get("blocking_issues_must_be_zero", True) and blocking != 0:
                    report.error("quality-gate", "事件 %s 存在 blocking issue，不能 APPROVED" % sid)
                if quality.get("require_tests_when_applicable", True) and tests_passed is not True:
                    report.error("quality-gate", "事件 %s required_tests_passed 必须为 true" % sid)
                if quality.get("require_evidence", True) and evidence_present is not True:
                    report.error("quality-gate", "事件 %s required_evidence_present 必须为 true" % sid)
                review_artifacts = [
                    a for a in e.get("artifacts", []) if isinstance(a, dict)
                    and "artifacts/reviews/" in str(a.get("path", "")).replace("\\", "/")
                ]
                if not review_artifacts:
                    report.error("missing-review-artifact",
                                 "事件 %s REVIEW_APPROVED 必须引用版本化 review 产物" % sid)

        # Solo 模式的补偿性证据门槛：发布者=执行者，独立判断缺席，必须
        # 显式自证——self_review 标记 + 独立重跑过的命令清单（评审时重新
        # 执行，不接受执行时缓存的结论）。
        if solo and etype == "REVIEW_APPROVED":
            if payload.get("self_review") is not True:
                report.error("solo-review",
                             "事件 %s solo 模式 REVIEW_APPROVED 必须 payload.self_review=true" % sid)
            cmds = payload.get("reproduced_commands")
            if (not isinstance(cmds, list) or not cmds
                    or not all(isinstance(c, str) and c.strip() for c in cmds)):
                report.error("solo-review",
                             "事件 %s solo 模式 REVIEW_APPROVED 必须附 payload.reproduced_commands"
                             "（评审阶段独立重跑的命令清单）" % sid)

# ---------------------------------------------------------------- 路径与产物

def _is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(root)]) == os.path.realpath(root)
    except ValueError:
        return False


def find_collaboration_root(task_dir: str) -> str:
    """从 .../tasks/<task-id>（含其测试子目录）定位协作根目录。"""
    current = os.path.realpath(task_dir)
    while True:
        if os.path.basename(current) == "tasks":
            return os.path.dirname(current)
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.realpath(os.getcwd())
        current = parent


def _permission_roots(control: Dict[str, Any], collaboration_root: str
                      ) -> Tuple[List[str], List[str]]:
    permissions = control.get("permissions", {}) if control else {}
    allowed_raw = permissions.get("allowed_paths", ["./"])
    forbidden_raw = permissions.get("forbidden_paths", [])

    def resolve(values: Any) -> List[str]:
        if not isinstance(values, list):
            values = [values]
        roots: List[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            roots.append(os.path.realpath(
                value if os.path.isabs(value) else os.path.join(collaboration_root, value)
            ))
        return roots

    return resolve(allowed_raw), resolve(forbidden_raw)


def _check_allowed_path(full: str, control: Dict[str, Any], collaboration_root: str,
                        report: ValidationReport, eid: str) -> bool:
    real = os.path.realpath(full)
    allowed, forbidden = _permission_roots(control, collaboration_root)
    if not allowed or not any(_is_within(real, root) for root in allowed):
        report.error("path-not-allowed", "事件 %s 产物路径超出 permissions.allowed_paths: %r"
                     % (_short(eid), full))
        return False
    if any(_is_within(real, root) for root in forbidden):
        report.error("path-forbidden", "事件 %s 产物路径命中 permissions.forbidden_paths: %r"
                     % (_short(eid), full))
        return False
    return True


def resolve_artifact_path(path: str, task_dir: str, collaboration_root: str,
                          control: Dict[str, Any], report: ValidationReport,
                          eid: str) -> Optional[str]:
    """解析产物路径（只读），含 legacy fallback。"""
    if not isinstance(path, str) or not path.strip():
        report.error("artifact-missing", "事件 %s 含空产物 path" % _short(eid))
        return None

    if os.path.isabs(path):
        if not os.path.isfile(path):
            return None
        return path if _check_allowed_path(path, control, collaboration_root, report, eid) else None

    primary = os.path.normpath(os.path.join(task_dir, path))
    if os.path.isfile(primary):
        if not _is_within(primary, task_dir):
            report.error("symlink-escape", "事件 %s 相对产物通过符号链接逃逸任务目录: %r" % (_short(eid), path))
            return None
        return primary if _check_allowed_path(primary, control, collaboration_root, report, eid) else None

    norm = os.path.normpath(path)
    if norm.startswith("..") or norm == "..":
        return None

    legacy = os.path.normpath(os.path.join(collaboration_root, path))
    if not _is_within(legacy, collaboration_root):
        report.error("path-traversal", "事件 %s legacy 路径解析逃逸 repo root: %r" % (_short(eid), path))
        return None
    if os.path.isfile(legacy):
        if not _check_allowed_path(legacy, control, collaboration_root, report, eid):
            return None
        report.warn("legacy-path",
                    "legacy fallback：事件 %s 产物 %r 不在任务目录 %s 下，已使用仓库根相对路径 %s（只读，未修改历史文件）"
                    % (_short(eid), path, task_dir, legacy))
        return legacy

    return None


def _norm_logical_path(path: str) -> str:
    return os.path.normpath(path).replace("\\", "/")


def _build_supersede_index(events: List[Dict[str, Any]]) -> Dict[str, List[Tuple[int, int, str]]]:
    """path -> [(event_index, version, sha256)]，按链顺序。"""
    index: Dict[str, List[Tuple[int, int, str]]] = {}
    for i, e in enumerate(events):
        arts = e.get("artifacts")
        if not isinstance(arts, list):
            continue
        for a in arts:
            if not isinstance(a, dict):
                continue
            p = a.get("path")
            v = a.get("version")
            s = a.get("sha256")
            if isinstance(p, str) and isinstance(v, int) and isinstance(s, str):
                index.setdefault(_norm_logical_path(p), []).append((i, v, s))
    return index


def validate_artifacts(events: List[Dict[str, Any]], task_dir: str,
                       collaboration_root: str, control: Dict[str, Any],
                       report: ValidationReport) -> None:
    supersede_index = _build_supersede_index(events)
    for i, e in enumerate(events):
        eid = e.get("event_id", "?")
        arts = e.get("artifacts")
        if not isinstance(arts, list):
            continue
        for a in arts:
            if not isinstance(a, dict):
                continue
            p = a.get("path", "")
            full = resolve_artifact_path(p, task_dir, collaboration_root, control, report, eid)
            if full is None:
                report.error("artifact-missing", "产物缺失：%s（事件 %s）" % (p, _short(eid)),
                             eid if isinstance(eid, str) else None)
                continue
            try:
                h = hashlib.sha256()
                with open(full, "rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        h.update(chunk)
            except OSError as ex:
                report.error("artifact-unreadable", "产物读取失败：%s（事件 %s）：%s" % (p, _short(eid), ex))
                continue
            actual = h.hexdigest()
            expected = a.get("sha256")
            if actual == expected:
                continue
            # supersede：同一逻辑路径在后续事件中以更高版本或匹配当前文件的新哈希取代
            entries = supersede_index.get(_norm_logical_path(p), [])
            later = [(j, v, s) for (j, v, s) in entries if j > i]
            version = a.get("version")
            superseded = any(
                (isinstance(version, int) and v > version) or s == actual
                for (j, v, s) in later
            )
            if superseded:
                report.warn("superseded",
                            "产物已被后续事件 supersede：%s（事件 %s）expected=%s 当前文件=%s…，视为合法版本演进"
                            % (p, _short(eid), _short(expected), actual[:12]),
                            eid if isinstance(eid, str) else None)
            else:
                report.error("hash-mismatch",
                             "产物哈希不一致：%s（事件 %s）expected=%s actual=%s…"
                             % (p, _short(eid), _short(expected), actual[:12]),
                             eid if isinstance(eid, str) else None)


# ---------------------------------------------------------------- 事件解析

def parse_events(text: str, report: ValidationReport) -> List[Dict[str, Any]]:
    begins = text.count(EVENT_BEGIN)
    ends = text.count(EVENT_END)
    if begins != ends:
        report.error("marker-mismatch", "事件标记不配对：BEGIN=%d END=%d" % (begins, ends))

    blocks = EVENT_RE.findall(text)
    if begins != len(blocks):
        report.error("marker-mismatch", "有效事件块数量(%d)与 BEGIN 标记数(%d)不一致，存在残缺事件"
                     % (len(blocks), begins))

    events: List[Dict[str, Any]] = []
    for i, raw in enumerate(blocks, 1):
        try:
            e = json.loads(raw)
        except json.JSONDecodeError as ex:
            report.error("json-invalid", "第 %d 个事件 JSON 非法: %s" % (i, ex))
            continue
        if not isinstance(e, dict):
            report.error("json-invalid", "第 %d 个事件 JSON 顶层必须为对象" % i)
            continue
        events.append(e)
    return events


def serialize_event(event: Dict[str, Any], indent: Optional[int] = 2) -> str:
    """把事件 dict 序列化为完整 MMAC 事件块。"""
    return "%s\n```json\n%s\n```\n%s" % (
        EVENT_BEGIN,
        json.dumps(event, ensure_ascii=False, indent=indent),
        EVENT_END,
    )


# ---------------------------------------------------------------- grandfather

def load_expected_warnings(task_dir: str) -> List[Dict[str, str]]:
    """读取可选的 expected-warnings.json：把已知历史问题显式降级为告警。

    格式：{"downgrade": [{"event_id": "<完整事件ID>", "rule": "<rule-id>"}, ...]}
    event_id 必须为完整 ID 且精确匹配；缺失或前缀通配会被拒绝（见 apply），
    防止一份配置静默降级未来的新错误。
    """
    path = os.path.join(task_dir, "expected-warnings.json")
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data.get("downgrade", [])
        return [e for e in entries
                if isinstance(e, dict) and isinstance(e.get("rule"), str)]
    except (OSError, json.JSONDecodeError):
        return []


def apply_expected_warnings(report: ValidationReport, entries: List[Dict[str, str]]) -> None:
    for entry in entries:
        rid = entry.get("event_id")
        # 必须提供 event_id 且精确匹配才允许降级；否则该条目本身报错（必须人工修正）
        if not isinstance(rid, str) or not rid.strip():
            report.error("expected-warnings-invalid",
                         "expected-warnings.json 条目必须包含 event_id（精确匹配，禁止通配）: %r" % entry)
    if report.errors and any(i.rule == "expected-warnings-invalid" for i in report.errors):
        return  # 配置非法时不执行任何降级
    kept: List[Issue] = []
    for issue in report.errors:
        matched = None
        for entry in entries:
            rid = entry.get("event_id")
            if issue.rule != entry["rule"]:
                continue
            if isinstance(rid, str) and isinstance(issue.event_id, str) \
                    and issue.event_id == rid:
                matched = entry
                break
        if matched:
            report.warn(issue.rule, "grandfathered（expected-warnings.json）：" + issue.message,
                        issue.event_id)
        else:
            kept.append(issue)
    report.errors = kept

# ---------------------------------------------------------------- 顶层 API

def validate_task(task_dir: str, candidate: Optional[Dict[str, Any]] = None,
                  use_expected_warnings: bool = True) -> ValidationReport:
    """校验任务目录；candidate 只在内存中预校验，不修改文件。"""
    task_dir = task_dir.rstrip("/")
    report = ValidationReport(task_dir)
    coord = os.path.join(task_dir, "coordination.md")
    if not os.path.isfile(coord):
        report.error("coordination-missing", "找不到 coordination.md: %s" % coord)
        return report

    try:
        with open(coord, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as ex:
        report.error("coordination-unreadable", "coordination.md 读取失败: %s" % ex)
        return report

    events = parse_events(text, report)
    if candidate is not None:
        if isinstance(candidate, dict):
            events.append(candidate)
        else:
            report.error("candidate-invalid", "候选事件 JSON 顶层必须为对象")

    control = parse_control(task_dir, report)
    report.control = control
    collaboration_root = find_collaboration_root(task_dir)

    for i, e in enumerate(events, 1):
        validate_event_fields(i, e, report)
    validate_references(events, report)
    report.final_status = validate_state_machine(events, report)
    validate_control_policy(events, control, report)
    validate_artifacts(events, task_dir, collaboration_root, control, report)

    if use_expected_warnings:
        apply_expected_warnings(report, load_expected_warnings(task_dir))

    report.events = events
    return report


def format_report(report: ValidationReport, candidate: bool = False) -> str:
    lines: List[str] = []
    for issue in report.errors:
        lines.append("✗ " + issue.message)
    for issue in report.warnings:
        lines.append("⚠ " + issue.message)
    label = "（含候选事件）" if candidate else ""
    verdict = "全部通过 ✓" if report.ok else "%d 个错误 ✗" % len(report.errors)
    lines.append("")
    lines.append("校验 %d 个事件%s：%s（%d 个告警）"
                 % (len(report.events), label, verdict, len(report.warnings)))
    if report.events:
        last = report.events[-1]
        lines.append("当前状态：%s | 最新事件：%s by %s" % (
            report.final_status, last.get("type"),
            (last.get("actor") or {}).get("instance_id", "?")))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_output = False
    if "--json" in argv:
        argv.remove("--json")
        json_output = True
    if len(argv) not in (1, 3) or (len(argv) == 3 and argv[1] != "--candidate"):
        print(__doc__)
        return 2
    task_dir = argv[0]
    candidate = None
    if len(argv) == 3:
        try:
            with open(argv[2], encoding="utf-8") as fh:
                candidate = json.load(fh)
        except (OSError, json.JSONDecodeError) as ex:
            print("✗ 候选事件读取失败: %s" % ex)
            return 1

    report = validate_task(task_dir, candidate=candidate)
    if json_output:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(report, candidate=candidate is not None))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
