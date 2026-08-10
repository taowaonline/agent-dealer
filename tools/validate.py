#!/usr/bin/env python3
"""MMAC 跨模型协作协议校验器（SKILL.md §7 配套工具）。

用法：
  python3 tools/validate.py tasks/<task-id>
  python3 tools/validate.py tasks/<task-id> --candidate tmp/event.json

校验内容（v2）：
1. 事件标记配对（MMAC-EVENT-BEGIN / END）与 JSON 合法性；
2. 必需字段完整性 + 字段类型/格式（actor/recipient/timestamp/revision_cycle/sha256）；
3. event_id 全局唯一；
4. previous_event_id 链式完整、caused_by 引用合法、同一 previous 的分叉检测；
5. 状态机流转合法性、事件 type 与 status 一致性、task_id 一致性、首事件/终态后规则；
6. actor.model 必须非空且不得为占位符（configured-model / placeholder 等）；
7. control.md 驱动的角色授权、质量门、返工上限与子任务完成门槛；
8. artifacts 路径安全（拒绝 `..`、符号链接逃逸与 allowlist 越界）、SHA-256 一致性；
   - 任务目录内相对路径按当前协议解析；
   - 历史任务（如 task-001）使用相对项目根路径时，提供只读 legacy fallback 并打印告警；
   - 任务目录外文件应使用绝对路径。

`--candidate` 只在内存中把 JSON 事件接到当前事件链末尾进行预校验，不修改文件。

退出码：0 = 全部通过（允许有 legacy 告警）；1 = 存在错误。

兼容性：仅使用 Python 3.8+ 标准库；不发起网络请求；保留原有 CLI 调用形式。
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

# 标准 type -> 期望 status；None 表示该事件不改变任务状态（status-keeping）
EVENT_EXPECTED_STATUS: Dict[str, Optional[str]] = {
    "TASK_CREATED": "CREATED",
    "PLANNING_STARTED": "PLANNING",
    "PLAN_READY": "PLAN_READY",
    "TASK_DECOMPOSED": None,      # status-keeping
    "TASK_CLAIMED": "CLAIMED",
    "TASK_RECLAIMED": "CLAIMED",
    "EXECUTION_STARTED": "EXECUTING",
    "REVISION_STARTED": "EXECUTING",
    "HEARTBEAT": None,             # status-keeping
    "WORK_READY": "WORK_READY",
    "REVIEW_STARTED": "REVIEWING",
    "REVIEW_APPROVED": "APPROVED",
    "REVISION_REQUIRED": "REVISION_REQUIRED",
    "TASK_BLOCKED": "BLOCKED",
    "TASK_FAILED": "FAILED",
    "TASK_CANCELLED": "CANCELLED",
    "TASK_REOPENED": "CLAIMED",    # 人类重新打开终态任务，回到可执行状态
    "ROLE_OVERRIDE": None,         # status-keeping
    "EVENT_REJECTED": None,        # status-keeping
}

# 状态机：status -> 允许的下一 status（事件发布后的任务状态）
TRANSITIONS: Dict[str, set] = {
    "CREATED": {"PLANNING", "CANCELLED"},
    "PLANNING": {"PLAN_READY", "BLOCKED", "FAILED", "CANCELLED"},
    "PLAN_READY": {"CLAIMED", "CANCELLED", "FAILED"},
    "CLAIMED": {"EXECUTING", "CLAIMED", "FAILED", "CANCELLED", "BLOCKED"},
    "EXECUTING": {"WORK_READY", "BLOCKED", "FAILED", "CANCELLED"},
    # 并行执行：某个子任务 WORK_READY 后，另一子任务仍可 CLAIMED/EXECUTING；
    # 只有 REVIEW_STARTED 才进入 REVIEWING（语义上表示"全部 WORK_READY 收齐"）。
    "WORK_READY": {"REVIEWING", "CLAIMED", "EXECUTING", "WORK_READY", "CANCELLED", "FAILED"},
    "REVIEWING": {"APPROVED", "REVISION_REQUIRED", "BLOCKED", "FAILED", "CANCELLED"},
    "REVISION_REQUIRED": {"CLAIMED", "EXECUTING", "BLOCKED", "FAILED", "CANCELLED"},
    # 终态：仅允许 TASK_REOPENED（status -> CLAIMED）或 status-keeping
    "APPROVED": {"CLAIMED"},
    "BLOCKED": {"CLAIMED"},
    "FAILED": {"CLAIMED"},
    "CANCELLED": {"CLAIMED"},
}

TERMINAL = {"APPROVED", "BLOCKED", "FAILED", "CANCELLED"}

# 占位 model 检测关键词（小写匹配）
PLACEHOLDER_MODEL_TOKENS = ("configured", "placeholder", "todo", "tbd", "xxx")

# SHA-256 hex 格式
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# ISO 8601 带时区：YYYY-MM-DDTHH:MM:SS[.ffffff](Z|±HH:MM)
ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?"
    r"(Z|[+-]\d{2}:?\d{2})$"
)

EVENT_RE = re.compile(
    r"<!-- MMAC-EVENT-BEGIN -->\s*```json\s*(\{.*?\})\s*```\s*<!-- MMAC-EVENT-END -->",
    re.S,
)

def _parse_scalar(raw: str) -> Any:
    """解析 control.md 所需的安全 YAML 子集，不引入第三方依赖。"""
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


def parse_control(task_dir: str, errors: List[str]) -> Dict[str, Any]:
    """读取协议所需 control.md 字段；接受纯 YAML 或 fenced YAML。"""
    path = os.path.join(task_dir, "control.md")
    if not os.path.isfile(path):
        fail(errors, f"找不到 control.md: {path}")
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as ex:
        fail(errors, f"control.md 读取失败: {ex}")
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
    }
    if not agent_roles:
        fail(errors, "control.md 缺少 agents 角色映射，无法执行角色授权校验")
    required = {
        "workflow": ("planning_agent", "default_executor", "multimodal_executor", "reviewer"),
        "quality_gate": ("target_score", "max_score", "max_revision_cycles"),
        "permissions": ("allowed_paths", "forbidden_paths"),
    }
    for section, fields in required.items():
        for field in fields:
            if field not in control[section]:
                fail(errors, f"control.md 缺少 {section}.{field}")
    for field in ("planning_agent", "default_executor", "multimodal_executor", "reviewer"):
        if field in control["workflow"] and not isinstance(control["workflow"][field], str):
            fail(errors, f"control.md workflow.{field} 必须为字符串")
    for field in ("target_score", "max_score", "max_revision_cycles"):
        value = control["quality_gate"].get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            fail(errors, f"control.md quality_gate.{field} 必须为非负整数")
    if (
        isinstance(control["quality_gate"].get("target_score"), int)
        and isinstance(control["quality_gate"].get("max_score"), int)
        and control["quality_gate"]["target_score"] > control["quality_gate"]["max_score"]
    ):
        fail(errors, "control.md target_score 不得高于 max_score")
    for field in ("allowed_paths", "forbidden_paths"):
        value = control["permissions"].get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            fail(errors, f"control.md permissions.{field} 必须为字符串数组")
    rubric = control["rubric"]
    if rubric and (not all(isinstance(v, int) for v in rubric.values()) or sum(rubric.values()) != 100):
        fail(errors, "control.md rubric 权重必须全部为整数且总和为 100")
    return control


def fail(errors: List[str], msg: str) -> None:
    errors.append(msg)
    print("✗ " + msg)


def warn(warnings: List[str], msg: str) -> None:
    warnings.append(msg)
    print("⚠ " + msg)


def is_placeholder_model(model: Any) -> bool:
    if not isinstance(model, str) or not model.strip():
        return True
    low = model.strip().lower()
    return any(tok in low for tok in PLACEHOLDER_MODEL_TOKENS)


def _short(value: Any) -> str:
    s = str(value)
    return s if len(s) <= 12 else s[:12]


def validate_event_fields(
    idx: int, e: Dict[str, Any], errors: List[str]
) -> None:
    """字段存在、类型、格式校验。"""
    eid = e.get("event_id", f"#{idx}")

    # 必需字段
    for f in REQUIRED_FIELDS:
        if f not in e:
            fail(errors, f"事件 {_short(eid)} 缺少必需字段 {f}")

    # event_id：非空字符串
    eid_val = e.get("event_id")
    if not isinstance(eid_val, str) or not eid_val.strip():
        fail(errors, f"事件 #{idx} event_id 必须为非空字符串，实际类型 {type(eid_val).__name__}")

    # task_id：非空字符串
    tid = e.get("task_id")
    if not isinstance(tid, str) or not tid.strip():
        fail(errors, f"事件 {_short(eid)} task_id 必须为非空字符串")

    # type / status：非空字符串
    for f in ("type", "status"):
        v = e.get(f)
        if not isinstance(v, str) or not v.strip():
            fail(errors, f"事件 {_short(eid)} {f} 必须为非空字符串")

    # protocol_version
    pv = e.get("protocol_version")
    if not isinstance(pv, str) or not pv.strip():
        fail(errors, f"事件 {_short(eid)} protocol_version 必须为非空字符串")

    # timestamp：ISO 8601 带时区
    ts = e.get("timestamp")
    if isinstance(ts, str):
        if not ISO_RE.match(ts):
            fail(errors, f"事件 {_short(eid)} timestamp 不符合 ISO 8601+时区格式: {ts!r}")
        else:
            # 进一步验证可解析
            try:
                datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError as ex:
                fail(errors, f"事件 {_short(eid)} timestamp 无法解析: {ts!r} ({ex})")
    else:
        fail(errors, f"事件 {_short(eid)} timestamp 必须为字符串")

    # revision_cycle：非负整数
    rc = e.get("revision_cycle")
    if not isinstance(rc, int) or isinstance(rc, bool) or rc < 0:
        fail(errors, f"事件 {_short(eid)} revision_cycle 必须为非负整数，实际 {rc!r}")

    # actor：dict，包含 role/instance_id/provider/client/model
    actor = e.get("actor")
    if not isinstance(actor, dict):
        fail(errors, f"事件 {_short(eid)} actor 必须为对象")
    else:
        for k in ("role", "instance_id", "provider", "client", "model"):
            v = actor.get(k)
            if not isinstance(v, str) or not v.strip():
                fail(errors, f"事件 {_short(eid)} actor.{k} 必须为非空字符串")
        # actor.model 占位符升级为错误
        if isinstance(actor.get("model"), str) and is_placeholder_model(actor.get("model")):
            fail(
                errors,
                f"事件 {_short(eid)} actor.model 不得为占位符: {actor.get('model')!r}"
                "（应填实际模型标识，如 glm-5.2 / gpt-5.6-luna / kimi-k2.5）",
            )

    # recipient：dict，包含 role
    recipient = e.get("recipient")
    if not isinstance(recipient, dict):
        fail(errors, f"事件 {_short(eid)} recipient 必须为对象")
    else:
        rr = recipient.get("role")
        if not isinstance(rr, str) or not rr.strip():
            fail(errors, f"事件 {_short(eid)} recipient.role 必须为非空字符串")

    # previous_event_id：字符串或 None
    pe = e.get("previous_event_id")
    if not (pe is None or (isinstance(pe, str) and pe.strip())):
        fail(errors, f"事件 {_short(eid)} previous_event_id 必须为字符串或 null")

    # caused_by：字符串或 None
    cb = e.get("caused_by")
    if not (cb is None or (isinstance(cb, str) and cb.strip())):
        fail(errors, f"事件 {_short(eid)} caused_by 必须为字符串或 null")

    # artifacts：list
    arts = e.get("artifacts")
    if not isinstance(arts, list):
        fail(errors, f"事件 {_short(eid)} artifacts 必须为数组")
        return
    for j, a in enumerate(arts):
        if not isinstance(a, dict):
            fail(errors, f"事件 {_short(eid)} artifacts[{j}] 必须为对象")
            continue
        for k in ("path", "sha256", "media_type"):
            v = a.get(k)
            if not isinstance(v, str) or not v.strip():
                fail(errors, f"事件 {_short(eid)} artifacts[{j}].{k} 必须为非空字符串")
        # version：整数 >= 1
        ver = a.get("version")
        if not isinstance(ver, int) or isinstance(ver, bool) or ver < 1:
            fail(errors, f"事件 {_short(eid)} artifacts[{j}].version 必须为 >=1 的整数")
        # sha256 hex
        sh = a.get("sha256")
        if isinstance(sh, str) and not SHA256_RE.match(sh):
            fail(errors, f"事件 {_short(eid)} artifacts[{j}].sha256 不是合法的 SHA-256 hex: {sh!r}")
        # path traversal 检查（仅对相对路径）
        p = a.get("path")
        if isinstance(p, str) and not os.path.isabs(p):
            # 规范化后必须仍位于"任务目录"概念下；禁止通过 .. 逃逸
            norm = os.path.normpath(p)
            if norm.startswith("../") or norm == ".." or "/.." in norm:
                fail(errors, f"事件 {_short(eid)} artifacts[{j}].path 含非法 `..` 穿越: {p!r}")


def validate_references(
    events: List[Dict[str, Any]],
    errors: List[str],
) -> None:
    """唯一 event_id、previous_event_id 链式、caused_by 引用、分叉检测。"""
    ids: List[str] = []
    id_set: Dict[str, int] = {}
    for i, e in enumerate(events):
        eid = e.get("event_id")
        if not isinstance(eid, str):
            continue
        if eid in id_set:
            fail(
                errors,
                f"event_id 重复：{eid}（第 {id_set[eid] + 1} 与第 {i + 1} 个事件）",
            )
        else:
            id_set[eid] = i
        ids.append(eid)

    # previous_event_id 链式 + 分叉
    prev: Optional[str] = None
    seen_prev: Dict[str, str] = {}
    for i, e in enumerate(events):
        eid = e.get("event_id", f"#{i}")
        pe = e.get("previous_event_id")
        if i == 0:
            if pe is not None:
                fail(errors, f"首个事件 {_short(eid)} 的 previous_event_id 必须为 null，实际 {_short(pe)}")
        else:
            if not isinstance(pe, str):
                fail(errors, f"事件 {_short(eid)} previous_event_id 必须为字符串（首事件之后）")
            elif pe != prev:
                fail(
                    errors,
                    f"事件链断裂：{_short(eid)} 的 previous_event_id={_short(pe)}"
                    f"，期望 {_short(prev)}",
                )
            if pe in seen_prev:
                fail(
                    errors,
                    f"检测到分叉：{_short(eid)} 与 {_short(seen_prev[pe])} 引用同一 previous_event_id={_short(pe)}",
                )
            else:
                seen_prev[pe] = eid
        prev = eid

    # caused_by 必须引用当前事件之前已经存在的事件（或为 null）
    prior_ids: set = set()
    for i, e in enumerate(events):
        eid = e.get("event_id", f"#{i}")
        cb = e.get("caused_by")
        if cb is not None and isinstance(cb, str) and cb not in prior_ids:
            fail(
                errors,
                f"事件 {_short(eid)} caused_by 必须引用更早事件，实际为不存在或未来事件: {_short(cb)}",
            )
        if isinstance(eid, str):
            prior_ids.add(eid)


def validate_state_machine(
    events: List[Dict[str, Any]],
    errors: List[str],
    warnings: List[str],
) -> Optional[str]:
    """type<->status 一致性 + 状态机流转 + task_id 一致性。"""
    if not events:
        return None

    # task_id 一致性
    base_tid = events[0].get("task_id")
    for i, e in enumerate(events[1:], 1):
        if e.get("task_id") != base_tid:
            fail(
                errors,
                f"task_id 不一致：事件 #{i} task_id={e.get('task_id')!r}，预期 {base_tid!r}",
            )

    status: Optional[str] = None
    for i, e in enumerate(events):
        eid = e.get("event_id", f"#{i}")
        etype = e.get("type")
        new_status = e.get("status")

        # type <-> status 一致性
        if isinstance(etype, str) and etype in EVENT_EXPECTED_STATUS:
            expected = EVENT_EXPECTED_STATUS[etype]
            if expected is not None:
                if new_status != expected:
                    fail(
                        errors,
                        f"事件 {_short(eid)} 类型 {etype} 期望 status={expected}，实际 {new_status!r}",
                    )

        # 首事件必须是 TASK_CREATED / CREATED
        if i == 0:
            if etype != "TASK_CREATED":
                fail(errors, f"首个事件必须为 TASK_CREATED，实际 {etype!r}")
            if new_status != "CREATED":
                fail(errors, f"首个事件 status 必须为 CREATED，实际 {new_status!r}")

        if isinstance(etype, str) and etype not in EVENT_EXPECTED_STATUS:
            fail(errors, f"事件 {_short(eid)} 类型 {etype} 未在 EVENT_EXPECTED_STATUS 中定义")
            continue

        # status-keeping 事件：字段 status 必须与进入事件前的状态完全一致
        if isinstance(etype, str) and EVENT_EXPECTED_STATUS.get(etype) is None:
            if status is None or new_status != status:
                fail(
                    errors,
                    f"状态保持事件 {_short(eid)} {etype} 不得改变 status："
                    f"当前 {status!r}，事件填写 {new_status!r}",
                )
            continue

        # 状态流转
        if status is None:
            pass  # 首事件已校验
        elif status in TERMINAL:
            # 终态之后只允许 TASK_REOPENED（或 status-keeping，已在上面 continue）
            if etype != "TASK_REOPENED":
                fail(
                    errors,
                    f"终态 {status} 之后仍出现状态变更事件 {etype} -> {new_status}（事件 {_short(eid)}）",
                )
        elif new_status != status and new_status not in TRANSITIONS.get(status, set()):
            fail(
                errors,
                f"非法状态流转：{status} -> {new_status}（事件 {_short(eid)} {etype}）",
            )

        if isinstance(new_status, str):
            status = new_status

    return status


def _event_payload(e: Dict[str, Any]) -> Dict[str, Any]:
    payload = e.get("payload")
    return payload if isinstance(payload, dict) else {}


def validate_control_policy(
    events: List[Dict[str, Any]],
    control: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """按 control.md 强制角色授权、质量门、返工上限和并行子任务门槛。"""
    if not control:
        return
    workflow = control.get("workflow", {})
    quality = control.get("quality_gate", {})
    planner = workflow.get("planning_agent")
    reviewer = workflow.get("reviewer")
    executors = {
        workflow.get("default_executor"),
        workflow.get("multimodal_executor"),
    }
    executors.discard(None)
    registered = set(control.get("agent_roles", [])) | {"human", "coordinator"}

    planner_types = {"PLANNING_STARTED", "PLAN_READY", "TASK_DECOMPOSED"}
    reviewer_types = {"REVIEW_STARTED", "REVIEW_APPROVED", "REVISION_REQUIRED"}
    executor_types = {
        "TASK_CLAIMED", "TASK_RECLAIMED", "EXECUTION_STARTED",
        "REVISION_STARTED", "HEARTBEAT", "WORK_READY",
    }

    # 汇总方案声明的子任务。接受旧字段 subtask，新增事件统一使用 subtask_id。
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
    max_cycles_raw = quality.get("max_revision_cycles", 3)
    target_score_raw = quality.get("target_score", 90)
    max_score_raw = quality.get("max_score", 100)
    max_cycles = max_cycles_raw if isinstance(max_cycles_raw, int) and not isinstance(max_cycles_raw, bool) else 3
    target_score = target_score_raw if isinstance(target_score_raw, int) and not isinstance(target_score_raw, bool) else 90
    max_score = max_score_raw if isinstance(max_score_raw, int) and not isinstance(max_score_raw, bool) else 100
    require_subtask_ids = workflow.get("require_subtask_ids", False) is True

    for index, e in enumerate(events):
        eid = e.get("event_id", f"#{index}")
        etype = e.get("type")
        actor = e.get("actor") if isinstance(e.get("actor"), dict) else {}
        role = actor.get("role")
        recipient = e.get("recipient") if isinstance(e.get("recipient"), dict) else {}
        recipient_role = recipient.get("role")
        payload = _event_payload(e)
        cycle = e.get("revision_cycle")

        if isinstance(role, str) and registered and role not in registered:
            fail(errors, f"事件 {_short(eid)} actor.role={role!r} 未在 control.md 注册")
        if isinstance(recipient_role, str) and registered and recipient_role not in registered:
            fail(errors, f"事件 {_short(eid)} recipient.role={recipient_role!r} 未在 control.md 注册")

        if etype == "TASK_CREATED" and role not in {planner, "human", "coordinator"}:
            fail(errors, f"事件 {_short(eid)} TASK_CREATED 只能由 planning_agent、人类或协调器发布")
        if etype in planner_types and role != planner:
            fail(errors, f"事件 {_short(eid)} {etype} 只能由 planning_agent={planner} 发布，实际 {role}")
        if etype in reviewer_types and role != reviewer:
            fail(errors, f"事件 {_short(eid)} {etype} 只能由 reviewer={reviewer} 发布，实际 {role}")
        if etype == "TASK_REOPENED" and role not in {"human", "coordinator"}:
            fail(errors, f"事件 {_short(eid)} TASK_REOPENED 只能由 human/coordinator 发布")
        if etype == "ROLE_OVERRIDE":
            if role not in {"human", "coordinator"}:
                fail(errors, f"事件 {_short(eid)} ROLE_OVERRIDE 只能由 human/coordinator 发布")
            granted = payload.get("role") or payload.get("allow_role")
            if isinstance(granted, str):
                override_roles.add(granted)
        if etype in executor_types and role not in executors | override_roles:
            fail(
                errors,
                f"事件 {_short(eid)} {etype} 只能由执行角色 {sorted(executors | override_roles)} 发布，实际 {role}",
            )

        if isinstance(cycle, int) and not isinstance(cycle, bool):
            if isinstance(max_cycles, int) and cycle > max_cycles:
                fail(errors, f"事件 {_short(eid)} revision_cycle={cycle} 超过上限 {max_cycles}")
            if cycle < previous_cycle or cycle > previous_cycle + 1:
                fail(errors, f"事件 {_short(eid)} revision_cycle 非法跳变：{previous_cycle} -> {cycle}")
            previous_cycle = cycle

        subtask_id = payload.get("subtask_id")
        if subtask_id is None and isinstance(payload.get("subtask"), str):
            subtask_id = payload.get("subtask")
            warn(warnings, f"legacy 子任务字段：事件 {_short(eid)} 使用 payload.subtask；新事件改用 subtask_id")
        if isinstance(subtask_id, str):
            if subtasks and subtask_id not in subtasks:
                fail(errors, f"事件 {_short(eid)} 引用未声明子任务 {subtask_id!r}")
            owner = subtasks.get(subtask_id)
            if owner and etype in executor_types and role != owner:
                fail(errors, f"事件 {_short(eid)} 子任务 {subtask_id} owner={owner}，实际 actor={role}")
            if etype == "WORK_READY":
                ready_subtasks.add(subtask_id)
        elif len(subtasks) == 1 and etype == "WORK_READY":
            # v1.0 单子任务历史事件可无 ID，唯一映射无歧义。
            ready_subtasks.update(subtasks)
        elif len(subtasks) > 1 and etype in executor_types:
            message = f"并行任务事件 {_short(eid)} {etype} 缺少 payload.subtask_id"
            if require_subtask_ids:
                fail(errors, message)
            else:
                warn(warnings, "legacy " + message)

        if etype == "REVIEW_STARTED" and subtasks:
            missing = sorted(set(subtasks) - ready_subtasks)
            if missing:
                fail(errors, f"事件 {_short(eid)} 在子任务全部 WORK_READY 前开始审查，缺少 {missing}")

        if etype == "REVISION_REQUIRED":
            if isinstance(max_cycles, int) and isinstance(cycle, int) and cycle >= max_cycles:
                fail(errors, f"事件 {_short(eid)} 已达返工上限 {max_cycles}，必须 TASK_BLOCKED")
            next_cycle = payload.get("next_revision_cycle")
            if not isinstance(next_cycle, int) or next_cycle != cycle + 1:
                fail(errors, f"事件 {_short(eid)} next_revision_cycle 必须等于 {cycle + 1}")

        if etype in {"REVIEW_APPROVED", "REVISION_REQUIRED"} and quality.get("enabled", True):
            score = payload.get("score")
            blocking = payload.get("blocking_issues")
            tests_passed = payload.get("required_tests_passed")
            evidence_present = payload.get("required_evidence_present")
            if not isinstance(score, int) or isinstance(score, bool) or score < 0 or score > max_score:
                fail(errors, f"事件 {_short(eid)} payload.score 必须是 0..{max_score} 整数")
            payload_target = payload.get("target_score")
            if payload_target is not None and payload_target != target_score:
                fail(errors, f"事件 {_short(eid)} target_score={payload_target} 与 control.md={target_score} 不一致")
            if not isinstance(blocking, int) or isinstance(blocking, bool) or blocking < 0:
                fail(errors, f"事件 {_short(eid)} blocking_issues 必须为非负整数")
            if not isinstance(tests_passed, bool) or not isinstance(evidence_present, bool):
                fail(errors, f"事件 {_short(eid)} 测试与证据标志必须为布尔值")

            if etype == "REVIEW_APPROVED":
                if isinstance(score, int) and score < target_score:
                    fail(errors, f"事件 {_short(eid)} 审批分数 {score} 低于门槛 {target_score}")
                if quality.get("blocking_issues_must_be_zero", True) and blocking != 0:
                    fail(errors, f"事件 {_short(eid)} 存在 blocking issue，不能 APPROVED")
                if quality.get("require_tests_when_applicable", True) and tests_passed is not True:
                    fail(errors, f"事件 {_short(eid)} required_tests_passed 必须为 true")
                if quality.get("require_evidence", True) and evidence_present is not True:
                    fail(errors, f"事件 {_short(eid)} required_evidence_present 必须为 true")
                review_artifacts = [
                    a for a in e.get("artifacts", []) if isinstance(a, dict)
                    and "artifacts/reviews/" in str(a.get("path", "")).replace("\\", "/")
                ]
                if not review_artifacts:
                    fail(errors, f"事件 {_short(eid)} REVIEW_APPROVED 必须引用版本化 review 产物")


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


def _permission_roots(
    control: Dict[str, Any], collaboration_root: str,
) -> Tuple[List[str], List[str]]:
    permissions = control.get("permissions", {}) if control else {}
    allowed_raw = permissions.get("allowed_paths", ["./"])
    forbidden_raw = permissions.get("forbidden_paths", [])
    allowed_values = allowed_raw if isinstance(allowed_raw, list) else [allowed_raw]
    forbidden_values = forbidden_raw if isinstance(forbidden_raw, list) else [forbidden_raw]

    def resolve(values: List[Any]) -> List[str]:
        roots: List[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            roots.append(os.path.realpath(
                value if os.path.isabs(value) else os.path.join(collaboration_root, value)
            ))
        return roots

    return resolve(allowed_values), resolve(forbidden_values)


def _check_allowed_path(
    full: str, control: Dict[str, Any], collaboration_root: str,
    errors: List[str], eid: str,
) -> bool:
    real = os.path.realpath(full)
    allowed, forbidden = _permission_roots(control, collaboration_root)
    if not allowed or not any(_is_within(real, root) for root in allowed):
        fail(errors, f"事件 {_short(eid)} 产物路径超出 permissions.allowed_paths: {full!r}")
        return False
    if any(_is_within(real, root) for root in forbidden):
        fail(errors, f"事件 {_short(eid)} 产物路径命中 permissions.forbidden_paths: {full!r}")
        return False
    return True


def resolve_artifact_path(
    path: str, task_dir: str, collaboration_root: str, control: Dict[str, Any],
    errors: List[str], warnings: List[str], eid: str,
) -> Optional[str]:
    """解析产物路径，含 legacy fallback。

    - 绝对路径：直接读取（必须存在）。
    - 任务目录内相对路径：task_dir/path。
    - legacy fallback：当 task_dir/path 不存在、且 path 为不含 `..` 的相对路径、
      且看起来是相对项目根的旧风格路径时，尝试用进程 cwd 解析并打印 legacy 告警。
      绝不修改任何历史文件。
    """
    if not isinstance(path, str) or not path.strip():
        fail(errors, f"事件 {_short(eid)} 含空产物 path")
        return None

    if os.path.isabs(path):
        if not os.path.isfile(path):
            return None
        return path if _check_allowed_path(path, control, collaboration_root, errors, eid) else None

    # 相对路径：先按当前协议解析（task_dir 下）
    primary = os.path.normpath(os.path.join(task_dir, path))
    if os.path.isfile(primary):
        # 相对产物必须真实位于任务目录，防止任务目录内 symlink 指向外部。
        if not _is_within(primary, task_dir):
            fail(errors, f"事件 {_short(eid)} 相对产物通过符号链接逃逸任务目录: {path!r}")
            return None
        return primary if _check_allowed_path(primary, control, collaboration_root, errors, eid) else None

    # legacy fallback：尝试相对 cwd（项目根）
    # 仅当路径不含 .. 且尝试解析为项目根相对路径时
    norm = os.path.normpath(path)
    if norm.startswith("..") or norm == "..":
        # 已在字段校验中失败；这里直接返回 None
        return None

    cwd = os.getcwd()
    legacy = os.path.normpath(os.path.join(collaboration_root, path))
    # 安全：legacy 必须严格位于协作根目录之下
    if not _is_within(legacy, collaboration_root):
        fail(errors, f"事件 {_short(eid)} legacy 路径解析逃逸 repo root: {path!r}")
        return None
    if os.path.isfile(legacy):
        if not _check_allowed_path(legacy, control, collaboration_root, errors, eid):
            return None
        warn(
            warnings,
            f"legacy fallback：事件 {_short(eid)} 产物 {path!r} 不在任务目录 {task_dir} 下，"
            f"已使用仓库根相对路径 {legacy}（只读，未修改历史文件）",
        )
        return legacy

    return None


def validate_artifacts(
    events: List[Dict[str, Any]],
    task_dir: str,
    collaboration_root: str,
    control: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    for e in events:
        eid = e.get("event_id", "?")
        arts = e.get("artifacts")
        if not isinstance(arts, list):
            continue
        for a in arts:
            if not isinstance(a, dict):
                continue
            p = a.get("path", "")
            full = resolve_artifact_path(
                p, task_dir, collaboration_root, control, errors, warnings, eid
            )
            if full is None:
                fail(errors, f"产物缺失：{p}（事件 {_short(eid)}）")
                continue
            try:
                with open(full, "rb") as fh:
                    data = fh.read()
            except OSError as ex:
                fail(errors, f"产物读取失败：{p}（事件 {_short(eid)}）：{ex}")
                continue
            actual = hashlib.sha256(data).hexdigest()
            expected = a.get("sha256")
            if actual != expected:
                fail(
                    errors,
                    f"产物哈希不一致：{p}（事件 {_short(eid)}）expected={_short(expected)} actual={actual[:12]}…",
                )


def parse_events(text: str, errors: List[str]) -> List[Dict[str, Any]]:
    begins = text.count("<!-- MMAC-EVENT-BEGIN -->")
    ends = text.count("<!-- MMAC-EVENT-END -->")
    if begins != ends:
        fail(errors, f"事件标记不配对：BEGIN={begins} END={ends}")

    blocks = EVENT_RE.findall(text)
    if begins != len(blocks):
        fail(errors, f"有效事件块数量({len(blocks)})与 BEGIN 标记数({begins})不一致，存在残缺事件")

    events: List[Dict[str, Any]] = []
    for i, raw in enumerate(blocks, 1):
        try:
            e = json.loads(raw)
        except json.JSONDecodeError as ex:
            fail(errors, f"第 {i} 个事件 JSON 非法: {ex}")
            continue
        events.append(e)
    return events


def main() -> int:
    if len(sys.argv) not in (2, 4) or (len(sys.argv) == 4 and sys.argv[2] != "--candidate"):
        print(__doc__)
        return 1
    task_dir = sys.argv[1].rstrip("/")
    candidate_path = sys.argv[3] if len(sys.argv) == 4 else None
    coord = os.path.join(task_dir, "coordination.md")
    errors: List[str] = []
    warnings: List[str] = []

    if not os.path.isfile(coord):
        print(f"✗ 找不到 coordination.md: {coord}")
        return 1

    with open(coord, encoding="utf-8") as fh:
        text = fh.read()

    events = parse_events(text, errors)
    if candidate_path:
        try:
            with open(candidate_path, encoding="utf-8") as fh:
                candidate = json.load(fh)
            if not isinstance(candidate, dict):
                fail(errors, "候选事件 JSON 顶层必须为对象")
            else:
                events.append(candidate)
        except (OSError, json.JSONDecodeError) as ex:
            fail(errors, f"候选事件读取失败: {ex}")

    control = parse_control(task_dir, errors)
    collaboration_root = find_collaboration_root(task_dir)

    # 字段层校验（即便解析失败也尽量继续）
    for i, e in enumerate(events, 1):
        validate_event_fields(i, e, errors)

    # 引用与链式
    validate_references(events, errors)

    # 状态机
    final_status = validate_state_machine(events, errors, warnings)

    # control.md 驱动的权限与质量策略
    validate_control_policy(events, control, errors, warnings)

    # 产物
    validate_artifacts(events, task_dir, collaboration_root, control, errors, warnings)

    for w in warnings:
        # 已在产生处打印；这里不重复
        pass

    label = "（含候选事件）" if candidate_path else ""
    print(f"\n校验 {len(events)} 个事件{label}：{'全部通过 ✓' if not errors else f'{len(errors)} 个错误 ✗'}"
          f"（{len(warnings)} 个告警）")
    if events:
        last = events[-1]
        print(f"当前状态：{final_status} | 最新事件：{last.get('type')} by {last.get('actor', {}).get('instance_id', '?')}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
